#!/usr/bin/env ts-node
import { execSync } from 'child_process';
import { readFileSync, readdirSync, existsSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

/**
 * Run cdk synth to trigger cdk-nag checks and generate a consolidated report.
 *
 * cdk-nag produces per-stack CSV and JSON files in cdk.out/ during synthesis.
 * This script:
 *   1. Runs `cdk synth` to trigger all nag checks
 *   2. Collects the JSON report files from cdk.out/
 *   3. Merges them into a single consolidated report at reports/cdk-nag-report.json
 *   4. Prints a summary to stdout
 */

interface NagFinding {
  ruleId: string;
  ruleInfo: string;
  ruleLevel: string;
  compliance: string;
  resource: string;
  suppressionReason?: string;
}

interface StackReport {
  stack: string;
  findings: NagFinding[];
}

interface ConsolidatedReport {
  generatedAt: string;
  summary: {
    totalFindings: number;
    nonCompliant: number;
    suppressed: number;
    compliant: number;
    byLevel: Record<string, number>;
  };
  stacks: StackReport[];
}

function runSynth(): void {
  console.log('🔍 Running cdk synth to trigger cdk-nag checks...\n');
  try {
    execSync('npx cdk synth --quiet 2>&1', {
      cwd: join(__dirname, '..'),
      encoding: 'utf-8',
      stdio: 'inherit',
    });
  } catch {
    // cdk synth may exit non-zero when nag findings exist — that's expected
    console.log('\n⚠️  cdk synth completed with warnings (expected when nag findings exist)\n');
  }
}

function collectReports(): ConsolidatedReport {
  const cdkOutDir = join(__dirname, '..', 'cdk.out');

  if (!existsSync(cdkOutDir)) {
    console.error('❌ cdk.out/ not found. Did cdk synth run?');
    process.exit(1);
  }

  const nagFiles = readdirSync(cdkOutDir).filter(
    (f: string) => f.startsWith('AwsSolutions-') && f.endsWith('.json')
  );

  if (nagFiles.length === 0) {
    console.log('✅ No cdk-nag report files found — all checks may have passed.');
    return {
      generatedAt: new Date().toISOString(),
      summary: { totalFindings: 0, nonCompliant: 0, suppressed: 0, compliant: 0, byLevel: {} },
      stacks: [],
    };
  }

  const stacks: StackReport[] = [];
  let totalFindings = 0;
  let nonCompliant = 0;
  let suppressed = 0;
  let compliant = 0;
  const byLevel: Record<string, number> = {};

  for (const file of nagFiles) {
    const raw = readFileSync(join(cdkOutDir, file), 'utf-8');
    let lines: NagFinding[];

    try {
      // cdk-nag JSON reports are newline-delimited JSON (one object per line)
      lines = raw
        .trim()
        .split('\n')
        .filter((l: string) => l.trim())
        .map((l: string) => JSON.parse(l) as NagFinding);
    } catch {
      console.warn(`⚠️  Could not parse ${file}, skipping`);
      continue;
    }

    // Stack name from filename: AwsSolutions-<stackName>-NagReport.json
    const stackName = file.replace('AwsSolutions-', '').replace('-NagReport.json', '');
    stacks.push({ stack: stackName, findings: lines });

    for (const finding of lines) {
      totalFindings++;
      const level = finding.ruleLevel || 'Unknown';
      byLevel[level] = (byLevel[level] || 0) + 1;

      if (finding.compliance === 'Non-Compliant') {
        if (finding.suppressionReason) {
          suppressed++;
        } else {
          nonCompliant++;
        }
      } else {
        compliant++;
      }
    }
  }

  return {
    generatedAt: new Date().toISOString(),
    summary: { totalFindings, nonCompliant, suppressed, compliant, byLevel },
    stacks,
  };
}

function printSummary(report: ConsolidatedReport): void {
  const { summary, stacks } = report;

  console.log('═══════════════════════════════════════════');
  console.log('  cdk-nag Report Summary');
  console.log('═══════════════════════════════════════════\n');
  console.log(`  Generated:      ${report.generatedAt}`);
  console.log(`  Total findings: ${summary.totalFindings}`);
  console.log(`  Non-compliant:  ${summary.nonCompliant}`);
  console.log(`  Suppressed:     ${summary.suppressed}`);
  console.log(`  Compliant:      ${summary.compliant}`);

  if (Object.keys(summary.byLevel).length > 0) {
    console.log('\n  By level:');
    for (const [level, count] of Object.entries(summary.byLevel)) {
      console.log(`    ${level}: ${count}`);
    }
  }

  // Per-stack breakdown
  console.log('\n───────────────────────────────────────────');
  console.log('  Per-stack breakdown');
  console.log('───────────────────────────────────────────\n');

  for (const stack of stacks) {
    const stackNonCompliant = stack.findings.filter(
      (f) => f.compliance === 'Non-Compliant' && !f.suppressionReason
    ).length;
    const stackSuppressed = stack.findings.filter(
      (f) => f.compliance === 'Non-Compliant' && !!f.suppressionReason
    ).length;
    const stackCompliant = stack.findings.filter(
      (f) => f.compliance !== 'Non-Compliant'
    ).length;

    console.log(`  📦 ${stack.stack}`);
    console.log(`     Findings: ${stack.findings.length}  (❌ ${stackNonCompliant} non-compliant, ⚠️  ${stackSuppressed} suppressed, ✅ ${stackCompliant} compliant)`);

    // Show non-compliant (unsuppressed) findings
    const unsuppressed = stack.findings.filter(
      (f) => f.compliance === 'Non-Compliant' && !f.suppressionReason
    );
    if (unsuppressed.length > 0) {
      console.log('     Non-compliant:');
      for (const f of unsuppressed) {
        console.log(`       ❌ [${f.ruleId}] ${f.resource}`);
        console.log(`          ${f.ruleInfo}`);
      }
    }
    console.log('');
  }

  console.log('═══════════════════════════════════════════\n');
}

function main(): void {
  // Step 1: Run cdk synth
  runSynth();

  // Step 2: Collect and merge reports
  const report = collectReports();

  // Step 3: Write consolidated report
  const reportsDir = join(__dirname, '..', 'reports');
  if (!existsSync(reportsDir)) {
    mkdirSync(reportsDir, { recursive: true });
  }
  const reportPath = join(reportsDir, 'cdk-nag-report.json');
  writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf-8');
  console.log(`📄 Consolidated report written to: reports/cdk-nag-report.json\n`);

  // Step 4: Print summary
  printSummary(report);

  // Exit with non-zero if there are unsuppressed non-compliant findings
  if (report.summary.nonCompliant > 0) {
    console.log(`❌ ${report.summary.nonCompliant} non-compliant finding(s) require attention.\n`);
    process.exit(1);
  } else {
    console.log('✅ No unsuppressed non-compliant findings.\n');
  }
}

if (require.main === module) {
  main();
}

export { collectReports, printSummary, ConsolidatedReport };
