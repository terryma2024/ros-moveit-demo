uint64 chunk_sequence
string simulation_session_id
uint64 reset_epoch
uint64 first_physics_step
uint64 last_physics_step
float64 first_simulation_time_s
float64 last_simulation_time_s
uint64 failed_publish_attempts
# Publish-path instrumentation (CP-3410), filled by the plugin: CLOCK_MONOTONIC ns on the clock of the samples' clock intervals.
# handoff: the physics thread posted this chunk to the publishing thread; publish: that thread was about to call publish().
uint64 handoff_monotonic_ns
uint64 publish_monotonic_ns
# Cumulative count of publish attempts the physics thread had to defer (the slot was busy), since the last reset.
uint64 publish_deferrals_total
bool evidence_loss
PhysicsStepEvidence[] samples
