import sys
from pathlib import Path

sys.path.append(Path(__file__).parent.joinpath("src").as_posix())

from f1_race_replay.main import main

main()
