"""Record raw, process offline (CP-3428 pilot).

During execution only `raw_recorder` writes the sources losslessly (a rosbag2 MCAP bag and a sidecar of the Recorder-style planning
scene reads). After the run `processor` replays the bag through the EXISTING Recorder modules and produces the sealed episode.
"""
