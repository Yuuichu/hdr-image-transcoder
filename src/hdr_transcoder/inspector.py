"""Image inspection and debug-overlay helpers."""
import argparse
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import wrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hdr_transcoder.color import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_BT709_MATRIX,
    CICP_BT709_PRIMARIES,
    CICP_PQ_TRANSFER,
    CICP_SRGB_TRANSFER,
)
from hdr_transcoder.config import GAINMAP_HEADROOM_TOLERANCE_STOPS
from hdr_transcoder.formats.decoder import (
    AVIFDEC,
    SUPPORTED_FORMATS,
    _read_avif_cicp,
    _read_jxl_info,
    decode_to_scrgb,
    probe_format,
)
from hdr_transcoder.formats.gainmap import AVIFGAINMAPUTIL
from hdr_transcoder.processor import prepare_base_sdr


HEADROOM_RE = re.compile(
    r"(Base|Alternate) headroom:\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*\(as fraction:\s*([0-9]+)/([0-9]+)\)",
    re.IGNORECASE,
)

PRIMARIES_LABELS = {
    CICP_BT709_PRIMARIES: "BT.709 / sRGB",
    CICP_BT2020_PRIMARIES: "Rec.2020",
}

TRANSFER_LABELS = {
    CICP_SRGB_TRANSFER: "sRGB",
    CICP_PQ_TRANSFER: "PQ / ST.2084",
    8: "Linear",
}

MATRIX_LABELS = {
    0: "RGB identity",
    CICP_BT709_MATRIX: "BT.709",
    6: "BT.601",
    CICP_BT2020_MATRIX: "Rec.2020 NCL",
}


def _label(mapping, value):
    if value is None:
        return "Unknown"
    return mapping.get(value, f"Unknown ({value})")


def _safe_float(value):
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return value


def _source_peak_headroom(peak):
    return math.log2(max(float(peak), 1.0))


