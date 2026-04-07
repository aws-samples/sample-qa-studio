import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['test/**/*.test.js'],
    coverage: {
      provider: 'v8',
      include: ['*.js'],
      exclude: ['vitest.config.js', 'eslint.config.js', 'test/**']
    }
  }
});
