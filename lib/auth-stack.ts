import { Construct } from 'constructs';
import { CfnOutput } from 'aws-cdk-lib';
import { UserPool, UserPoolClient, OAuthScope, CfnUserPoolUser } from 'aws-cdk-lib/aws-cognito';
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

  constructor(scope: Construct, id: string, props: NovaActQAStudioAuthStackCreateProps) {
    super(scope, id, props);

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
      },
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