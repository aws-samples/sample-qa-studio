import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import * as path from 'path';
import * as fs from 'fs';
import { loadConfig } from '../lib/config';

// Load configuration from lib/config.ts
const config = loadConfig();
const rootPackageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf-8'));


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
    '__APP_CONFIG__': JSON.stringify({
      baseName: config.baseName,
      defaultRegion: config.defaultRegion,
      enabledRegions: config.enabledRegions,
      bedrockModelId: config.bedrockModelId,
      apiEndpoint: config.apiEndpoint,
      version: rootPackageJson.version,
    })
  }
})