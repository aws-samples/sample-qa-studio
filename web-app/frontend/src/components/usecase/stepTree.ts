/**
 * Pure helpers for the one-level step tree used by the step editors.
 *
 * Storage is flat: every step has a global `sort`; a child of a `repeat`
 * step carries `parent_step_id`. The editor keeps a repeat's children
 * contiguous directly after it (an invariant of the editor, not of the
 * storage). These helpers group a flat list into blocks, flatten blocks
 * back into a renumbered list, and implement block-aware reordering.
 */

export interface TreeStep {
  sk: string;
  id?: string;
  sort: number;
  step_type?: string;
  parent_step_id?: string | null;
  instruction?: string;
  repeat_columns?: string[];
  repeat_rows?: string[][];
  /** Repeat steps: application dataset reference, exclusive with the inline fields. */
  dataset_id?: string | null;
}

/** A top-level step with its children (empty for non-repeat steps). */
export interface StepBlock<T extends TreeStep = TreeStep> {
  head: T;
  children: T[];
  /** True when `head` has a parent_step_id that does not resolve to a repeat. */
  orphan: boolean;
}

function stepIdOf(step: TreeStep): string {
  return step.id ?? step.sk.replace(/^STEP#/, '');
}

function isRepeatStep(step: TreeStep | undefined | null): boolean {
  return step?.step_type === 'repeat';
}

/**
 * Group a flat step list into ordered blocks. Children are attached to
 * their repeat in `sort` order; a child whose parent is missing or not a
 * repeat becomes its own top-level block flagged `orphan`.
 */
export function groupStepsByParent<T extends TreeStep>(steps: T[]): StepBlock<T>[] {
  const ordered = [...steps].sort((a, b) => a.sort - b.sort);
  const repeatsById = new Map<string, T>();
  for (const step of ordered) {
    if (isRepeatStep(step)) repeatsById.set(stepIdOf(step), step);
  }
  const childrenByParent = new Map<string, T[]>();
  const blocks: StepBlock<T>[] = [];
  for (const step of ordered) {
    const parentId = step.parent_step_id || undefined;
    if (parentId && repeatsById.has(parentId) && !isRepeatStep(step)) {
      const list = childrenByParent.get(parentId) ?? [];
      list.push(step);
      childrenByParent.set(parentId, list);
      continue;
    }
    blocks.push({ head: step, children: [], orphan: Boolean(parentId) });
  }
  for (const block of blocks) {
    if (isRepeatStep(block.head)) {
      block.children = childrenByParent.get(stepIdOf(block.head)) ?? [];
    }
  }
  return blocks;
}

/** Flatten blocks back into one list, renumbering `sort` 1..n. */
export function flattenBlocks<T extends TreeStep>(blocks: StepBlock<T>[]): T[] {
  const flat: T[] = [];
  for (const block of blocks) {
    flat.push(block.head, ...block.children);
  }
  return flat.map((step, index) => ({ ...step, sort: index + 1 }));
}

/** Steps in display order (heads followed by their children). */
export function orderStepsByTree<T extends TreeStep>(steps: T[]): T[] {
  return groupStepsByParent(steps).flatMap((block) => [block.head, ...block.children]);
}

/** Sort position a new child should take: right after the block of `repeat`. */
export function blockEndPosition(steps: TreeStep[], repeatSk: string): number {
  const block = groupStepsByParent(steps).find((b) => b.head.sk === repeatSk);
  if (!block) return steps.length + 1;
  const last = block.children.length > 0 ? block.children[block.children.length - 1] : block.head;
  return last.sort + 1;
}

/** Children of the repeat identified by `repeatSk`. */
export function childrenOf<T extends TreeStep>(steps: T[], repeatSk: string): T[] {
  return groupStepsByParent(steps).find((b) => b.head.sk === repeatSk)?.children ?? [];
}

function locate<T extends TreeStep>(blocks: StepBlock<T>[], sk: string): { blockIndex: number; childIndex: number } | null {
  for (let blockIndex = 0; blockIndex < blocks.length; blockIndex += 1) {
    if (blocks[blockIndex].head.sk === sk) return { blockIndex, childIndex: -1 };
    const childIndex = blocks[blockIndex].children.findIndex((c) => c.sk === sk);
    if (childIndex !== -1) return { blockIndex, childIndex };
  }
  return null;
}

function arrayMove<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/**
 * Block-aware reorder: move the item `fromSk` onto the slot of `toSk`.
 *
 * - A top-level step (a repeat with all its children, or a plain step)
 *   moves as one block; dropping onto a child lands the block before or
 *   after that child's whole block (never inside it).
 * - A child moves only within its own block; dropping it anywhere else is
 *   rejected.
 *
 * Returns the new flat list renumbered 1..n, or `null` when the move is
 * rejected (callers treat `null` as a no-op so the drag snaps back).
 */
export function reorderStepTree<T extends TreeStep>(steps: T[], fromSk: string, toSk: string): T[] | null {
  if (fromSk === toSk) return null;
  const blocks = groupStepsByParent(steps);
  const from = locate(blocks, fromSk);
  const to = locate(blocks, toSk);
  if (!from || !to) return null;

  if (from.childIndex === -1) {
    // Whole-block move. Dropping onto a child targets that child's block.
    if (from.blockIndex === to.blockIndex) return null;
    return flattenBlocks(arrayMove(blocks, from.blockIndex, to.blockIndex));
  }

  // Child move: only within the same block, onto another child.
  if (to.blockIndex !== from.blockIndex || to.childIndex === -1) return null;
  const block = blocks[from.blockIndex];
  const nextBlocks = [...blocks];
  nextBlocks[from.blockIndex] = {
    ...block,
    children: arrayMove(block.children, from.childIndex, to.childIndex),
  };
  return flattenBlocks(nextBlocks);
}
