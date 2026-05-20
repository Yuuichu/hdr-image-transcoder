"""Compatibility wrapper for hdr_transcoder.cli."""

from hdr_transcoder.cli import *  # noqa: F401,F403
from hdr_transcoder.cli import main

if __name__ == "__main__":
    main()
