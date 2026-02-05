import { Duration, Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Runtime, Architecture, Code, Function } from 'aws-cdk-lib/aws-lambda';
import { Effect, PolicyStatement } from 'aws-cdk-lib/aws-iam';

export interface NovaActQAStudioBaseStackCreateProps extends StackProps {
  baseName: string
}

export interface createPythonLambdaProps {
  path: string,
  handler?: string,
  memorySize?: number,
  environment?: { [key: string]: string; },
  timeout?: Duration,
  runtime?: Runtime,
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

  protected createPythonLambda(props: createPythonLambdaProps): Function {
    const name = this.cdkName(this.snakeToPascal(props.path))
    const fn = new Function(this, `lambda_${name}`, {
      functionName: name,
      runtime: props.runtime || Runtime.PYTHON_3_13,
      architecture: Architecture.ARM_64,
      memorySize: props.memorySize || 128,
      code: Code.fromAsset('endpoints'),
      timeout: props.timeout || Duration.seconds(5),
      handler: props.handler || `${props.path}.handler`,
      environment: props.environment,
      logRetention: 5
    });

    // Explicitly add CloudWatch Logs permissions
    fn.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      resources: [`arn:aws:logs:*:*:*`]
    }));

    return fn
  }

  constructor(scope: Construct, id: string, props: NovaActQAStudioBaseStackCreateProps) {
    super(scope, id, props);

    this.baseName = props.baseName
  }
}