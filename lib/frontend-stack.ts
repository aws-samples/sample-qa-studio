import { Construct } from 'constructs';
import { RemovalPolicy, CfnOutput, Duration } from 'aws-cdk-lib';
import {
  Distribution,
  ViewerProtocolPolicy,
  CachePolicy,
  CacheHeaderBehavior,
  CacheQueryStringBehavior,
  CacheCookieBehavior,
  AllowedMethods,
  OriginRequestPolicy,
  PriceClass,
  OriginRequestHeaderBehavior,
  OriginRequestQueryStringBehavior,
  OriginRequestCookieBehavior
} from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin, RestApiOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { RestApi } from 'aws-cdk-lib/aws-apigateway';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioFrontendStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  api: RestApi
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
export class NovaActQAStudioFrontendStack extends NovaActQAStudioBaseStack {
  public readonly distribution: Distribution
  public readonly frontendBucket: Bucket

  constructor(scope: Construct, id: string, props: NovaActQAStudioFrontendStackCreateProps) {
    super(scope, id, props);

    this.frontendBucket = new Bucket(this, 'FrontendBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // CloudFront Distribution with S3 origin
    this.distribution = new Distribution(this, 'distribution', {
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(this.frontendBucket),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS
      },
      additionalBehaviors: {
        "/prod/*": {
          origin: new RestApiOrigin(props.api, {
            originPath: '/'
          }),
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: AllowedMethods.ALLOW_ALL,
          cachePolicy: CachePolicy.CACHING_DISABLED,
          originRequestPolicy: OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER
        }
      },
      priceClass: PriceClass.PRICE_CLASS_100,
      defaultRootObject: 'index.html',
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html'
        }
      ]
    });

    this.log('CloudFrontDistributionDomain', this.distribution.distributionDomainName)
    this.log('frontendBucket', this.frontendBucket.bucketName)

    // Export the distribution domain name for use in other stacks
    new CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
      description: 'CloudFront Distribution Domain Name',
      exportName: `${props.baseName}-distribution-domain-name`
    });

    // Note: amplifyconfiguration.json will be generated post-deployment
    // by running: make config.write or npx ts-node scripts/write-config.ts
  }
}