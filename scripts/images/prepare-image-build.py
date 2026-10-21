"""Retain a new tracked source snapshot and exact Docker build invocation."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

# Run from the worktree to build (it reads `git ls-files` of the current directory). Host paths come from the arguments;
# their defaults are the host values (scripts/gate/hosts/<host>.env, loaded by scripts/gate/load_host.zsh).
parser=argparse.ArgumentParser()
parser.add_argument('--role',choices=('inference','shard'),default='inference')
parser.add_argument('--evidence-root',default=os.environ.get('EVIDENCE_R'),help='image-build-<T>/ and current-*-path.txt are written here (default $EVIDENCE_R)')
parser.add_argument('--native-build-deps',default=os.environ.get('NATIVE_BUILD_DEPS'),help='directory holding node/ (default $NATIVE_BUILD_DEPS)')
parser.add_argument('--bun',default=os.environ.get('BUN_BIN'),help='bun binary (default $BUN_BIN)')
parser.add_argument('--bun-cache',default=os.environ.get('BUN_CACHE'),help='bun install cache (default $BUN_CACHE)')
parser.add_argument('--lodepng',default=os.environ.get('DEPS_FREEZE') and os.environ['DEPS_FREEZE']+'/build-deps/lodepng',help='lodepng source (default $DEPS_FREEZE/build-deps/lodepng)')
args=parser.parse_args()
for name in ('evidence_root','native_build_deps','bun','bun_cache','lodepng'):
    if not getattr(args,name):
        parser.error('--%s is required on this host (host value not set)'%name.replace('_','-'))
role=args.role
root=Path(args.evidence_root)
tools=Path(args.native_build_deps)                  # node and the other build dependencies live here (not in git: binaries)
base_tag = ("so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1" if role=='inference' else
            "so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115")
base_id = ("sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457" if role=='inference' else
           "sha256:5998505c1debdd1a3410ed6bd1aec8796ef3f82e3b3dc403bbc992423b6304fd")
base = json.loads(subprocess.check_output(["docker", "image", "inspect", base_tag], text=True))[0]
assert base["Id"] == base_id, "DEPENDENCY_BASE_IDENTITY_CHANGED"
build = root / ("image-build-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
build.mkdir(mode=0o700)
source = build / "context/source"
source.mkdir(parents=True, mode=0o700)
entries = {}
for name in subprocess.check_output(["git", "ls-files", "--recurse-submodules", "-z"]).decode().split("\0"):
    if not name or not name.startswith(("src/", "scripts/", "third_party/")):
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
# The copied cache must hold every package of the web lockfile under the registry key the image build uses
# (build-bun.bash sets BUN_CONFIG_REGISTRY to the same default). An incomplete cache would send the image build to the
# network, which is how a 20-minute build happened. Install into a scratch directory with --offline and refuse otherwise.
with tempfile.TemporaryDirectory(prefix='so101-web-cache-check-') as scratch:
    for name in ('package.json','bun.lock'):
        shutil.copy2(source/'src/so101_teleop/web'/name,scratch)
    check=subprocess.run([str(deps/'bun'),'install','--frozen-lockfile','--offline','--cache-dir',str(cache_copy)],cwd=scratch,
                         env={**os.environ,'BUN_CONFIG_REGISTRY':os.environ.get('BUN_CONFIG_REGISTRY','https://registry.npmmirror.com')},
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    assert check.returncode==0, 'BUN_CACHE_INCOMPLETE_FOR_WEB_LOCKFILE: '+check.stdout[-2000:]
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
(build / "base-image-inspect.json").write_text(json.dumps(base, sort_keys=True, indent=2)+"\n")
argv = ["docker", "build", "--network", 'none' if role=='inference' else 'default', "--progress", "plain", "--iidfile", str(build / (role+".iid")),
        "-t", "so101-campaign-"+role+":dispatch-2130aaf1-"+commit[:12], "-f",
        str(source / ("src/so101_demo_py/docker/campaign-"+role+"/Dockerfile")), str(build / "context")]
(build / "argv.json").write_text(json.dumps(argv, indent=2)+"\n")
(root / "current-image-build-path.txt").write_text(str(build)+"\n")
(root / ("current-"+role+"-image-build-path.txt")).write_text(str(build)+"\n")
(build / "build.py").write_text('import subprocess,json,time,pathlib\nr=pathlib.Path(__file__).parent\nt=time.monotonic()\nwith (r/"build.log").open("wb") as log:\n p=subprocess.Popen(json.loads((r/"argv.json").read_text()),stdout=log,stderr=subprocess.STDOUT)\n (r/"build-process.json").write_text(json.dumps({"pid":p.pid,"argv":p.args}))\n rc=p.wait()\n(r/"result.json").write_text(json.dumps({"exit_code":rc,"elapsed_s":time.monotonic()-t})+"\\n")\nprint((r/"result.json").read_text())\nraise SystemExit(rc)\n')
print(build, len(entries))
