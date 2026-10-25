std_msgs/Header header
string simulation_session_id
uint64 reset_epoch
uint64 simulation_step
bool paused
string model_sha256
float64[] qpos
float64[] qvel
int64 clock_interval_begin_monotonic_ns
int64 clock_interval_end_monotonic_ns
# Indoor P3 (D1). A stack launched on a visual variant of the nominal scene declares the nominal model identity in `model_sha256` and says so:
# `declared_model_sha256` (equal to model_sha256) and `equivalence_proof_sha256` are set, `loaded_model_sha256` is the hash of the model it
# really loaded. Without an override, declared and proof are empty and loaded equals model_sha256.
string loaded_model_sha256
string declared_model_sha256
string equivalence_proof_sha256
