#!/usr/bin/env zsh
set -euo pipefail

typeset evidence_root=""
typeset batch_id=""
integer evidence_count=0
integer batch_count=0
integer index=1

while (( index <= $# )); do
  typeset argument="${@[$index]}"
  case "$argument" in
    --evidence-root)
      (( index += 1 ))
      (( index <= $# )) || { print -u2 "missing --evidence-root value"; exit 2; }
      evidence_root="${@[$index]}"
      (( evidence_count += 1 ))
      ;;
    --batch-id)
      (( index += 1 ))
      (( index <= $# )) || { print -u2 "missing --batch-id value"; exit 2; }
      batch_id="${@[$index]}"
      (( batch_count += 1 ))
      ;;
    --evidence-root=*|--batch-id=*)
      print -u2 "use separate --evidence-root and --batch-id arguments"
      exit 2
      ;;
  esac
  (( index += 1 ))
done

(( evidence_count == 1 )) || { print -u2 "exactly one --evidence-root is required"; exit 2; }
(( batch_count == 1 )) || { print -u2 "exactly one --batch-id is required"; exit 2; }
[[ "$evidence_root" == /* ]] || { print -u2 "--evidence-root must be absolute"; exit 2; }
typeset normalized_root="${evidence_root:A}"
[[ "$evidence_root" == "$normalized_root" ]] || {
  print -u2 "--evidence-root must be normalized"
  exit 2
}
[[ "$batch_id" =~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,4}$' ]] || {
  print -u2 "--batch-id must be a 1-5 character ASCII identifier"
  exit 2
}

typeset runtime_root="${evidence_root%/}/r/${batch_id}"
integer runner_pid=0

function forward_signal() {
  typeset signal_name="$1"
  if (( runner_pid > 0 )); then
    kill -s "$signal_name" "$runner_pid" 2>/dev/null || true
  fi
}

trap 'forward_signal INT' INT
trap 'forward_signal TERM' TERM

so101_parallel_batch "$@" &
runner_pid=$!
integer handshake_attempt=0
while (( handshake_attempt < 1000 )); do
  if [[ -d "$runtime_root" ]]; then
    umask 077
    typeset handshake_tmp="${runtime_root}/.handshake.${$}.tmp"
    print -r -- "{\"schema_version\":1,\"wrapper_pid\":${$},\"runner_pid\":${runner_pid},\"batch_id\":\"${batch_id}\"}" >! "$handshake_tmp"
    mv "$handshake_tmp" "${runtime_root}/handshake.json"
    break
  fi
  typeset runner_state="$(ps -o state= -p "$runner_pid" 2>/dev/null | tr -d '[:space:]')"
  [[ -n "$runner_state" && "$runner_state" != Z* ]] || break
  sleep 0.01
  (( handshake_attempt += 1 ))
done
if [[ ! -f "${runtime_root}/handshake.json" ]]; then
  typeset runner_state="$(ps -o state= -p "$runner_pid" 2>/dev/null | tr -d '[:space:]')"
  if [[ -n "$runner_state" && "$runner_state" != Z* ]]; then
    forward_signal TERM
    wait "$runner_pid" 2>/dev/null || true
    print -u2 "adaptive runner handshake was not established"
    exit 70
  fi
fi
integer runner_code=0
wait "$runner_pid" || runner_code=$?
while (( runner_code > 128 )) && kill -0 "$runner_pid" 2>/dev/null; do
  runner_code=0
  wait "$runner_pid" || runner_code=$?
done

integer cleanup_code=0
so101_parallel_batch_cleanup --runtime-root "$runtime_root" || cleanup_code=$?
if (( cleanup_code != 0 )); then
  exit "$cleanup_code"
fi
exit "$runner_code"
