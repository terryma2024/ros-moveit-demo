#!/usr/bin/env zsh
# Manual entry for the so101_teleop web front end tests. Not part of the gate.
#   run_web_tests.zsh [--e2e] [--install] [--dry-run]
# Default: the unit tests (`vitest run`). --e2e adds the Playwright tests (`test:e2e`, needs the Playwright browsers installed on
# this host). --install runs `bun install --frozen-lockfile` first (otherwise a missing node_modules is an error).
# --dry-run prints the commands and runs nothing. bun is $BUN_BIN, else the host env file's BUN_BIN, else `bun` on PATH.
set -o pipefail
FG=${0:A:h}
WEB=${FG:h:h}/src/so101_teleop/web
e2e=0 install=0 dry=0
for a in "$@"; do
  case $a in
    --e2e) e2e=1 ;;
    --install) install=1 ;;
    --dry-run) dry=1 ;;
    -h|--help) sed -n '2,7p' $0 | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) print -u2 "run_web_tests: unknown argument $a"; exit 2 ;;
  esac
done
if [[ -z $BUN_BIN ]]; then
  if source $FG/load_host.zsh 2>/dev/null && so101_load_host 2>/dev/null; then :; fi
  BUN_BIN=${BUN_BIN:-$(command -v bun)}
fi
[[ -n $BUN_BIN && ( $dry == 1 || -x $BUN_BIN ) ]] || { print -u2 "run_web_tests: no bun (set BUN_BIN)"; exit 3 }
[[ -d $WEB ]] || { print -u2 "run_web_tests: no web directory $WEB"; exit 3 }
cmds=()
(( install )) && cmds+=("install --frozen-lockfile")
[[ $dry == 1 || $install == 1 || -d $WEB/node_modules ]] || { print -u2 "run_web_tests: $WEB/node_modules is missing (use --install)"; exit 4 }
cmds+=("run test")
(( e2e )) && cmds+=("run test:e2e")
cd $WEB || exit 3
rc=0
for c in $cmds; do
  print -r -- "+ $BUN_BIN ${=c}"
  (( dry )) && continue
  $BUN_BIN ${=c} || { rc=$?; print -u2 "run_web_tests: '${=c}' failed (rc=$rc)"; break }
done
exit $rc
