# Source this file, then call `so101_load_host [name]`.
# Loads scripts/gate/hosts/<name>.env into the environment. Name order: the argument, $GATE_HOST,
# then the `hostname` match against HOST_NAMES of the hosts/*.env files. An unknown host is
# refused (return 2); nothing is guessed. A variable that is already set in the environment keeps
# its value, so a caller can override any host value for one run.
_SO101_GATE_DIR=${${(%):-%x}:A:h}

so101_load_host() {
  setopt localoptions extendedglob
  local name=${1:-${GATE_HOST:-}} dir=$_SO101_GATE_DIR/hosts file line key hn names n
  if [[ -z $name ]]; then
    hn=${${(L)$(hostname)}%%.*}
    for file in $dir/*.env(N); do
      names=$(sed -n 's/^HOST_NAMES=//p' $file | tr -d "\"'")
      for n in ${=names}; do
        [[ $n == $hn ]] && name=${file:t:r}
      done
    done
    [[ -n $name ]] || { print -u2 "unknown host: hostname '$hn' matches no hosts/*.env (use --host <name>)"; return 2; }
  fi
  [[ $name == [a-z0-9-]## && -r $dir/$name.env ]] || { print -u2 "unknown host: '$name' (no $dir/$name.env)"; return 2; }
  while IFS= read -r line; do
    [[ -z $line || $line == \#* ]] && continue
    key=${line%%=*}
    [[ $key == [A-Z][A-Z0-9_]# ]] || { print -u2 "bad line in $dir/$name.env: $line"; return 2; }
    [[ -v $key ]] || eval "export $line"
  done < $dir/$name.env
  export GATE_HOST=$name
}
