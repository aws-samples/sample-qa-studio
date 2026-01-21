import { Construct } from 'constructs';
import { RestApi, IAuthorizer, IResource } from 'aws-cdk-lib/aws-apigateway';
import { UserPool } from 'aws-cdk-lib/aws-cognito';
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps, HttpMethod } from './base-stack';

interface NovaActQAStudioRoutesAuthStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  apiId: string
  apiRootResourceId: string
  authorizer: IAuthorizer
  userPool: UserPool
}

export class NovaActQAStudioRoutesAuthStack extends NovaActQAStudioBaseStack {
  private userPool: UserPool

  constructor(scope: Construct, id: string, props: NovaActQAStudioRoutesAuthStackCreateProps) {
    super(scope, id, props);
    this.authorizer = props.authorizer
    this.userPool = props.userPool

    const apiInstance = RestApi.fromRestApiAttributes(this, 'api_instance', {
      restApiId: props.apiId,
      rootResourceId: props.apiRootResourceId
    })

    // Lambda Functions for OAuth Client Management
    const listOAuthClientsLambda = this.createPythonLambda({
      path: 'list_oauth_clients',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    })

    const createOAuthClientLambda = this.createPythonLambda({
      path: 'create_oauth_client',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    })

    const getOAuthClientLambda = this.createPythonLambda({
      path: 'get_oauth_client',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    })

    const deleteOAuthClientLambda = this.createPythonLambda({
      path: 'delete_oauth_client',
      environment: {
        USER_POOL_ID: this.userPool.userPoolId
      }
    })

    // Grant Cognito permissions for OAuth client management
    const cognitoActions = [
      'cognito-idp:CreateUserPoolClient',
      'cognito-idp:DescribeUserPoolClient',
      'cognito-idp:ListUserPoolClients',
      'cognito-idp:DeleteUserPoolClient',
      'cognito-idp:UpdateUserPoolClient'
    ];

    [listOAuthClientsLambda, createOAuthClientLambda, getOAuthClientLambda, deleteOAuthClientLambda].forEach(lambda => {
      lambda.addToRolePolicy(new PolicyStatement({
        effect: Effect.ALLOW,
        actions: cognitoActions,
        resources: [this.userPool.userPoolArn]
      }));
    });

    // API Routes
    // /oauth-clients
    const oauthClients = this.addResource(apiInstance.root, 'oauth-clients')
    this.addMethod(oauthClients, HttpMethod.GET, listOAuthClientsLambda)
    this.addMethod(oauthClients, HttpMethod.POST, createOAuthClientLambda)

    // /oauth-clients/{id}
    const oauthClient = this.addResource(oauthClients, '{id}')
    this.addMethod(oauthClient, HttpMethod.GET, getOAuthClientLambda)
    this.addMethod(oauthClient, HttpMethod.DELETE, deleteOAuthClientLambda)

    this.log('authRoutesCreated', 'true')
  }
}
