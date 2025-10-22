# Release Process

This document describes how to create a new release of Nova Act QA Studio.

## Prerequisites

- Clean git working directory (no uncommitted changes)
- All tests passing
- Up-to-date with remote main branch
- Node.js and npm installed
- Go 1.22+ installed (for Lambda builds)

## Release Types

- **Patch** (`1.0.0` → `1.0.1`): Bug fixes, minor updates
- **Minor** (`1.0.0` → `1.1.0`): New features, backwards compatible
- **Major** (`1.0.0` → `2.0.0`): Breaking changes
- **Prerelease** (`1.0.0` → `1.0.1-beta.0`): Beta/RC versions

## Creating a Release

### 1. Prepare for Release

```bash
# Ensure you're on main branch
git checkout main
git pull

# Ensure working directory is clean
git status

# Run tests
make test_all
```

### 2. Create the Release

```bash
# For a patch release (most common)
npm run release:patch

# For a minor release (new features)
npm run release:minor

# For a major release (breaking changes)
npm run release:major

# For a pre-release (testing)
npm run release:prerelease
```

### 3. What Happens Automatically

The release script will:

1. ✅ Check git status (must be clean)
2. ✅ Bump version in `package.json`
3. ✅ Generate `CHANGELOG.md` from git commits
4. ✅ Build Lambda functions (ARM64)
5. ✅ Build frontend (production)
6. ✅ Compile CDK TypeScript
7. ✅ Create release zip in `/release/` directory
8. ✅ Commit version bump and changelog
9. ✅ Create git tag (e.g., `v1.2.3`)
10. ✅ Push commits and tags to remote
11. ✅ Clean up build artifacts

### 4. Post-Release Steps

1. **Verify the release**:
   ```bash
   # Check the release archive
   ls -lh release/
   
   # Verify git tag
   git tag -l
   ```

2. **Create GitHub Release** (manual):
   - Go to GitHub → Releases → Draft a new release
   - Select the tag (e.g., `v1.2.3`)
   - Copy changelog entry from `CHANGELOG.md`
   - Upload the release zip from `/release/` directory
   - Publish release

3. **Announce the release**:
   - Update documentation if needed
   - Notify users/team

## Commit Message Format

For best changelog generation, use conventional commits:

```
feat: Add user management API
fix: Resolve CORS issue with CloudFront
docs: Update deployment instructions
perf: Optimize Lambda cold starts
refactor: Simplify authentication flow
test: Add integration tests for API
chore: Update dependencies
```

Format: `type(scope): message`

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `perf`: Performance improvement
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

## Release Archive Contents

The generated `nova-act-qa-studio-vX.Y.Z.zip` contains:

```
nova-act-qa-studio-v1.2.3/
├── lambdas/              # Pre-built Lambda functions
├── frontend/             # Built React application
├── worker/               # Worker source + Dockerfile
├── lib/                  # Compiled CDK code
├── bin/                  # Compiled CDK code
├── scripts/              # Deployment scripts
├── package.json          # With version
├── configuration.json.sample
├── CHANGELOG.md
├── README.md
└── LICENSE
```

## Troubleshooting

### Release fails with "Git working directory is not clean"

```bash
# Check what's uncommitted
git status

# Commit or stash changes
git add .
git commit -m "chore: prepare for release"
```

### Release fails during build

```bash
# Clean and try again
npm run clean:lambdas
rm -rf frontend/dist
npm run release:patch
```

### Need to undo a release

```bash
# Delete local tag
git tag -d v1.2.3

# Delete remote tag
git push origin :refs/tags/v1.2.3

# Revert commit
git revert HEAD
```

### Testing a release without pushing

Modify `scripts/release.js` and comment out the `pushToRemote()` call temporarily.

## Best Practices

1. **Test before releasing**: Always run tests before creating a release
2. **Use conventional commits**: Helps generate meaningful changelogs
3. **Review changelog**: Check `CHANGELOG.md` after generation
4. **Test the archive**: Extract and test the release zip before publishing
5. **Document breaking changes**: Clearly note breaking changes in commit messages
6. **Keep releases small**: Frequent small releases are better than large ones

## Questions?

See [CONTRIBUTING.md](CONTRIBUTING.md) for more information.
