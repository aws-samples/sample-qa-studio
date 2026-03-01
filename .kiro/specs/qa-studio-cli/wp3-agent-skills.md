# WP3: Agent Skills

## Objective

Create Agent Skills for Kiro IDE integration that guide Kiro on using the QA Studio CLI.

## Duration

Week 3-4 (7-10 days)

## Requirements

### 1. Skills Directory Structure

**Create:**
```
qa-studio-cli/skills/
├── qa-studio-tests/
│   ├── SKILL.md
│   └── reference/
│       ├── step-types.md
│       ├── validation-operators.md
│       └── manual-creation.md
└── qa-studio-suites/
    └── SKILL.md
```

### 2. qa-studio-tests Skill

**File: `skills/qa-studio-tests/SKILL.md`**

**YAML Frontmatter:**
```yaml
---
name: qa-studio-tests
description: Create and manage QA Studio UI tests. Use when developer asks to create tests, mentions testing/QA, or wants to verify functionality. Supports AI-generated tests from user journeys and manual step-by-step creation.
---
```

**Content Structure:**
1. Prerequisites (check auth with `qa-studio status`)
2. Creating Tests
   - AI-Generated (recommended) - using `qa-studio tests create --from-journey`
   - Manual Creation - link to reference/manual-creation.md
3. Executing Tests Locally
   - `qa-studio run` with base URL override
   - Variable overrides
   - Common patterns
4. Managing Tests
   - List, get, delete commands
5. Step Types - link to reference/step-types.md
6. Validation Operators - link to reference/validation-operators.md

