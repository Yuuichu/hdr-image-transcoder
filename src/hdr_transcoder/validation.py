"""Runtime fidelity validation shared by CLI and tests."""
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from hdr_transcoder.config import (
    BT2020_PQ_CICP,
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_PQ_TRANSFER,
    DISPLAY_PEAK_TOLERANCE_SCRGB,
    GAINMAP_DECODE_PEAK_TOLERANCE_STOPS,
    GAINMAP_HEADROOM_TOLERANCE_STOPS,
    JXL_MASTER_PEAK_TOLERANCE_SCRGB,
)
from hdr_transcoder.formats.decoder import _read_avif_cicp, _read_jxl_info, decode_to_scrgb
from hdr_transcoder.formats.jxl import JXL_MODE_LINEAR_SRGB, JXL_MODE_REC2020_PQ
from hdr_transcoder.tools import AVIFDEC, AVIFGAINMAPUTIL

HEADROOM_FLOAT_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def source_peak_headroom(source_pixels):
    source_peak = max(float(np.max(source_pixels[..., :3])), 1.0)
    return math.log2(source_peak)


def stop_delta(left_peak, right_peak):
    if left_peak <= 0 or right_peak <= 0:
        return float("inf")
    return abs(math.log2(right_peak / left_peak))


def verify_peak(source_pixels, output_path, tolerance=DISPLAY_PEAK_TOLERANCE_SCRGB):
    decoded, width, height = decode_to_scrgb(str(output_path))
    if decoded.shape[:2] != source_pixels.shape[:2]:
        raise ValueError(f"Fidelity verify failed: output dimensions are {width}x{height}")
    source_peak = float(np.max(source_pixels[..., :3]))
    output_peak = float(np.max(decoded[..., :3]))
    delta = abs(source_peak - output_peak)
    if delta > tolerance:
        raise ValueError(
            "Fidelity verify failed: HDR peak changed "
            f"source_peak={source_peak:.4f}, output_peak={output_peak:.4f}, "
            f"delta={delta:.4f}, tolerance={tolerance:.4f} scRGB"
        )
    print(f"  Fidelity verify: peak {output_peak:.4f} (source {source_peak:.4f}, delta {delta:.4f})")
    return {"sourcePeak": source_peak, "outputPeak": output_peak, "delta": delta, "tolerance": tolerance}


def verify_peak_stops(source_pixels, output_path, tolerance_stops=GAINMAP_DECODE_PEAK_TOLERANCE_STOPS):
    decoded, width, height = decode_to_scrgb(str(output_path))
    if decoded.shape[:2] != source_pixels.shape[:2]:
        raise ValueError(f"Fidelity verify failed: output dimensions are {width}x{height}")
    source_peak = float(np.max(source_pixels[..., :3]))
    output_peak = float(np.max(decoded[..., :3]))
    delta = stop_delta(source_peak, output_peak)
    if delta > tolerance_stops:
        raise ValueError(
            "Fidelity verify failed: decoded gainmap peak drift "
            f"source_peak={source_peak:.4f}, output_peak={output_peak:.4f}, "
            f"delta={delta:.4f} stops, tolerance={tolerance_stops:.4f} stops"
        )
    print(
        "  Fidelity verify: gainmap decoded peak "
        f"{output_peak:.4f} (source {source_peak:.4f}, delta {delta:.4f} stops)"
    )
    return {"sourcePeak": source_peak, "outputPeak": output_peak, "deltaStops": delta, "toleranceStops": tolerance_stops}


def verify_jxl_metadata(output_path, jxl_mode):
    info = _read_jxl_info(Path(output_path).read_bytes())
    if jxl_mode == JXL_MODE_LINEAR_SRGB and info.get("transfer") != "linear":
        raise ValueError("Fidelity verify failed: JXL master output is not linear")
    if jxl_mode == JXL_MODE_REC2020_PQ and info.get("transfer") != "pq":
        raise ValueError("Fidelity verify failed: JXL display output is not PQ")
    print(f"  Fidelity verify: JXL transfer={info.get('transfer')}")
    return info


