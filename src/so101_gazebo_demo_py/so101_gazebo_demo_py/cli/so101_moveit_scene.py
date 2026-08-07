import argparse

def main(argv=None):
    parser=argparse.ArgumentParser(description="Observe or update the SO-101 MoveIt Planning Scene")
    parser.add_argument("--operation", choices=("observe","attach","detach"), default="observe")
    parser.parse_args(argv)
    return 0
