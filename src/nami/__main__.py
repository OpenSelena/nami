"""Executable module entrypoint for python -m nami."""

from __future__ import annotations

import sys

from nami.cli import main

if __name__ == "__main__":
    sys.exit(main())
