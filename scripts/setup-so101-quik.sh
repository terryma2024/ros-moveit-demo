#!/usr/bin/env bash
# Bootstrap both CPU IK backends without installing into a shared Python or ROS prefix.
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
prefix="${HOME}/.local/share/so101-quik"
python_override=""
index="https://pypi.tuna.tsinghua.edu.cn/simple"
usage() {
    cat <<'USAGE'
Usage: bash scripts/setup-so101-quik.sh [--prefix DIR] [--python EXECUTABLE] [--index URL]

Prepare Python, Eigen 3.4.0 and both native/QuIK CPU kernels in an isolated prefix.
Supported: Ubuntu 24.04 x86_64 and Apple Silicon macOS.
Default prefix: $HOME/.local/share/so101-quik (must be empty or owned by this setup).
--python uses an existing CPython 3.11 on Mac or 3.12 on Linux, such as ROS Python;
         all packages still go into a new private virtual environment.
--index  chooses the Python package index (default: TUNA PyPI mirror).
Ubuntu installs missing build tools through apt-get (root or sudo required).
Mac requires Apple command line tools; a missing toolchain opens its OS installer.
Outputs: activate.sh, build-env.sh and manifest.json. Reruns verify installed artifacts.
USAGE
}
fail() { printf 'SO101_QUIK_SETUP: %s\n' "$*" >&2; exit 1; }
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --prefix|--python|--index)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "MISSING_OPTION_VALUE: $1"
            case "$1" in
                --prefix) prefix=$2 ;;
                --python) python_override=$2 ;;
                --index) index=$2 ;;
            esac
            shift 2 ;;
        *) fail "UNKNOWN_OPTION: $1" ;;
    esac
done

