#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s RELAY_EXECUTABLE\n' "$0" >&2
  exit 2
fi

relay_executable="$1"
partition="attachment_relay_test_$$"
event_topic="/test/$$/attachment_event"
state_topic="/test/$$/attachment_state"
detach_topic="/test/$$/detach"
log_dir="$(mktemp -d)"
relay_pid=""
cleanup() {
  if [[ -n "${relay_pid}" ]]; then
    kill -TERM "${relay_pid}" 2>/dev/null || true
    wait "${relay_pid}" 2>/dev/null || true
  fi
  rm -rf "${log_dir}"
}
trap cleanup EXIT INT TERM
export GZ_PARTITION="${partition}"

start_relay() {
  local enforce="$1"
  local log_file="$2"
  "${relay_executable}" --ros-args \
    -p event_topic:="${event_topic}" -p state_topic:="${state_topic}" \
    -p detach_topic:="${detach_topic}" \
    -p enforce_initially_detached:="${enforce}" \
    -p publish_period_seconds:=0.02 >"${log_file}" 2>&1 &
  relay_pid=$!
  for _ in {1..30}; do
    grep -q 'initial state remains unknown' "${log_file}" && return 0
    sleep 0.1
  done
  printf 'relay did not become ready\n' >&2
  return 1
}

capture_state() {
  local expected="$1"
  local output="$2"
  timeout 3 gz topic -e -t "${state_topic}" -n 1 >"${output}"
  grep -Eq "data: *\"?${expected}\"?" "${output}"
}

start_relay true "${log_dir}/enforcing_relay.log"
if timeout 0.3 gz topic -e -t "${state_topic}" -n 1 \
  >"${log_dir}/unexpected_initial.txt"
then
  printf 'relay published a guessed initial state\n' >&2
  exit 1
fi
timeout 3 gz topic -e -t "${detach_topic}" -n 1 \
  >"${log_dir}/initial_detach_command.txt" &
detach_subscriber_pid=$!
wait "${detach_subscriber_pid}"
if timeout 0.3 gz topic -e -t "${state_topic}" -n 1 \
  >"${log_dir}/unexpected_attached.txt"
then
  printf 'relay published state before initial detach was confirmed\n' >&2
  exit 1
fi
gz topic -t "${event_topic}" -m gz.msgs.StringMsg -p 'data: "detached"'
sleep 0.1
capture_state detached "${log_dir}/enforced_detached.txt"
kill -TERM "${relay_pid}"
wait "${relay_pid}" 2>/dev/null || true
relay_pid=""

event_topic="/test/$$/attachment_event_non_enforcing"
state_topic="/test/$$/attachment_state_non_enforcing"
detach_topic="/test/$$/detach_non_enforcing"
start_relay false "${log_dir}/relay.log"
gz topic -t "${event_topic}" -m gz.msgs.StringMsg -p 'data: "attached"'
sleep 0.1
capture_state attached "${log_dir}/attached.txt"

gz topic -t "${event_topic}" -m gz.msgs.StringMsg -p 'data: "invalid"'
sleep 0.1
capture_state attached "${log_dir}/invalid_ignored.txt"
grep -q 'Ignoring invalid attachment event' "${log_dir}/relay.log"

gz topic -t "${event_topic}" -m gz.msgs.StringMsg -p 'data: "detached"'
sleep 0.1
capture_state detached "${log_dir}/detached.txt"

printf 'PASS: attachment relay publishes durable validated state\n'
