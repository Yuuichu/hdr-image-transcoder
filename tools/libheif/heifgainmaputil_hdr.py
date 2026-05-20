"""Headroom-aware ISO 21496-1 gainmap HEIC assembler.

Combines SDR base PNG + HDR alternate PNG into a gainmap HEIC using
pillow_heif for HEVC encoding and ISOBMFF container assembly.

Mirrors the CLI interface of avifgainmaputil_hdr.exe for consistency.

Usage:
    python heifgainmaputil_hdr.py combine base.png alternate.png output.heic
        [--qcolor <0-100>] [--qgain-map <0-100>]
        [--depth-gain-map <8|10|12>] [--yuv-gain-map <444|420>]
        [--speed <0-10>]
        [--cicp-base <P/T/M>] [--cicp-alternate <P/T/M>]
        [--base-headroom <stops>] [--alternate-headroom <stops>]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

CICP_SRGB = (1, 13, 1)
CICP_BT2020_PQ = (9, 16, 9)


def _srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Convert sRGB (0-255 uint8) to linear luminance."""
    linear = srgb.astype(np.float32) / 255.0
    mask = linear <= 0.04045
    linear[mask] /= 12.92
    linear[~mask] = ((linear[~mask] + 0.055) / 1.055) ** 2.4
    return linear


