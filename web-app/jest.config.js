// Jest covers the CDK app and deploy scripts only. The frontend has its own
// vitest suite (web-app/frontend), which Jest can't parse.
module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/lib', '<rootDir>/scripts'],
  testMatch: ['**/*.test.ts'],
  // Resolve .ts before .js so tests exercise the sources, not stale `tsc`
  // output (lib/*.js, gitignored) left next to them by `npm run build`.
  moduleFileExtensions: ['ts', 'tsx', 'js', 'json'],
  transform: { '^.+\\.tsx?$': 'ts-jest' },
};
