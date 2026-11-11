import { describe, it, expect } from 'vitest';

import {
  blockEndPosition,
  childrenOf,
  flattenBlocks,
  groupStepsByParent,
  orderStepsByTree,
  reorderStepTree,
} from '../stepTree';

const step = (sk: string, sort: number, extra: Record<string, unknown> = {}) => ({
  sk: `STEP#${sk}`, id: sk, sort, instruction: sk, step_type: 'navigation', ...extra,
});

// a, R1[c1, c2], b, R2[d1], e
const STEPS = [
  step('a', 1),
  step('R1', 2, { step_type: 'repeat', repeat_columns: ['x'], repeat_rows: [['1']] }),
  step('c1', 3, { parent_step_id: 'R1' }),
  step('c2', 4, { parent_step_id: 'R1' }),
  step('b', 5),
  step('R2', 6, { step_type: 'repeat', repeat_columns: ['y'], repeat_rows: [['2']] }),
  step('d1', 7, { parent_step_id: 'R2' }),
  step('e', 8),
];

const order = (steps: { sk: string }[]) => steps.map((s) => s.sk.replace('STEP#', ''));

describe('groupStepsByParent', () => {
  it('groups children under their repeat in sort order', () => {
    const blocks = groupStepsByParent(STEPS);
    expect(blocks.map((b) => [b.head.id, b.children.map((c) => c.id)])).toEqual([
      ['a', []], ['R1', ['c1', 'c2']], ['b', []], ['R2', ['d1']], ['e', []],
    ]);
    expect(blocks.every((b) => !b.orphan)).toBe(true);
  });

  it('tolerates unsorted input', () => {
    const shuffled = [STEPS[3], STEPS[0], STEPS[2], STEPS[1]];
    expect(order(orderStepsByTree(shuffled))).toEqual(['a', 'R1', 'c1', 'c2']);
  });

  it('flags orphans (missing parent or non-repeat parent) as top-level blocks', () => {
    const blocks = groupStepsByParent([
      step('a', 1),
      step('o1', 2, { parent_step_id: 'ghost' }),
      step('o2', 3, { parent_step_id: 'a' }),
    ]);
    expect(blocks.map((b) => [b.head.id, b.orphan])).toEqual([['a', false], ['o1', true], ['o2', true]]);
  });

  it('a repeat without children is an empty block', () => {
    const blocks = groupStepsByParent([step('R', 1, { step_type: 'repeat' })]);
    expect(blocks[0].children).toEqual([]);
  });
});

describe('flattenBlocks / helpers', () => {
  it('renumbers 1..n', () => {
    const flat = flattenBlocks(groupStepsByParent(STEPS));
    expect(flat.map((s) => s.sort)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(order(flat)).toEqual(['a', 'R1', 'c1', 'c2', 'b', 'R2', 'd1', 'e']);
  });

  it('blockEndPosition is right after the last child (or the repeat itself)', () => {
    expect(blockEndPosition(STEPS, 'STEP#R1')).toBe(5);
    expect(blockEndPosition([step('R', 3, { step_type: 'repeat' })], 'STEP#R')).toBe(4);
    expect(blockEndPosition(STEPS, 'STEP#missing')).toBe(9);
  });

  it('childrenOf returns the block children', () => {
    expect(order(childrenOf(STEPS, 'STEP#R1'))).toEqual(['c1', 'c2']);
    expect(childrenOf(STEPS, 'STEP#a')).toEqual([]);
  });
});

describe('reorderStepTree', () => {
  it('moves a repeat with all its children as one block', () => {
    const next = reorderStepTree(STEPS, 'STEP#R1', 'STEP#e');
    expect(order(next!)).toEqual(['a', 'b', 'R2', 'd1', 'e', 'R1', 'c1', 'c2']);
    expect(next!.map((s) => s.sort)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it('moves a plain step before a block when dropped on its head', () => {
    const next = reorderStepTree(STEPS, 'STEP#e', 'STEP#R1');
    expect(order(next!)).toEqual(['a', 'e', 'R1', 'c1', 'c2', 'b', 'R2', 'd1']);
  });

  it('dropping a top-level step onto a child lands around the block, never inside', () => {
    const next = reorderStepTree(STEPS, 'STEP#a', 'STEP#c1');
    expect(order(next!)).toEqual(['R1', 'c1', 'c2', 'a', 'b', 'R2', 'd1', 'e']);
    const back = reorderStepTree(STEPS, 'STEP#e', 'STEP#c2');
    expect(order(back!)).toEqual(['a', 'e', 'R1', 'c1', 'c2', 'b', 'R2', 'd1']);
  });

  it('reorders a child within its block', () => {
    const next = reorderStepTree(STEPS, 'STEP#c2', 'STEP#c1');
    expect(order(next!)).toEqual(['a', 'R1', 'c2', 'c1', 'b', 'R2', 'd1', 'e']);
  });

  it('rejects dragging a child out of its block', () => {
    expect(reorderStepTree(STEPS, 'STEP#c1', 'STEP#b')).toBeNull();
    expect(reorderStepTree(STEPS, 'STEP#c1', 'STEP#d1')).toBeNull();
    expect(reorderStepTree(STEPS, 'STEP#c1', 'STEP#R1')).toBeNull();
  });

  it('rejects no-op moves and unknown ids', () => {
    expect(reorderStepTree(STEPS, 'STEP#a', 'STEP#a')).toBeNull();
    expect(reorderStepTree(STEPS, 'STEP#a', 'STEP#nope')).toBeNull();
    expect(reorderStepTree(STEPS, 'STEP#R1', 'STEP#c1')).toBeNull();
  });

  it('children always follow their parent in the result', () => {
    const targets = STEPS.map((s) => s.sk);
    for (const from of targets) {
      for (const to of targets) {
        const next = reorderStepTree(STEPS, from, to);
        if (!next) continue;
        const ids = order(next);
        const r1 = ids.indexOf('R1');
        expect(new Set(ids.slice(r1 + 1, r1 + 3))).toEqual(new Set(['c1', 'c2']));
        expect(ids.indexOf('d1')).toBe(ids.indexOf('R2') + 1);
        expect(next.map((s) => s.sort)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
      }
    }
  });
});
