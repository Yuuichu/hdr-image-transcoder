"""
Backward-compatible JXR to AVIF wrapper.

This module forwards to hdr2avif.py, which supports JXR and other HDR formats.

Usage:
    python jxr2avif.py <input.jxr> [output.avif]
    python jxr2avif.py <directory> --output-dir <dir>
"""
from hdr2avif import main


if __name__ == "__main__":
    main()
