"""Layered validation for HDR delivery and gainmap outputs."""
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

from hdr_transcoder.color import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_BT709_MATRIX,
    CICP_BT709_PRIMARIES,
    CICP_PQ_TRANSFER,
    CICP_SRGB_TRANSFER,
)
from hdr_transcoder.config import (
    BT2020_PQ_CICP,
    DISPLAY_DECODE_PEAK_TOLERANCE_STOPS,
    GAINMAP_DECODE_PEAK_TOLERANCE_STOPS,
    GAINMAP_HEADROOM_TOLERANCE_STOPS,
    PROJECT_ROOT,
    ULTRAHDR_DECODE_PEAK_TOLERANCE_STOPS,
)
from hdr_transcoder.formats.decoder import _read_avif_cicp, decode_to_scrgb
from hdr_transcoder.processor import _srgb_inverse_gamma, prepare_base_sdr
from hdr_transcoder.tools import AVIFDEC, AVIFGAINMAPUTIL
from hdr_transcoder.validation import (
    _read_gainmap_alternate_cicp,
    _read_gainmap_metadata,
    source_peak_headroom,
    stop_delta,
    verify_avif_metadata,
    verify_jxl_metadata,
)


STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_FAIL = "fail"
STATUS_SKIPPED = "skipped"


def _as_rgb_float(pixels):
    pixels = np.asarray(pixels)
    if pixels.ndim == 2:
        pixels = pixels[..., np.newaxis]
    if pixels.ndim != 3:
        raise ValueError(f"Expected image array with 2 or 3 dimensions, got {pixels.shape}")
    if pixels.shape[2] == 1:
        pixels = np.repeat(pixels, 3, axis=2)
    if pixels.shape[2] > 3:
        pixels = pixels[..., :3]
    if np.issubdtype(pixels.dtype, np.floating):
        return np.clip(pixels.astype(np.float32), 0.0, 1.0)
    if not np.issubdtype(pixels.dtype, np.integer):
        raise TypeError(f"Unsupported image dtype: {pixels.dtype}")
    info = np.iinfo(pixels.dtype)
    return np.clip(pixels.astype(np.float32) / float(info.max), 0.0, 1.0)


def _decode_png_or_jpeg_to_sdr_linear(path):
    import imagecodecs

    suffix = Path(path).suffix.lower()
    raw = Path(path).read_bytes()
    if suffix in {".jpg", ".jpeg"}:
        pixels = imagecodecs.jpeg_decode(raw)
    else:
        pixels = imagecodecs.png_decode(raw)
    return _srgb_inverse_gamma(_as_rgb_float(pixels))


def _write_png(path, pixels):
    import imagecodecs

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(pixels)
    if np.issubdtype(array.dtype, np.floating):
        array = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    path.write_bytes(imagecodecs.png_encode(array))
    return path


def _falsecolor_diff(diff):
    diff = np.asarray(diff, dtype=np.float32)
    if diff.ndim == 3:
        diff = np.max(np.abs(diff[..., :3]), axis=-1)
    scale = np.percentile(diff, 99.0) if diff.size else 1.0
    scale = max(float(scale), 1e-6)
    norm = np.clip(diff / scale, 0.0, 1.0)
    return np.stack(
        [
            norm,
            np.clip(1.0 - np.abs(norm - 0.5) * 2.0, 0.0, 1.0),
            1.0 - norm,
        ],
        axis=-1,
    )


def _new_layer(name):
    return {
        "name": name,
        "status": STATUS_SKIPPED,
        "checks": [],
        "metrics": {},
        "artifacts": {},
    }


def _add_check(layer, name, status, message, **values):
    layer["checks"].append({
        "name": name,
        "status": status,
        "message": message,
        **values,
    })
    if status == STATUS_SKIPPED:
        return
    if status == STATUS_FAIL:
        layer["status"] = STATUS_FAIL
    elif status == STATUS_WARNING and layer["status"] not in {STATUS_FAIL}:
        layer["status"] = STATUS_WARNING
    elif layer["status"] == STATUS_SKIPPED:
        layer["status"] = STATUS_PASS


