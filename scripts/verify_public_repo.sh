#!/usr/bin/env bash
# Verify no banned paths are tracked or staged for commit.
# See docs/adr/0008-repository-publication-boundaries.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BANNED_FILE="${ROOT}/.github/banned-paths.txt"
FAIL=0

if [[ ! -f "${BANNED_FILE}" ]]; then
  echo "ERROR: missing ${BANNED_FILE}"
  exit 1
fi

has_git() {
  git -C "${ROOT}" rev-parse --git-dir >/dev/null 2>&1
}

# Paths never scanned (tooling caches — covered by .gitignore)
prune_path() {
  case "$1" in
    */.git/*|*/.git|*/.venv/*|*/.mypy_cache/*|*/.pytest_cache/*|*/.ruff_cache/*) return 0 ;;
  esac
  return 1
}

report_banned() {
  local label="$1"
  echo "BANNED (${label}): $2"
  FAIL=1
}

check_tracked_glob() {
  local pattern="$1"
  local matches
  matches="$(git -C "${ROOT}" ls-files --cached -- "${pattern}" 2>/dev/null || true)"
  if [[ -n "${matches}" ]]; then
    echo "${matches}" | while IFS= read -r f; do
      [[ -n "${f}" ]] && report_banned "tracked" "${f}"
    done
  fi
}

check_tracked_exact() {
  local rel="$1"
  if git -C "${ROOT}" ls-files --error-unmatch "${rel}" >/dev/null 2>&1; then
    report_banned "tracked" "${rel}"
  fi
}

check_worktree_glob() {
  local pattern="$1"
  local base
  base="$(basename "${pattern}")"
  [[ "${base}" == "*"* ]] || return 0

  while IFS= read -r -d '' f; do
    prune_path "${f}" && continue
    report_banned "present on disk" "${f#${ROOT}/}"
  done < <(find "${ROOT}" \( -path "${ROOT}/.git" -o -path "${ROOT}/.venv" -o -path "${ROOT}/.mypy_cache" -o -path "${ROOT}/.pytest_cache" -o -path "${ROOT}/.ruff_cache" \) -prune -o -name "${base#\*}" -print0 2>/dev/null)
}

check_worktree_exact() {
  local rel="$1"
  local full="${ROOT}/${rel}"
  if [[ -e "${full}" ]]; then
    report_banned "present on disk" "${rel}"
  fi
}

echo "VALENCE public repository boundary check (ADR-0008)"
echo "---------------------------------------------------"

if has_git; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    if [[ "${line}" == *"*"* || "${line}" == *"?"* ]]; then
      check_tracked_glob "${line}"
    else
      check_tracked_exact "${line}"
    fi
  done < "${BANNED_FILE}"

  for f in "demo.mp4" "advance_demo.mp4" "demo (copy 1).mp4"; do
    check_tracked_exact "${f}"
  done
else
  echo "Note: not a git repo yet — checking working tree for banned root artifacts."
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    if [[ "${line}" == *"*"* || "${line}" == *"?"* ]]; then
      check_worktree_glob "${line}"
    else
      check_worktree_exact "${line}"
    fi
  done < "${BANNED_FILE}"
fi

if [[ "${FAIL}" -eq 1 ]]; then
  echo ""
  if has_git; then
    echo "FAILED: Remove banned files from the git index, e.g.:"
    echo "  git rm --cached <file>"
  else
    echo "FAILED: Banned files exist locally (they will be ignored by .gitignore once you git init)."
    echo "Safe to delete demo media and temp dirs before your first commit."
  fi
  echo "See docs/adr/0008-repository-publication-boundaries.md"
  exit 1
fi

echo "OK: No banned paths detected."
