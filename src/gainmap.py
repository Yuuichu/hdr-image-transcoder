"""
AVIF gainmap encoder using libavif's avifgainmaputil.

Combines SDR base + HDR alternate into a gainmap AVIF.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools" / "libavif"
AVIFGAINMAPUTIL = TOOLS_DIR / "avifgainmaputil.exe"


def encode_gainmap_avif(sdr_8bit, hdr_16bit, output_path, quality=95, speed=6, max_headroom=0):
    """Encode SDR base + HDR alternate to gainmap AVIF.

    Args:
        sdr_8bit: ndarray (H, W, 3) uint8, sRGB SDR base
        hdr_16bit: ndarray (H, W, 3) uint16, linear scRGB HDR alternate
        output_path: str or Path, output AVIF file path
        quality: 0-100, AVIF encoding quality (default 95)
        speed: 0-10, encoder speed (default 6)
        max_headroom: log2 max gain, 0 = auto-detect (default 0)

    Returns:
        Path to the output AVIF file
    """
    import imagecodecs

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not AVIFGAINMAPUTIL.exists():
        raise FileNotFoundError(f"Missing libavif tool: {AVIFGAINMAPUTIL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        base_png = tmp / "base.png"
        alternate_png = tmp / "alternate.png"

        base_png.write_bytes(imagecodecs.png_encode(sdr_8bit))
        alternate_png.write_bytes(imagecodecs.png_encode(hdr_16bit))

        cmd = [
            str(AVIFGAINMAPUTIL), "combine",
            str(base_png),
            str(alternate_png),
            str(output_path),
            "--qcolor", str(quality),
            "--qgain-map", str(quality),
            "--speed", str(speed),
            "--cicp-base", "1/13/0",
            "--cicp-alternate", "1/16/0",
            "--max-headroom", str(max_headroom),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stderr and result.stderr.strip():
            from textwrap import indent
            print(f"avifgainmaputil stderr:\n{indent(result.stderr.strip(), '  ')}", file=sys.stderr)
        if result.returncode != 0:
            from textwrap import indent
            detail = ""
            if result.stderr:
                detail = f"\nSTDERR:\n{indent(result.stderr.strip(), '  ')}"
            if result.stdout:
                detail += f"\nSTDOUT:\n{indent(result.stdout.strip(), '  ')}"
            raise RuntimeError(
                f"avifgainmaputil exited with code {result.returncode}{detail}"
            )

    return output_path
