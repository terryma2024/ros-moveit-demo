"""Validate or incrementally build the production Teleop Web bundle."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence


class WebBundleError(RuntimeError):
    """Raised when the production Web bundle cannot be safely served."""


Runner = Callable[..., subprocess.CompletedProcess]
PINNED_BUN = Path("/home/lenovo/.bun/bin/bun")
ASSET_REFERENCE = re.compile(r"(?:src|href)=[\"']([^\"']+)[\"']")


def _run(command: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None):
    return subprocess.run(command, cwd=cwd, env=dict(env) if env is not None else None, text=True, capture_output=True, check=False)


def select_bun(
    env: Mapping[str, str] | None = None,
    *,
    runner: Runner = _run,
    pinned_bun: Path = PINNED_BUN,
) -> Path:
    """Return the configured project Bun executable."""
    environment = dict(os.environ if env is None else env)
    candidates = [Path(environment["SO101_TELEOP_BUN"])] if environment.get("SO101_TELEOP_BUN") else []
    candidates.append(Path(pinned_bun))
    path_bun = shutil.which("bun", path=environment.get("PATH", ""))
    if path_bun:
        candidates.append(Path(path_bun))

    checked: list[str] = []
    for bun in candidates:
        if not bun.is_file():
            continue
        result = runner([str(bun), "--version"], env=environment)
        version_text = (result.stdout or "").strip()
        checked.append(f"{bun}={version_text or 'unknown'}")
        if result.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+", version_text):
            return bun
    detail = ", ".join(checked) if checked else "no Bun executable found"
    raise WebBundleError(f"Bun is required for the Teleop Web build; {detail}. Set SO101_TELEOP_BUN.")


def _input_files(source_dir: Path) -> list[Path]:
    fixed = [
        "package.json", "bun.lock", "index.html", "vite.config.ts",
        "tailwind.config.ts", "postcss.config.cjs", "tsconfig.json",
        "tsconfig.node.json", "components.json",
    ]
    paths = [source_dir / name for name in fixed if (source_dir / name).is_file()]
    paths.extend(path for path in (source_dir / "src").rglob("*") if path.is_file())
    return paths


def _referenced_assets(dist: Path) -> list[Path]:
    index = dist / "index.html"
    if not index.is_file() or index.stat().st_size == 0:
        raise WebBundleError(f"Web bundle index is missing or empty: {index}")
    references = []
    for reference in ASSET_REFERENCE.findall(index.read_text(encoding="utf-8")):
        if reference.startswith(("http://", "https://", "data:")):
            continue
        target = dist / reference.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if "assets/" in reference or target.suffix in {".js", ".css"}:
            references.append(target)
    if not references:
        raise WebBundleError(f"Web bundle index has no JavaScript or CSS asset references: {index}")
    for asset in references:
        if not asset.is_file() or asset.stat().st_size == 0:
            raise WebBundleError(f"Web bundle asset is missing or empty: {asset}")
    return references


def validate_web_bundle(dist: Path) -> Path:
    _referenced_assets(dist)
    return dist


def _is_fresh(source_dir: Path, dist: Path) -> bool:
    try:
        assets = _referenced_assets(dist)
    except WebBundleError:
        return False
    inputs = _input_files(source_dir)
    if not inputs:
        return True
    output_time = min(path.stat().st_mtime_ns for path in [dist / "index.html", *assets])
    return max(path.stat().st_mtime_ns for path in inputs) <= output_time


def _lock_fingerprint(source_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("package.json", "bun.lock"):
        path = source_dir / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _checked_run(runner: Runner, command: list[str], *, cwd: Path, env: Mapping[str, str]) -> None:
    result = runner(command, cwd=cwd, env=env)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise WebBundleError(f"Command {' '.join(Path(part).name if index == 0 else part for index, part in enumerate(command))} failed in {cwd}: {stderr}")


def ensure_web_bundle(
    source_dir: str | Path,
    build_if_needed: bool = True,
    *,
    runner: Runner = _run,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return a validated dist path, building it synchronously when stale."""
    source = Path(source_dir).resolve()
    dist = source / "dist"
    if _is_fresh(source, dist):
        print(f"SO101_TELEOP_WEB_PREFLIGHT web bundle fresh: {dist}", flush=True)
        return dist
    if not build_if_needed:
        return validate_web_bundle(dist)
    if not (source / "package.json").is_file():
        raise WebBundleError(f"Web source is invalid (package.json missing): {source}")

    print(f"SO101_TELEOP_WEB_PREFLIGHT web bundle missing or stale; building: {source}", flush=True)

    environment = dict(os.environ if env is None else env)
    bun = select_bun(environment, runner=runner)
    environment["PATH"] = f"{bun.parent}{os.pathsep}{environment.get('PATH', '')}"
    marker = source / "node_modules" / ".so101-lock.sha256"
    fingerprint = _lock_fingerprint(source)
    recorded = marker.read_text().strip() if marker.is_file() else ""
    if recorded != fingerprint:
        print("SO101_TELEOP_WEB_PREFLIGHT dependency fingerprint changed; running bun install --frozen-lockfile", flush=True)
        _checked_run(runner, [str(bun), "install", "--frozen-lockfile"], cwd=source, env=environment)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{fingerprint}\n")
    else:
        print("SO101_TELEOP_WEB_PREFLIGHT dependency fingerprint unchanged; skipping bun install", flush=True)
    _checked_run(runner, [str(bun), "run", "build"], cwd=source, env=environment)
    validated = validate_web_bundle(dist)
    print(f"SO101_TELEOP_WEB_PREFLIGHT web bundle built and validated: {validated}", flush=True)
    return validated