**Key Principles:**
- Concise main file (under 500 lines)
- Progressive disclosure (reference files for details)
- Third-person description
- Assume Claude is smart (don't over-explain)
- Include concrete examples

**Example Section:**
```markdown
## Creating Tests

### AI-Generated (Recommended)

Generate complete tests from natural language:

```bash
qa-studio tests create --from-journey \
  --title "Login Flow" \
  --url "https://app.com/login" \
  --journey "User enters credentials, clicks login, verifies dashboard" \
  --region us-east-1
```

**When to use:**
- Developer describes what to test
- Creating new test from scratch
- Testing complete user flow

**Tips for good user journeys:**
- Be specific about actions (click, type, select)
- Include expected outcomes (verify, check)
- Mention element descriptions

### Manual Creation

For step-by-step control, see [reference/manual-creation.md](reference/manual-creation.md)
```

### 3. Reference Files

**File: `skills/qa-studio-tests/reference/step-types.md`**

Complete guide on all 7 step types:
- navigation - Click buttons, fill forms
- url - Navigate to URL
- secret - Use stored credentials
- validation - Check page values
- retrieve_value - Capture values into variables
- assertion - Compare captured variables
- download - Download files

**For each type include:**
- Description
- Required fields
- Examples with actual commands
- When to use

**File: `skills/qa-studio-tests/reference/validation-operators.md`**

Complete operator reference:
- String operators: exact, exact_case_insensitive, contains, contains_case_insensitive, not_equal
- Number operators: equals, less_then, greater_then, greater_or_equal_then, less_or_equal_then
- Boolean operators: exact

**Include examples for each operator**

**File: `skills/qa-studio-tests/reference/manual-creation.md`**

Step-by-step guide for manual test creation:
1. Create blank test
2. Add steps one by one
3. Configure variables and secrets
4. Test locally

### 4. qa-studio-suites Skill

**File: `skills/qa-studio-suites/SKILL.md`**

**YAML Frontmatter:**
```yaml
---
name: qa-studio-suites
description: Manage QA Studio test suites. Use when developer wants to group tests, run multiple tests together, or organize test collections.
---
```

**Content Structure:**
1. Prerequisites
2. Creating Suites
3. Adding Tests to Suite
4. Executing Suites
5. Managing Suites

**Keep concise** - suites are simpler than tests, no need for reference files

### 5. Skills Installation Commands

**Modify: `qa-studio-cli/src/cli.py`**

**Add commands:**

#### `qa-studio setup`
```python
@cli.command()
def setup():
    """Setup QA Studio skills for Kiro IDE."""
    kiro_skills_dir = Path.home() / '.kiro' / 'skills'
    package_skills = Path(__file__).parent.parent / 'skills'
    
    # Check if Kiro directory exists
    if not (Path.home() / '.kiro').exists():
        click.echo("⚠️  Kiro IDE not detected (~/.kiro/ not found)")
        click.echo("   Install Kiro IDE first, then run this command again")
        return
    
    # Create skills directory
    kiro_skills_dir.mkdir(parents=True, exist_ok=True)
    
    # Create symlinks for each skill
    installed = []
    for skill_dir in package_skills.iterdir():
        if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
            link = kiro_skills_dir / skill_dir.name
            
            if link.exists():
                if link.is_symlink():
                    click.echo(f"✓ {skill_dir.name} already installed")
                else:
                    click.echo(f"⚠️  {skill_dir.name} exists but is not a symlink")
                continue
            
            try:
                link.symlink_to(skill_dir)
                installed.append(skill_dir.name)
                click.echo(f"✓ Installed {skill_dir.name}")
            except OSError as e:
                click.echo(f"✗ Failed to install {skill_dir.name}: {e}")
    
    if installed:
        click.echo(f"\n✓ Installed {len(installed)} skill(s) to ~/.kiro/skills/")
        click.echo("\nNext steps:")
        click.echo("  1. Run 'qa-studio login' to authenticate")
        click.echo("  2. Use Kiro IDE to create and run tests")
    else:
        click.echo("\n✓ All skills already installed")
```

#### `qa-studio uninstall`
```python
@cli.command()
def uninstall():
    """Remove QA Studio skills from Kiro IDE."""
    kiro_skills_dir = Path.home() / '.kiro' / 'skills'
    package_skills = Path(__file__).parent.parent / 'skills'
    
    removed = []
    for skill_dir in package_skills.iterdir():
        if skill_dir.is_dir():
            link = kiro_skills_dir / skill_dir.name
            if link.is_symlink():
                link.unlink()
                removed.append(skill_dir.name)
                click.echo(f"✓ Removed {skill_dir.name}")
    
    if removed:
        click.echo(f"\n✓ Removed {len(removed)} skill(s)")
    else:
        click.echo("No skills to remove")
```

**Update `qa-studio status` to show skills:**
```python
@cli.command()
def status():
    """Show authentication and skills status."""
    # ... existing auth check ...
    
    # Check skills
    kiro_skills_dir = Path.home() / '.kiro' / 'skills'
    package_skills = Path(__file__).parent.parent / 'skills'
    
    if not kiro_skills_dir.exists():
        click.echo("✗ Kiro skills directory not found")
        click.echo("  Run 'qa-studio setup' to install skills")
        return
    
    click.echo("\nSkills:")
    for skill_dir in package_skills.iterdir():
        if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
            link = kiro_skills_dir / skill_dir.name
            if link.exists() and link.is_symlink():
                click.echo(f"  ✓ {skill_dir.name}")
            else:
                click.echo(f"  ✗ {skill_dir.name} (not installed)")
    
    if any(not (kiro_skills_dir / sd.name).exists() for sd in package_skills.iterdir()):
        click.echo("\nRun 'qa-studio setup' to install missing skills")
```

## Agent Skills Best Practices

Follow these principles from Anthropic's Agent Skills documentation:

### 1. Concise is Key
- Keep SKILL.md under 500 lines
- Assume Claude is smart - don't over-explain
- Only add context Claude doesn't already have

### 2. Progressive Disclosure
- Main SKILL.md is overview
- Reference files for detailed content
- Claude reads only what's needed

### 3. Clear Descriptions
- Write in third person
- Include what the skill does AND when to use it
- Be specific with key terms

### 4. Consistent Naming
- Use gerund form: `qa-studio-tests`, `qa-studio-suites`
- Lowercase letters, numbers, hyphens only
- No reserved words

### 5. Examples Over Explanations
- Show concrete examples
- Include input/output pairs
- Use real commands

### 6. One Level Deep
- Reference files link directly from SKILL.md
- Avoid nested references
- Keep navigation simple

## Testing

### Manual Testing with Kiro

```bash
# Install skills
qa-studio setup

# Verify symlinks created
ls -la ~/.kiro/skills/

# Test with Kiro IDE
kiro chat

# In Kiro chat:
> "Create a test for the login flow"
# Kiro should load qa-studio-tests skill and use it

> "Run the test against localhost"
# Kiro should call qa-studio run with --base-url

> "Create a test suite with these tests"
# Kiro should load qa-studio-suites skill
```

### Validation Checklist

**SKILL.md Quality:**
- [ ] YAML frontmatter valid (name, description)
- [ ] Description in third person
- [ ] Description includes what AND when
- [ ] Main content under 500 lines
- [ ] Examples are concrete
- [ ] References are one level deep
- [ ] No Windows-style paths

**Progressive Disclosure:**
- [ ] Main SKILL.md is concise overview
- [ ] Detailed content in reference files
- [ ] Clear links to reference files
- [ ] Reference files have table of contents (if >100 lines)

**Kiro Integration:**
- [ ] Skills discoverable by Kiro
- [ ] Skills reference correct CLI commands
- [ ] Examples match actual CLI syntax
- [ ] Error handling guidance included

## Success Criteria

- ✅ `qa-studio setup` creates symlinks in `~/.kiro/skills/`
- ✅ Skills follow Agent Skills best practices
- ✅ Skills use progressive disclosure effectively
- ✅ SKILL.md files under 500 lines
- ✅ Reference files well-organized
- ✅ Kiro can discover and use skills
- ✅ Skills reference CLI commands correctly
- ✅ Examples are concrete and accurate
- ✅ `qa-studio uninstall` removes symlinks cleanly
- ✅ `qa-studio status` shows skills status

## Dependencies

- Package 2 (Runner integration working)

## Deliverable

Working skills that Kiro can use:
```bash
qa-studio setup
kiro chat
> "Create a test for login"
# Kiro uses qa-studio-tests skill
```

## Next Steps

After completion, proceed to Package 4 (API Wrapper Commands) to add test management commands.
