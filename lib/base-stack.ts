import { Duration, Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Runtime, Architecture, Code, Function } from 'aws-cdk-lib/aws-lambda';
import { PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';

export interface NovaActQAStudioBaseStackCreateProps extends StackProps {
  baseName: string
}

export interface createLambdaProps {
  // name: string,
  path: string,
  memorySize?: number,
  environment?: { [key: string]: string; },
  timeout?: Duration,
}

export class NovaActQAStudioBaseStack extends Stack {
  protected baseName: string = ""

  protected cdkName(name: string): string {
    return `${this.baseName}-${name.toLocaleLowerCase().replace("_", "-")}`
  }

  protected snakeToPascal(str: string): string {
  return str
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join('');
}


  protected log(resource: string, value: string) {
    new CfnOutput(this, resource, {
      value
    });
  }

  protected createLambda(props: createLambdaProps): Function {
    const name = this.cdkName(this.snakeToPascal(props.path))
    const fn = new Function(this, `lambda_${name}`, {
      functionName: name,
      runtime: Runtime.PROVIDED_AL2023,
      architecture: Architecture.ARM_64,
      memorySize: props.memorySize || 128,
      code: Code.fromAsset(`lambda/cmd/${props.path}`),
      timeout: props.timeout || Duration.seconds(5),
      handler: 'import.handler',
      environment: props.environment,
      logRetention: 5
    });

    fn.addToRolePolicy(new PolicyStatement({
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      resources: ['*'],
      effect: Effect.ALLOW
    }))

    return fn
  }

  constructor(scope: Construct, id: string, props: NovaActQAStudioBaseStackCreateProps) {
    super(scope, id, props);

    this.baseName = props.baseName
  }
}