def _finalize_layer(layer):
    return layer


def _peak_metrics(pixels):
    rgb = np.maximum(np.asarray(pixels)[..., :3].astype(np.float32), 0.0)
    if rgb.size == 0:
        return {"max": 0.0, "p99": 0.0, "p999": 0.0, "mean": 0.0}
    flat = rgb.reshape(-1, rgb.shape[-1]).max(axis=1)
    return {
        "max": float(np.max(flat)),
        "p99": float(np.percentile(flat, 99.0)),
        "p999": float(np.percentile(flat, 99.9)),
        "mean": float(np.mean(flat)),
    }


def _sdr_diff_metrics(reference_linear, output_linear):
    diff = output_linear[..., :3] - reference_linear[..., :3]
    abs_diff = np.abs(diff)
    reference_luma = np.mean(reference_linear[..., :3], axis=-1)
    output_luma = np.mean(output_linear[..., :3], axis=-1)
    dark_mask = reference_luma < 0.02
    mid_mask = (reference_luma >= 0.18) & (reference_luma <= 0.60)
    clipping = np.mean(np.any(output_linear[..., :3] >= 0.999, axis=-1))
    return {
        "meanAbsRgb": float(np.mean(abs_diff)),
        "p95AbsRgb": float(np.percentile(abs_diff, 95.0)),
        "maxAbsRgb": float(np.max(abs_diff)),
        "blackLift": float(np.mean(output_luma[dark_mask] - reference_luma[dark_mask])) if dark_mask.any() else 0.0,
        "midtoneDelta": float(np.mean(output_luma[mid_mask] - reference_luma[mid_mask])) if mid_mask.any() else 0.0,
        "clippedPixelRatio": float(clipping),
    }


def _hdr_diff_metrics(source_pixels, reconstructed):
    source = np.maximum(source_pixels[..., :3].astype(np.float32), 0.0)
    output = np.maximum(reconstructed[..., :3].astype(np.float32), 0.0)
    source_peak = _peak_metrics(source)
    output_peak = _peak_metrics(output)
    diff = output - source
    source_luma = np.mean(source, axis=-1)
    output_luma = np.mean(output, axis=-1)
    highlight_mask = source_luma >= np.percentile(source_luma, 99.0) if source_luma.size else np.zeros(source_luma.shape, dtype=bool)
    return {
        "source": source_peak,
        "output": output_peak,
        "maxStopDelta": stop_delta(source_peak["max"], output_peak["max"]),
        "p99StopDelta": stop_delta(source_peak["p99"], output_peak["p99"]),
        "p999StopDelta": stop_delta(source_peak["p999"], output_peak["p999"]),
        "meanLuminanceDelta": float(np.mean(output_luma - source_luma)),
        "meanAbsRgb": float(np.mean(np.abs(diff))),
        "highlightMeanStopDelta": stop_delta(
            float(np.mean(source_luma[highlight_mask])) if highlight_mask.any() else source_peak["p99"],
            float(np.mean(output_luma[highlight_mask])) if highlight_mask.any() else output_peak["p99"],
        ),
        "clippedPixelRatio": float(np.mean(np.any(output >= 99.0, axis=-1))),
    }


def _gainmap_metrics(pixels):
    data = _as_rgb_float(pixels)
    flat = data.reshape(-1, data.shape[-1])
    return {
        "width": int(data.shape[1]),
        "height": int(data.shape[0]),
        "channels": int(data.shape[2]),
        "min": float(np.min(flat)),
        "max": float(np.max(flat)),
        "mean": float(np.mean(flat)),
        "std": float(np.std(flat)),
        "lowClipRatio": float(np.mean(flat <= 0.001)),
        "highClipRatio": float(np.mean(flat >= 0.999)),
    }


def _run_tool(args, timeout=300):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result


def _extract_avif_base(output_path, run_dir, logs):
    base_png = run_dir / "output_sdr_base.png"
    result = _run_tool([str(AVIFDEC), str(output_path), str(base_png)], timeout=300)
    logs["stdout"].append(result.stdout or "")
    logs["stderr"].append(result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or "avifdec failed")
    return base_png


