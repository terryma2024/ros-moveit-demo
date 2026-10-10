# Retired Task 6 / held-cup sealed artifacts (2026-10-10)

Retired by CP-3529 decision 1 after the Head-geometry merge. Nothing was re-sealed.

## Reason

- The eight sealed profiles were hand-measured on the old compiled model `b3b2e83c…` and have no generator in the tree: the `build_*_manifest` functions only replay and verify them against pinned digests.
- A static import graph from the v3 Teacher CLIs and the Head search CLIs reaches none of the modules that load them (only `contact_collector`, which does not read them).
- The merged model (Head neck height 0.389 m and camera geoms, compiled scene model `17c415d9…`) changes the model hash they bind, so every one of them fails closed.
- `contact-calibration-schema.json` is read by no producer or verifier of the r11 contact proposal (`act_collect_contact_calibration`, `act_analyze_contact_calibration`, `act_activate_contact_policy`); the only reader was `test_d1_act_cup_joint`.

Modules and tests that only these artifacts used were removed with them; the static graph shows no remaining module or test imports any of them. The two `task6_*` modules were import aliases of `visible_approach_diagnostic` and `grasp_contact_transition_diagnostic`. Recover any file with `git show <commit>:<path>`.

| file | kind | last sha256 | last commit |
|---|---|---|---|
| `src/so101_demo_py/config/act/contact-calibration-schema.json` | sealed artifact | `2555a146abe18e92f52ff19007089f6fbd52d62a44318de22ba79bd24afb365a` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/held_cup_micro_lift_candidates_v1.json` | sealed artifact | `6b626287cdfefc8e210385a32abc76eb2800f23ff985783a055b3c84dd0ed437` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/held_cup_transfer_v2.json` | sealed artifact | `e196a112210bc07a35bcc2a56ca37dd06166caf64226626f40132c554e6c2bba` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/held_cup_transfer_v3.json` | sealed artifact | `06f13cb86de4798c3eab2c9c896f0bec6b24a82d17c1d3c6e008b1fd050c4b86` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/task6_alt_full_contact_v1.json` | sealed artifact | `1466bd37e05c5ff8c1a7e6ffed2efdfbdecc87a7234ed1148ac5f84988769ac7` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/task6_contact_transition_v1.json` | sealed artifact | `25a8c8d98777cd6f242c2e45a0cc4ed8e194156a7473158578c730319f64454f` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/task6_visible_approach_v1.json` | sealed artifact | `b9c73aa3ee5e75c049f13c9f39aea692fa7635c05290a7a2c74d09d2c4c0e687` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/config/mujoco/act/visible_approach_candidate_v1.json` | sealed artifact | `5d96190dfb92fe1a2385a99257d4f3f43dd02edf351462515831e7406b8df22b` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/src/act/alternate_anchor_grasp_contact_diagnostic.py` | module | `615901083641185d2cb3a8e64485fa675fdfc852e81eede59051fc0ec06e437d` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/approach_grasp_contact_diagnostic.py` | module | `40ee854d9f5bd84f13a7e81e37bbf071cf51ac534281247d65cebaf5443cf4ae` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/src/act/grasp_contact_transition_diagnostic.py` | module | `a8c41b6f6b31c9fde2e389381c0bd216f85215fc2b19cd1eb95977d920318e41` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/held_cup_micro_lift_candidate.py` | module | `87f647970c8917ddcf4a5ce3a08201d9e4b2daf9ffbf9d8adf0bd926740eb09f` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/held_cup_micro_lift_diagnostic.py` | module | `896cbb78312aa86b5d5e1d58e964d8b432e42a71d206654a8bd5cc4164bbd7e7` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/src/act/held_cup_transfer_profile.py` | module | `777e5cc1f54e09e980c07ff82940147398d5b50e28e6f005a6b3612b2e2fe862` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/held_cup_transfer_schedule.py` | module | `4c958d2089bc9d6b20aeb6c43d6b24a2e6bb405928ff14e52b9476bb129d5cae` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/task6_alt_full_contact_diagnostic.py` | module | `72e0d70817cbe3fccf126ceca823275cf1fe10f69c708acab8c9b0ad5ea9982c` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/src/act/task6_full_contact_diagnostic.py` | module | `21d76d94ece63505bf887d25db5437f7fd10586d43e17c0fda07b60c9d1e7172` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/src/act/visible_approach_candidate.py` | module | `66940b56f02e792f79d7d9f76f6f7c1d7506dc284f99d2e1f2d59bdbdfd0a579` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/src/act/visible_approach_diagnostic.py` | module | `c2733cfac6a3bd4144fbe5087c3d3fc57afdaa6fbe895e86378d5ea2a214dd9c` | 8ab61b431 2026-10-10 |
| `src/so101_demo_py/src/act/task6_route_diagnostic.py` | module | `50ddd4876aa6ceecda5b3c0a7e5e7150dbc70e918ee7bbaa9aec45ff2cdc24df` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/src/act/task6_contact_transition.py` | module | `6efc94ca91a28c60f8ccb419f959037ed2108cc49fa31a3c205b85025870d9da` | b10388d1c 2026-09-27 |
| `src/so101_demo_py/test/test_act_held_cup_micro_lift_candidate.py` | test | `f285498413f0a14479720c2a08486612e49b699b1a386e6cf6f18ce9e4c0af7b` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_held_cup_micro_lift_diagnostic.py` | test | `7402f03f1a8419d47c589bcd64c7ee944c67f76cc85c5e72e55f6e4c04470fae` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_held_cup_motion_guard.py` | test | `29c868c06b4716b92a5cb5e1d8a756174c3c3039c0ac162c2d48725bb9b3a1a3` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_held_cup_transfer_profile.py` | test | `eee0194a8927395aafe8b29a61bb375dc917ca79ee533da9e9c002dd26816774` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_held_cup_transfer_schedule.py` | test | `29bb63c1c77e7de812659ee050a44a3101f0d72928603ae8402efbd63dfb9cfd` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_task6_alt_full_contact_diagnostic.py` | test | `ef54afa25265947e5391d5b5386e2203ee028c78764d0e0fbd7a6319f26cc974` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_task6_contact_transition.py` | test | `f16e3cc7556fc9ddaf0cd771582f252e981a0482d4b6b6c9aeee40493c6bf472` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_task6_full_contact_diagnostic.py` | test | `eaaf4c985575feaa72e211bdc568a4eee8c544ca08261911dd137493de9fef8e` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_task6_route_diagnostic.py` | test | `7e7ce7690bfe9426bee9bfbc3d7946babd4d2ee69bbb841fb6f00a02f9ff3ed8` | 2b2abaa08 2026-10-08 |
| `src/so101_demo_py/test/test_act_visible_approach_candidate.py` | test | `6aa1bc9a048472827f1d8d1f51cf533e544b576e24c890c9331c523e51914d99` | 04bf5a277 2026-09-27 |
