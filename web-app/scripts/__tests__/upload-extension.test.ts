import { extensionTargets } from '../upload-extension';

describe('extensionTargets', () => {
  it('targets the artefact bucket of the default and every enabled region once', () => {
    expect(extensionTargets('123', {
      baseName: 'studio',
      defaultRegion: 'eu-central-1',
      enabledRegions: ['eu-central-1', 'us-east-1'],
    })).toEqual([
      { region: 'eu-central-1', bucket: '123-studio-artefacts-eu-central-1' },
      { region: 'us-east-1', bucket: '123-studio-artefacts-us-east-1' },
    ]);
  });

  it('includes the default region even when it is not listed as enabled', () => {
    expect(extensionTargets('123', { baseName: 's', defaultRegion: 'us-east-1', enabledRegions: ['us-west-2'] })
      .map(t => t.region)).toEqual(['us-east-1', 'us-west-2']);
  });
});