def _extract_avif_gainmap(output_path, run_dir, logs):
    gainmap_png = run_dir / "output_gainmap.png"
    result = _run_tool(
        [str(AVIFGAINMAPUTIL), "extractgainmap", str(output_path), str(gainmap_png), "-q", "100"],
        timeout=300,
    )
    logs["stdout"].append(result.stdout or "")
    logs["stderr"].append(result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or "extractgainmap failed")
    return gainmap_png


def _extract_secondary_jpeg(raw):
    starts = []
    offset = 0
    while True:
        index = raw.find(b"\xff\xd8", offset)
        if index < 0:
            break
        starts.append(index)
        offset = index + 2
    if len(starts) < 2:
        raise ValueError("Ultra HDR secondary JPEG gainmap image was not found")

    start = starts[1]
    end = raw.find(b"\xff\xd9", start + 2)
    if end < 0:
        raise ValueError("Ultra HDR secondary JPEG gainmap image has no EOI marker")
    return raw[start:end + 2]


def _timestamped_run_dir(root, output_path):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = Path(output_path).stem
    return Path(root) / f"{timestamp}-{stem}"


def _default_run_dir(output_path):
    return _timestamped_run_dir(PROJECT_ROOT / "output" / "validation-runs", output_path)


def _resolve_report_dir(output_path, validation_report):
    if validation_report and validation_report != "auto":
        path = Path(validation_report)
        if path.suffix.lower() in {".md", ".markdown"}:
            return path.parent, path
        run_dir = _timestamped_run_dir(path, output_path)
        return run_dir, run_dir / "report.md"
    run_dir = _default_run_dir(output_path)
    return run_dir, run_dir / "report.md"


def _metadata_for_output(output_path, output_format, jxl_mode):
    output_path = Path(output_path)
    if output_format == "gainmap":
        return {
            "containerCicp": _read_avif_cicp(output_path.read_bytes()),
            "gainmap": _read_gainmap_metadata(output_path),
            "alternateCicp": _read_gainmap_alternate_cicp(output_path),
        }
    if output_format == "ultrahdr":
        from hdr_transcoder.inspector import _inspect_ultrahdr_gainmap

        return {"gainmap": _inspect_ultrahdr_gainmap(output_path)}
    if output_format == "avif":
        return {"containerCicp": verify_avif_metadata(output_path)}
    if output_format == "jxl":
        return {"jxl": verify_jxl_metadata(output_path, jxl_mode)}
    if output_format == "heif":
        from hdr_transcoder.inspector import inspect_image

        return {"inspector": inspect_image(output_path)}
    return {}


