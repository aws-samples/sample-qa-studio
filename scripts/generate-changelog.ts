#!/usr/bin/env ts-node
import { execSync } from 'child_process';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

/**
 * Generate changelog from git commits using conventional commit format
 */

interface Commit {
  hash: string;
  subject: string;
  author: string;
  date: string;
}

interface ParsedCommit {
  type: string;
  scope: string | null;
  message: string;
}

interface Category {
  title: string;
  items: string[];
}

interface Categories {
  [key: string]: Category;
}

function getLastTag(): string | null {
  try {
    return execSync('git describe --tags --abbrev=0', { encoding: 'utf-8' }).trim();
  } catch {
    // No tags yet
    return null;
  }
}

function getCommitsSinceTag(tag: string | null): Commit[] {
  const range = tag ? `${tag}..HEAD` : 'HEAD';
  try {
    const commits = execSync(`git log ${range} --pretty=format:"%H|%s|%an|%ad" --date=short`, {
      encoding: 'utf-8'
    }).trim();
    
    if (!commits) return [];
    
    return commits.split('\n').map(line => {
      const [hash, subject, author, date] = line.split('|');
      return { hash, subject, author, date };
    });
  } catch {
    return [];
  }
}

function parseConventionalCommit(subject: string): ParsedCommit {
  // Match: type(scope): message or type: message
  const match = subject.match(/^(\w+)(?:\(([^)]+)\))?: (.+)$/);
  
  if (match) {
    return {
      type: match[1],
      scope: match[2] || null,
      message: match[3]
    };
  }
  
  return {
    type: 'other',
    scope: null,
    message: subject
  };
}

function categorizeCommits(commits: Commit[]): Categories {
  const categories: Categories = {
    feat: { title: 'Features', items: [] },
    fix: { title: 'Bug Fixes', items: [] },
    docs: { title: 'Documentation', items: [] },
    perf: { title: 'Performance', items: [] },
    refactor: { title: 'Refactoring', items: [] },
    test: { title: 'Tests', items: [] },
    chore: { title: 'Chores', items: [] },
    other: { title: 'Other Changes', items: [] }
  };
  
  commits.forEach(commit => {
    const parsed = parseConventionalCommit(commit.subject);
    const category = categories[parsed.type] || categories.other;
    
    const scopePrefix = parsed.scope ? `**${parsed.scope}**: ` : '';
    category.items.push(`- ${scopePrefix}${parsed.message} (${commit.hash.substring(0, 7)})`);
  });
  
  return categories;
}

function generateChangelog(version: string, categories: Categories, date: string): string {
  let changelog = `## [${version}] - ${date}\n\n`;
  
  // Only include categories that have items
  Object.values(categories).forEach(category => {
    if (category.items.length > 0) {
      changelog += `### ${category.title}\n\n`;
      category.items.forEach(item => {
        changelog += `${item}\n`;
      });
      changelog += '\n';
    }
  });
  
  return changelog;
}

function prependToChangelog(newContent: string): void {
  const changelogPath = join(__dirname, '..', 'CHANGELOG.md');
  let existingContent = '';
  
  if (existsSync(changelogPath)) {
    existingContent = readFileSync(changelogPath, 'utf-8');
    // Remove the header if it exists
    existingContent = existingContent.replace(/^# Changelog\n\n/, '');
  }
  
  const fullContent = `# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n${newContent}${existingContent}`;
  
  writeFileSync(changelogPath, fullContent, 'utf-8');
  console.log('✅ CHANGELOG.md updated');
}

function main(): void {
  const version = process.argv[2];
  
  if (!version) {
    console.error('Usage: ts-node generate-changelog.ts <version>');
    process.exit(1);
  }
  
  const lastTag = getLastTag();
  console.log(`📝 Generating changelog for version ${version}`);
  console.log(`📌 Last tag: ${lastTag || 'none (first release)'}`);
  
  const commits = getCommitsSinceTag(lastTag);
  
  if (commits.length === 0) {
    console.log('⚠️  No commits found since last tag');
    return;
  }
  
  console.log(`📊 Found ${commits.length} commits`);
  
  const categories = categorizeCommits(commits);
  const date = new Date().toISOString().split('T')[0];
  const changelogEntry = generateChangelog(version, categories, date);
  
  prependToChangelog(changelogEntry);
}

if (require.main === module) {
  main();
}

export { generateChangelog, categorizeCommits, parseConventionalCommit };
