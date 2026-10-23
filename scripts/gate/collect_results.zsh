#!/usr/bin/env zsh
# usage: collect_results.zsh <evidence gate dir> <build root>
# Copies the result files (not the trees) of the test-run.* and demo-run.* directories of the build root into the evidence gate dir
# under the same names: regular files down to depth 2 (junit.xml, logs, rc/elapsed files, part summaries). colcon-log-* directories
# and the build/install/log trees stay in the build root. Nothing is deleted from the build root.
set -o pipefail
G=${1:?evidence gate dir}; GB=${2:?build root}
test -d $G && test -d $GB || exit 90
rc=0
for d in $GB/test-run.*(N/) $GB/demo-run.*(N/); do
  name=${d:t}
  mkdir -p $G/$name || { rc=1; continue }
  find $d -maxdepth 3 -type f -not -path '*/colcon-log-*' -printf '%P\n' | while IFS= read -r rel; do
    mkdir -p $G/$name/${rel:h}
    cp -p -- $d/$rel $G/$name/$rel || rc=1
  done
  print "collected $name files=$(find $G/$name -type f | wc -l) bytes=$(du -sb $G/$name | cut -f1)"
done
exit $rc
