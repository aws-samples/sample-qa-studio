/**
 * Guard: every Python Lambda built from a local asset has a source module
 * that defines its handler. A Lambda whose module was deleted (e.g. the
 * former stop_suite_execution) still synthesizes and deploys, then fails on
 * every invocation with "Unable to import module".
 *
 * Reads each Function's asset source directory (AssetStaging.sourcePath) and
 * its CloudFormation `Handler`, so overrides of the default
 * `<path>.handler` are honoured.
 */
import * as fs from 'fs';
import * as path from 'path';
import { Stack } from 'aws-cdk-lib';
import { CfnFunction, Function as LambdaFunction } from 'aws-cdk-lib/aws-lambda';
import { AssetStaging } from 'aws-cdk-lib';

jest.mock('../config', () => {
  const actual = jest.requireActual('../config');
  const sample = require('path').join(__dirname, '..', '..', 'configuration.json.sample');
  return { ...actual, loadConfig: () => actual.loadConfig(sample) };
});

import { synthStacks } from './synthStacks';

const LAMBDAS_DIR = path.resolve(__dirname, '..', '..', 'lambdas');

export interface LambdaEntry {
  id: string;
  sourceDir: string;
  handler: string;
}

/** Why `entry` cannot be imported/called, or null when its handler exists. */
export function handlerProblem({ sourceDir, handler }: LambdaEntry): string | null {
  const dot = handler.lastIndexOf('.');
  if (dot <= 0) return `handler "${handler}" is not <module>.<function>`;
  const moduleFile = path.join(sourceDir, `${handler.slice(0, dot).replace(/\./g, path.sep)}.py`);
  const functionName = handler.slice(dot + 1);
  if (!fs.existsSync(moduleFile)) return `missing module ${path.relative(LAMBDAS_DIR, moduleFile)}`;
  const defines = new RegExp(`^(async\\s+)?def\\s+${functionName}\\s*\\(|^${functionName}\\s*=`, 'm');
  if (!defines.test(fs.readFileSync(moduleFile, 'utf-8'))) {
    return `${path.relative(LAMBDAS_DIR, moduleFile)} does not define ${functionName}`;
  }
  return null;
}

/** Python Lambdas whose code is a local directory under web-app/lambdas. */
function localPythonLambdas(stacks: Stack[]): LambdaEntry[] {
  const entries: LambdaEntry[] = [];
  for (const stack of stacks) {
    for (const node of stack.node.findAll()) {
      if (!(node instanceof LambdaFunction)) continue;
      const cfn = node.node.defaultChild as CfnFunction;
      if (!String(cfn.runtime ?? '').startsWith('python')) continue;
      const staging = node.node.findAll().find((c): c is AssetStaging => c instanceof AssetStaging);
      if (!staging || !path.resolve(staging.sourcePath).startsWith(LAMBDAS_DIR + path.sep)) continue;
      entries.push({ id: node.node.path, sourceDir: staging.sourcePath, handler: cfn.handler! });
    }
  }
  return entries;
}

describe('Lambda sources', () => {
  const { storage, auth, worker, lambdas, api } = synthStacks({ withApi: true });
  const entries = localPythonLambdas([storage, auth, worker, lambdas, api!]);

  it('finds the local Python Lambdas of every stack', () => {
    const ids = entries.map(e => e.id.split('/')[0]);
    expect(new Set(ids)).toEqual(new Set(['storage', 'auth', 'worker', 'lambdas', 'api']));
    expect(entries.length).toBeGreaterThan(100);
  });

  it('every handler module exists and defines its handler function', () => {
    const problems = entries
      .map(e => ({ id: e.id, problem: handlerProblem(e) }))
      .filter(p => p.problem !== null);
    expect(problems).toEqual([]);
  });
});

describe('handlerProblem', () => {
  const sourceDir = path.join(LAMBDAS_DIR, 'endpoints');

  it('accepts an existing module and function', () => {
    expect(handlerProblem({ id: 'x', sourceDir, handler: 'get_usecase.handler' })).toBeNull();
  });

  it('accepts a dotted module path', () => {
    expect(handlerProblem({ id: 'x', sourceDir, handler: 'application_router.handler' })).toBeNull();
  });

  it('reports a missing module', () => {
    expect(handlerProblem({ id: 'x', sourceDir, handler: 'stop_suite_execution.handler' })).toBe(
      'missing module endpoints/stop_suite_execution.py',
    );
  });

  it('reports a missing function', () => {
    expect(handlerProblem({ id: 'x', sourceDir, handler: 'get_usecase.no_such_function' })).toBe(
      'endpoints/get_usecase.py does not define no_such_function',
    );
  });

  it('rejects a handler without a function part', () => {
    expect(handlerProblem({ id: 'x', sourceDir, handler: 'get_usecase' })).toBe(
      'handler "get_usecase" is not <module>.<function>',
    );
  });
});
