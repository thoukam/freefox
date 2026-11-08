#!/usr/bin/env python3
"""Local web dashboard.

Kept for backward compatibility: prefer the installed `freefox-dashboard` command.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.dashboard import main  # noqa: E402

if __name__ == "__main__":
    main()
