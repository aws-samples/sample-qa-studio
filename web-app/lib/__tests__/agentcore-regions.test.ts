/**
 * Guard: wizard sessions and runs can use any enabled region. The worker task
 * role may create and drive AgentCore browsers in every enabled region and
 * write to every regional artefact bucket, and /wizard/start can name the
 * regional bucket (AgentCore records only to a same-region bucket). The worker creates the browser in the use case's
 * executing_region; a role scoped to the stack's region alone fails every
 * wizard session / run of a use case in another enabled region with
 * AccessDenied on bedrock-agentcore:CreateBrowser.
 */
import { Template } from 'aws-cdk-lib/assertions';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { loadConfig } from '../config';
import { synthStacks } from './synthStacks';

/** Every resource string of the worker policies that allow bedrock-agentcore:CreateBrowser. */
function createBrowserResources(template: any): string[] {
  return Object.values<any>(template.Resources)
    .filter(r => r.Type === 'AWS::IAM::Policy')
    .flatMap(r => r.Properties.PolicyDocument.Statement)
    .filter((s: any) => s.Effect === 'Allow' && ([] as string[]).concat(s.Action).includes('bedrock-agentcore:CreateBrowser'))
    .flatMap((s: any) => ([] as any[]).concat(s.Resource))
    .map((res: any) => (typeof res === 'string' ? res : JSON.stringify(res)));
}

describe('worker AgentCore permissions', () => {
  const { worker } = synthStacks();
  const resources = createBrowserResources(Template.fromStack(worker).toJSON());
  const { enabledRegions } = loadConfig();

  it('the sample config enables more than one region', () => {
    expect(enabledRegions.length).toBeGreaterThan(1);
  });

  it.each(['browser', 'browser-custom', 'browser-session'])('allow %s/* in every enabled region', (kind) => {
    const missing = enabledRegions.filter(
      (region: string) => !resources.some(r => r.includes(`arn:aws:bedrock-agentcore:${region}:`) && r.includes(`:${kind}/*`)),
    );
    expect(missing).toEqual([]);
  });
});

describe('wizard start and regional artefact buckets', () => {
  const { worker } = synthStacks();
  const template = Template.fromStack(worker).toJSON();
  const { enabledRegions } = loadConfig();

  it('start_wizard_session gets the bucket prefix and default region', () => {
    const fn = Object.values<any>(template.Resources).find(
      r => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === 'start_wizard_session.handler',
    );
    const env = fn.Properties.Environment.Variables;
    expect(env.DEFAULT_REGION).toBeTruthy();
    expect(env.S3_BUCKET_PREFIX).toBeTruthy();
  });

  it('the task role may write to the artefact bucket of every enabled region', () => {
    const s3Resources = Object.values<any>(template.Resources)
      .filter(r => r.Type === 'AWS::IAM::Policy')
      .flatMap(r => r.Properties.PolicyDocument.Statement)
      .filter((st: any) => ([] as string[]).concat(st.Action).includes('s3:PutObject*'))
      .flatMap((st: any) => ([] as any[]).concat(st.Resource))
      .map((res: any) => JSON.stringify(res));
    // The default region's bucket is the stack's own artefacts bucket (a Fn::GetAtt);
    // the other regions' buckets are named.
    const { defaultRegion } = loadConfig();
    const missing = enabledRegions
      .filter((region: string) => region !== defaultRegion)
      .filter((region: string) => !s3Resources.some(r => r.includes(`artefacts-${region}`) && r.includes('/*')));
    expect(missing).toEqual([]);
    expect(s3Resources.some(r => r.includes('Fn::GetAtt') && r.includes('artefacts'))).toBe(true);
  });
});
