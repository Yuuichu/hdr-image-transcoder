"""
AVIF gainmap encoder using libavif's avifgainmaputil.

Combines SDR base + HDR alternate into a gainmap AVIF.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from hdr_transcoder.color import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_BT709_MATRIX,
    CICP_BT709_PRIMARIES,
    CICP_PQ_TRANSFER,
    CICP_SRGB_TRANSFER,
)
from hdr_transcoder.config import GAINMAP_ENCODE_TIMEOUT_SECONDS
from hdr_transcoder.tools import AVIFGAINMAPUTIL, AVIFGAINMAPUTIL_HDR


def encode_gainmap_avif(
    sdr_8bit,
    hdr_16bit,
    output_path,
    quality=100,
    speed=0,
    max_headroom=None,
    base_headroom=None,
    alternate_headroom=None,
):
    """Encode SDR base + HDR alternate to gainmap AVIF.

    Args:
        sdr_8bit: ndarray (H, W, 3) uint8, sRGB SDR base
        hdr_16bit: ndarray (H, W, 3) uint16, PQ-encoded Rec.2020 HDR alternate
        output_path: str or Path, output AVIF file path
        quality: 0-100, AVIF encoding quality (default 100)
        speed: 0-10, encoder speed (default 0)
        max_headroom: optional legacy libavif headroom cap
        base_headroom: optional log2 base headroom metadata override
        alternate_headroom: optional log2 alternate headroom metadata override

    Returns:
        Path to the output AVIF file
    """
    import imagecodecs

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not AVIFGAINMAPUTIL_HDR.exists():
        raise FileNotFoundError(
            f"Missing patched libavif gain map tool: {AVIFGAINMAPUTIL_HDR}. "
            "Gainmap AVIF encoding requires avifgainmaputil_hdr.exe so HDR "
            "headroom metadata can be written explicitly."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        base_png = tmp / "base.png"
        alternate_png = tmp / "alternate.png"

        base_png.write_bytes(imagecodecs.png_encode(sdr_8bit))
        alternate_png.write_bytes(imagecodecs.png_encode(hdr_16bit))

        cmd = [
            str(AVIFGAINMAPUTIL_HDR), "combine",
            str(base_png),
            str(alternate_png),
            str(output_path),
            "--qcolor", str(quality),
            "--qgain-map", str(quality),
            "--depth-gain-map", "12",
            "--yuv-gain-map", "444",
            "--speed", str(speed),
            "--cicp-base", f"{CICP_BT709_PRIMARIES}/{CICP_SRGB_TRANSFER}/{CICP_BT709_MATRIX}",
            "--cicp-alternate", f"{CICP_BT2020_PRIMARIES}/{CICP_PQ_TRANSFER}/{CICP_BT2020_MATRIX}",
        ]
        if max_headroom is not None:
            cmd.extend(["--max-headroom", str(max_headroom)])
        if base_headroom is not None:
            cmd.extend(["--base-headroom", str(base_headroom)])
        if alternate_headroom is not None:
            cmd.extend(["--alternate-headroom", str(alternate_headroom)])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=GAINMAP_ENCODE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"avifgainmaputil_hdr combine timed out after {GAINMAP_ENCODE_TIMEOUT_SECONDS}s"
            ) from exc
        if result.stderr and result.stderr.strip():
            from textwrap import indent
            print(f"avifgainmaputil_hdr stderr:\n{indent(result.stderr.strip(), '  ')}", file=sys.stderr)
        if result.returncode != 0:
            from textwrap import indent
            detail = ""
            if result.stderr:
                detail = f"\nSTDERR:\n{indent(result.stderr.strip(), '  ')}"
            if result.stdout:
                detail += f"\nSTDOUT:\n{indent(result.stdout.strip(), '  ')}"
            raise RuntimeError(
                f"avifgainmaputil_hdr exited with code {result.returncode}{detail}"
            )

    return output_path
