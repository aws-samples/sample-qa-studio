#!/bin/bash
# Build a lightweight Chrome extension zip for deployment.
#
# Strategy: exclusion-based packaging (like .dockerignore / .npmignore).
# Instead of listing every runtime file explicitly (which breaks when new
# files are added), we copy everything into a staging directory and exclude
# known non-runtime patterns. Then we validate the output against
# manifest.json to catch missing files early.
#
# Usage: ./build-extension.sh [output_path]
#   output_path  - Optional. Defaults to ../nova-act-recorder.zip
#
# Requirements:
#   - jq (for manifest.json parsing and validation)
#   - zip
#
# Size constraint: AgentCore browser requires extensions < 10MB.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="${1:-${SCRIPT_DIR}/../nova-act-recorder.zip}"
OUTPUT="$(cd "$(dirname "$OUTPUT")" && pwd)/$(basename "$OUTPUT")"
DIST_DIR="${SCRIPT_DIR}/.dist"

MAX_SIZE_BYTES=10485760  # 10MB AgentCore limit

echo "Building Nova Act Recorder extension..."

# ── Clean staging directory ───────────────────────────────────────────
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# ── Copy files using exclusion patterns ───────────────────────────────
# rsync exclusion list — mirrors the .gitignore + dev-only artifacts.
# New runtime .js/.html/.css files are automatically included.
rsync -a \
  --exclude='node_modules/' \
  --exclude='.dist/' \
  --exclude='test/' \
  --exclude='.git/' \
  --exclude='.kiro/' \
  --exclude='.vscode/' \
  --exclude='*.test.js' \
  --exclude='*.spec.js' \
  --exclude='*.md' \
  --exclude='*.log' \
  --exclude='.gitignore' \
  --exclude='.DS_Store' \
  --exclude='package.json' \
  --exclude='package-lock.json' \
  --exclude='eslint.config.js' \
  --exclude='vitest.config.js' \
  --exclude='build-extension.sh' \
  --exclude='.eslintrc*' \
  --exclude='.prettierrc*' \
  --exclude='tsconfig*.json' \
  --exclude='icons/*.svg' \
  "$SCRIPT_DIR/" "$DIST_DIR/"

# ── Validate manifest.json exists ─────────────────────────────────────
MANIFEST="$DIST_DIR/manifest.json"
if [ ! -f "$MANIFEST" ]; then
  echo "ERROR: manifest.json not found in staging directory." >&2
  exit 1
fi

# ── Validate all manifest-referenced files exist ──────────────────────
MISSING=0

validate_file() {
  local file="$1"
  local context="$2"
  if [ ! -f "$DIST_DIR/$file" ]; then
    echo "ERROR: manifest.json ($context) references '$file' but it is missing from build." >&2
    MISSING=$((MISSING + 1))
  fi
}

# Service worker / background script
BG_SCRIPT=$(jq -r '.background.service_worker // empty' "$MANIFEST")
if [ -n "$BG_SCRIPT" ]; then
  validate_file "$BG_SCRIPT" "background.service_worker"
fi

# Content scripts
CONTENT_SCRIPTS=$(jq -r '.content_scripts[]?.js[]? // empty' "$MANIFEST")
for file in $CONTENT_SCRIPTS; do
  validate_file "$file" "content_scripts.js"
done

# Content script CSS
CONTENT_CSS=$(jq -r '.content_scripts[]?.css[]? // empty' "$MANIFEST")
for file in $CONTENT_CSS; do
  validate_file "$file" "content_scripts.css"
done

# Side panel / popup pages
for key in '.side_panel.default_path' '.action.default_popup' '.browser_action.default_popup'; do
  PAGE=$(jq -r "$key // empty" "$MANIFEST")
  if [ -n "$PAGE" ]; then
    validate_file "$PAGE" "$key"
  fi
done

# Icons
ICONS=$(jq -r '.icons // {} | values[]' "$MANIFEST")
for file in $ICONS; do
  validate_file "$file" "icons"
done

# Web accessible resources
WAR_FILES=$(jq -r '.web_accessible_resources[]?.resources[]? // empty' "$MANIFEST")
for file in $WAR_FILES; do
  validate_file "$file" "web_accessible_resources"
done

if [ "$MISSING" -gt 0 ]; then
  echo "ERROR: $MISSING file(s) referenced in manifest.json are missing. Build aborted." >&2
  rm -rf "$DIST_DIR"
  exit 1
fi

# ── List staged files ─────────────────────────────────────────────────
echo "Staged files:"
(cd "$DIST_DIR" && find . -type f | sort | sed 's|^\./|  |')

# ── Create zip ────────────────────────────────────────────────────────
rm -f "$OUTPUT"
(cd "$DIST_DIR" && zip -r -q "$OUTPUT" .)

SIZE=$(wc -c < "$OUTPUT" | tr -d ' ')
SIZE_KB=$((SIZE / 1024))

echo "Created: $OUTPUT (${SIZE_KB}KB)"

if [ "$SIZE" -gt "$MAX_SIZE_BYTES" ]; then
  echo "ERROR: Zip is ${SIZE_KB}KB — exceeds 10MB AgentCore limit." >&2
  rm -rf "$DIST_DIR"
  exit 1
fi

# ── Cleanup ───────────────────────────────────────────────────────────
rm -rf "$DIST_DIR"
echo "Done."