def _inspect_avif_gainmap(path):
    info = {"present": False}
    if not AVIFGAINMAPUTIL.exists():
        info["warning"] = f"Missing avifgainmaputil.exe: {AVIFGAINMAPUTIL}"
        return info

    try:
        result = subprocess.run(
            [str(AVIFGAINMAPUTIL), "printmetadata", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        info["warning"] = "avifgainmaputil printmetadata timed out"
        return info

    if result.returncode != 0:
        text = (result.stderr or result.stdout or "").strip()
        if "does not contain a gain map" not in text:
            info["warning"] = text or f"printmetadata exited with {result.returncode}"
        return info

    info["present"] = True
    info["raw"] = result.stdout
    for match in HEADROOM_RE.finditer(result.stdout):
        key = match.group(1).lower()
        info[f"{key}_headroom"] = _safe_float(match.group(2))
        info[f"{key}_headroom_fraction"] = {
            "numerator": int(match.group(3)),
            "denominator": int(match.group(4)),
        }
    return info


def _inspect_avif_alternate_color(path, warnings):
    if not AVIFDEC.exists():
        warnings.append(f"Missing avifdec.exe: {AVIFDEC}")
        return None
    try:
        result = subprocess.run(
            [str(AVIFDEC), "--info", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        warnings.append("avifdec --info timed out")
        return None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        warnings.append(f"avifdec --info failed: {detail}")
        return None

    text = f"{result.stdout}\n{result.stderr}"
    marker = re.search(r"\*\s+Alternate image:", text)
    if not marker:
        return None
    block = text[marker.end() : marker.end() + 400]
    fields = {}
    patterns = {
        "primaries": r"Color Primaries:\s*(\d+)",
        "transfer": r"Transfer Char\.\s*:\s*(\d+)",
        "matrix": r"Matrix Coeffs\.\s*:\s*(\d+)",
        "bit_depth": r"Bit Depth\s*:\s*(\d+)",
        "planes": r"Planes\s*:\s*(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, block)
        if match:
            fields[key] = int(match.group(1))
    if not fields:
        return None
    fields["primaries_label"] = _label(PRIMARIES_LABELS, fields.get("primaries"))
    fields["transfer_label"] = _label(TRANSFER_LABELS, fields.get("transfer"))
    fields["matrix_label"] = _label(MATRIX_LABELS, fields.get("matrix"))
    fields["source"] = "avifdec alternate image"
    return fields


def _inspect_color_metadata(path, fmt, warnings):
    raw = path.read_bytes()
    color = {
        "primaries": None,
        "primaries_label": "Unknown",
        "transfer": None,
        "transfer_label": "Unknown",
        "matrix": None,
        "matrix_label": "Unknown",
        "source": None,
    }

    if fmt == "avif":
        cicp = _read_avif_cicp(raw)
        color.update(
            {
                "primaries": cicp.get("primaries"),
                "transfer": cicp.get("transfer"),
                "matrix": cicp.get("matrix"),
                "source": "avif CICP",
            }
        )
    elif fmt == "jpegxl":
        try:
            jxl = _read_jxl_info(raw)
            color.update(
                {
                    "primaries": jxl.get("primaries"),
                    "transfer_name": jxl.get("transfer"),
                    "source": "jxlinfo",
                }
            )
            if jxl.get("transfer") == "pq":
                color["transfer"] = CICP_PQ_TRANSFER
            elif jxl.get("transfer") == "srgb":
                color["transfer"] = CICP_SRGB_TRANSFER
            elif jxl.get("transfer") == "linear":
                color["transfer"] = 8
        except Exception as exc:
            warnings.append(f"JXL metadata unavailable: {exc}")
    elif fmt == "heif":
        try:
            import pillow_heif

            heif = pillow_heif.open_heif(path, convert_hdr_to_8bit=False)
            nclx = heif[0].info.get("nclx_profile") or {}
            color.update(
                {
                    "primaries": nclx.get("color_primaries"),
                    "transfer": nclx.get("transfer_characteristics"),
                    "matrix": nclx.get("matrix_coefficients"),
                    "source": "HEIF nclx",
                }
            )
        except Exception as exc:
            warnings.append(f"HEIF nclx metadata unavailable: {exc}")

    color["primaries_label"] = _label(PRIMARIES_LABELS, color.get("primaries"))
    color["transfer_label"] = _label(TRANSFER_LABELS, color.get("transfer"))
    color["matrix_label"] = _label(MATRIX_LABELS, color.get("matrix"))
    return color


def inspect_image(path):
    """Return structured technical information for one image."""
    path = Path(path)
    warnings = []
    result = {
        "path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else None,
        "detected_format": None,
        "format_name": "Unknown",
        "width": None,
        "height": None,
        "channels": None,
        "dtype": None,
        "hdr": {},
        "color": {},
        "gainmap": {},
        "warnings": warnings,
        "error": None,
    }

    if not path.exists():
        result["error"] = "File does not exist"
        return result

    fmt = probe_format(str(path))
    result["detected_format"] = fmt
    result["format_name"] = SUPPORTED_FORMATS.get(fmt, (fmt or "unknown", []))[0]

    if fmt in {"avif", "jpegxl", "heif"}:
        result["color"] = _inspect_color_metadata(path, fmt, warnings)
    if fmt == "avif":
        result["gainmap"] = _inspect_avif_gainmap(path)
        alternate_color = _inspect_avif_alternate_color(path, warnings)
        if alternate_color:
            result["gainmap"]["alternate_color"] = alternate_color

    try:
        pixels, width, height = decode_to_scrgb(str(path))
    except Exception as exc:
        result["error"] = str(exc)
        return result

    rgb = np.asarray(pixels[..., :3], dtype=np.float32)
    invalid = ~np.isfinite(rgb)
    finite_rgb = rgb[np.isfinite(rgb)]
    peak = float(np.max(finite_rgb)) if finite_rgb.size else None
    rgb_min = float(np.min(finite_rgb)) if finite_rgb.size else None
    non_finite_count = int(np.count_nonzero(invalid))
    if non_finite_count:
        warnings.append(f"Decoded pixels contain {non_finite_count} non-finite RGB sample(s)")

    result.update(
        {
            "width": int(width),
            "height": int(height),
            "channels": int(pixels.shape[2]) if pixels.ndim == 3 else None,
            "dtype": str(pixels.dtype),
        }
    )
    result["hdr"] = {
        "is_hdr": bool(peak is not None and peak > 1.0),
        "rgb_min": rgb_min,
        "rgb_max": peak,
        "peak_headroom": _source_peak_headroom(peak) if peak is not None else None,
        "non_finite_count": non_finite_count,
    }

    gainmap = result.get("gainmap") or {}
    alternate = gainmap.get("alternate_headroom")
    peak_headroom = result["hdr"].get("peak_headroom")
    if (
        alternate is not None
        and peak_headroom is not None
        and alternate + GAINMAP_HEADROOM_TOLERANCE_STOPS < peak_headroom
    ):
        warnings.append(
            f"Gainmap alternate headroom {alternate:.3f} is below decoded peak headroom {peak_headroom:.3f}"
        )
    if fmt in {"avif", "heif"} and not result.get("color", {}).get("transfer"):
        warnings.append("HDR color metadata was not detected")

    return result


def _format_float(value, digits=3):
    if value is None:
        return "Unknown"
    return f"{float(value):.{digits}f}"


def overlay_lines(info):
    """Return compact lines suitable for drawing on an image."""
    color = info.get("color") or {}
    hdr = info.get("hdr") or {}
    gainmap = info.get("gainmap") or {}
    lines = [
        "HDR Transcoder Debug",
        f"File: {info.get('filename')}",
        f"Format: {info.get('format_name')} ({info.get('detected_format')})",
        f"Size: {info.get('width')}x{info.get('height')}",
        (
            "Color: "
            f"{color.get('primaries_label', 'Unknown')} / "
            f"{color.get('transfer_label', 'Unknown')} / "
            f"{color.get('matrix_label', 'Unknown')}"
        ),
        (
            "Peak: "
            f"{_format_float(hdr.get('rgb_max'))} scRGB, "
            f"{_format_float(hdr.get('peak_headroom'))} stops"
        ),
    ]
    if gainmap.get("present"):
        lines.append(
            "Gainmap: "
            f"base {_format_float(gainmap.get('base_headroom'))} stops, "
            f"alternate {_format_float(gainmap.get('alternate_headroom'))} stops"
        )
        alternate_color = gainmap.get("alternate_color") or {}
        if alternate_color:
            lines.append(
                "Alt Color: "
                f"{alternate_color.get('primaries_label', 'Unknown')} / "
                f"{alternate_color.get('transfer_label', 'Unknown')} / "
                f"{alternate_color.get('matrix_label', 'Unknown')}"
            )
    for warning in (info.get("warnings") or [])[:3]:
        lines.append(f"Warning: {warning}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return lines


def _load_font(size):
    candidates = [
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def _wrap_lines(lines, width, font):
    sample_bbox = font.getbbox("M")
    char_width = max(sample_bbox[2] - sample_bbox[0], 1)
    max_chars = max((width - 24) // char_width, 16)
    wrapped = []
    for line in lines:
        wrapped.extend(wrap(line, width=max_chars) or [""])
    return wrapped


def create_debug_overlay(image_path, overlay_path=None, info=None):
    """Create an SDR PNG with debug text overlaid. Returns the output path."""
    image_path = Path(image_path)
    if overlay_path is None:
        overlay_path = image_path.with_name(f"{image_path.stem}_debug.png")
    overlay_path = Path(overlay_path)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)

    if info is None:
        info = inspect_image(image_path)
    if info.get("error"):
        raise ValueError(f"Cannot create debug overlay: {info['error']}")

    pixels, width, height = decode_to_scrgb(str(image_path))
    sdr = prepare_base_sdr(pixels[..., :3], headroom=2.0)
    image = Image.fromarray(sdr, mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")

    font_size = max(10, min(22, int(max(width, height) / 55)))
    font = _load_font(font_size)
    lines = _wrap_lines(overlay_lines(info), width, font)
    line_height = max(font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 4, font_size + 4)
    padding = max(8, font_size // 2)
    max_lines = max(1, int((height * 0.4 - padding * 2) // line_height))
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["..."]

    text_width = 0
    for line in lines:
        bbox = font.getbbox(line)
        text_width = max(text_width, bbox[2] - bbox[0])
    box_width = min(width, text_width + padding * 2)
    box_height = min(height, len(lines) * line_height + padding * 2)
    draw.rectangle((0, 0, box_width, box_height), fill=(0, 0, 0, 175))

    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=(255, 255, 255, 245), font=font)
        y += line_height

    image.save(overlay_path)
    return overlay_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect HDR image metadata and decoded peak information.")
    parser.add_argument("paths", nargs="+", help="Image file(s) to inspect")
    parser.add_argument("--overlay", action="store_true", help="Create debug overlay PNG(s)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    results = []
    for path in args.paths:
        info = inspect_image(path)
        if args.overlay and not info.get("error"):
            info["debug_overlay_path"] = str(create_debug_overlay(path, info=info))
        results.append(info)

    payload = results[0] if len(results) == 1 else results
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main(sys.argv[1:])
