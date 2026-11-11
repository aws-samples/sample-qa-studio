import { describe, expect, it } from 'vitest';
import type { ExecutionVariablesResponse } from '../../../utils/api';
import {
  buildVariableContext,
  resolveTemplate,
  type TemplateSegment,
  type VariableContext,
  type VariableKind,
} from '../variableTokens';

function context(overrides: Partial<VariableContext> = {}): VariableContext {
  return {
    executionId: 'exec-123',
    createdAt: '2024-05-01T10:00:00Z',
    executionVariables: {},
    runtimeVariables: {},
    pendingRuntimeNames: new Set<string>(),
    ...overrides,
  };
}

/** The single variable segment of a template that consists of one token. */
function onlyVariable(text: string, ctx: VariableContext, row?: Record<string, string | number>) {
  const segments = resolveTemplate(text, ctx, row);
  expect(segments).toHaveLength(1);
  const [segment] = segments;
  if (segment.type !== 'variable') throw new Error(`expected a variable segment, got ${JSON.stringify(segment)}`);
  return segment;
}

const variable = (name: string, kind: VariableKind, display: string, placeholder = false): TemplateSegment => ({
  type: 'variable',
  name,
  kind,
  display,
  placeholder,
});

/** An unresolved token: the name is kept on the segment, the badge shows the UNDEFINED_VALUE placeholder. */
const undefinedVariable = (name: string): TemplateSegment => variable(name, 'undefined', 'UNDEFINED_VALUE', true);

describe('resolveTemplate: token grammar', () => {
  it('returns no segments for an empty string', () => {
    expect(resolveTemplate('', context())).toEqual([]);
  });

  it('returns text without tokens verbatim, including lone braces', () => {
    expect(resolveTemplate('a { b } c', context())).toEqual([{ type: 'text', text: 'a { b } c' }]);
  });

  it('splits text and tokens in order, keeping surrounding text verbatim', () => {
    const ctx = context({ executionVariables: { product: 'Shoes', size: '42' } });
    expect(resolveTemplate('Search {{product}} in size {{size}}.', ctx)).toEqual([
      { type: 'text', text: 'Search ' },
      variable('product', 'regular', 'Shoes'),
      { type: 'text', text: ' in size ' },
      variable('size', 'regular', '42'),
      { type: 'text', text: '.' },
    ]);
  });

  it('produces adjacent segments for adjacent tokens', () => {
    const ctx = context({ executionVariables: { a: '1', b: '2' } });
    expect(resolveTemplate('{{a}}{{b}}', ctx)).toEqual([variable('a', 'regular', '1'), variable('b', 'regular', '2')]);
  });

  it('classifies a token with whitespace inside the braces as undefined, named by the trimmed inner text', () => {
    const ctx = context({ executionVariables: { name: 'Alice' } });
    expect(onlyVariable('{{ name }}', ctx)).toEqual(undefinedVariable('name'));
    expect(onlyVariable('{{name }}', ctx)).toEqual(undefinedVariable('name'));
    expect(onlyVariable('{{\tname}}', ctx)).toEqual(undefinedVariable('name'));
  });

  it('does not treat a whitespace-padded built-in as a built-in', () => {
    expect(onlyVariable('{{ ExecutionID }}', context())).toEqual(undefinedVariable('ExecutionID'));
  });

  it('leaves malformed braces as text', () => {
    const ctx = context({ executionVariables: { name: 'Alice' } });
    expect(resolveTemplate('{{name}', ctx)).toEqual([{ type: 'text', text: '{{name}' }]);
    expect(resolveTemplate('{name}}', ctx)).toEqual([{ type: 'text', text: '{name}}' }]);
    expect(resolveTemplate('{{}}', ctx)).toEqual([{ type: 'text', text: '{{}}' }]);
    expect(resolveTemplate('{{   }}', ctx)).toEqual([{ type: 'text', text: '{{   }}' }]);
  });

  it('resolves the innermost token of triple braces, like str.replace in the runner', () => {
    const ctx = context({ executionVariables: { name: 'Alice' } });
    expect(resolveTemplate('{{{name}}}', ctx)).toEqual([
      { type: 'text', text: '{' },
      variable('name', 'regular', 'Alice'),
      { type: 'text', text: '}' },
    ]);
  });

  it('handles braces inside a would-be token like the runner', () => {
    const ctx = context({ executionVariables: { me: 'X' } });
    // No `{{me}}` substring: the runner substitutes nothing.
    expect(resolveTemplate('{{na{me}}', ctx)).toEqual([{ type: 'text', text: '{{na{me}}' }]);
    // `{{me}}` is a substring: the runner substitutes it.
    expect(resolveTemplate('{{na{{me}}', ctx)).toEqual([
      { type: 'text', text: '{{na' },
      variable('me', 'regular', 'X'),
    ]);
  });

  it('preserves the original casing and does not resolve case-insensitively', () => {
    const ctx = context({ executionVariables: { Product: 'Shoes' } });
    expect(onlyVariable('{{Product}}', ctx)).toEqual(variable('Product', 'regular', 'Shoes'));
    expect(onlyVariable('{{product}}', ctx)).toEqual(undefinedVariable('product'));
    expect(onlyVariable('{{uniqueid}}', ctx)).toEqual(undefinedVariable('uniqueid'));
  });

  it('resolves repeated tokens independently', () => {
    const ctx = context({ executionVariables: { a: '1' } });
    expect(resolveTemplate('{{a}}-{{a}}', ctx)).toEqual([
      variable('a', 'regular', '1'),
      { type: 'text', text: '-' },
      variable('a', 'regular', '1'),
    ]);
  });
});

