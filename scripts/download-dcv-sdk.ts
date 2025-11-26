#!/usr/bin/env ts-node
import { writeFileSync, existsSync, mkdirSync, rmSync, readFileSync } from 'fs';
import { join } from 'path';
import { execSync } from 'child_process';
import { loadConfig } from '../lib/config';

interface VersionCache {
  url: string;
  timestamp: number;
}

const dcvDir = join(__dirname, '..', 'frontend', 'public', 'dcv');
const versionCachePath = join(dcvDir, '.version-cache.json');

function readVersionCache(): VersionCache | null {
  try {
    if (existsSync(versionCachePath)) {
      const cacheContent = readFileSync(versionCachePath, 'utf-8');
      return JSON.parse(cacheContent);
    }
  } catch (error) {
    console.warn('⚠️  Could not read version cache:', error);
  }
  return null;
}

function writeVersionCache(url: string) {
  try {
    mkdirSync(dcvDir, { recursive: true });
    const cache: VersionCache = {
      url,
      timestamp: Date.now()
    };
    writeFileSync(versionCachePath, JSON.stringify(cache, null, 2), 'utf-8');
  } catch (error) {
    console.warn('⚠️  Could not write version cache:', error);
  }
}

function needsUpdate(dcvReleaseUrl: string): boolean {
  const cache = readVersionCache();
  
  if (!cache) {
    console.log('📦 No previous version found');
    return true;
  }
  
  if (cache.url !== dcvReleaseUrl) {
    console.log('🔄 DCV SDK URL has changed');
    console.log(`   Old: ${cache.url}`);
    console.log(`   New: ${dcvReleaseUrl}`);
    return true;
  }
  
  console.log('✅ DCV SDK is up to date');
  return false;
}

function downloadAndExtract(url: string) {
  console.log(`📥 Downloading DCV SDK from: ${url}`);
  
  const tempDir = join(__dirname, '..', '.tmp-dcv-download');
  const tempExtractDir = join(tempDir, 'extracted');
  const tempFile = join(tempDir, 'dcv-sdk.zip');
  
  try {
    // Create temp directory
    mkdirSync(tempDir, { recursive: true });
    
    // Download the file
    console.log('⬇️  Downloading...');
    execSync(`curl -L -o "${tempFile}" "${url}"`, { stdio: 'inherit' });
    
    // Extract to temp directory first
    console.log('📦 Extracting archive...');
    mkdirSync(tempExtractDir, { recursive: true });
    execSync(`unzip -q "${tempFile}" -d "${tempExtractDir}"`, { stdio: 'inherit' });
    
    // Find the dcvjs-umd folder
    console.log('🔍 Locating dcvjs-umd folder...');
    const findResult = execSync(`find "${tempExtractDir}" -type d -name "dcvjs-umd"`, { encoding: 'utf-8' }).trim();
    
    if (!findResult) {
      throw new Error('dcvjs-umd folder not found in the downloaded archive');
    }
    
    const dcvjsUmdPath = findResult.split('\n')[0]; // Take first match if multiple
    console.log(`   Found: ${dcvjsUmdPath}`);
    
    // Clean existing DCV directory (but preserve our custom README.md)
    const customReadmePath = join(dcvDir, 'README.md');
    let customReadmeContent = '';
    
    if (existsSync(dcvDir)) {
      console.log('🧹 Cleaning existing DCV directory...');
      
      // Backup our custom README.md if it exists and starts with "# DCV SDK Directory"
      if (existsSync(customReadmePath)) {
        const content = readFileSync(customReadmePath, 'utf-8');
        if (content.startsWith('# DCV SDK Directory')) {
          customReadmeContent = content;
        }
      }
      
      rmSync(dcvDir, { recursive: true, force: true });
    }
    
    mkdirSync(dcvDir, { recursive: true });
    
    // Copy dcvjs-umd contents to dcv directory
    console.log('📋 Copying dcvjs-umd contents...');
    execSync(`cp -R "${dcvjsUmdPath}"/* "${dcvDir}/"`, { stdio: 'inherit' });
    
    // Restore our custom README.md if we had one
    if (customReadmeContent) {
      console.log('📝 Restoring custom README.md...');
      writeFileSync(customReadmePath, customReadmeContent, 'utf-8');
    }
    
    // Write version cache
    writeVersionCache(url);
    
    console.log('✅ DCV SDK (dcvjs-umd) downloaded and extracted successfully');
    
  } catch (error) {
    console.error('❌ Error downloading or extracting DCV SDK:', error);
    process.exit(1);
  } finally {
    // Clean up temp directory
    if (existsSync(tempDir)) {
      rmSync(tempDir, { recursive: true, force: true });
    }
  }
}

function main() {
  console.log('🚀 DCV SDK Download Script\n');
  
  try {
    const config = loadConfig();
    const dcvReleaseUrl = config.dcvRelease;
    
    if (!dcvReleaseUrl) {
      console.log('⚠️  No dcvRelease URL found in configuration');
      console.log('   Skipping DCV SDK download');
      process.exit(0);
    }
    
    if (!needsUpdate(dcvReleaseUrl)) {
      console.log('⏭️  Skipping download - already up to date');
      process.exit(0);
    }
    
    downloadAndExtract(dcvReleaseUrl);
  } catch (error) {
    console.error('❌ Error:', error);
    process.exit(1);
  }
}

main();
