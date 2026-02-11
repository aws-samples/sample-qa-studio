import { Construct } from 'constructs';
import { CfnOutput } from 'aws-cdk-lib';
import { UserPool, UserPoolClient, OAuthScope, CfnUserPoolUser, UserPoolResourceServer, UserPoolDomain, ResourceServerScope, CfnUserPoolGroup, CfnUserPoolUserToGroupAttachment, CfnUserPool } from 'aws-cdk-lib/aws-cognito';
import { Function } from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioAuthStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  adminEmail: string
}

/**
 * Key Components:
 * - UserPool: Manages user authentication and storage
 * - UserPoolClient: Client application that interacts with the UserPool
 *
 * Readable Attributes:
 * - userPool.userPoolId: Unique identifier for the Cognito User Pool
 * - userPoolClient.userPoolClientId: Client ID for the User Pool Client
 * 
 * Required Props:
 * - baseName: Base name for resource naming
 */
export class NovaActQAStudioAuthStack extends NovaActQAStudioBaseStack {
  public readonly userPool: UserPool
  public readonly userPoolClient: UserPoolClient
  public readonly resourceServer: UserPoolResourceServer
  public readonly userPoolDomain: UserPoolDomain
  public readonly preTokenGenerationLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioAuthStackCreateProps) {
    super(scope, id, props);

    // Create pre-token generation Lambda for scope injection
    this.preTokenGenerationLambda = this.createPythonLambda({
      path: 'pre_token_generation',
      codeDirectory: 'lambdas/auth',
      environment: {}
    });

    this.userPool = new UserPool(this, 'user_pool', {
      userPoolName: this.cdkName('user-pool'),
      signInAliases: { email: true },
      selfSignUpEnabled: false,
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      }
    });

    // Grant Cognito permission to invoke the Lambda BEFORE configuring the trigger
    this.preTokenGenerationLambda.addPermission('CognitoInvoke', {
      principal: new iam.ServicePrincipal('cognito-idp.amazonaws.com'),
      sourceArn: this.userPool.userPoolArn
    });

    // Configure pre-token generation Lambda trigger (V2) using L1 construct
    // V2 is required for claimsOverrideDetails support
    const cfnUserPool = this.userPool.node.defaultChild as CfnUserPool;
    cfnUserPool.addPropertyOverride('LambdaConfig.PreTokenGenerationConfig', {
      LambdaVersion: 'V2_0',
      LambdaArn: this.preTokenGenerationLambda.functionArn
    });

    // Define OAuth scopes - single source of truth
    const apiScopes = [
      {
        scopeName: 'usecases.read',
        scopeDescription: 'Read use cases'
      },
      {
        scopeName: 'usecases.write',
        scopeDescription: 'Create, update, delete use cases'
      },
      {
        scopeName: 'templates.read',
        scopeDescription: 'Read templates'
      },
      {
        scopeName: 'templates.write',
        scopeDescription: 'Create, update, delete templates'
      },
      {
        scopeName: 'executions.read',
        scopeDescription: 'View execution results'
      },
      {
        scopeName: 'executions.write',
        scopeDescription: 'Modify execution records'
      },
      {
        scopeName: 'usecases.execute',
        scopeDescription: 'Trigger use case executions'
      },
      {
        scopeName: 'oauth-clients.read',
        scopeDescription: 'Read OAuth clients'
      },
      {
        scopeName: 'oauth-clients.write',
        scopeDescription: 'Create, update, delete OAuth clients'
      },
      {
        scopeName: 'admin',
        scopeDescription: 'Full administrative access'
      }
    ];

    // Create resource server for M2M authentication and scope-based authorization
    this.resourceServer = new UserPoolResourceServer(this, 'resource_server', {
      userPool: this.userPool,
      identifier: 'api',
      userPoolResourceServerName: this.cdkName('api-resource-server'),
      scopes: apiScopes
    });

    // Create Cognito domain for OAuth endpoints (required for M2M authentication)
    this.userPoolDomain = new UserPoolDomain(this, 'user_pool_domain', {
      userPool: this.userPool,
      cognitoDomain: {
        domainPrefix: this.cdkName('auth').toLowerCase().replace(/_/g, '-')
      }
    });

    this.userPoolClient = new UserPoolClient(this, 'user_pool_client', {
      userPoolClientName: this.cdkName('client'),
      userPool: this.userPool,
      generateSecret: false,
      authFlows: {
        userSrp: true,
        userPassword: true
      },
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true
        },
        scopes: [
          OAuthScope.OPENID,
          OAuthScope.EMAIL,
          OAuthScope.PROFILE,
          // Map API scopes to OAuth scopes
          ...apiScopes.map(scope => 
            OAuthScope.resourceServer(this.resourceServer, new ResourceServerScope(scope))
          )
        ]
      }
    });

    // Create admin user
    const adminUser = new CfnUserPoolUser(this, 'admin_user', {
      userPoolId: this.userPool.userPoolId,
      username: props.adminEmail,
      userAttributes: [
        {
          name: 'email',
          value: props.adminEmail,
        },
        {
          name: 'email_verified',
          value: 'true',
        }
      ],
      desiredDeliveryMediums: ['EMAIL'],
      forceAliasCreation: false,
      // messageAction: 'SUPPRESS' to skip welcome email, or omit to send one
    });

    // Create Cognito user groups for scope-based authorization
    const usersGroup = new CfnUserPoolGroup(this, 'users_group', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'users',
      description: 'Default user permissions'
    });

    const adminsGroup = new CfnUserPoolGroup(this, 'admins_group', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'admins',
      description: 'Administrative permissions'
    });

    // Assign admin user to admins group
    const adminUserGroupAttachment = new CfnUserPoolUserToGroupAttachment(this, 'admin_user_group', {
      userPoolId: this.userPool.userPoolId,
      username: props.adminEmail,
      groupName: 'admins'
    });

    // Ensure groups are created before user is added to them
    adminUserGroupAttachment.addDependency(adminsGroup);
    adminUserGroupAttachment.addDependency(adminUser);

    this.log('userPoolId', this.userPool.userPoolId)
    this.log('userPoolClientId', this.userPoolClient.userPoolClientId)
    this.log('cognitoDomain', this.userPoolDomain.domainName)
    this.log('adminEmail', props.adminEmail)

    // Export values for post-deployment config generation
    new CfnOutput(this, 'UserPoolIdOutput', {
      value: this.userPool.userPoolId,
      description: 'Cognito User Pool ID',
      exportName: `${props.baseName}-user-pool-id`
    });

    new CfnOutput(this, 'UserPoolClientIdOutput', {
      value: this.userPoolClient.userPoolClientId,
      description: 'Cognito User Pool Client ID',
      exportName: `${props.baseName}-user-pool-client-id`
    });

    new CfnOutput(this, 'CognitoDomainOutput', {
      value: `https://${this.userPoolDomain.domainName}.auth.${this.region}.amazoncognito.com`,
      description: 'Cognito Domain URL for OAuth (free, managed by AWS)',
      exportName: `${props.baseName}-cognito-domain`
    });
  }
}