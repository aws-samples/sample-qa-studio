import { Construct } from 'constructs';
import { CfnOutput } from 'aws-cdk-lib';
import { RestApi, CognitoUserPoolsAuthorizer, Cors, EndpointType } from 'aws-cdk-lib/aws-apigateway';
import { UserPool } from 'aws-cdk-lib/aws-cognito';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioApiStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  userPool: UserPool
}

export class NovaActQAStudioApiStack extends NovaActQAStudioBaseStack {
  public readonly api: RestApi
  public readonly authorizer: CognitoUserPoolsAuthorizer

  constructor(scope: Construct, id: string, props: NovaActQAStudioApiStackCreateProps) {
    super(scope, id, props);

    this.api = new RestApi(this, 'Api', {
      restApiName: this.cdkName('service'),
      endpointTypes: [EndpointType.REGIONAL],
      defaultCorsPreflightOptions: {
        allowOrigins: Cors.ALL_ORIGINS,
        allowMethods: Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization', 'X-Amz-Date', 'X-Api-Key', 'X-Amz-Security-Token']
      }
    });
    
    // Cognito Authorizer
    this.authorizer = new CognitoUserPoolsAuthorizer(this, 'authorizer', {
      cognitoUserPools: [props.userPool]
    });

    this.log('apigatewayDomain', this.api.url)

    // Export API URL for post-deployment config generation
    new CfnOutput(this, 'ApiUrlOutput', {
      value: this.api.url,
      description: 'API Gateway URL',
      exportName: `${props.baseName}-api-url`
    });
  }
}
