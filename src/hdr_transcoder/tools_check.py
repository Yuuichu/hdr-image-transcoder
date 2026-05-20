"""CLI entry point for runtime tool and dependency checks."""
import sys

from hdr_transcoder.tools import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
