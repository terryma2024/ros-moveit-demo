#!/usr/bin/env zsh
# Record what a built so101-campaign-shard-deps image holds, for the repository: every installed apt package with its version
# (dpkg-query -W) and the venv's pip set (pip freeze --all). The files are a record, not build inputs; the image itself is pinned by ID.
# usage: record_deps_installed.zsh IMAGE_ID_OR_TAG
set -o pipefail
IMG=${1:?usage: record_deps_installed.zsh IMAGE_ID_OR_TAG}
D=${0:A:h}
docker run --rm --network none --entrypoint dpkg-query $IMG -W | LC_ALL=C sort > $D/shard-deps-apt-installed.tsv || exit 1
docker run --rm --network none --entrypoint /act/venv/bin/python $IMG -m pip freeze --all | LC_ALL=C sort > $D/shard-deps-pip-installed.txt || exit 1
print "apt $(wc -l < $D/shard-deps-apt-installed.tsv) packages, pip $(wc -l < $D/shard-deps-pip-installed.txt) distributions recorded"
