import { App, Stack } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { AttributeType, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Code, Function, Runtime } from 'aws-cdk-lib/aws-lambda';
import { configureAuthorizerClientBinding, OAUTH_CLIENTS_PK } from '../authorizer-client-binding';

function synth(): Template {
  const stack = new Stack(new App(), 'TestStack');
  const table = new Table(stack, 'table', {
    partitionKey: { name: 'pk', type: AttributeType.STRING },
    sortKey: { name: 'sk', type: AttributeType.STRING },
  });
  const fn = new Function(stack, 'authorizer', {
    runtime: Runtime.PYTHON_3_13,
    handler: 'authorizer.handler',
    code: Code.fromInline('def handler(e, c): pass'),
    environment: { USER_POOL_ID: 'pool' },
  });
  configureAuthorizerClientBinding(fn, table, 'worker-client-id');
  return Template.fromStack(stack);
}

describe('configureAuthorizerClientBinding', () => {
  const template = synth();

  it('sets TABLE_NAME and WORKER_CLIENT_ID on the authorizer', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      Environment: {
        Variables: {
          USER_POOL_ID: 'pool',
          TABLE_NAME: { Ref: Match.stringLikeRegexp('^table') },
          WORKER_CLIENT_ID: 'worker-client-id',
        },
      },
    });
  });

  it('grants only dynamodb:GetItem on the OAUTH_CLIENTS partition', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: [
          {
            Action: 'dynamodb:GetItem',
            Effect: 'Allow',
            Resource: { 'Fn::GetAtt': [Match.stringLikeRegexp('^table'), 'Arn'] },
            Condition: {
              'ForAllValues:StringEquals': { 'dynamodb:LeadingKeys': [OAUTH_CLIENTS_PK] },
            },
          },
        ],
      },
    });
  });

  it('adds no other DynamoDB permissions', () => {
    const policies = template.findResources('AWS::IAM::Policy');
    const actions = Object.values(policies).flatMap((p: any) =>
      p.Properties.PolicyDocument.Statement.flatMap((s: any) => [].concat(s.Action)));
    expect(actions.filter((a: string) => a.startsWith('dynamodb:'))).toEqual(['dynamodb:GetItem']);
  });
});