# Resolve parents before writing anything; never accept a checkout or shared runtime.
[ ! -L "$prefix" ] || fail "UNSAFE_PREFIX: symbolic link"
case "$prefix/" in ../*|*/../*) fail "UNSAFE_PREFIX: parent traversal" ;; esac
parent=$(dirname "$prefix")
pending=$(basename "$prefix")
while [ ! -d "$parent" ]; do
    [ ! -e "$parent" ] || fail "UNSAFE_PREFIX: parent is not a directory"
    pending="$(basename "$parent")/$pending"
    parent=$(dirname "$parent")
done
resolved_parent=$(cd "$parent" && pwd -P)
prefix="${resolved_parent%/}/$pending"
case "$prefix/" in
    "$repo/"*|/usr/*|/System/*|/Library/*|/opt/ros/*|/opt/data/so101/*|/home/|/Users/|//|/./)
        fail "UNSAFE_PREFIX: $prefix" ;;
esac
if [ -e "$prefix" ]; then
    [ -d "$prefix" ] || fail "UNSAFE_PREFIX: not a directory"
    [ -O "$prefix" ] || fail "UNSAFE_PREFIX: different owner"
    if [ ! -f "$prefix/.so101-quik-prefix" ]; then
        [ -z "$(ls -A "$prefix")" ] || fail "UNMANAGED_PREFIX: $prefix"
    else
        [ "$(cat "$prefix/.so101-quik-prefix")" = "so101-quik-v1:$(id -u)" ] || fail "INCOMPATIBLE_PREFIX"
    fi
fi

case "$(uname -s):$(uname -m)" in
    Darwin:arm64) platform=mac; uv_target=aarch64-apple-darwin ;;
    Linux:x86_64)
        [ -r /etc/os-release ] || fail "UNSUPPORTED_PLATFORM"
        # OS-owned metadata, not a downloaded script.
        . /etc/os-release
        [ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] || fail "UNSUPPORTED_PLATFORM: Ubuntu 24.04 required"
        platform=linux; uv_target=x86_64-unknown-linux-gnu ;;
    *) fail "UNSUPPORTED_PLATFORM: $(uname -s) $(uname -m)" ;;
esac
umask 077
mkdir -p "$prefix"
printf 'so101-quik-v1:%s\n' "$(id -u)" > "$prefix/.so101-quik-prefix"
mkdir "$prefix/.setup-lock" 2>/dev/null || fail "SETUP_ALREADY_RUNNING: $prefix"
trap 'rmdir "$prefix/.setup-lock"' EXIT
mkdir -p "$prefix/bin" "$prefix/downloads" "$prefix/cache" "$prefix/python" "$prefix/logs"
# Committed, repository-owned version constants; no remote installer is executed.
. "$repo/scripts/so101-quik-bootstrap.lock.env"
export QUIK_SETUP_EIGEN_URL QUIK_SETUP_EIGEN_SHA256 QUIK_SETUP_SETUPTOOLS
export QUIK_SETUP_WHEEL QUIK_SETUP_TYPING_EXTENSIONS QUIK_SETUP_PYYAML
export UV_CACHE_DIR="$prefix/cache" UV_PYTHON_INSTALL_DIR="$prefix/python"
export UV_PYTHON_BIN_DIR="$prefix/bin" UV_NO_CONFIG=1 PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH PYTHONHOME

if [ "$platform" = linux ]; then
    if ! command -v g++ >/dev/null || ! command -v curl >/dev/null || ! command -v tar >/dev/null ||
       [ ! -f /etc/ssl/certs/ca-certificates.crt ]; then
        if [ "$(id -u)" -eq 0 ]; then
            apt-get update
            DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential curl ca-certificates tar
        elif command -v sudo >/dev/null; then
            sudo apt-get update
            sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential curl ca-certificates tar
        else
            fail "SYSTEM_TOOLS_REQUIRE_ADMIN: install build-essential curl ca-certificates tar"
        fi
    fi
    export CC="$(command -v gcc)" CXX="$(command -v g++)"
    uv_sha=$QUIK_SETUP_UV_LINUX_SHA256
    python_version=$QUIK_SETUP_PYTHON_LINUX
else
    if ! xcrun --find clang++ >/dev/null 2>&1 || ! xcrun --show-sdk-path >/dev/null 2>&1; then
        xcode-select --install || true
        fail "APPLE_TOOLCHAIN_PENDING: complete the Apple installer, then rerun"
    fi
    export CC="$(xcrun --find clang)" CXX="$(xcrun --find clang++)"
    export SDKROOT="$(xcrun --show-sdk-path)"
    uv_sha=$QUIK_SETUP_UV_MAC_SHA256
    python_version=$QUIK_SETUP_PYTHON_MAC
fi
"$CXX" --version

sha256() {
    if command -v sha256sum >/dev/null; then sha256sum "$1" | awk '{print $1}'
    else shasum -a 256 "$1" | awk '{print $1}'; fi
}
sha256_stream() {
    if command -v sha256sum >/dev/null; then sha256sum | awk '{print $1}'
    else shasum -a 256 | awk '{print $1}'; fi
}
uv_archive="$prefix/downloads/uv-$QUIK_SETUP_UV_VERSION-$uv_target.tar.gz"
if [ ! -f "$uv_archive" ]; then
    for uv_base in \
        "https://releases.astral.sh/github/uv/releases/download/$QUIK_SETUP_UV_VERSION" \
        "https://github.com/astral-sh/uv/releases/download/$QUIK_SETUP_UV_VERSION"; do
        if curl --fail --location --retry 3 --connect-timeout 30 --max-time 600 \
            --speed-time 30 --speed-limit 1024 "$uv_base/uv-$uv_target.tar.gz" -o "$uv_archive.part"; then
            [ "$(sha256 "$uv_archive.part")" = "$uv_sha" ] || fail "UV_SHA256_MISMATCH"
            mv "$uv_archive.part" "$uv_archive"
            break
        fi
    done
    [ -f "$uv_archive" ] || fail "UV_DOWNLOAD_FAILED: official release endpoints unavailable"
fi
[ "$(sha256 "$uv_archive")" = "$uv_sha" ] || fail "UV_SHA256_MISMATCH"
uv="$prefix/bin/uv"
if [ ! -x "$uv" ]; then
    tar -xzf "$uv_archive" -C "$prefix/bin" --strip-components=1 "uv-$uv_target/uv"
fi
[ ! -L "$uv" ] || fail "UV_BINARY_MISMATCH: symbolic link"
[ "$(sha256 "$uv")" = "$(tar -xOf "$uv_archive" "uv-$uv_target/uv" | sha256_stream)" ] || fail "UV_BINARY_MISMATCH"
[ "$("$uv" --version | awk '{print $1 " " $2}')" = "uv $QUIK_SETUP_UV_VERSION" ] || fail "UV_VERSION_MISMATCH"
if [ -n "$python_override" ]; then
    [ -x "$python_override" ] || fail "PYTHON_NOT_EXECUTABLE: $python_override"
    selected_python=$python_override
else
    "$uv" python install "$python_version" --no-bin
    selected_python=$("$uv" python find "$python_version" --managed-python)
fi
"$selected_python" -c 'import sys; expected=(3,11) if sys.platform=="darwin" else (3,12); assert sys.implementation.name=="cpython" and sys.version_info[:2]==expected, "INCOMPATIBLE_PYTHON: expected CPython %s.%s" % expected'
if [ ! -x "$prefix/env/bin/python" ]; then
    "$uv" venv --python "$selected_python" --no-python-downloads "$prefix/env"
fi

# Preserve user proxy exclusions; bypass the default mirror for this process only.
if [ "$index" = https://pypi.tuna.tsinghua.edu.cn/simple ]; then
    export NO_PROXY="${NO_PROXY:+$NO_PROXY,}pypi.tuna.tsinghua.edu.cn"
    export no_proxy="${no_proxy:+$no_proxy,}pypi.tuna.tsinghua.edu.cn"
fi
"$prefix/env/bin/python" "$repo/scripts/so101_quik_setup.py" \
    --repo "$repo" --prefix "$prefix" --index "$index" --base-python "$selected_python"
printf '\nSetup verified. source %q\nROS build environment: source %q\n' "$prefix/activate.sh" "$prefix/build-env.sh"
