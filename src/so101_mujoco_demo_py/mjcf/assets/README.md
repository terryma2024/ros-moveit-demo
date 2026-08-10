# SO-101 model assets

These files are exact copies from behavior source commit
`8d7913e7f552a40ee627d65be8b873ac16748bc9`. Their original repository paths and SHA-256
values are recorded in `docs/provenance.json` and `config/model-parity.yaml`.

They are local inputs for the independent MuJoCo/URDF model. Runtime never resolves assets from
another ROS package and never downloads model content.

`docs/provenance.json` records every exact source path, destination path, source commit, and source
SHA-256. `config/model-parity.yaml` independently lists every copied destination filename and exact
SHA-256; its key set must equal the complete local STL set.
