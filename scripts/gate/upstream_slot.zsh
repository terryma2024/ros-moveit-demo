# Source this file: `upstream_slot <run-dir> <package>` returns when this caller may start a ctest of <package>.
# A ctest tag has minute resolution (Testing/<YYYYmmdd-HHMM>/Test.xml, named by Testing/TAG) and colcon test-result reads only the newest, so
# two ctest runs of one package started within the same minute would write the same Test.xml. Starts of one package are serialised and at least
# UPSTREAM_SLOT_GAP_S (default 75) seconds apart; packages do not wait for each other.
zmodload zsh/datetime zsh/zselect
upstream_slot() {
  local run=$1 pkg=$2 gap=${UPSTREAM_SLOT_GAP_S:-75} lock stamp last now
  lock=$run/slot-$pkg.lock; stamp=$run/slot-$pkg.last
  until mkdir $lock 2>/dev/null; do zselect -t 20; done
  last=$(cat $stamp 2>/dev/null); now=$EPOCHSECONDS
  [[ -n $last ]] && (( now - last < gap )) && zselect -t $(( (gap - (now - last)) * 100 ))
  print -r -- $EPOCHSECONDS > $stamp
  rmdir $lock
}