def _validate_metadata(output_path, output_format, jxl_mode, source_pixels):
    layer = _new_layer("Metadata")
    try:
        metadata = _metadata_for_output(output_path, output_format, jxl_mode)
        layer["metrics"] = metadata
    except Exception as exc:
        _add_check(layer, "read-metadata", STATUS_FAIL, str(exc))
        return _finalize_layer(layer)

    expected_sdr = {
        "primaries": CICP_BT709_PRIMARIES,
        "transfer": CICP_SRGB_TRANSFER,
        "matrix": CICP_BT709_MATRIX,
    }
    expected_hdr = {
        "primaries": CICP_BT2020_PRIMARIES,
        "transfer": CICP_PQ_TRANSFER,
        "matrix": CICP_BT2020_MATRIX,
    }

    if output_format == "gainmap":
        cicp = layer["metrics"].get("containerCicp") or {}
        if any(cicp.get(key) != value for key, value in expected_sdr.items()):
            _add_check(layer, "sdr-base-cicp", STATUS_FAIL, "SDR base CICP is not BT.709/sRGB/BT.709", actual=cicp, expected=expected_sdr)
        else:
            _add_check(layer, "sdr-base-cicp", STATUS_PASS, "SDR base CICP is BT.709/sRGB/BT.709", actual=cicp)

        alternate = layer["metrics"].get("alternateCicp") or {}
        if any(alternate.get(key) != value for key, value in expected_hdr.items()):
            _add_check(layer, "alternate-cicp", STATUS_FAIL, "Gainmap alternate CICP is not Rec.2020/PQ/Rec.2020", actual=alternate, expected=expected_hdr)
        else:
            _add_check(layer, "alternate-cicp", STATUS_PASS, "Gainmap alternate CICP is Rec.2020/PQ/Rec.2020", actual=alternate)

        gainmap = layer["metrics"].get("gainmap") or {}
        required = source_peak_headroom(source_pixels)
        actual = gainmap.get("alternateHeadroom")
        if actual is None:
            _add_check(layer, "alternate-headroom", STATUS_FAIL, "Gainmap alternate headroom is missing")
        else:
            delta = max(required - actual, 0.0)
            status = STATUS_FAIL if delta > GAINMAP_HEADROOM_TOLERANCE_STOPS else STATUS_PASS
            _add_check(
                layer,
                "alternate-headroom",
                status,
                "Gainmap alternate headroom covers source peak" if status == STATUS_PASS else "Gainmap alternate headroom is below source peak",
                sourcePeakHeadroom=required,
                actualHeadroom=actual,
                deltaStops=delta,
                toleranceStops=GAINMAP_HEADROOM_TOLERANCE_STOPS,
            )

    elif output_format in {"avif", "heif"}:
        cicp = (layer["metrics"].get("containerCicp") or (layer["metrics"].get("inspector") or {}).get("color") or {})
        if any(cicp.get(key) != value for key, value in BT2020_PQ_CICP.items()):
            _add_check(layer, "display-hdr-cicp", STATUS_FAIL, "Display HDR output is not tagged Rec.2020/PQ/Rec.2020", actual=cicp, expected=BT2020_PQ_CICP)
        else:
            _add_check(layer, "display-hdr-cicp", STATUS_PASS, "Display HDR output is tagged Rec.2020/PQ/Rec.2020", actual=cicp)

    elif output_format == "ultrahdr":
        gainmap = layer["metrics"].get("gainmap") or {}
        if gainmap.get("present"):
            _add_check(layer, "ultrahdr-gainmap", STATUS_PASS, "Ultra HDR gain map metadata detected", actual=gainmap)
        else:
            _add_check(layer, "ultrahdr-gainmap", STATUS_FAIL, "Ultra HDR gain map metadata not detected", actual=gainmap)

    elif output_format == "jxl":
        _add_check(layer, "jxl-metadata", STATUS_PASS, "JPEG XL metadata read successfully", actual=layer["metrics"].get("jxl"))
    else:
        _add_check(layer, "metadata", STATUS_WARNING, f"No dedicated metadata checks for {output_format}")

    return _finalize_layer(layer)


