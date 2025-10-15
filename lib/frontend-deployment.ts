import { Construct } from 'constructs';
import { Distribution } from 'aws-cdk-lib/aws-cloudfront';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioFrontendDeploymentStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  frontendBucket: Bucket
  distribution: Distribution
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
export class NovaActQAStudioFrontendDeploymentStack extends NovaActQAStudioBaseStack {

  constructor(scope: Construct, id: string, props: NovaActQAStudioFrontendDeploymentStackCreateProps) {
    super(scope, id, props);

    new BucketDeployment(this, 'frontendDeployment', {
      sources: [Source.asset('./frontend/build')],
      destinationBucket: props.frontendBucket,
      distribution: props.distribution,
      distributionPaths: ['/*']
    });
  }
}