#!/usr/bin/env bash
#
# deploy.sh — stage all changes, generate a commit message with an LLM, commit, and push.
#
# Usage:
#   ./deploy.sh [-y] [remote] [branch]
#
#   -y        Skip the confirmation prompt (non-interactive).
#   remote    Git remote to push to (default: origin).
#   branch    Branch to push (default: current branch).
#
# Requires: git, and the `claude` CLI on PATH for message generation.

set -euo pipefail

# --- args -------------------------------------------------------------------
ASSUME_YES=0
if [[ "${1:-}" == "-y" ]]; then
    ASSUME_YES=1
    shift
fi

REMOTE="${1:-origin}"
BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"

# --- sanity checks ----------------------------------------------------------
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "error: not inside a git repository" >&2
    exit 1
}

# Move to repo root so paths are consistent.
cd "$(git rev-parse --show-toplevel)"

# Stage everything (including deletions).
git add -A

# Nothing to commit? Bail out gracefully.
if git diff --cached --quiet; then
    echo "Nothing to commit — working tree clean."
    exit 0
fi

# --- generate commit message with the LLM -----------------------------------
DIFF="$(git diff --cached)"
STAT="$(git diff --cached --stat)"

PROMPT="You are writing a git commit message. Output ONLY the commit message itself,
no preamble, no code fences, no explanation. Use the Conventional Commits style:
a concise <=72 char subject line (type: summary), then a blank line, then a short
body of bullet points describing the key changes. Base it on this staged diff.

Files changed:
${STAT}

Diff:
${DIFF}"

echo "Generating commit message with Claude..." >&2

MSG="$(printf '%s' "$PROMPT" | claude -p 2>/dev/null || true)"

# Fallback if the LLM is unavailable or returns nothing.
if [[ -z "${MSG// }" ]]; then
    echo "warning: LLM produced no message; falling back to a generic message." >&2
    MSG="chore: update $(echo "$STAT" | tail -1 | xargs)"
fi

# --- confirm ----------------------------------------------------------------
echo
echo "----- commit message -----"
echo "$MSG"
echo "--------------------------"
echo "Push target: $REMOTE/$BRANCH"
echo

if [[ "$ASSUME_YES" -ne 1 ]]; then
    read -r -p "Commit and push? [y/N] " reply
    case "$reply" in
        [yY] | [yY][eE][sS]) ;;
        *)
            echo "Aborted. Changes remain staged."
            exit 1
            ;;
    esac
fi

# --- commit & push ----------------------------------------------------------
git commit -m "$MSG"
git push "$REMOTE" "$BRANCH"

echo "Done."
