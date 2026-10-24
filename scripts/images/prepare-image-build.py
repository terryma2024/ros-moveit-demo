"""Retain the build context (the mount-base files of the tracked source) and the exact Docker build invocation of the so101-mount-base image."""
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
parser.add_argument('--role',choices=('mount-base',),default='mount-base')
parser.add_argument('--no-cache',action='store_true',help='docker build --no-cache: every layer is built again (the determinism acceptance builds twice this way)')
parser.add_argument('--evidence-root',default=os.environ.get('EVIDENCE_R'),help='image-build-<T>/ and current-*-path.txt are written here (default $EVIDENCE_R)')
args=parser.parse_args()
role=args.role
if not args.evidence_root:
    parser.error('--evidence-root is required on this host (host value not set)')
root=Path(args.evidence_root)
build = root / ("image-build-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
build.mkdir(mode=0o700)
source = build / "context/source"
source.mkdir(parents=True, mode=0o700)
entries = {}
MOUNT_DIR = 'src/so101_demo_py/docker/mount-base/'
MOUNT_FILES = (MOUNT_DIR+'Dockerfile', MOUNT_DIR+'bootstrap.bash', MOUNT_DIR+'check-mount-commit.bash', MOUNT_DIR+'apt-pins.txt', MOUNT_DIR+'apt-packages.txt', MOUNT_DIR+'pip-requirements.lock',
               'src/so101_demo_py/config/perception/inference-requirements.lock')      # flattened into the mount-base build context
for name in subprocess.check_output(["git", "ls-files", "--recurse-submodules", "-z"]).decode().split("\0"):
    if not name or not name.startswith(("src/", "scripts/", "third_party/")):
        continue
    if name not in MOUNT_FILES:
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
(build / "source-files.json").write_text(json.dumps(entries, sort_keys=True, indent=2)+"\n")
(build / "mount-context").mkdir()
for name in MOUNT_FILES:
    shutil.copy2(source / name, build / "mount-context" / Path(name).name)
# The mount base reaches the network (apt and pip) and holds dependencies only; the project code is mounted at run time.
networked = True
tag = "so101-mount-base:ros-jazzy-torch2.13.0-cu130-v1"
dockerfile = build / "mount-context/Dockerfile"
context = build / "mount-context"
# BUILD_PROXY / BUILD_NO_PROXY (host values) route the networked steps through a proxy that listens on the host's loopback: the build
# then needs the host network namespace. The proxy variables go in as docker's predefined build arguments, which are neither
# recorded in the image history nor part of the image environment. Not set: the build is exactly as before.
proxy = os.environ.get('BUILD_PROXY') if networked else None
proxy_args = []
if proxy:
    no_proxy = os.environ.get('BUILD_NO_PROXY', '')
    for name, value in (('HTTP_PROXY', proxy), ('HTTPS_PROXY', proxy), ('NO_PROXY', no_proxy), ('http_proxy', proxy), ('https_proxy', proxy), ('no_proxy', no_proxy)):
        if value:
            proxy_args += ["--build-arg", name+"="+value]
argv = ["docker", "build", *(["--no-cache"] if args.no_cache else []), "--network", 'host' if proxy else 'default' if networked else 'none', *proxy_args,
        "--progress", "plain", "--iidfile", str(build / (role+".iid")), "-t", tag, "-f", str(dockerfile), str(context)]
(build / "argv.json").write_text(json.dumps(argv, indent=2)+"\n")
(root / "current-image-build-path.txt").write_text(str(build)+"\n")
(root / ("current-"+role+"-image-build-path.txt")).write_text(str(build)+"\n")
(build / "build.py").write_text('import subprocess,json,time,pathlib\nr=pathlib.Path(__file__).parent\nt=time.monotonic()\nwith (r/"build.log").open("wb") as log:\n p=subprocess.Popen(json.loads((r/"argv.json").read_text()),stdout=log,stderr=subprocess.STDOUT)\n (r/"build-process.json").write_text(json.dumps({"pid":p.pid,"argv":p.args}))\n rc=p.wait()\n(r/"result.json").write_text(json.dumps({"exit_code":rc,"elapsed_s":time.monotonic()-t})+"\\n")\nprint((r/"result.json").read_text())\nraise SystemExit(rc)\n')
print(build, len(entries))
