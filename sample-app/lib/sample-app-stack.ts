import { Stack, StackProps, RemovalPolicy, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  Distribution,
  ViewerProtocolPolicy,
  PriceClass,
  Function as CloudFrontFunction,
  FunctionCode,
  FunctionEventType,
  SecurityPolicyProtocol,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { Bucket, BucketEncryption, ObjectOwnership } from 'aws-cdk-lib/aws-s3';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';

export class SampleAppStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const accessLogBucket = new Bucket(this, 'AccessLogBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: BucketEncryption.S3_MANAGED,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
      enforceSSL: true,
    });

    const siteBucket = new Bucket(this, 'SiteBucket', {
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: accessLogBucket,
      serverAccessLogsPrefix: 's3-access-logs/',
      enforceSSL: true,
    });

    const spaRouting = new CloudFrontFunction(this, 'SPARouting', {
      code: FunctionCode.fromInline(`
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    if (uri.indexOf('.') === -1 && uri !== '/') {
        request.uri = '/index.html';
    }
    if (uri === '' || uri === '/') {
        request.uri = '/index.html';
    }
    return request;
}
      `.trim()),
      comment: 'SPA routing for AnyCompany sample app',
    });

    const distribution = new Distribution(this, 'Distribution', {
      logBucket: accessLogBucket,
      logFilePrefix: 'cloudfront/',
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        functionAssociations: [{
          function: spaRouting,
          eventType: FunctionEventType.VIEWER_REQUEST,
        }],
      },
      priceClass: PriceClass.PRICE_CLASS_100,
      minimumProtocolVersion: SecurityPolicyProtocol.TLS_V1_2_2021,
      defaultRootObject: 'index.html',
    });

    new BucketDeployment(this, 'DeploySite', {
      sources: [Source.asset(path.join(process.cwd(), 'dist'))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    new CfnOutput(this, 'SampleAppUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'AnyCompany Sample App URL',
    });
  }
}
