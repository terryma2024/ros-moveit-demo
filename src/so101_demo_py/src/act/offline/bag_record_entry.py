"""The stock `ros2 bag record` verb with one change: only the recorder's own logger runs at DEBUG.

`ros2 bag record --log-level debug` sets the DEBUG level for every logger of the process. rcl then prints two lines for every
message it takes (about 500 000 lines and 40 MB in a 100 s episode), written synchronously by the thread that also takes the
messages. The per-topic transport-loss lines the offline gate reconciles are logged by the recorder node's own logger, so this
entry keeps the global level at INFO and raises that one logger. Arguments, QoS overrides, cache, storage, signal handling and the
bag are the verb's own.
"""
import argparse
import sys


def _recorder_class(base, set_logger_level, debug):
    """`base` with its log level fixed to INFO and the node's own logger raised to DEBUG once the node exists."""

    class Recorder(base):
        def __init__(self, storage_options, record_options, log_level, node_name):
            super().__init__(storage_options, record_options, "info", node_name)
            set_logger_level(node_name, debug)

    return Recorder


def main(argv=None):
    import rclpy.logging
    import ros2bag.verb.record as stock

    stock.Recorder = _recorder_class(stock.Recorder, rclpy.logging.set_logger_level, rclpy.logging.LoggingSeverity.DEBUG)
    parser = argparse.ArgumentParser(prog="bag_record_entry")
    verb = stock.RecordVerb()
    verb.add_arguments(parser, "record")
    return verb.main(args=parser.parse_args(sys.argv[1:] if argv is None else argv)) or 0


if __name__ == "__main__":
    sys.exit(main())
