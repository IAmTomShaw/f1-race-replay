import argparse

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-y", "--year",
        type=int,
        default=2025,
        help="Year to use (default: 2025)"
    )

    parser.add_argument(
        "-r", "--round",
        type=int,
        default=1,
        help="Round number to use (default: 1)"
    )

    parser.add_argument(
        "-s","--speed",
        type=float,
        default=1,
        help="Playback speed (default: 1)"
    )

    return parser.parse_args()