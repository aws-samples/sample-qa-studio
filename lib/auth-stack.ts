import { Construct } from 'constructs';
import { CfnOutput } from 'aws-cdk-lib';
import { UserPool, UserPoolClient, OAuthScope, CfnUserPoolUser } from 'aws-cdk-lib/aws-cognito';
import { Function } from 'aws-cdk-lib/aws-lambda';
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
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
  public readonly listUsersLambda: Function
  public readonly addUserLambda: Function
  public readonly removeUserLambda: Function

  constructor(scope: Construct, id: string, props: NovaActQAStudioAuthStackCreateProps) {
    super(scope, id, props);

    this.userPool = new UserPool(this, 'user_pool', {
      userPoolName: this.cdkName('user-pool'),
      signInAliases: { email: true },
      selfSignUpEnabled: false,
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
          OAuthScope.PROFILE
        ]
      }
    });

    // Create admin user
    new CfnUserPoolUser(this, 'admin_user', {
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

    // Management Lambdas
    this.listUsersLambda = this.createLambda({
      path: 'list_users',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    });

    this.addUserLambda = this.createLambda({
      path: 'create_user',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    });

    this.removeUserLambda = this.createLambda({
      path: 'delete_user',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    });

    // Grant Cognito permissions for user management
    this.listUsersLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:ListUsers'
      ],
      resources: [this.userPool.userPoolArn]
    }));

    this.addUserLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:*'
      ],
      resources: [this.userPool.userPoolArn]
    }));

    this.removeUserLambda.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'cognito-idp:AdminDeleteUser'
      ],
      resources: [this.userPool.userPoolArn]
    }));

    this.log('userPoolId', this.userPool.userPoolId)
    this.log('userPoolClientId', this.userPoolClient.userPoolClientId)
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
  }
}