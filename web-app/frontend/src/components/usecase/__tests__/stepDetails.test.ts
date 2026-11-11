import { describe, it, expect } from 'vitest';
import { hasExpectation, stepDetailLines } from '../stepDetails';

describe('stepDetailLines', () => {
  it('navigation and unknown types have no detail lines', () => {
    expect(stepDetailLines({ step_type: 'navigation' })).toEqual([]);
    expect(stepDetailLines({})).toEqual([]);
    expect(stepDetailLines({ step_type: 'download' })).toEqual([]);
  });

  it('repeat describes the dataset', () => {
    expect(
      stepDetailLines({ step_type: 'repeat', repeat_columns: ['email', 'role'], repeat_rows: [['a', 'b'], ['c', 'd']] }),
    ).toEqual(['2 rows · email, role']);
  });

  it('repeat with dataset_id names the application dataset instead of counting inline rows', () => {
    const datasets = [
      { dataset_id: 'ds-1', name: 'customers', description: '', column_count: 3, row_count: 5, updated_at: '' },
      { dataset_id: 'ds-2', name: 'leads', description: '', column_count: 1, row_count: 1, updated_at: '' },
    ];
    expect(stepDetailLines({ step_type: 'repeat', dataset_id: 'ds-1' }, datasets)).toEqual([
      'Application dataset: customers · 5 rows · 3 columns',
    ]);
    // Unknown id (or no list passed): never "0 rows".
    expect(stepDetailLines({ step_type: 'repeat', dataset_id: 'ds-9' }, datasets)).toEqual(['Application dataset (not loaded)']);
    expect(stepDetailLines({ step_type: 'repeat', dataset_id: 'ds-1' })).toEqual(['Application dataset (not loaded)']);
  });

  it('secret names the key, if set', () => {
    expect(stepDetailLines({ step_type: 'secret', secret_key: 'password' })).toEqual(['Secret: password']);
    expect(stepDetailLines({ step_type: 'secret' })).toEqual([]);
  });

  it.each([
    ['bool', 'equals', 'true', 'Validation: Boolean expects True'],
    ['bool', 'equals', 'false', 'Validation: Boolean expects False'],
    ['string', 'contains', 'Welcome', 'Validation: Text contains "Welcome"'],
    ['number', 'greater_then', '3', 'Validation: Number is greater than 3'],
  ])('validation %s %s %s', (validation_type, validation_operator, validation_value, expected) => {
    expect(stepDetailLines({ step_type: 'validation', validation_type, validation_operator, validation_value })).toEqual([
      expected,
    ]);
  });

  it('assertion uses the Assertion prefix', () => {
    expect(
      stepDetailLines({ step_type: 'assertion', validation_type: 'string', validation_operator: 'not_equal', validation_value: 'ok' }),
    ).toEqual(['Assertion: Text does not equal "ok"']);
  });

  it('validation without a known type has no line', () => {
    expect(stepDetailLines({ step_type: 'validation' })).toEqual([]);
    expect(stepDetailLines({ step_type: 'assertion', validation_type: 'regex' })).toEqual([]);
  });

  it('retrieve_value names the captured variable', () => {
    expect(stepDetailLines({ step_type: 'retrieve_value', capture_variable: 'order_id' })).toEqual([
      'Captures variable: order_id',
    ]);
  });

  it('browser lists the action and known args', () => {
    expect(
      stepDetailLines({ step_type: 'browser', browser_action: 'reload', browser_args: '{"hard": true}' }),
    ).toEqual(['Action: reload', 'Hard reload']);
    expect(
      stepDetailLines({ step_type: 'browser', browser_action: 'goto', browser_args: '{"url": "https://example.com"}' }),
    ).toEqual(['Action: goto', 'URL: https://example.com']);
    expect(stepDetailLines({ step_type: 'browser', browser_action: 'back', browser_args: 'not json' })).toEqual([
      'Action: back',
    ]);
  });

  it('transform lists the operation and target variable', () => {
    expect(stepDetailLines({ step_type: 'transform', transform_operation: 'uppercase', capture_variable: 'name' })).toEqual([
      'Operation: uppercase',
      '→ {{ name }}',
    ]);
    expect(stepDetailLines({ step_type: 'transform', transform_operation: 'trim' })).toEqual(['Operation: trim']);
  });

  it('network_assertion summarises the matcher', () => {
    expect(
      stepDetailLines({
        step_type: 'network_assertion',
        network_method: 'POST',
        network_url_pattern: '/api/orders',
        network_request_body: '{}',
        network_mock_response: '{}',
        network_mock_passthrough: true,
        network_response_status: 201,
        network_response_body: '{}',
      }),
    ).toEqual(['Network: POST /api/orders · req body (exact) · passthrough mock · resp 201 · resp body (subset)']);
    expect(stepDetailLines({ step_type: 'network_assertion', network_url_pattern: '/x', network_response_status: 0 })).toEqual([
      'Network: any /x · resp 0',
    ]);
    expect(stepDetailLines({ step_type: 'network_assertion' })).toEqual([]);
  });
});

describe('hasExpectation', () => {
  it('is true for bool, string and number only', () => {
    expect(hasExpectation({ validation_type: 'bool' })).toBe(true);
    expect(hasExpectation({ validation_type: 'string' })).toBe(true);
    expect(hasExpectation({ validation_type: 'number' })).toBe(true);
    expect(hasExpectation({ validation_type: 'regex' })).toBe(false);
    expect(hasExpectation({})).toBe(false);
  });
});