describe('resolveTemplate: classification', () => {
  it('shows UniqueID as a predefined UNIQUE_ID placeholder', () => {
    expect(onlyVariable('{{UniqueID}}', context())).toEqual(variable('UniqueID', 'predefined', 'UNIQUE_ID', true));
  });

  it('shows Time as a predefined TIMESTAMP placeholder', () => {
    expect(onlyVariable('{{Time}}', context())).toEqual(variable('Time', 'predefined', 'TIMESTAMP', true));
  });

  it('shows ExecutionID as the EXECUTION_ID placeholder, not the id', () => {
    expect(onlyVariable('{{ExecutionID}}', context())).toEqual(variable('ExecutionID', 'predefined', 'EXECUTION_ID', true));
    expect(onlyVariable('{{ExecutionID}}', context({ executionId: '' }))).toEqual(
      variable('ExecutionID', 'predefined', 'EXECUTION_ID', true),
    );
  });

  it('shows CreatedAt as the CREATED_AT placeholder, with or without created_at', () => {
    for (const createdAt of ['2024-05-01T10:00:00Z', undefined, '']) {
      expect(onlyVariable('{{CreatedAt}}', context({ createdAt }))).toEqual(
        variable('CreatedAt', 'predefined', 'CREATED_AT', true),
      );
    }
  });

  it('shows a captured runtime variable with its value', () => {
    const ctx = context({ runtimeVariables: { orderId: 'A-1' } });
    expect(onlyVariable('{{orderId}}', ctx)).toEqual(variable('orderId', 'runtime', 'A-1'));
  });

  it('shows RepeatIndex and RepeatTotal from the row as REPEAT_INDEX / REPEAT_TOTAL placeholders', () => {
    const row = { RepeatIndex: 2, RepeatTotal: '5' };
    expect(onlyVariable('{{RepeatIndex}}', context(), row)).toEqual(
      variable('RepeatIndex', 'predefined', 'REPEAT_INDEX', true),
    );
    expect(onlyVariable('{{RepeatTotal}}', context(), row)).toEqual(
      variable('RepeatTotal', 'predefined', 'REPEAT_TOTAL', true),
    );
  });

  it('classifies RepeatIndex without row variables as undefined', () => {
    expect(onlyVariable('{{RepeatIndex}}', context())).toEqual(undefinedVariable('RepeatIndex'));
  });

  it('shows other row variables (dataset columns) as regular, converting numbers to strings', () => {
    const row = { email: 'a@b.c', age: 30 };
    expect(onlyVariable('{{email}}', context(), row)).toEqual(variable('email', 'regular', 'a@b.c'));
    expect(onlyVariable('{{age}}', context(), row)).toEqual(variable('age', 'regular', '30'));
  });

  it('shows an execution variable as regular', () => {
    const ctx = context({ executionVariables: { baseUrl: 'https://example.com' } });
    expect(onlyVariable('{{baseUrl}}', ctx)).toEqual(variable('baseUrl', 'regular', 'https://example.com'));
  });

  it('shows a not-yet-captured runtime variable as a runtime placeholder with its name', () => {
    const ctx = context({ pendingRuntimeNames: new Set(['token']) });
    expect(onlyVariable('{{token}}', ctx)).toEqual(variable('token', 'runtime', 'token', true));
  });

  it('classifies an unknown name as undefined with the UNDEFINED_VALUE placeholder', () => {
    expect(onlyVariable('{{prodcut}}', context())).toEqual(undefinedVariable('prodcut'));
  });

  it('does not resolve names inherited from Object.prototype', () => {
    expect(onlyVariable('{{toString}}', context())).toEqual(undefinedVariable('toString'));
    expect(onlyVariable('{{constructor}}', context(), {})).toEqual(undefinedVariable('constructor'));
  });

  it('treats an empty-string value as resolved, flagged as an EMPTY_VALUE placeholder of its kind', () => {
    expect(onlyVariable('{{a}}', context({ runtimeVariables: { a: '' } }))).toEqual(
      variable('a', 'runtime', 'EMPTY_VALUE', true),
    );
    expect(onlyVariable('{{a}}', context(), { a: '' })).toEqual(variable('a', 'regular', 'EMPTY_VALUE', true));
    expect(onlyVariable('{{a}}', context({ executionVariables: { a: '' } }))).toEqual(
      variable('a', 'regular', 'EMPTY_VALUE', true),
    );
  });

  it('does not flag whitespace-only values as empty', () => {
    expect(onlyVariable('{{a}}', context({ executionVariables: { a: ' ' } }))).toEqual(variable('a', 'regular', ' '));
  });
});

