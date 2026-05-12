import { Construct } from 'constructs';
import { CfnOutput, RemovalPolicy, SecretValue } from 'aws-cdk-lib';
import { UserPool, UserPoolClient, OAuthScope, CfnUserPoolUser, UserPoolResourceServer, UserPoolDomain, ResourceServerScope, CfnUserPoolGroup, CfnUserPoolUserToGroupAttachment, CfnUserPool } from 'aws-cdk-lib/aws-cognito';
import { Function } from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { AwsCustomResource, AwsCustomResourcePolicy, PhysicalResourceId } from 'aws-cdk-lib/custom-resources';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioAuthStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  adminEmail: string
  /** OAuth callback URLs for CLI and IDE extensions */
  callbackUrls?: string[]
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
  // Worker M2M client for the CLI-unified-runner refactor (R-AUTH).
  // Uses client-credentials flow; credentials stored in Secrets Manager.
  public readonly workerM2MClient: UserPoolClient
  public readonly workerCredentialsSecret: Secret

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
        scopeName: 'suite.read',
        scopeDescription: 'Read test suites and suite executions'
      },
      {
        scopeName: 'suite.write',
        scopeDescription: 'Create, update, delete, and execute test suites'
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
        callbackUrls: props.callbackUrls && props.callbackUrls.length > 0
          ? props.callbackUrls
          : undefined,
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

    // ─── Worker M2M OAuth Client (CLI-unified-runner, R-AUTH) ──────────
    // The cloud worker uses client-credentials flow to authenticate
    // against the same Cognito pool as user-facing clients.  The client
    // secret is stored in Secrets Manager and injected into the ECS task
    // at runtime via the ECS `secrets:` mechanism (see worker-stack.ts).
    // Scopes: api/executions.read + api/executions.write — the worker
    // only ever writes execution/step state and reads execution details.
    this.workerM2MClient = new UserPoolClient(this, 'worker_m2m_client', {
      userPoolClientName: this.cdkName('worker-m2m'),
      userPool: this.userPool,
      generateSecret: true,
      authFlows: {
        // No user-facing auth flows — this client uses only OAuth
        // client-credentials grant (M2M).
      },
      oAuth: {
        flows: {
          clientCredentials: true,
        },
        // The CLI's client-credentials provider requests all scopes in
        // M2M_SCOPES (qa_studio_cli/auth/client_credentials.py).
        // Cognito returns invalid_grant when the request includes scopes
        // the app client isn't allowed, so we must grant the full set
        // the worker needs across both single-usecase and suite modes.
        scopes: [
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'executions.read',
              scopeDescription: 'View execution results',
            }),
          ),
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'executions.write',
              scopeDescription: 'Modify execution records',
            }),
          ),
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'usecases.read',
              scopeDescription: 'Read use cases',
            }),
          ),
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'usecases.execute',
              scopeDescription: 'Trigger use case executions',
            }),
          ),
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'suite.read',
              scopeDescription: 'Read test suites and suite executions',
            }),
          ),
          OAuthScope.resourceServer(
            this.resourceServer,
            new ResourceServerScope({
              scopeName: 'suite.write',
              scopeDescription: 'Create, update, delete, and execute test suites',
            }),
          ),
        ],
      },
    });
    // UserPoolClient must exist before we can read its secret.
    this.workerM2MClient.node.addDependency(this.resourceServer);

    // Cognito does not expose the generated client secret as a CFN
    // attribute.  We resolve it via an AwsCustomResource that calls
    // DescribeUserPoolClient at deploy time.  The `ClientSecret` is then
    // written into a Secrets Manager secret alongside the `ClientId`.
    const describeClient = new AwsCustomResource(
      this,
      'worker_m2m_describe_client',
      {
        onCreate: {
          service: 'CognitoIdentityServiceProvider',
          action: 'describeUserPoolClient',
          parameters: {
            UserPoolId: this.userPool.userPoolId,
            ClientId: this.workerM2MClient.userPoolClientId,
          },
          physicalResourceId: PhysicalResourceId.of(
            `worker-m2m-describe-${this.workerM2MClient.userPoolClientId}`,
          ),
        },
        onUpdate: {
          service: 'CognitoIdentityServiceProvider',
          action: 'describeUserPoolClient',
          parameters: {
            UserPoolId: this.userPool.userPoolId,
            ClientId: this.workerM2MClient.userPoolClientId,
          },
          physicalResourceId: PhysicalResourceId.of(
            `worker-m2m-describe-${this.workerM2MClient.userPoolClientId}`,
          ),
        },
        policy: AwsCustomResourcePolicy.fromStatements([
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ['cognito-idp:DescribeUserPoolClient'],
            resources: [this.userPool.userPoolArn],
          }),
        ]),
        // Avoid logging the secret response in custom-resource CloudWatch.
        installLatestAwsSdk: false,
      },
    );
    describeClient.node.addDependency(this.workerM2MClient);

    // Secrets Manager secret containing both client_id and client_secret.
    // Stored as JSON so the ECS task definition can select individual
    // fields via `Secret.fromSecretsManager(secret, 'client_id')`.
    this.workerCredentialsSecret = new Secret(this, 'worker_m2m_credentials', {
      secretName: `${this.baseName}-worker-m2m-credentials`,
      description:
        'OAuth client credentials for the QA Studio worker (CLI-unified-runner)',
      // We inject a placeholder here; the AwsCustomResource below
      // rewrites the value with the real client_secret post-deploy.
      secretObjectValue: {
        client_id: SecretValue.unsafePlainText(
          this.workerM2MClient.userPoolClientId,
        ),
        client_secret: SecretValue.unsafePlainText('PLACEHOLDER'),
      },
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Populate the real client_secret via a second custom resource that
    // calls secretsmanager:PutSecretValue.  Kept separate from the
    // describe above so the two IAM policies stay scoped narrowly.
    const writeSecret = new AwsCustomResource(
      this,
      'worker_m2m_write_secret',
      {
        onCreate: {
          service: 'SecretsManager',
          action: 'putSecretValue',
          parameters: {
            SecretId: this.workerCredentialsSecret.secretArn,
            SecretString: JSON.stringify({
              client_id: this.workerM2MClient.userPoolClientId,
              client_secret: describeClient.getResponseField(
                'UserPoolClient.ClientSecret',
              ),
            }),
          },
          physicalResourceId: PhysicalResourceId.of(
            `worker-m2m-write-${this.workerM2MClient.userPoolClientId}`,
          ),
        },
        onUpdate: {
          service: 'SecretsManager',
          action: 'putSecretValue',
          parameters: {
            SecretId: this.workerCredentialsSecret.secretArn,
            SecretString: JSON.stringify({
              client_id: this.workerM2MClient.userPoolClientId,
              client_secret: describeClient.getResponseField(
                'UserPoolClient.ClientSecret',
              ),
            }),
          },
          physicalResourceId: PhysicalResourceId.of(
            `worker-m2m-write-${this.workerM2MClient.userPoolClientId}`,
          ),
        },
        policy: AwsCustomResourcePolicy.fromStatements([
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ['secretsmanager:PutSecretValue'],
            resources: [this.workerCredentialsSecret.secretArn],
          }),
        ]),
        installLatestAwsSdk: false,
      },
    );
    writeSecret.node.addDependency(describeClient);
    writeSecret.node.addDependency(this.workerCredentialsSecret);

    new CfnOutput(this, 'WorkerM2MClientIdOutput', {
      value: this.workerM2MClient.userPoolClientId,
      description: 'Worker M2M Client ID (secret lives in Secrets Manager)',
      exportName: `${props.baseName}-worker-m2m-client-id`,
    });
    new CfnOutput(this, 'WorkerCredentialsSecretArnOutput', {
      value: this.workerCredentialsSecret.secretArn,
      description: 'ARN of the Secrets Manager secret with worker M2M credentials',
      exportName: `${props.baseName}-worker-m2m-secret-arn`,
    });

    // SSM parameter for the Cognito token endpoint.  The worker
    // entrypoint reads this to configure the CLI's client-credentials
    // auth provider.
    const tokenEndpoint = `https://${this.userPoolDomain.domainName}.auth.${this.region}.amazoncognito.com/oauth2/token`;
    new StringParameter(this, 'WorkerTokenEndpointParameter', {
      parameterName: `/qa-studio/${this.baseName}/cognito-token-endpoint`,
      stringValue: tokenEndpoint,
      description: 'OAuth token endpoint for the worker M2M client',
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