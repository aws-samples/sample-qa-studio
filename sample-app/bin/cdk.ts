#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { SampleAppStack } from '../lib/sample-app-stack';

const app = new App();

new SampleAppStack(app, 'SampleApp', {
  stackName: 'anycompany-sample-app',
});

app.synth();