describe('resolveTemplate: precedence', () => {
  it('runtime beats row beats execution variables', () => {
    const all = context({ runtimeVariables: { x: 'runtime' }, executionVariables: { x: 'regular' } });
    expect(onlyVariable('{{x}}', all, { x: 'row' })).toEqual(variable('x', 'runtime', 'runtime'));

    const noRuntime = context({ executionVariables: { x: 'regular' } });
    expect(onlyVariable('{{x}}', noRuntime, { x: 'row' })).toEqual(variable('x', 'regular', 'row'));
  });

  it('built-ins beat a runtime variable, row variable and execution variable of the same name', () => {
    const ctx = context({
      runtimeVariables: { ExecutionID: 'r', UniqueID: 'r', Time: 'r', CreatedAt: 'r' },
      executionVariables: { ExecutionID: 'e', UniqueID: 'e', Time: 'e', CreatedAt: 'e' },
    });
    const row = { ExecutionID: 'w', UniqueID: 'w', Time: 'w', CreatedAt: 'w' };
    expect(onlyVariable('{{ExecutionID}}', ctx, row)).toEqual(variable('ExecutionID', 'predefined', 'EXECUTION_ID', true));
    expect(onlyVariable('{{UniqueID}}', ctx, row)).toEqual(variable('UniqueID', 'predefined', 'UNIQUE_ID', true));
    expect(onlyVariable('{{Time}}', ctx, row)).toEqual(variable('Time', 'predefined', 'TIMESTAMP', true));
    expect(onlyVariable('{{CreatedAt}}', ctx, row)).toEqual(variable('CreatedAt', 'predefined', 'CREATED_AT', true));
  });

  it('a captured runtime variable beats a row RepeatIndex of the same name', () => {
    const ctx = context({ runtimeVariables: { RepeatIndex: '9' } });
    expect(onlyVariable('{{RepeatIndex}}', ctx, { RepeatIndex: 1 })).toEqual(variable('RepeatIndex', 'runtime', '9'));
  });

  it('a defined value beats a pending runtime name', () => {
    const pending = new Set(['x']);
    expect(onlyVariable('{{x}}', context({ pendingRuntimeNames: pending }), { x: 'row' })).toEqual(
      variable('x', 'regular', 'row'),
    );
    expect(
      onlyVariable('{{x}}', context({ pendingRuntimeNames: pending, executionVariables: { x: 'regular' } })),
    ).toEqual(variable('x', 'regular', 'regular'));
  });
});

