#!/usr/bin/env bash
# Bump version in pyproject.toml + README, commit, tag, push.
# GitHub Actions (publish.yml) then builds + publishes to PyPI via OIDC.
#
# Usage:
#   scripts/release.sh 0.1.0a4
#   scripts/release.sh 0.1.0          # stable release
#   scripts/release.sh 0.1.0a4 --dry-run
#
set -euo pipefail

# ---- args -----------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "usage: $0 <new-version> [--dry-run]" >&2
    echo "example: $0 0.1.0a4" >&2
    exit 1
fi

NEW="$1"
DRY_RUN=0
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

# Validate PEP 440 version (basic): N.N.N[aN|bN|rcN]
if ! [[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+([ab]|rc)?[0-9]*$ ]]; then
    echo "✗ '$NEW' doesn't look like a PEP 440 version (e.g. 0.1.0, 0.1.0a4, 1.0.0rc1)" >&2
    exit 1
fi

cd "$(git rev-parse --show-toplevel)"

# ---- preflight ------------------------------------------------------------
echo "→ release target: v$NEW"

# Working tree must be clean (apart from the files we're about to edit)
if [[ -n "$(git status --porcelain)" ]]; then
    echo "✗ working tree is dirty. commit or stash first:" >&2
    git status --short >&2
    exit 1
fi

# Must be on main (or pass --force; keeping simple for now)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "✗ not on main (current: $BRANCH). switch with: git checkout main" >&2
    exit 1
fi

# Tag must not already exist
if git rev-parse "v$NEW" >/dev/null 2>&1; then
    echo "✗ tag v$NEW already exists locally" >&2
    exit 1
fi
if git ls-remote --tags origin "refs/tags/v$NEW" | grep -q .; then
    echo "✗ tag v$NEW already exists on origin" >&2
    exit 1
fi

# Local must be in sync with origin
git fetch --quiet origin main
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)
if [[ "$LOCAL" != "$REMOTE" ]]; then
    echo "✗ local main is not in sync with origin/main. pull/push first." >&2
    exit 1
fi

# Tests must pass (skip in dry-run if you want — kept on for safety)
if command -v pytest >/dev/null 2>&1; then
    echo "→ running tests..."
    python -m pytest -q --tb=line || {
        echo "✗ tests failed. fix before releasing." >&2
        exit 1
    }
else
    echo "⚠ pytest not on PATH — skipping test gate"
fi

# ---- bump -----------------------------------------------------------------
echo "→ bumping pyproject.toml and README.md to $NEW"

# pyproject.toml: version = "..."
sed -i.bak -E "s/^version = \"[^\"]+\"/version = \"$NEW\"/" pyproject.toml
rm -f pyproject.toml.bak

# README.md: > **Status:** early alpha (`X`)
sed -i.bak -E "s/early alpha \(\`[^\`]+\`\)/early alpha (\`$NEW\`)/" README.md
rm -f README.md.bak

echo "→ diff:"
git --no-pager diff --stat
git --no-pager diff pyproject.toml README.md | head -20

# ---- dry-run exit ---------------------------------------------------------
if [[ $DRY_RUN -eq 1 ]]; then
    echo ""
    echo "✓ dry-run complete. reverting changes."
    git checkout -- pyproject.toml README.md
    exit 0
fi

# ---- commit + tag + push --------------------------------------------------
echo ""
read -p "→ commit and push v$NEW? [y/N] " yn
if [[ "$yn" != "y" && "$yn" != "Y" ]]; then
    echo "aborted. reverting changes."
    git checkout -- pyproject.toml README.md
    exit 1
fi

git add pyproject.toml README.md
git commit -m "release: $NEW"
git tag "v$NEW"
git push origin main
git push origin "v$NEW"

echo ""
echo "✓ pushed v$NEW"
echo "→ watch: https://github.com/kinginsun/pkflow/actions"
echo "→ approve at: https://github.com/kinginsun/pkflow/deployments"
echo "→ result:    https://pypi.org/project/pkflow/$NEW/"
