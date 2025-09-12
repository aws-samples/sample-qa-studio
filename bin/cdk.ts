#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { NovaActQAStudio } from '../lib/cdk-stack';

const app = new cdk.App();

const baseName = app.node.tryGetContext('baseName') || "nova-act-qa-studio"

new NovaActQAStudio(app, 'NovaActQAStudio', {
  baseName: baseName
});