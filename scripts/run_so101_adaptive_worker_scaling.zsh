#!/usr/bin/env zsh
set -euo pipefail

typeset worker_counts=""
typeset evidence_root=""
integer dry_run=0
integer index=1

while (( index <= $# )); do
  typeset argument="${@[$index]}"
  case "$argument" in
    --worker-counts)
      (( index += 1 ))
      (( index <= $# )) || { print -u2 "missing --worker-counts value"; exit 2; }
      worker_counts="${@[$index]}"
      ;;
    --evidence-root)
      (( index += 1 ))
      (( index <= $# )) || { print -u2 "missing --evidence-root value"; exit 2; }
      evidence_root="${@[$index]}"
      ;;
    --dry-run)
      dry_run=1
      ;;
    *)
      print -u2 "unknown argument: $argument"
      exit 2
      ;;
  esac
  (( index += 1 ))
done

[[ -n "$worker_counts" ]] || { print -u2 "--worker-counts is required"; exit 2; }
[[ "$evidence_root" == /* ]] || { print -u2 "--evidence-root must be absolute"; exit 2; }
[[ "$evidence_root" == "${evidence_root:A}" ]] || {
  print -u2 "--evidence-root must be normalized"
  exit 2
}

typeset -a counts
counts=(${(s:,:)worker_counts})
(( ${#counts} > 0 )) || { print -u2 "--worker-counts must not be empty"; exit 2; }
typeset -A seen
typeset count
for count in $counts; do
  [[ "$count" == <-> ]] || { print -u2 "invalid Worker count: $count"; exit 2; }
  (( count == 1 || count == 2 || count == 4 || count == 6 || count == 8 )) || {
    print -u2 "unsupported Worker count: $count"
    exit 2
  }
  [[ -z "${seen[$count]:-}" ]] || { print -u2 "duplicate Worker count: $count"; exit 2; }
  seen[$count]=1
done

typeset script_dir="${0:A:h}"
typeset repo_root="${script_dir:h}"
typeset points="$repo_root/src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml"
typeset config="$repo_root/src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml"
typeset adaptive_config="$repo_root/src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml"
typeset yolo_weights="/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt"
typeset grounded_root="/data/work/so101-models/grounded-sam-v2-scipy-lock"
typeset -A batch_ids=(1 wx101 2 wx201 4 wx401 6 wx601 8 wx801)

function batch_command() {
  typeset requested_count="$1"
  typeset batch_id="${batch_ids[$requested_count]}"
  reply=(
    scripts/run_so101_adaptive_batch.zsh
    --adaptive-workers
    --points "$points"
    --config "$config"
    --adaptive-config "$adaptive_config"
    --batch-id "$batch_id"
    --evidence-root "$evidence_root"
    --worker-count "$requested_count"
    --initial-points-per-worker 3
    --worker-start-timeout-s 120
    --max-infra-attempts-per-point 5
    --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
    --yolo-weights "$yolo_weights"
    --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
    --grounded-root "$grounded_root"
    --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
    --run-mode execute
  )
}

if (( dry_run )); then
  for count in $counts; do
    typeset -a command
    batch_command "$count"
    command=($reply)
    print -r -- "${(j: :)command}"
  done
  exit 0
fi

typeset reports_root="$evidence_root/reports"
typeset summary="$reports_root/worker-scaling-summary.json"
[[ ! -e "$summary" ]] || { print -u2 "summary already exists: $summary"; exit 2; }
mkdir -p "$reports_root"
typeset -a fragments

for count in $counts; do
  typeset batch_id="${batch_ids[$count]}"
  typeset runtime_root="$evidence_root/r/$batch_id"
  typeset timing="$reports_root/worker-scaling-$batch_id.time"
  typeset console="$reports_root/worker-scaling-$batch_id.log"
  typeset fragment="$reports_root/worker-scaling-$batch_id.json"
  [[ ! -e "$runtime_root" ]] || { print -u2 "runtime root already exists: $runtime_root"; exit 2; }
  [[ ! -e "$timing" && ! -e "$console" && ! -e "$fragment" ]] || {
    print -u2 "run report already exists for $batch_id"
    exit 2
  }

  typeset -a command
  batch_command "$count"
  command=($reply)
  integer exit_code=0
  /usr/bin/time -p -o "$timing" "${command[@]}" > "$console" 2>&1 || exit_code=$?

  typeset aggregate="$runtime_root/aggregate_results.json"
  typeset cleanup="$runtime_root/cleanup-receipt.json"
  [[ -f "$aggregate" && -f "$cleanup" ]] || {
    print -u2 "missing aggregate or cleanup receipt for $batch_id"
    exit 1
  }
  [[ $(jq -r '.cleanup_complete' "$cleanup") == true ]] || {
    print -u2 "cleanup incomplete for $batch_id"
    exit 1
  }
  typeset owned
  for owned in "$runtime_root"/p/*/owned-processes.json; do
    [[ $(jq -r '.processes | length' "$owned") -eq 0 ]] || {
      print -u2 "owned processes remain for $batch_id"
      exit 1
    }
  done

  typeset elapsed_s
  elapsed_s=$(awk '$1 == "real" {print $2}' "$timing")
  typeset batch_status
  batch_status=$(jq -r '.status' "$aggregate")
  integer point_passed
  point_passed=$(jq '[.point_statuses[] | select(. == "PASSED")] | length' "$aggregate")
  integer point_failed
  point_failed=$(jq '[.point_statuses[] | select(. != "PASSED")] | length' "$aggregate")
  typeset levels_json
  levels_json=$(jq -c '.levels_used' "$aggregate")
  typeset expected_levels="[$count]"
  typeset valid=false
  if (( exit_code == 0 && point_passed == 20 && point_failed == 0 )) \
    && [[ "$batch_status" == COMPLETED ]] \
    && [[ "$levels_json" == "$expected_levels" ]] \
    && [[ $(jq -r '.batch_cleanup_complete' "$aggregate") == true ]]; then
    valid=true
  fi

  jq -n \
    --argjson requested_worker_count "$count" \
    --argjson levels_used "$levels_json" \
    --argjson elapsed_s "$elapsed_s" \
    --argjson point_passed "$point_passed" \
    --argjson point_failed "$point_failed" \
    --argjson valid_performance_sample "$valid" \
    --argjson exit_code "$exit_code" \
    --arg batch_id "$batch_id" \
    '{
      requested_worker_count: $requested_worker_count,
      batch_id: $batch_id,
      levels_used: $levels_used,
      elapsed_s: $elapsed_s,
      point_passed: $point_passed,
      point_failed: $point_failed,
      valid_performance_sample: $valid_performance_sample,
      exit_code: $exit_code
    }' > "$fragment"
  fragments+=("$fragment")
done

typeset w1_elapsed
w1_elapsed=$(jq -r 'select(.requested_worker_count == 1 and .valid_performance_sample) | .elapsed_s' $fragments)
jq -s --argjson w1_elapsed "${w1_elapsed:-null}" '
  {
    baseline_worker_count: 1,
    runs: map(. + {
      speedup_vs_w1: (
        if .valid_performance_sample and $w1_elapsed != null
        then ($w1_elapsed / .elapsed_s)
        else null
        end
      )
    })
  }
' $fragments > "$summary"
jq . "$summary"
