import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import * as path from 'path';
import { loadConfig } from '../lib/config';

// Load configuration from lib/config.ts
const config = loadConfig();

export default defineConfig({
  resolve: {
    alias: {
      'dcv': path.resolve(__dirname, './public/dcv/dcv.js'),
    },
    extensions: ['.ts', '.tsx', '.js', '.jsx']
  },
  plugins: [react()],
  build: {
    outDir: 'build'
  },
  server: {
    port: 3000
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
  define: {
    // Expose config values as compile-time constants
    '__APP_CONFIG__': {
      baseName: JSON.stringify(config.baseName),
      defaultRegion: JSON.stringify(config.defaultRegion),
      enabledRegions: config.enabledRegions, // Don't stringify arrays - Vite handles this
      bedrockModelId: JSON.stringify(config.bedrockModelId),
      apiEndpoint: JSON.stringify(config.apiEndpoint),
    }
  }
})