def _compute_gain_map(sdr_8bit: np.ndarray, hdr_16bit: np.ndarray) -> np.ndarray:
    """Compute an RGB ISO 21496-1 gain map from SDR base and HDR alternate.

    Args:
        sdr_8bit: (H, W, 3) uint8 sRGB SDR base
        hdr_16bit: (H, W, 3) uint16 PQ BT.2020 HDR alternate

    Returns:
        (H, W, 3) uint8 gain map
    """
    from hdr_transcoder.color import clamp_small_negatives, linear_bt2020_to_srgb

    sdr_linear = _srgb_to_linear(sdr_8bit)

    hdr_float = hdr_16bit.astype(np.float32) / 65535.0
    hdr_linear = _pq_to_linear(hdr_float, max_nits=10000.0)
    hdr_linear = clamp_small_negatives(linear_bt2020_to_srgb(hdr_linear / 100.0))

    eps = 1e-8
    ratio = np.maximum(hdr_linear, eps) / np.maximum(sdr_linear, eps)
    gain_log = np.log2(np.maximum(ratio, eps))

    log_min = -8.0
    log_max = 8.0
    gain_norm = (gain_log - log_min) / (log_max - log_min)
    gain_norm = np.clip(gain_norm, 0.0, 1.0)

    return (gain_norm * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


def _pq_to_linear(pq_values: np.ndarray, max_nits: float = 10000.0) -> np.ndarray:
    """Convert PQ-encoded values to linear nits using ST.2084 EOTF."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875

    pq = np.maximum(pq_values, 0.0)
    pq_pow = np.power(pq, 1.0 / m2)
    numerator = np.maximum(pq_pow - c1, 0.0)
    denominator = c2 - c3 * pq_pow
    linear = np.power(numerator / np.maximum(denominator, 1e-10), 1.0 / m1)
    return linear * max_nits


def _parse_cicp(cicp_str: str) -> tuple[int, int, int]:
    """Parse CICP string like '9/16/9' into (primaries, transfer, matrix)."""
    parts = cicp_str.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid CICP string: {cicp_str}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def combine(
    base_png: Path,
    alternate_png: Path,
    output_heic: Path,
    qcolor: int = 100,
    qgain_map: int = 100,
    depth_gain_map: int = 12,
    yuv_gain_map: str = "444",
    speed: int = 0,
    cicp_base: str = "1/13/1",
    cicp_alternate: str = "9/16/9",
    base_headroom: float | None = None,
    alternate_headroom: float | None = None,
) -> Path:
    """Combine SDR base PNG and HDR alternate PNG into a gainmap HEIC."""
    import imagecodecs
    from hdr_transcoder.formats.isobmff import build_heic_gainmap_container, encode_and_extract_hevc

    output_heic = Path(output_heic)
    output_heic.parent.mkdir(parents=True, exist_ok=True)

    sdr = np.asarray(imagecodecs.png_decode(base_png.read_bytes()))
    hdr = np.asarray(imagecodecs.png_decode(alternate_png.read_bytes()))
    if sdr.ndim == 3 and sdr.shape[2] >= 3:
        sdr_rgb = sdr[..., :3]
    else:
        sdr_rgb = sdr
    if hdr.ndim == 3 and hdr.shape[2] >= 3:
        hdr_rgb = hdr[..., :3]
    else:
        hdr_rgb = hdr

    hdr_16bit = hdr_rgb
    if hdr_rgb.dtype != np.uint16:
        hdr_float = np.clip(hdr_rgb.astype(np.float32) / 255.0, 0.0, 1.0) if hdr_rgb.dtype == np.uint8 else hdr_rgb.astype(np.float32)
        if hdr_float.max() <= 1.0:
            hdr_16bit = (hdr_float * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)
        else:
            hdr_16bit = hdr_float.astype(np.uint16)

    gainmap = _compute_gain_map(sdr_rgb, hdr_16bit)

    base_p, base_t, base_m = _parse_cicp(cicp_base)
    alt_p, alt_t, alt_m = _parse_cicp(cicp_alternate)

    sdr_hvcC, sdr_bitstream, sdr_w, sdr_h = encode_and_extract_hevc(
        sdr_rgb, color_primaries=base_p, transfer_characteristics=base_t,
        matrix_coefficients=base_m, full_range_flag=1,
        quality=qcolor,
    )

    alt_hvcC, alt_bitstream, alt_w, alt_h = encode_and_extract_hevc(
        hdr_16bit, color_primaries=alt_p, transfer_characteristics=alt_t,
        matrix_coefficients=alt_m, full_range_flag=1,
        quality=qcolor,
    )

    gm_rgb = np.stack([gainmap] * 3, axis=-1) if gainmap.ndim == 2 else gainmap
    gm_hvcC, gm_bitstream, gm_w, gm_h = encode_and_extract_hevc(
        gm_rgb, color_primaries=1, transfer_characteristics=13,
        matrix_coefficients=1, full_range_flag=1,
        quality=qgain_map,
    )

    bh = base_headroom if base_headroom is not None else 0.0
    ah = alternate_headroom if alternate_headroom is not None else 3.0

    container = build_heic_gainmap_container(
        sdr_bitstream=sdr_bitstream,
        sdr_hvcC=sdr_hvcC,
        alt_bitstream=alt_bitstream,
        alt_hvcC=alt_hvcC,
        gainmap_bitstream=gm_bitstream,
        gainmap_hvcC=gm_hvcC,
        sdr_width=sdr_w,
        sdr_height=sdr_h,
        alt_width=alt_w,
        alt_height=alt_h,
        gainmap_width=gm_w,
        gainmap_height=gm_h,
        base_headroom=bh,
        alternate_headroom=ah,
    )

    output_heic.write_bytes(container)
    return output_heic


def printmetadata(heic_path: Path) -> None:
    """Print gainmap metadata from a HEIC file."""
    from hdr_transcoder.formats.isobmff import read_heic_gainmap_metadata

    metadata = read_heic_gainmap_metadata(heic_path)
    if metadata is None:
        print("No gain map metadata (tmap box) found")
        return

    print("Gain map metadata:")
    for line in metadata["raw"].splitlines():
        print(f"  {line}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: heifgainmaputil_hdr <command> [args]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  combine <base.png> <alt.png> <output.heic> [...]", file=sys.stderr)
        print("  printmetadata <file.heic>", file=sys.stderr)
        return 1

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "combine":
        if len(args) < 3:
            print("combine requires base.png alternate.png output.heic", file=sys.stderr)
            return 1

        base_png = Path(args[0])
        alt_png = Path(args[1])
        output_heic = Path(args[2])
        extra = args[3:]

        qcolor = 100
        qgain_map = 100
        depth_gain_map = 12
        yuv_gain_map = "444"
        speed = 0
        cicp_base = "1/13/1"
        cicp_alternate = "9/16/9"
        base_headroom = None
        alternate_headroom = None

        i = 0
        while i < len(extra):
            arg = extra[i]
            if arg == "--qcolor" or arg == "-q":
                qcolor = int(extra[i + 1]); i += 2
            elif arg == "--qgain-map":
                qgain_map = int(extra[i + 1]); i += 2
            elif arg == "--depth-gain-map":
                depth_gain_map = int(extra[i + 1]); i += 2
            elif arg == "--yuv-gain-map":
                yuv_gain_map = extra[i + 1]; i += 2
            elif arg == "--speed" or arg == "-s":
                speed = int(extra[i + 1]); i += 2
            elif arg == "--cicp-base":
                cicp_base = extra[i + 1]; i += 2
            elif arg == "--cicp-alternate":
                cicp_alternate = extra[i + 1]; i += 2
            elif arg == "--base-headroom":
                base_headroom = float(extra[i + 1]); i += 2
            elif arg == "--alternate-headroom":
                alternate_headroom = float(extra[i + 1]); i += 2
            elif arg.startswith("--qcolor="):
                qcolor = int(arg.split("=", 1)[1]); i += 1
            elif arg.startswith("--qgain-map="):
                qgain_map = int(arg.split("=", 1)[1]); i += 1
            elif arg.startswith("--depth-gain-map="):
                depth_gain_map = int(arg.split("=", 1)[1]); i += 1
            elif arg.startswith("--yuv-gain-map="):
                yuv_gain_map = arg.split("=", 1)[1]; i += 1
            elif arg.startswith("--speed="):
                speed = int(arg.split("=", 1)[1]); i += 1
            elif arg.startswith("--cicp-base="):
                cicp_base = arg.split("=", 1)[1]; i += 1
            elif arg.startswith("--cicp-alternate="):
                cicp_alternate = arg.split("=", 1)[1]; i += 1
            elif arg.startswith("--base-headroom="):
                base_headroom = float(arg.split("=", 1)[1]); i += 1
            elif arg.startswith("--alternate-headroom="):
                alternate_headroom = float(arg.split("=", 1)[1]); i += 1
            elif arg in ("-h", "--help"):
                print(__doc__)
                return 0
            else:
                i += 1

        try:
            result = combine(
                base_png, alt_png, output_heic,
                qcolor=qcolor, qgain_map=qgain_map,
                depth_gain_map=depth_gain_map,
                yuv_gain_map=yuv_gain_map,
                speed=speed,
                cicp_base=cicp_base,
                cicp_alternate=cicp_alternate,
                base_headroom=base_headroom,
                alternate_headroom=alternate_headroom,
            )
            print(f"Wrote gainmap HEIC: {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    elif command == "printmetadata":
        if len(args) < 1:
            print("printmetadata requires a HEIC file path", file=sys.stderr)
            return 1
        try:
            printmetadata(Path(args[0]))
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
