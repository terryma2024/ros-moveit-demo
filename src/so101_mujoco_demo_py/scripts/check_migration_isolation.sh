#!/usr/bin/env bash
set -euo pipefail

readonly expected_branch="codex/so101-mujoco-ros2"
readonly main_base_commit="d300e7a41fb274d6d7e120699b7040666ea61904"
readonly protected_tree="src/so101_gazebo_"'demo_py'
readonly new_package_tree="src/so101_mujoco_demo_py"
readonly legacy_namespace="so101_gazebo_"'demo_py'
readonly backup_branch="codex/so101-mujoco-ros2-pre-"'isolation-20260810'

fail() {
  printf 'migration isolation check failed: %s\n' "$1" >&2
  exit 1
}

repository_root=$(git rev-parse --show-toplevel 2>/dev/null) ||
  fail "not inside a Git worktree"
cd "$repository_root"

current_branch=$(git branch --show-current)
if [[ "$current_branch" != "$expected_branch" ]]; then
  fail "unexpected branch '$current_branch' (expected '$expected_branch')"
fi

merge_base=$(git merge-base HEAD origin/main 2>/dev/null) ||
  fail "cannot determine main merge-base"
if [[ "$merge_base" != "$main_base_commit" ]]; then
  fail "unexpected main merge-base '$merge_base' (expected '$main_base_commit')"
fi

if ! git diff --quiet "$main_base_commit" -- "$protected_tree"; then
  fail "protected Gazebo tree differs from $main_base_commit"
fi

protected_status=$(git status --short -- "$protected_tree")
if [[ -n "$protected_status" ]]; then
  fail "protected Gazebo tree has worktree changes"
fi

legacy_matches=$(rg -n --no-messages \
  --glob '!**/docs/provenance.json' \
  --glob '!**/__pycache__/**' \
  "$legacy_namespace" "$new_package_tree" || true)
if [[ -n "$legacy_matches" ]]; then
  printf '%s\n' "$legacy_matches" >&2
  fail "new implementation references the legacy Gazebo Python namespace"
fi

backup_documented=false
while IFS= read -r matched_file; do
  [[ -z "$matched_file" ]] && continue
  matched_file=${matched_file#./}
  case "$matched_file" in
    docs/*)
      backup_documented=true
      ;;
    *)
      printf '%s\n' "$matched_file" >&2
      fail "backup branch reference outside documentation"
      ;;
  esac
done < <(
  rg -l --hidden --no-ignore --no-messages \
    --glob '!.git/**' \
    --glob '!**/__pycache__/**' \
    "$backup_branch" . || true
)

if [[ "$backup_documented" != true ]]; then
  fail "backup branch reference missing from documentation"
fi

printf 'migration isolation check passed\n'
