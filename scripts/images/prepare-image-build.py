"""Retain a new tracked source snapshot and exact Docker build invocation."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess

# Run from the worktree to build (it reads `git ls-files` of the current directory). Host paths come from the arguments;
# their defaults are the host values (scripts/gate/hosts/<host>.env, loaded by scripts/gate/load_host.zsh).
parser=argparse.ArgumentParser()
parser.add_argument('--role',choices=('inference','shard-deps','shard','mount-base'),default='inference')
parser.add_argument('--no-cache',action='store_true',help='docker build --no-cache: every layer is built again (the determinism acceptance builds twice this way)')
parser.add_argument('--pin-shard-deps',default=None,help='sha256 image ID of the so101-campaign-shard-deps base when base-image-ids.json has none yet (a new base is pinned there once it is built and transferred)')
parser.add_argument('--evidence-root',default=os.environ.get('EVIDENCE_R'),help='image-build-<T>/ and current-*-path.txt are written here (default $EVIDENCE_R)')
parser.add_argument('--native-build-deps',default=os.environ.get('NATIVE_BUILD_DEPS'),help='directory holding node/ (default $NATIVE_BUILD_DEPS)')
parser.add_argument('--bun',default=os.environ.get('BUN_BIN'),help='bun binary (default $BUN_BIN)')
parser.add_argument('--bun-cache',default=os.environ.get('BUN_CACHE'),help='bun install cache (default $BUN_CACHE)')
parser.add_argument('--lodepng',default=os.environ.get('DEPS_FREEZE') and os.environ['DEPS_FREEZE']+'/build-deps/lodepng',help='lodepng source (default $DEPS_FREEZE/build-deps/lodepng)')
args=parser.parse_args()
role=args.role
needs_build_deps=role not in ('shard-deps','mount-base')      # the dependency bases hold only apt and pip steps: no node, bun or lodepng
for name in ('evidence_root','native_build_deps','bun','bun_cache','lodepng') if needs_build_deps else ('evidence_root',):
    if not getattr(args,name):
        parser.error('--%s is required on this host (host value not set)'%name.replace('_','-'))
root=Path(args.evidence_root)
tools=Path(args.native_build_deps or '.')                  # node and the other build dependencies live here (not in git: binaries)
if role=='mount-base':
    base=None        # built FROM a registry image pinned by digest in its Dockerfile; no local base to compare
else:
    pins=json.loads((Path(__file__).with_name('base-image-ids.json')).read_text())[role]
    base_tag=pins['tag']
    base_id=pins['id'] or args.pin_shard_deps
    assert base_id, 'DEPENDENCY_BASE_NOT_PINNED'
    assert pins['id'] is None or args.pin_shard_deps in (None,pins['id']), 'DEPENDENCY_BASE_PIN_CONFLICT'
    base = json.loads(subprocess.check_output(["docker", "image", "inspect", base_tag], text=True))[0]
    assert base["Id"] == base_id, "DEPENDENCY_BASE_IDENTITY_CHANGED"
build = root / ("image-build-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
build.mkdir(mode=0o700)
source = build / "context/source"
source.mkdir(parents=True, mode=0o700)
entries = {}
DEPS_DIR = 'src/so101_demo_py/docker/campaign-shard-deps/'     # the whole build context of the shard-deps base
MOUNT_DIR = 'src/so101_demo_py/docker/mount-base/'
MOUNT_FILES = (MOUNT_DIR+'Dockerfile', MOUNT_DIR+'bootstrap.bash', DEPS_DIR+'apt-packages.txt', DEPS_DIR+'pip-requirements.lock',
               'src/so101_demo_py/config/perception/inference-requirements.lock')      # flattened into the mount-base build context
for name in subprocess.check_output(["git", "ls-files", "--recurse-submodules", "-z"]).decode().split("\0"):
    if not name or not name.startswith(("src/", "scripts/", "third_party/")):
        continue
    if role == 'shard-deps' and not name.startswith(DEPS_DIR):
        continue
    if role == 'mount-base' and name not in MOUNT_FILES:
        continue
    path = Path(name)
    if not path.is_file() and not path.is_symlink():
        continue
    target = source / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        target.symlink_to(path.readlink())
    else:
        shutil.copy2(path, target)
    entries[name] = hashlib.sha256(path.read_bytes()).hexdigest()
if needs_build_deps:
    deps=source/'build-deps'
    deps.mkdir()
    node=tools/'node/node-v24.18.1-linux-x64/bin/node'
    assert node.is_file()
    (deps/'node/bin').mkdir(parents=True)
    shutil.copy2(node,deps/'node/bin/node')
    shutil.copy2(args.bun,deps/'bun')
    cache_source=Path(args.bun_cache)
    cache_copy=deps/'bun-cache'
    shutil.copytree(cache_source,cache_copy,symlinks=True)
    cache_links={}
    for link in cache_copy.rglob('*'):
        if not link.is_symlink():
            continue
        original=link.readlink()
        if not original.is_absolute():
            assert link.resolve(strict=True).is_relative_to(cache_copy), 'EXTERNAL_CACHE_LINK'
            continue
        resolved=original.resolve(strict=True)
        assert resolved.is_relative_to(cache_source), 'EXTERNAL_CACHE_LINK'
        target=cache_copy/resolved.relative_to(cache_source)
        assert target.exists() and target.resolve(strict=True).is_relative_to(cache_copy), 'CACHE_LINK_TARGET_MISSING'
        normalized=os.path.relpath(target,link.parent)
        replacement=link.with_name(link.name+'.normalized-link')
        assert not replacement.exists() and not replacement.is_symlink()
        replacement.symlink_to(normalized)
        os.replace(replacement,link)
        cache_links[link.relative_to(source).as_posix()]={'original':str(original),'normalized':normalized}
    (build/'normalized-build-cache-links.json').write_text(json.dumps(cache_links,sort_keys=True,indent=2)+'\n')
    shutil.copytree(args.lodepng,deps/'lodepng',symlinks=True)
    dependency_hashes={}
    for path in deps.rglob('*'):
        if path.is_file() and not path.is_symlink():
            dependency_hashes[path.relative_to(source).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    (build/'build-dependency-files.json').write_text(json.dumps(dependency_hashes,sort_keys=True,indent=2)+'\n')
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
submodules = {}
for line in subprocess.check_output(["git", "submodule", "status"], text=True).splitlines():
    fields = line.split()
    submodules[fields[1]] = fields[0]
(source / ".image-git.json").write_text(json.dumps(dict(git_commit=commit, submodules=submodules), sort_keys=True)+"\n")
(build / "source-files.json").write_text(json.dumps(entries, sort_keys=True, indent=2)+"\n")
if base is not None:
    (build / "base-image-inspect.json").write_text(json.dumps(base, sort_keys=True, indent=2)+"\n")
if role == 'mount-base':
    (build / "mount-context").mkdir()
    for name in MOUNT_FILES:
        shutil.copy2(source / name, build / "mount-context" / Path(name).name)
# Only the dependency bases (shard-deps, mount-base) reach the network (apt and pip); the images built from the source snapshot run
# with --network none.
networked = role in ('shard-deps', 'mount-base')
tag = {'shard-deps': "so101-campaign-shard-deps:ros-jazzy-yolo11n-v1", 'mount-base': "so101-mount-base:ros-jazzy-torch2.13.0-cu130-v1"}.get(role) or "so101-campaign-"+role+":dispatch-2130aaf1-"+commit[:12]
dockerfile = source / (DEPS_DIR + "Dockerfile") if role == 'shard-deps' else build / "mount-context/Dockerfile" if role == 'mount-base' else source / ("src/so101_demo_py/docker/campaign-"+role+"/Dockerfile")
context = source / DEPS_DIR if role == 'shard-deps' else build / "mount-context" if role == 'mount-base' else build / "context"
argv = ["docker", "build", *(["--no-cache"] if args.no_cache else []), "--network", 'default' if networked else 'none', "--progress", "plain", "--iidfile", str(build / (role+".iid")),
        "-t", tag, "-f", str(dockerfile), str(context)]
(build / "argv.json").write_text(json.dumps(argv, indent=2)+"\n")
(root / "current-image-build-path.txt").write_text(str(build)+"\n")
(root / ("current-"+role+"-image-build-path.txt")).write_text(str(build)+"\n")
(build / "build.py").write_text('import subprocess,json,time,pathlib\nr=pathlib.Path(__file__).parent\nt=time.monotonic()\nwith (r/"build.log").open("wb") as log:\n p=subprocess.Popen(json.loads((r/"argv.json").read_text()),stdout=log,stderr=subprocess.STDOUT)\n (r/"build-process.json").write_text(json.dumps({"pid":p.pid,"argv":p.args}))\n rc=p.wait()\n(r/"result.json").write_text(json.dumps({"exit_code":rc,"elapsed_s":time.monotonic()-t})+"\\n")\nprint((r/"result.json").read_text())\nraise SystemExit(rc)\n')
print(build, len(entries))
