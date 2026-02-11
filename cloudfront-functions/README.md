# CloudFront Functions

This directory contains TypeScript source files for CloudFront Functions that are compiled to ES5 JavaScript during the build process.

## Why TypeScript?

CloudFront Functions are written in TypeScript for:
- Type safety and better IDE support
- Consistent development experience with the rest of the CDK project
- Version control of source files (compiled JS files are gitignored by default)
- Better documentation through JSDoc comments

## Build Process

CloudFront Functions are automatically compiled during the CDK build:

```bash
npm run build              # Builds both CDK and CloudFront functions
npm run build:cloudfront   # Builds only CloudFront functions
```

Compiled files are output to `lib/cloudfront-functions/` and are **gitignored** (not tracked in version control). Only the TypeScript source files in this directory are tracked in git.

**Important**: You must run `npm run build` before deploying to ensure the compiled CloudFront functions exist.

## CloudFront Function Limitations

CloudFront Functions have strict constraints:
- **ES5 only**: No arrow functions, const/let, template literals, etc.
- **Maximum size**: 10KB
- **No external dependencies**: Cannot import npm packages
- **Limited runtime APIs**: Only basic JavaScript features available
- **No async/await**: Functions must be synchronous

## TypeScript Configuration

The `tsconfig.json` in this directory is configured to:
- Target ES5 for CloudFront compatibility
- Remove comments to reduce file size
- Output to `lib/cloudfront-functions/`

## Adding New Functions

1. Create a new `.ts` file in this directory
2. Write your function following CloudFront Function constraints
3. Run `npm run build:cloudfront` to compile
4. Reference the compiled `.js` file in your CDK stack:
   ```typescript
   const myFunction = new CloudFrontFunction(this, 'MyFunction', {
     code: FunctionCode.fromFile({ 
       filePath: path.join(__dirname, 'cloudfront-functions', 'my-function.js') 
     })
   });
   ```

## Current Functions

- **spa-routing.ts**: Handles SPA routing by rewriting paths to `/index.html` while preserving API routes
