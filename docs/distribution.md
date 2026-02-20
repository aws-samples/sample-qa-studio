# Distribution

This guide covers how to package QA Studio as a distributable release archive and deploy it in a new environment. For standard development deployment, see the [Getting Started](../README.md#getting-started) section in the project root README.

## Creating a Release Package

Create a distributable package for sharing or deploying elsewhere:

```bash
# Create a patch release (bug fixes)
npm run release:patch

# Create a minor release (new features)
npm run release:minor

# Create a major release (breaking changes)
npm run release:major

# Create a pre-release (beta/rc)
npm run release:prerelease
```

The release process handles versioning, changelog generation, and packaging automatically.

## What's in the Package

The generated zip file contains everything needed for deployment:
- Python Lambda functions in `endpoints/` directory (no build needed)
- Frontend source code (built during deployment)
- Worker source code and Dockerfile
- CDK TypeScript source code
- Configuration templates
- Documentation

## Deploying from a Package

```bash
# Extract and navigate
unzip nova-act-qa-studio-v1.2.3.zip
cd nova-act-qa-studio-v1.2.3

# Install dependencies
npm install

# Compile CDK code
npm run build

# Set up your configuration
cp configuration.json.sample configuration.json
# Edit configuration.json with your settings

# Deploy everything
npm run deploy:release
```

The deployment installs dependencies, builds the frontend, and deploys all AWS resources. You'll need Node.js and npm, but not Go since Lambda functions are pre-built.
