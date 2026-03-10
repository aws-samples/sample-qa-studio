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
  OriginRequestHeaderBehavior,
  OriginRequestQueryStringBehavior,
  OriginRequestCookieBehavior,
  PriceClass,
  OriginProtocolPolicy,
  ResponseHeadersPolicy,
  Function as CloudFrontFunction,
  FunctionCode,
  FunctionEventType,
  SecurityPolicyProtocol,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin, HttpOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { Bucket, BucketEncryption, ObjectOwnership } from 'aws-cdk-lib/aws-s3';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import { NovaActQAStudioBaseStack, NovaActQAStudioBaseStackCreateProps } from './base-stack';
import * as path from 'path';

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

    // S3 bucket for CloudFront and frontend bucket access logs
    const accessLogBucket = new Bucket(this, 'AccessLogBucket', {
      bucketName: `${this.account}-${this.baseName}-cf-logs-${this.region}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: BucketEncryption.S3_MANAGED,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
      enforceSSL: true,
    });

    this.frontendBucket = new Bucket(this, 'FrontendBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: accessLogBucket,
      serverAccessLogsPrefix: 's3-access-logs/',
      enforceSSL: true,
    });

    // CloudFront Function for SPA routing
    // Compile TypeScript to JavaScript inline during deployment
    const spaRoutingFunction = new CloudFrontFunction(this, 'SPARoutingFunction', {
      code: FunctionCode.fromInline(`
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    
    // If the URI starts with /api, pass it through unchanged
    if (uri.indexOf('/api/') === 0) {
        return request;
    }
    
    // If the URI doesn't have a file extension and isn't the root,
    // rewrite it to /index.html for SPA routing
    if (uri.indexOf('.') === -1 && uri !== '/') {
        request.uri = '/index.html';
    }
    
    // If the URI is empty or just /, serve index.html
    if (uri === '' || uri === '/') {
        request.uri = '/index.html';
    }
    
    return request;
}
      `.trim()),
      comment: 'Rewrites paths for SPA routing while preserving API paths',
    });

    const cachePolicy = new CachePolicy(this, 'CachePolicy', {
      cachePolicyName: this.cdkName('cache-policy'),
      defaultTtl: Duration.seconds(0),
      minTtl: Duration.seconds(0),
      maxTtl: Duration.seconds(1),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
      cookieBehavior: CacheCookieBehavior.all(),
      headerBehavior: CacheHeaderBehavior.allowList('Origin', 'Access-Control-Request-Headers', 'Access-Control-Request-Method'),
      queryStringBehavior: CacheQueryStringBehavior.all()
    })

    // CloudFront Distribution with S3 origin
    this.distribution = new Distribution(this, 'distribution', {
      logBucket: accessLogBucket,
      logFilePrefix: 'cloudfront/',
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(this.frontendBucket),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        functionAssociations: [{
          function: spaRoutingFunction,
          eventType: FunctionEventType.VIEWER_REQUEST,
        }],
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
      minimumProtocolVersion: SecurityPolicyProtocol.TLS_V1_2_2021,
      defaultRootObject: 'index.html',
      // No error responses needed - CloudFront Function handles SPA routing at request time
      // This allows API errors (403, 404, etc.) to pass through correctly
    });

    this.log('CloudFrontDistributionDomain', `https://${this.distribution.distributionDomainName}`)
    this.log('frontendBucket', this.frontendBucket.bucketName)

    // Export the distribution domain name for use in other stacks
    new CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
      description: 'CloudFront Distribution Domain Name',
      exportName: `${props.baseName}-distribution-domain-name`
    });

    // Deploy frontend build to S3 bucket
    new BucketDeployment(this, 'FrontendDeployment', {
      sources: [Source.asset('./frontend/build')],
      destinationBucket: this.frontendBucket,
      distribution: this.distribution,
      distributionPaths: ['/*']
    });
  }
}