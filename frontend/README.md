# QA Studio Frontend

This project contains the QA Studio single page web application written in React and TypeScript.

## Project overview

This project builds a web app with the following technologies:

| Technology | Description | Link |
|---|---|---|
| Vite | JavaScript source code tooling and bundler | https://vitejs.dev/ |
| React | JavaScript library | https://react.dev/ |
| React Router | Single page app routing | https://reactrouter.com/ |
| Cloudscape Design System | AWS UI component library | https://cloudscape.design/ |
| AWS Amplify | Authentication and AWS integration | https://docs.amplify.aws/ |
| Vitest | Unit testing framework | https://vitest.dev/ |

## Project folder structure

```
public/                         Static files such as images and favicon
  dcv/                          DCV web client SDK assets
  testing-pages/                HTML test pages for development
src/                            React source code
  index.tsx                     App entry point, mounts React root
  App.tsx                       Main App component, configures routing, auth, and layout
  components/                   React components
    common/                     Shared reusable components (ErrorDisplay, LoadingStates, etc.)
    dcv/                        DCV viewer integration components
    execution/                  Execution detail and live view components
    templates/                  Template library and detail views
    usecase/                    Use case detail sub-components
    wizard/                     Interactive wizard flow components
    UserJourneyWizard/          AI-powered user journey generation
    __tests__/                  Component tests
  hooks/                        React Hooks
    useLiveViewUrl.ts           Hook for polling live view streaming URLs
    useModels.ts                Hook for fetching available Nova Act models
  utils/                        Utility functions
    api.ts                      API client with auth, retry, and error handling
    browser_regions.ts          Region configuration
    errorManager.ts             Centralized error handling
    retryManager.ts             Retry and circuit breaker logic
    s3Utils.ts                  S3 presigned URL utilities
    validation.ts               Form validation helpers
index.html                      Main application HTML file
.env-sample                     Sample .env file with required environment variables
vite.config.ts                  Vite build and dev server configuration
```

## Prerequisites

Before working with the frontend, complete the [Prerequisites](../README.md#prerequisites) and [Setup](../README.md#setup) sections in the project root README. This includes deploying the infrastructure and creating a valid `configuration.json` in the project root.

- Node.js 18+ and npm
- Project infrastructure deployed via `npm run deploy` from the project root
- A valid `configuration.json` in the project root (copy from `configuration.json.sample` and configure)

## Getting started

Install dependencies:

```
npm install
```

## Environment variables

This project uses Vite's `define` plugin to inject configuration at build time from `configuration.json` in the project root (loaded via `lib/config.ts`). The following values are exposed as `__APP_CONFIG__`:

- `baseName`: deployment base name
- `defaultRegion`: default AWS region
- `enabledRegions`: list of enabled AWS regions
- `bedrockModelId`: Bedrock model ID for AI features
- `apiEndpoint`: backend API endpoint URL

## Development

#### 1. Set your API Gateway URL

Set `apiGatewayUrl` in `configuration.json` (project root) to your deployed API Gateway URL:

```json
{
  "apiGatewayUrl": "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com"
}
```

The Vite dev server uses this to proxy `/api/*` requests to your backend. Without it, API calls will fail against localhost.

#### 2. Start the dev server

```
npm run dev
```

Runs the app in development mode on http://localhost:3000. Live updates as files are saved.

## Build

```
npm run build
```

Builds the app for production into the `build/` folder.

## Testing

```
npm run test:run
```

Runs the test suite once. Use `npm test` for watch mode during development.
