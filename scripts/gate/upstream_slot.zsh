# Source this file: `upstream_slot <run-dir> <package>` returns when this caller may start a ctest of <package>.
# A ctest tag has minute resolution (Testing/<YYYYmmdd-HHMM>/Test.xml, named by Testing/TAG) and colcon test-result reads only the newest, so
# two ctest runs of one package started within the same minute would write the same Test.xml. Starts of one package are serialised and at least
# in different tag minutes; packages do not wait for each other. A ctest is up to UPSTREAM_SLOT_MARGIN_S (default 15) seconds late after its slot
# (colcon start-up), so the next start waits for the first minute boundary after last+margin: at most 60+margin s, on average about half of that.
# UPSTREAM_SLOT_GAP_S (if set) selects the old rule instead: a fixed gap of that many seconds. Times are whole-minute aligned in every time zone
# this gate runs in (the tag is local time).
zmodload zsh/datetime zsh/zselect
# upstream_slot_delay <last start> <now>: seconds to wait before the next start of the same package may begin.
upstream_slot_delay() {
  local last=$1 now=$2
  if [[ -n ${UPSTREAM_SLOT_GAP_S:-} ]]; then
    (( now - last < UPSTREAM_SLOT_GAP_S )) && print -r -- $(( UPSTREAM_SLOT_GAP_S - (now - last) )) || print 0
  else
    local boundary=$(( ((last + ${UPSTREAM_SLOT_MARGIN_S:-15}) / 60 + 1) * 60 ))
    (( now < boundary )) && print -r -- $(( boundary - now )) || print 0
  fi
}
upstream_slot() {
  local run=$1 pkg=$2 lock stamp last now wait_s
  lock=$run/slot-$pkg.lock; stamp=$run/slot-$pkg.last
  until mkdir $lock 2>/dev/null; do zselect -t 20; done
  last=$(cat $stamp 2>/dev/null); now=$EPOCHSECONDS
  if [[ -n $last ]]; then
    wait_s=$(upstream_slot_delay $last $now)
    (( wait_s > 0 )) && zselect -t $(( wait_s * 100 ))
  fi
  print -r -- $EPOCHSECONDS > $stamp
  rmdir $lock
}
