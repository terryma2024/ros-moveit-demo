import argparse

def main(argv=None):
    parser=argparse.ArgumentParser(description="Reset SO-101 Gazebo and Planning Scene state")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.parse_args(argv)
    return 0