def _validate_sdr_base(output_path, output_format, source_pixels, headroom, run_dir, dump_layers, logs):
    layer = _new_layer("SDR Base")
    if output_format not in {"gainmap", "ultrahdr", "gainmap-heic"}:
        _add_check(layer, "not-applicable", STATUS_SKIPPED, "Single-layer display/master output has no SDR fallback base")
        return _finalize_layer(layer)

    reference_sdr = prepare_base_sdr(source_pixels, headroom=headroom)
    reference_linear = _srgb_inverse_gamma(reference_sdr)
    if dump_layers:
        layer["artifacts"]["referenceSdr"] = str(_write_png(run_dir / "reference_sdr.png", reference_sdr))

    try:
        if output_format == "gainmap":
            base_png = _extract_avif_base(output_path, run_dir, logs)
            output_linear = _decode_png_or_jpeg_to_sdr_linear(base_png)
            layer["artifacts"]["outputSdrBase"] = str(base_png)
        elif output_format == "ultrahdr":
            base_jpg = run_dir / "output_sdr_base.jpg"
            base_jpg.write_bytes(Path(output_path).read_bytes())
            output_linear = _decode_png_or_jpeg_to_sdr_linear(base_jpg)
            layer["artifacts"]["outputSdrBase"] = str(base_jpg)
            _add_check(layer, "jpeg-sdr-base", STATUS_WARNING, "Ultra HDR JPEG base has no CICP; viewers generally assume sRGB")
        else:
            _add_check(layer, "extract-base", STATUS_WARNING, "HEIC gainmap base extraction is not implemented yet")
            return _finalize_layer(layer)
    except Exception as exc:
        _add_check(layer, "extract-base", STATUS_FAIL, f"Unable to extract/decode SDR base: {exc}")
        return _finalize_layer(layer)

    if output_linear.shape[:2] != reference_linear.shape[:2]:
        _add_check(layer, "dimensions", STATUS_FAIL, "SDR base dimensions differ from source", actual=list(output_linear.shape[:2]), expected=list(reference_linear.shape[:2]))
        return _finalize_layer(layer)
    _add_check(layer, "dimensions", STATUS_PASS, "SDR base dimensions match source", actual=list(output_linear.shape[:2]))

    metrics = _sdr_diff_metrics(reference_linear, output_linear)
    layer["metrics"].update(metrics)
    if dump_layers:
        layer["artifacts"]["diffSdr"] = str(_write_png(run_dir / "diff_sdr.png", _falsecolor_diff(output_linear - reference_linear)))

    if metrics["p95AbsRgb"] > 0.12:
        _add_check(layer, "reference-diff", STATUS_FAIL, "SDR base is far from reference tone map", **metrics)
    elif metrics["p95AbsRgb"] > 0.04 or abs(metrics["midtoneDelta"]) > 0.03:
        _add_check(layer, "reference-diff", STATUS_WARNING, "SDR base differs noticeably from reference tone map", **metrics)
    else:
        _add_check(layer, "reference-diff", STATUS_PASS, "SDR base is close to reference tone map", **metrics)

    if metrics["blackLift"] > 0.015:
        _add_check(layer, "black-lift", STATUS_WARNING, "SDR base black level appears lifted", blackLift=metrics["blackLift"])
    else:
        _add_check(layer, "black-lift", STATUS_PASS, "SDR base black level is stable", blackLift=metrics["blackLift"])

    if metrics["clippedPixelRatio"] > 0.02:
        _add_check(layer, "clipping", STATUS_WARNING, "SDR base has notable clipping", clippedPixelRatio=metrics["clippedPixelRatio"])
    else:
        _add_check(layer, "clipping", STATUS_PASS, "SDR base clipping is low", clippedPixelRatio=metrics["clippedPixelRatio"])

    return _finalize_layer(layer)


