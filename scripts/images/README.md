# Image content manifest

`image_content_manifest.py` computes what an image contains, so two images built on different hosts can be compared by content
instead of by image ID. It reads a `docker save` tar (a file, or `-` for stdin), merges the layers and hashes the result. It does
not start the image and does not run code from it. It uses only the Python standard library.

```
python3 -I scripts/images/image_content_manifest.py manifest <tar|-> --exclusions scripts/images/image-content-exclusions.txt --output M.json
python3 -I scripts/images/image_content_manifest.py diff A.json B.json
python3 -I scripts/images/image_content_manifest.py check-no-pyc M.json [--base BASE.json]
```

`manifest` prints `content_sha256` on stdout. The entry count and the excluded counts go to stderr. Every refusal prints
`error: <ErrorName>: <cause>` and exits 2.

## What is hashed

- **Layers.** Plain and gzip layers, in the docker-archive layout (`manifest.json`) and the OCI layout (`index.json` and
  `blobs/`). The tar is read once, so the order of the members does not matter. An archive with more than one image is refused;
  attestation manifests in an OCI index are skipped.
- **Merge.** Layers apply in order. A whiteout `.wh.<name>` removes the path and its subtree. `.wh..wh..opq` clears the lower
  content of its directory and keeps the entries the same layer adds. A later entry replaces an earlier one; replacing a
  directory with a non-directory drops the old children. A hard link takes its target's content, mode, owner and group at the
  time the layer is applied, and keeps its `target`. Other `.wh..wh.*` names are ignored.
- **One entry per path.** `type` (`file`, `dir`, `symlink`, `hardlink`, `char`, `block`, `fifo`), `mode` as an octal string,
  `uid`, `gid`; for a file `size` and `sha256`; for a symlink `link`; for a device `major` and `minor`; `xattrs` (value hashes)
  when present. There are no mtimes, atimes or ctimes.
- **Image config.** `Entrypoint`, `Cmd`, `Env`, `WorkingDir`, `User`, `ExposedPorts`, `Volumes`, `Labels` and `Shell`.
- **Canonical JSON.** Sorted keys, no whitespace, ASCII-escaped (valid UTF-8), integers and strings only.

The output file has four parts: `content` (schema, config, entries and the list of exclusion globs), `content_sha256` (the
sha256 of the canonical bytes of `content`), `excluded` and `attribution`. Only `content` is hashed. `diff` and `check-no-pyc`
recompute the hash and refuse a manifest that does not match it.

## Exclusions

`image-content-exclusions.txt` has one rule per line: `<glob> | <reason> | <date added>`. `**` matches across `/`, `*` and `?`
do not. A path matched by a rule leaves `content.entries` and appears in `excluded.entries` with the rule and the sha256 of its
own entry, so an exclusion stays visible. The list of globs is part of `content`, so two manifests are comparable only when
they used the same rules.

The loader refuses any rule that could match at or inside `/act`, `/opt/ros`, `/usr/lib`, `/usr/bin` or `/act/venv` (for
example `/**`, `/usr/*` or `/**/site-packages/**`). Add a rule only after a determinism test shows the path varies between
builds of the same commit, and record the reason.

## diff

Lists every differing path with both sides (`A:` and `B:`), grouped by top-level directory, and a count per package. A path is
attributed to a dpkg package from `/var/lib/dpkg/info/*.list` and to a pip distribution from `*.dist-info/RECORD`. The path
lists of those files are stored in `attribution`, because the entries only hold their hashes. Exit status is 1 when anything
differs, 0 when nothing does.

## check-no-pyc

Fails (exit 1) when a `*.pyc` file exists anywhere under `/act` (this includes `/act/venv`), or in a `site-packages` directory
outside `/act` that the build added. With `--base BASE.json` (the base image's manifest) only `.pyc` files missing from the base
count. Without it, every `.pyc` in a `site-packages` directory counts. The first line of output gives the counts under `/act`,
under `/act/venv`, and added in `site-packages`.

## Tests

`scripts/tests/test_image_content_manifest.py` builds synthetic layer tars in the test and reads no host path.
