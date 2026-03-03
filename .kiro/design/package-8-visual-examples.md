# Package 8: Visual Examples

## Cache Badge Display

### Navigation Step WITH Cache
```
┌─────┬──────────────┬────────────────────────────────────────┐
│ Step│ Type         │ Details                                │
├─────┼──────────────┼────────────────────────────────────────┤
│  1  │ Navigation   │ Click login button                     │
│     │ ✓ Cached     │ Cached 2 hours ago                     │
└─────┴──────────────┴────────────────────────────────────────┘
```

### Navigation Step WITHOUT Cache
```
┌─────┬──────────────┬────────────────────────────────────────┐
│ Step│ Type         │ Details                                │
├─────┼──────────────┼────────────────────────────────────────┤
│  2  │ Navigation   │ Type username                          │
│     │              │                                        │
└─────┴──────────────┴────────────────────────────────────────┘
```

### Non-Navigation Step (No Cache Badge)
```
┌─────┬──────────────┬────────────────────────────────────────┐
│ Step│ Type         │ Details                                │
├─────┼──────────────┼────────────────────────────────────────┤
│  3  │ Validation   │ Verify login successful                │
│     │              │ Validation: Text contains "Welcome"    │
└─────┴──────────────┴────────────────────────────────────────┘
```

## Badge Styling

### Cache Badge
- **Color**: Green (`color="green"`)
- **Icon**: Checkmark (`<Icon name="check" />`)
- **Text**: "Cached"
- **Size**: Standard Cloudscape badge size
- **Position**: Stacked below step type badge

### Cache Age Text
- **Font Size**: 12px (small)
- **Color**: #5f6b7a (gray)
- **Style**: Italic
- **Format**: "Cached {relative_time}"

## Relative Time Examples

| Time Difference | Display Text          |
|----------------|-----------------------|
| < 1 minute     | "Cached just now"     |
| 1 minute       | "Cached 1 minute ago" |
| 5 minutes      | "Cached 5 minutes ago"|
| 1 hour         | "Cached 1 hour ago"   |
| 3 hours        | "Cached 3 hours ago"  |
| 1 day          | "Cached 1 day ago"    |
| 5 days         | "Cached 5 days ago"   |

## Component Hierarchy

```
StepsTable
├── Table
│   ├── Column: Step (sort number)
│   ├── Column: Type
│   │   └── SpaceBetween (vertical)
│   │       ├── Badge (step type)
│   │       └── Badge (cache indicator) ← NEW
│   │           └── Icon (checkmark) ← NEW
│   ├── Column: Details
│   │   └── div
│   │       ├── div (instruction)
│   │       ├── div (step-specific details)
│   │       └── div (cache age) ← NEW
│   ├── Column: Reorder
│   └── Column: Actions
```

## Code Example

### Before (Original)
```tsx
{ 
  id: 'type', 
  header: 'Type', 
  cell: item => getStepTypeBadge(item.step_type),
}
```

### After (With Cache Indicator)
```tsx
{ 
  id: 'type', 
  header: 'Type', 
  cell: item => getStepTypeBadge(item),  // Pass full item
}

// Function now returns:
<SpaceBetween direction="vertical" size="xxs">
  <Badge className="step">Navigation</Badge>
  {isNavigation && hasCachedSteps && (
    <Badge color="green">
      <Icon name="check" /> Cached
    </Badge>
  )}
</SpaceBetween>
```

## Data Flow

```
Backend (DynamoDB)
  ↓
  STEP record with cached_steps & cache_last_updated
  ↓
API (list_steps.py)
  ↓
  Returns steps with cache fields (snake_case)
  ↓
Frontend (StepsTable.tsx)
  ↓
  Renders cache badge + age for navigation steps
```

## Conditional Rendering Logic

```typescript
const hasCachedSteps = item.cached_steps && item.cached_steps !== 'null';
const isNavigation = !item.step_type || item.step_type === 'navigation';

// Show badge if:
// 1. Step is navigation type
// 2. cached_steps field exists and is not null
if (isNavigation && hasCachedSteps) {
  // Show cache badge
}
```

## Testing Scenarios

### Test 1: Navigation Step with Cache
```typescript
{
  step_type: 'navigation',
  cached_steps: '[{"type":"click","bbox":{...}}]',
  cache_last_updated: '2026-03-03T10:00:00Z'
}
// Expected: Shows "Cached" badge + age
```

### Test 2: Navigation Step without Cache
```typescript
{
  step_type: 'navigation',
  cached_steps: null,
  cache_last_updated: null
}
// Expected: No cache badge
```

### Test 3: Validation Step with Cache (Edge Case)
```typescript
{
  step_type: 'validation',
  cached_steps: '[{"type":"click"}]',  // Should never happen
  cache_last_updated: '2026-03-03T10:00:00Z'
}
// Expected: No cache badge (validation steps can't be cached)
```

### Test 4: Recent Cache
```typescript
{
  step_type: 'navigation',
  cached_steps: '[{"type":"click"}]',
  cache_last_updated: new Date(Date.now() - 10000).toISOString()  // 10 seconds ago
}
// Expected: Shows "Cached just now"
```

### Test 5: Old Cache
```typescript
{
  step_type: 'navigation',
  cached_steps: '[{"type":"click"}]',
  cache_last_updated: '2026-03-01T10:00:00Z'  // 2 days ago
}
// Expected: Shows "Cached 2 days ago"
```