describe('buildVariableContext', () => {
  const response = (overrides: Partial<ExecutionVariablesResponse> = {}): ExecutionVariablesResponse => ({
    variables: [],
    runtime_variables: [],
    execution_variables: {},
    ...overrides,
  });

  it('maps the execution and the /variables response', () => {
    const ctx = buildVariableContext(
      { sk: 'EXECUTION#ignored', execution_id: 'exec-1', created_at: '2024-01-01T00:00:00Z' },
      response({
        variables: [{ key: 'current', value: 'not used' }],
        runtime_variables: [
          { key: 'orderId', value: 'A-1' },
          { key: 'token', value: 'abc' },
        ],
        execution_variables: { product: 'Shoes' },
      }),
      [{ capture_variable: 'orderId' }, { capture_variable: 'later' }, { instruction: 'no capture' }],
    );
    expect(ctx).toEqual({
      executionId: 'exec-1',
      createdAt: '2024-01-01T00:00:00Z',
      executionVariables: { product: 'Shoes' },
      runtimeVariables: { orderId: 'A-1', token: 'abc' },
      pendingRuntimeNames: new Set(['later']),
    });
  });

  it('derives the execution id from sk when execution_id is missing', () => {
    expect(buildVariableContext({ sk: 'EXECUTION#exec-2' }, null, []).executionId).toBe('exec-2');
    expect(buildVariableContext({ sk: 'exec-3' }, null, []).executionId).toBe('exec-3');
    expect(buildVariableContext({ execution_id: '', sk: 'EXECUTION#exec-4' }, null, []).executionId).toBe('exec-4');
  });

  it('uses an empty execution id and no createdAt when the execution is missing', () => {
    for (const execution of [null, undefined, {}]) {
      const ctx = buildVariableContext(execution, undefined, []);
      expect(ctx.executionId).toBe('');
      expect(ctx.createdAt).toBeUndefined();
    }
  });

  it('treats a missing response as empty', () => {
    for (const variables of [null, undefined]) {
      const ctx = buildVariableContext({ execution_id: 'e' }, variables, [{ capture_variable: 'later' }]);
      expect(ctx.executionVariables).toEqual({});
      expect(ctx.runtimeVariables).toEqual({});
      expect(ctx.pendingRuntimeNames).toEqual(new Set(['later']));
    }
  });

  it('treats missing response fields as empty', () => {
    const partial = {} as ExecutionVariablesResponse;
    const ctx = buildVariableContext({ execution_id: 'e' }, partial, []);
    expect(ctx.executionVariables).toEqual({});
    expect(ctx.runtimeVariables).toEqual({});
    expect(ctx.pendingRuntimeNames).toEqual(new Set());
  });

  it('keeps the last value when a runtime key repeats', () => {
    const ctx = buildVariableContext(
      null,
      response({ runtime_variables: [{ key: 'a', value: '1' }, { key: 'a', value: '2' }] }),
      [],
    );
    expect(ctx.runtimeVariables).toEqual({ a: '2' });
  });

  it('converts non-string values to strings', () => {
    const ctx = buildVariableContext(
      null,
      {
        variables: [],
        runtime_variables: [{ key: 'n', value: 7 as unknown as string }],
        execution_variables: { m: 3 as unknown as string },
      },
      [],
    );
    expect(ctx.runtimeVariables).toEqual({ n: '7' });
    expect(ctx.executionVariables).toEqual({ m: '3' });
  });

  it('ignores steps without a usable capture_variable', () => {
    const ctx = buildVariableContext(null, null, [
      {},
      { capture_variable: '' },
      { capture_variable: null },
      { capture_variable: 42 },
      null,
      { capture_variable: 'ok' },
      { capture_variable: 'ok' },
    ]);
    expect(ctx.pendingRuntimeNames).toEqual(new Set(['ok']));
  });

  it('a captured runtime name is not pending', () => {
    const ctx = buildVariableContext(null, response({ runtime_variables: [{ key: 'done', value: '' }] }), [
      { capture_variable: 'done' },
    ]);
    expect(ctx.pendingRuntimeNames).toEqual(new Set());
    expect(onlyVariable('{{done}}', ctx)).toEqual(variable('done', 'runtime', 'EMPTY_VALUE', true));
  });
});