def _validate_gainmap(output_path, output_format, source_pixels, run_dir, dump_layers, logs):
    layer = _new_layer("Gainmap")
    if output_format not in {"gainmap", "ultrahdr", "gainmap-heic"}:
        _add_check(layer, "not-applicable", STATUS_SKIPPED, "Single-layer display/master output has no gainmap layer")
        return _finalize_layer(layer)

    try:
        if output_format == "gainmap":
            gainmap_png = _extract_avif_gainmap(output_path, run_dir, logs)
            import imagecodecs

            gainmap_pixels = imagecodecs.png_decode(gainmap_png.read_bytes())
            layer["artifacts"]["outputGainmap"] = str(gainmap_png)
            metadata = _read_gainmap_metadata(output_path)
            layer["metrics"]["metadata"] = metadata
        elif output_format == "ultrahdr":
            import imagecodecs

            raw = Path(output_path).read_bytes()
            decoded = imagecodecs.ultrahdr_decode(raw)
            if isinstance(decoded, tuple) and len(decoded) >= 2:
                gainmap_pixels = decoded[1]
            else:
                gainmap_pixels = imagecodecs.jpeg_decode(_extract_secondary_jpeg(raw))
            if dump_layers:
                layer["artifacts"]["outputGainmap"] = str(_write_png(run_dir / "output_gainmap.png", _as_rgb_float(gainmap_pixels)))
            from hdr_transcoder.inspector import _inspect_ultrahdr_gainmap

            metadata = _inspect_ultrahdr_gainmap(output_path)
            layer["metrics"]["metadata"] = metadata
        else:
            _add_check(layer, "extract-gainmap", STATUS_WARNING, "HEIC gainmap image extraction is not implemented yet")
            return _finalize_layer(layer)
    except Exception as exc:
        _add_check(layer, "extract-gainmap", STATUS_FAIL, f"Unable to extract/read gainmap: {exc}")
        return _finalize_layer(layer)

    metrics = _gainmap_metrics(gainmap_pixels)
    layer["metrics"].update(metrics)
    _add_check(layer, "present", STATUS_PASS, "Gainmap layer is present", **metrics)

    if metrics["std"] < 0.002:
        _add_check(layer, "flatness", STATUS_WARNING, "Gainmap is nearly flat", std=metrics["std"])
    else:
        _add_check(layer, "flatness", STATUS_PASS, "Gainmap has non-flat signal", std=metrics["std"])

    if metrics["lowClipRatio"] > 0.25 or metrics["highClipRatio"] > 0.25:
        _add_check(layer, "clip", STATUS_WARNING, "Gainmap has a large clipped area", lowClipRatio=metrics["lowClipRatio"], highClipRatio=metrics["highClipRatio"])
    else:
        _add_check(layer, "clip", STATUS_PASS, "Gainmap clipping is limited", lowClipRatio=metrics["lowClipRatio"], highClipRatio=metrics["highClipRatio"])

    metadata = layer["metrics"].get("metadata") or {}
    alternate = metadata.get("alternateHeadroom") or metadata.get("alternate_headroom")
    if alternate is not None:
        required = source_peak_headroom(source_pixels)
        delta = max(required - float(alternate), 0.0)
        status = STATUS_FAIL if delta > GAINMAP_HEADROOM_TOLERANCE_STOPS else STATUS_PASS
        _add_check(layer, "headroom", status, "Gainmap headroom matches source peak" if status == STATUS_PASS else "Gainmap headroom is too low", sourcePeakHeadroom=required, actualHeadroom=float(alternate), deltaStops=delta)

    return _finalize_layer(layer)


def _validate_reconstruction(output_path, output_format, source_pixels, run_dir, dump_layers):
    layer = _new_layer("HDR Reconstruction")
    try:
        reconstructed, width, height = decode_to_scrgb(str(output_path))
    except Exception as exc:
        _add_check(layer, "decode", STATUS_FAIL, f"Unable to decode/reconstruct HDR output: {exc}")
        return _finalize_layer(layer)

    if reconstructed.shape[:2] != source_pixels.shape[:2]:
        _add_check(layer, "dimensions", STATUS_FAIL, "HDR reconstruction dimensions differ from source", actual=[height, width], expected=list(source_pixels.shape[:2]))
        return _finalize_layer(layer)
    _add_check(layer, "dimensions", STATUS_PASS, "HDR reconstruction dimensions match source", actual=[height, width])

    metrics = _hdr_diff_metrics(source_pixels, reconstructed)
    layer["metrics"].update(metrics)
    if dump_layers:
        np.save(run_dir / "source_hdr.npy", source_pixels[..., :3].astype(np.float32))
        np.save(run_dir / "output_reconstructed_hdr.npy", reconstructed[..., :3].astype(np.float32))
        layer["artifacts"]["sourceHdr"] = str(run_dir / "source_hdr.npy")
        layer["artifacts"]["outputReconstructedHdr"] = str(run_dir / "output_reconstructed_hdr.npy")
        layer["artifacts"]["diffHdrFalsecolor"] = str(_write_png(run_dir / "diff_hdr_falsecolor.png", _falsecolor_diff(reconstructed[..., :3] - source_pixels[..., :3])))

    tolerance = ULTRAHDR_DECODE_PEAK_TOLERANCE_STOPS if output_format == "ultrahdr" else GAINMAP_DECODE_PEAK_TOLERANCE_STOPS
    if output_format in {"avif", "heif", "jxl"}:
        tolerance = DISPLAY_DECODE_PEAK_TOLERANCE_STOPS
    warn_tolerance = min(tolerance, 0.05)

    if metrics["p99StopDelta"] > tolerance:
        _add_check(layer, "p99-peak", STATUS_FAIL, "P99 HDR reconstruction peak drift is too high", deltaStops=metrics["p99StopDelta"], toleranceStops=tolerance)
    elif metrics["p99StopDelta"] > warn_tolerance:
        _add_check(layer, "p99-peak", STATUS_WARNING, "P99 HDR reconstruction peak drift is noticeable", deltaStops=metrics["p99StopDelta"], toleranceStops=warn_tolerance)
    else:
        _add_check(layer, "p99-peak", STATUS_PASS, "P99 HDR reconstruction peak drift is low", deltaStops=metrics["p99StopDelta"])

    if metrics["maxStopDelta"] > max(tolerance * 2.0, 0.10):
        _add_check(layer, "max-peak", STATUS_WARNING, "Max peak differs; check whether this is an isolated pixel", deltaStops=metrics["maxStopDelta"])
    else:
        _add_check(layer, "max-peak", STATUS_PASS, "Max peak is within warning range", deltaStops=metrics["maxStopDelta"])

    if abs(metrics["meanLuminanceDelta"]) > 0.05:
        _add_check(layer, "mean-luminance", STATUS_WARNING, "Mean luminance drift is noticeable", meanLuminanceDelta=metrics["meanLuminanceDelta"])
    else:
        _add_check(layer, "mean-luminance", STATUS_PASS, "Mean luminance drift is low", meanLuminanceDelta=metrics["meanLuminanceDelta"])

    return _finalize_layer(layer)