def verify_avif_metadata(output_path):
    cicp = _read_avif_cicp(Path(output_path).read_bytes())
    if any(cicp.get(key) != value for key, value in BT2020_PQ_CICP.items()):
        raise ValueError(f"Fidelity verify failed: AVIF CICP is {cicp}, expected {BT2020_PQ_CICP}")
    print("  Fidelity verify: AVIF CICP=9/16/9")
    return cicp


def _read_gainmap_metadata(output_path):
    result = subprocess.run(
        [str(AVIFGAINMAPUTIL), "printmetadata", str(output_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ValueError(f"Fidelity verify failed: cannot read gain map metadata: {detail}")

    payload = {"raw": result.stdout}
    for label in ("Base", "Alternate"):
        match = re.search(rf"{label} headroom:\s*({HEADROOM_FLOAT_RE})", result.stdout)
        if match:
            payload[f"{label.lower()}Headroom"] = float(match.group(1))
    return payload


def _read_gainmap_alternate_cicp(output_path):
    if not AVIFDEC.exists():
        raise ValueError(f"Fidelity verify failed: missing avifdec.exe for alternate CICP: {AVIFDEC}")
    result = subprocess.run(
        [str(AVIFDEC), "--info", str(output_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ValueError(f"Fidelity verify failed: avifdec --info failed: {detail}")

    text = f"{result.stdout}\n{result.stderr}"
    marker = re.search(r"\*\s+Alternate image:", text)
    if not marker:
        raise ValueError("Fidelity verify failed: AVIF gainmap alternate image metadata missing")
    block = text[marker.end(): marker.end() + 400]
    patterns = {
        "primaries": r"Color Primaries:\s*(\d+)",
        "transfer": r"Transfer Char\.\s*:\s*(\d+)",
        "matrix": r"Matrix Coeffs\.\s*:\s*(\d+)",
    }
    cicp = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, block)
        if match:
            cicp[key] = int(match.group(1))
    return cicp


def _read_heic_gainmap_metadata(output_path):
    """Parse tmap box from gainmap HEIC to get base/alternate headroom."""
    from hdr_transcoder.formats.isobmff import read_heic_container, read_heic_gainmap_metadata_from_container

    container = read_heic_container(output_path)
    if container is None:
        raise ValueError("Fidelity verify failed: HEIC missing gain map metadata container")
    metadata = read_heic_gainmap_metadata_from_container(container)
    if metadata is None:
        raise ValueError("Fidelity verify failed: gain map tmap box missing")
    return metadata


def _read_heic_gainmap_alternate_cicp(output_path):
    """Extract CICP from alternate image's colr nclx box in a gainmap HEIC."""
    from hdr_transcoder.formats.isobmff import read_heic_gainmap_alternate_cicp

    cicp = read_heic_gainmap_alternate_cicp(output_path)
    if cicp is None:
        raise ValueError("Fidelity verify failed: alternate image colr with PQ transfer not found in HEIC")
    return cicp


def verify_heic_gainmap_headroom(source_pixels, output_path, tolerance_stops=GAINMAP_HEADROOM_TOLERANCE_STOPS):
    required = source_peak_headroom(source_pixels)
    metadata = _read_heic_gainmap_metadata(output_path)
    alternate = metadata.get("alternateHeadroom")
    if alternate is None:
        raise ValueError("Fidelity verify failed: HEIC gain map alternate headroom missing")

    delta = required - alternate
    if delta > tolerance_stops:
        raise ValueError(
            "Fidelity verify failed: HEIC gain map alternate headroom below source peak "
            f"source_peak_headroom={required:.4f} stops, "
            f"actual_headroom={alternate:.4f} stops, "
            f"delta={delta:.4f} stops, tolerance={tolerance_stops:.4f} stops"
        )
    print(
        "  Fidelity verify: HEIC gain map alternate headroom "
        f"{alternate:.4f} stops (source {required:.4f}, delta {max(delta, 0.0):.4f}, "
        f"tolerance {tolerance_stops:.4f})"
    )
    return {
        "sourcePeakHeadroom": required,
        "actualHeadroom": alternate,
        "deltaStops": max(delta, 0.0),
        "toleranceStops": tolerance_stops,
        "baseHeadroom": metadata.get("baseHeadroom"),
    }


def verify_heic_gainmap_alternate_color(output_path):
    cicp = _read_heic_gainmap_alternate_cicp(output_path)
    expected = {
        "primaries": CICP_BT2020_PRIMARIES,
        "transfer": CICP_PQ_TRANSFER,
        "matrix": CICP_BT2020_MATRIX,
    }
    if any(cicp.get(key) != value for key, value in expected.items()):
        raise ValueError(f"Fidelity verify failed: HEIC gainmap alternate CICP is {cicp}, expected {expected}")
    print("  Fidelity verify: HEIC gainmap alternate CICP=9/16/9")
    return cicp


def verify_gainmap_headroom(source_pixels, output_path, tolerance_stops=GAINMAP_HEADROOM_TOLERANCE_STOPS):
    required = source_peak_headroom(source_pixels)
    metadata = _read_gainmap_metadata(output_path)
    alternate = metadata.get("alternateHeadroom")
    if alternate is None:
        raise ValueError("Fidelity verify failed: gain map alternate headroom missing")

    delta = required - alternate
    if delta > tolerance_stops:
        raise ValueError(
            "Fidelity verify failed: gain map alternate headroom below source peak "
            f"source_peak_headroom={required:.4f} stops, "
            f"actual_headroom={alternate:.4f} stops, "
            f"delta={delta:.4f} stops, tolerance={tolerance_stops:.4f} stops"
        )
    print(
        "  Fidelity verify: gain map alternate headroom "
        f"{alternate:.4f} stops (source {required:.4f}, delta {max(delta, 0.0):.4f}, "
        f"tolerance {tolerance_stops:.4f})"
    )
    return {
        "sourcePeakHeadroom": required,
        "actualHeadroom": alternate,
        "deltaStops": max(delta, 0.0),
        "toleranceStops": tolerance_stops,
        "baseHeadroom": metadata.get("baseHeadroom"),
    }


def verify_gainmap_alternate_color(output_path):
    cicp = _read_gainmap_alternate_cicp(output_path)
    expected = {
        "primaries": CICP_BT2020_PRIMARIES,
        "transfer": CICP_PQ_TRANSFER,
        "matrix": CICP_BT2020_MATRIX,
    }
    if any(cicp.get(key) != value for key, value in expected.items()):
        raise ValueError(f"Fidelity verify failed: gainmap alternate CICP is {cicp}, expected {expected}")
    print("  Fidelity verify: gainmap alternate CICP=9/16/9")
    return cicp


def verify_output(source_pixels, output_path, output_format, jxl_mode):
    result = {"ok": True, "checks": {}}
    if output_format == "jxl":
        result["checks"]["metadata"] = verify_jxl_metadata(output_path, jxl_mode)
        tolerance = JXL_MASTER_PEAK_TOLERANCE_SCRGB if jxl_mode == JXL_MODE_LINEAR_SRGB else DISPLAY_PEAK_TOLERANCE_SCRGB
        result["checks"]["peak"] = verify_peak(source_pixels, output_path, tolerance=tolerance)
    elif output_format == "avif":
        result["checks"]["metadata"] = verify_avif_metadata(output_path)
        result["checks"]["peak"] = verify_peak(source_pixels, output_path)
    elif output_format == "gainmap":
        result["checks"]["headroom"] = verify_gainmap_headroom(source_pixels, output_path)
        result["checks"]["alternateColor"] = verify_gainmap_alternate_color(output_path)
        result["checks"]["peak"] = verify_peak_stops(source_pixels, output_path)
    elif output_format == "gainmap-heic":
        result["checks"]["headroom"] = verify_heic_gainmap_headroom(source_pixels, output_path)
        result["checks"]["alternateColor"] = verify_heic_gainmap_alternate_color(output_path)
        result["checks"]["peak"] = verify_peak_stops(source_pixels, output_path)
    else:
        result["checks"]["peak"] = verify_peak(source_pixels, output_path)
    return result
