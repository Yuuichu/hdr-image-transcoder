"""JPEG XL HDR output encoder."""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from hdr_transcoder.color import clamp_small_negatives, linear_srgb_to_bt2020
from hdr_transcoder.config import JXL_ENCODE_TIMEOUT_SECONDS
from hdr_transcoder.tools import CJXL

JXL_MODE_REC2020_PQ = "rec2020-pq"
JXL_MODE_LINEAR_SRGB = "linear-srgb"
JXL_MODES = {JXL_MODE_REC2020_PQ, JXL_MODE_LINEAR_SRGB}


def require_cjxl():
    if not CJXL.exists():
        raise FileNotFoundError(
            f"Missing JPEG XL encoder: {CJXL}. "
            f"Re-download the full package or place cjxl.exe at {CJXL}."
        )


def jxl_distance(quality, lossless):
    if lossless:
        return 0.0
    return max((100 - quality) / 20.0, 0.0)


def as_finite_float32_rgb(pixels_rgb, context="pixels"):
    rgb = np.asarray(pixels_rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"{context} must be RGB image data, got shape {rgb.shape}")
    invalid = ~np.isfinite(rgb)
    if invalid.any():
        count = int(np.count_nonzero(invalid))
        raise ValueError(f"{context} contains {count} NaN or Infinity sample(s)")
    return rgb


def write_pfm(path, pixels_rgb):
    """Write float32 RGB PFM. PFM stores scanlines bottom-up."""
    rgb = np.flip(as_finite_float32_rgb(pixels_rgb, "PFM input"), axis=0)
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError(f"PFM requires RGB data, got {channels} channels")

    with open(path, "wb") as f:
        f.write(f"PF\n{width} {height}\n-1.0\n".encode("ascii"))
        f.write(rgb.tobytes())


def to_nonnegative_bt2020(rgb, context):
    bt2020 = clamp_small_negatives(linear_srgb_to_bt2020(rgb))
    min_value = float(np.min(bt2020)) if bt2020.size else 0.0
    if min_value < 0.0:
        print(
            f"Warning: {context} contains colors outside Rec.2020; clipping negative channels.",
            file=sys.stderr,
        )
    return np.maximum(bt2020, 0.0)


def run_cjxl(input_path, output_path, distance, effort, color_space, intensity_target=None):
    require_cjxl()

    cmd = [
        str(CJXL),
        str(input_path),
        str(output_path),
        "--distance",
        f"{distance:.6f}",
        "--effort",
        str(effort),
        "--container=1",
        "-x",
        f"color_space={color_space}",
        "--quiet",
    ]
    if intensity_target is not None:
        cmd.append(f"--intensity_target={intensity_target}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JXL_ENCODE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"cjxl timed out after {JXL_ENCODE_TIMEOUT_SECONDS}s") from exc

    if result.stderr and result.stderr.strip():
        from textwrap import indent

        print(f"cjxl stderr:\n{indent(result.stderr.strip(), '  ')}", file=sys.stderr)
    if result.returncode != 0:
        from textwrap import indent

        detail = ""
        if result.stderr:
            detail += f"\nSTDERR:\n{indent(result.stderr.strip(), '  ')}"
        if result.stdout:
            detail += f"\nSTDOUT:\n{indent(result.stdout.strip(), '  ')}"
        raise RuntimeError(f"cjxl exited with code {result.returncode}{detail}")


def encode_jxl_rec2020_pq(pixels_rgb, output_path, quality, lossless, effort):
    from hdr_transcoder.processor import _linear_to_pq
    import imagecodecs

    pixels_rgb = as_finite_float32_rgb(pixels_rgb, "JXL input")
    bt2020_rgb = to_nonnegative_bt2020(pixels_rgb, "JXL Rec.2020 PQ input")
    luminance = bt2020_rgb * 100.0
    pq = _linear_to_pq(luminance)
    pq_16bit = (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.png"
        input_path.write_bytes(imagecodecs.png_encode(pq_16bit))
        run_cjxl(
            input_path,
            output_path,
            distance=jxl_distance(quality, lossless),
            effort=effort,
            color_space="RGB_D65_202_Rel_PeQ",
            intensity_target=10000,
        )


def encode_jxl_linear_srgb(pixels_rgb, output_path, quality, lossless, effort):
    pixels_rgb = as_finite_float32_rgb(pixels_rgb, "JXL input")
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.pfm"
        write_pfm(input_path, pixels_rgb)
        run_cjxl(
            input_path,
            output_path,
            distance=jxl_distance(quality, lossless),
            effort=effort,
            color_space="RGB_D65_SRG_Rel_Lin",
        )


def encode_jxl(pixels_rgb, output_path, quality=100, lossless=False, effort=7,
               mode=JXL_MODE_REC2020_PQ):
    if mode not in JXL_MODES:
        raise ValueError(f"Unknown JXL mode: {mode}. Supported: {', '.join(sorted(JXL_MODES))}")

    if mode == JXL_MODE_LINEAR_SRGB:
        encode_jxl_linear_srgb(pixels_rgb, output_path, quality, lossless, effort)
    else:
        encode_jxl_rec2020_pq(pixels_rgb, output_path, quality, lossless, effort)

    return output_path