def _overall_status(layers):
    statuses = [layer.get("status") for layer in layers.values()]
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_WARNING in statuses:
        return STATUS_WARNING
    return STATUS_PASS


def _write_report(report_path, result):
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Layer Validation Report",
        "",
        f"- Output: `{result['outputPath']}`",
        f"- Format: `{result['format']}`",
        f"- Overall: **{result['status']}**",
        "",
        "## Layers",
    ]
    for key, layer in result["layers"].items():
        lines.extend([
            "",
            f"### {layer['name']}: {layer['status']}",
            "",
        ])
        for check in layer.get("checks", []):
            lines.append(f"- `{check['status']}` {check['name']}: {check['message']}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def validate_layers(
    source_pixels,
    output_path,
    output_format,
    jxl_mode=None,
    headroom=2.0,
    dump_layers=False,
    validation_report=None,
):
    """Validate SDR base, gainmap, reconstruction, and metadata layers."""
    output_path = Path(output_path)
    run_dir, report_path = _resolve_report_dir(output_path, validation_report)
    run_dir.mkdir(parents=True, exist_ok=True)
    logs = {"stdout": [], "stderr": []}

    layers = {
        "sdrBase": _validate_sdr_base(output_path, output_format, source_pixels, headroom, run_dir, dump_layers, logs),
        "gainmap": _validate_gainmap(output_path, output_format, source_pixels, run_dir, dump_layers, logs),
        "hdrReconstruction": _validate_reconstruction(output_path, output_format, source_pixels, run_dir, dump_layers),
        "metadata": _validate_metadata(output_path, output_format, jxl_mode, source_pixels),
    }
    result = {
        "requested": True,
        "ok": all(layer["status"] not in {STATUS_FAIL} for layer in layers.values()),
        "status": _overall_status(layers),
        "outputPath": str(output_path),
        "format": output_format,
        "runDir": str(run_dir),
        "reportPath": str(report_path),
        "layers": layers,
    }

    (run_dir / "metadata.json").write_text(json.dumps(layers["metadata"]["metrics"], indent=2), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (run_dir / "stdout.log").write_text("".join(logs["stdout"]), encoding="utf-8")
    (run_dir / "stderr.log").write_text("".join(logs["stderr"]), encoding="utf-8")
    _write_report(report_path, result)

    print(f"  Layer validation: {result['status']} ({report_path})")
    for key in ("sdrBase", "gainmap", "hdrReconstruction", "metadata"):
        layer = layers[key]
        print(f"    {layer['name']}: {layer['status']}")

    return result
