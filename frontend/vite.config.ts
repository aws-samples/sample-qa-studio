import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import * as path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      'dcv': path.resolve(__dirname, './src/utils/dcvjs-esm/dcv.js'),
    }
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
})