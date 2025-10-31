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
  OriginProtocolPolicy,
  ResponseHeadersPolicy,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin, HttpOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';

interface NovaActQAStudioFrontendStackCreateProps extends NovaActQAStudioBaseStackCreateProps {
  apiId: string,
  apiEndpoint: string
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

    const cachePolicy = new CachePolicy(this, 'CachePolicy', {
      cachePolicyName: this.cdkName('cache-policy'),
      defaultTtl: Duration.seconds(0),
      minTtl: Duration.seconds(0),
      maxTtl: Duration.seconds(1),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
      cookieBehavior: CacheCookieBehavior.all(),
      headerBehavior: CacheHeaderBehavior.allowList('Origin', 'Access-Control-Request-Headers', 'Access-Control-Request-Method', 'Authorization'),
      queryStringBehavior: CacheQueryStringBehavior.all()
    })

    // CloudFront Distribution with S3 origin
    this.distribution = new Distribution(this, 'distribution', {
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(this.frontendBucket),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS
      },
      additionalBehaviors: {
        [`${props.apiEndpoint}/*`]: {
          origin: new HttpOrigin(`${ props.apiId }.execute-api.${ this.region }.amazonaws.com`, {
            protocolPolicy: OriginProtocolPolicy.HTTPS_ONLY
          }),
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: AllowedMethods.ALLOW_ALL,
          cachePolicy: cachePolicy,
          originRequestPolicy: OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
          responseHeadersPolicy: ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS_WITH_PREFLIGHT_AND_SECURITY_HEADERS,
        }
      },
      priceClass: PriceClass.PRICE_CLASS_100,
      defaultRootObject: 'index.html',
      errorResponses: [
        {
          httpStatus: 403,
          responseHttpStatus: 200,
          responsePagePath: '/index.html'
        }
      ]
    });

    this.log('CloudFrontDistributionDomain', `https://${this.distribution.distributionDomainName}`)
      this.log('frontendBucket', this.frontendBucket.bucketName)

    // Export the distribution domain name for use in other stacks
    new CfnOutput(this, 'DistributionDomainName', {
        value: this.distribution.distributionDomainName,
        description: 'CloudFront Distribution Domain Name',
        exportName: `${props.baseName}-distribution-domain-name`
      });
  }
}