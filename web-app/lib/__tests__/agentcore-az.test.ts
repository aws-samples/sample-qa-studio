/**
 * Guard: the AgentCore supported-AZ table is well-formed and the resolver maps
 * the account's AZ names to supported ones only, with actionable errors for
 * unknown regions and a failing AWS CLI. No AWS access: the lookup is injected.
 */
import {
  AGENTCORE_SUPPORTED_AZ_IDS,
  AGENTCORE_VPC_DOC_URL,
  resolveAgentCoreAzNames,
} from '../agentcore-az';

const EU_WEST_1 = JSON.stringify([
  ['eu-west-1c', 'euw1-az3'],
  ['eu-west-1a', 'euw1-az1'],
  ['eu-west-1b', 'euw1-az2'],
]);

describe('AGENTCORE_SUPPORTED_AZ_IDS', () => {
  it.each(Object.entries(AGENTCORE_SUPPORTED_AZ_IDS))('%s lists well-formed, unique AZ IDs', (region, ids) => {
    expect(region).toMatch(/^[a-z]{2}(-gov)?-[a-z]+-\d$/);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z]+\d+-az\d+$/);
  });
});

describe('resolveAgentCoreAzNames', () => {
  it('returns only the supported zone names, sorted', () => {
    const us = JSON.stringify([
      ['us-east-1a', 'use1-az6'],
      ['us-east-1b', 'use1-az1'],
      ['us-east-1c', 'use1-az2'],
      ['us-east-1d', 'use1-az4'],
      ['us-east-1e', 'use1-az3'],
    ]);
    expect(resolveAgentCoreAzNames('us-east-1', () => us)).toEqual(['us-east-1b', 'us-east-1c', 'us-east-1d']);
  });

  it('passes the region to the lookup', () => {
    const describe = jest.fn(() => EU_WEST_1);
    expect(resolveAgentCoreAzNames('eu-west-1', describe)).toEqual(['eu-west-1a', 'eu-west-1b', 'eu-west-1c']);
    expect(describe).toHaveBeenCalledWith('eu-west-1');
  });

  it('returns an empty list when the account has none of the supported zones', () => {
    expect(resolveAgentCoreAzNames('us-west-1', () => JSON.stringify([['us-west-1a', 'usw1-az2']]))).toEqual([]);
  });

  it('rejects an unknown region with the doc URL, without calling the lookup', () => {
    const describe = jest.fn(() => '[]');
    expect(() => resolveAgentCoreAzNames('mars-north-1', describe)).toThrow(
      /vpcId is set but region "mars-north-1" has no known AgentCore-supported/,
    );
    expect(() => resolveAgentCoreAzNames('mars-north-1', describe)).toThrow(AGENTCORE_VPC_DOC_URL);
    expect(describe).not.toHaveBeenCalled();
  });

  it('turns a CLI failure into an actionable error', () => {
    const failing = () => {
      throw new Error('Unable to locate credentials');
    };
    expect(() => resolveAgentCoreAzNames('eu-west-1', failing)).toThrow(
      /describe-availability-zones" failed\. Ensure the AWS CLI is installed and credentials.*Unable to locate credentials/,
    );
  });

  it.each(['not json', '{"a": 1}'])('rejects unparseable output %p', (raw) => {
    expect(() => resolveAgentCoreAzNames('eu-west-1', () => raw)).toThrow(/Failed to parse/);
  });
});
