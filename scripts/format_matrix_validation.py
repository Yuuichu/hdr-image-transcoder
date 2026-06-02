"""Run an end-to-end HDR format matrix with detailed logs.

This script is intentionally CLI-driven: it exercises hdr2avif.py the same way
the Windows app/user workflow does, then inspects every output with the local
project decoders and bundled command-line tools.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hdr_transcoder.color import clamp_small_negatives, linear_srgb_to_bt2020  # noqa: E402
from hdr_transcoder.config import (  # noqa: E402
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_PQ_TRANSFER,
)
from hdr_transcoder.formats.decoder import (  # noqa: E402
    SUPPORTED_FORMATS,
    _read_tiff_cicp,
    decode_to_scrgb,
    probe_format,
)
from hdr_transcoder.inspector import inspect_image  # noqa: E402
from hdr_transcoder.processor import _linear_to_pq, _srgb_gamma, _srgb_inverse_gamma, prepare_base_sdr  # noqa: E402
from hdr_transcoder.tools import (  # noqa: E402
    AVIFDEC,
    AVIFGAINMAPUTIL,
    CJXL,
    DJXL,
    JXLINFO,
    check_runtime_environment,
    check_tool_invocation,
)


BT2020_PQ = {
    "primaries": CICP_BT2020_PRIMARIES,
    "transfer": CICP_PQ_TRANSFER,
    "matrix": CICP_BT2020_MATRIX,
}


@dataclass
class OutputCase:
    name: str
    output_format: str
    extension: str
    fidelity: str
    extra_args: list[str] = field(default_factory=list)
    expected_color: dict[str, int] | None = None
    expected_gainmap: bool = False
    expected_alternate_color: dict[str, int] | None = None
    notes: list[str] = field(default_factory=list)


class RunLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = path.open("w", encoding="utf-8", newline="\n")

    def close(self) -> None:
        self._file.close()

    def line(self, message: str = "") -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        text = f"[{stamp}] {message}"
        print(text)
        self._file.write(text + "\n")
        self._file.flush()

    def section(self, title: str) -> None:
        self.line("")
        self.line("=" * 80)
        self.line(title)
        self.line("=" * 80)

    def block(self, title: str, content: str | None) -> None:
        self.line(f"-- {title} --")
        if content:
            for part in content.rstrip().splitlines():
                self.line(part)
        else:
            self.line("<empty>")


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=json_default),
        encoding="utf-8",
    )


def cmdline(cmd: list[str | Path]) -> str:
    return subprocess.list2cmdline([str(x) for x in cmd])


def run_command(
    log: RunLog,
    name: str,
    cmd: list[str | Path],
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    log.section(f"TEST {name}")
    log.line(f"CWD: {cwd}")
    log.line(f"CMD: {cmdline(cmd)}")
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [str(x) for x in cmd],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        elapsed = time.perf_counter() - start
        log.line(f"RETURN_CODE: {result.returncode}")
        log.line(f"ELAPSED_SECONDS: {elapsed:.3f}")
        log.block("STDOUT", result.stdout)
        log.block("STDERR", result.stderr)
        return {
            "name": name,
            "cmd": [str(x) for x in cmd],
            "returnCode": result.returncode,
            "elapsedSeconds": elapsed,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        log.line(f"TIMEOUT after {elapsed:.3f}s")
        log.block("STDOUT", exc.stdout if isinstance(exc.stdout, str) else None)
        log.block("STDERR", exc.stderr if isinstance(exc.stderr, str) else None)
        return {
            "name": name,
            "cmd": [str(x) for x in cmd],
            "returnCode": None,
            "elapsedSeconds": elapsed,
            "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
            "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
            "ok": False,
            "error": f"timeout after {timeout}s",
        }


def make_reference_scrgb(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    rgb = np.zeros((height, width, 3), dtype=np.float32)
    rgb[..., 0] = 0.03 + 0.55 * x + 0.10 * y
    rgb[..., 1] = 0.03 + 0.20 * x + 0.45 * y
    rgb[..., 2] = 0.04 + 0.35 * (1.0 - x) + 0.15 * y

    # Neutral 1000-nit patch, 600-nit yellow sign, and saturated blue-green.
    rgb[height // 10 : height // 4, width // 10 : width // 3, :] = 10.0
    rgb[height // 3 : height * 2 // 3, width // 2 : width * 3 // 4, :] = [6.0, 4.4, 0.7]
    rgb[height * 2 // 3 : height * 9 // 10, width // 5 : width // 2, :] = [0.4, 2.8, 4.8]
    return rgb


def write_float_tiff(path: Path, pixels: np.ndarray) -> None:
    import imagecodecs

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        imagecodecs.tiff_encode(
            np.asarray(pixels, dtype=np.float32),
            photometric="rgb",
            planarconfig="contig",
        )
    )


def write_pq_bt2020_tiff(path: Path, scrgb_pixels: np.ndarray) -> None:
    import imagecodecs

    bt2020 = clamp_small_negatives(linear_srgb_to_bt2020(np.maximum(scrgb_pixels, 0.0)))
    bt2020 = np.maximum(bt2020, 0.0)
    pq = _linear_to_pq(bt2020 * 100.0, max_nits=10000.0)
    pq_16bit = (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        imagecodecs.tiff_encode(
            pq_16bit,
            photometric="rgb",
            planarconfig="contig",
        )
    )


def source_stats(path: Path, pq_input: bool, tiff_pq_primaries: int | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    fmt = probe_format(path)
    cicp = _read_tiff_cicp(raw) if fmt == "tiff" else {}
    pixels, width, height = decode_to_scrgb(
        path,
        pq_input=pq_input,
        tiff_pq_primaries=tiff_pq_primaries,
    )
    rgb = np.asarray(pixels[..., :3], dtype=np.float32)
    return {
        "path": str(path),
        "format": fmt,
        "formatName": SUPPORTED_FORMATS.get(fmt, (fmt or "unknown", []))[0],
        "pqInput": pq_input,
        "tiffPqPrimaries": tiff_pq_primaries,
        "tiffCicp": cicp,
        "width": width,
        "height": height,
        "rgbMin": float(np.nanmin(rgb)),
        "rgbMax": float(np.nanmax(rgb)),
        "peakHeadroomStops": math.log2(max(float(np.nanmax(rgb)), 1.0)),
        "hdrPixelPercent": float(np.mean(np.max(rgb, axis=-1) > 1.0) * 100.0),
    }


def validate_inspection(
    case: OutputCase,
    info: dict[str, Any],
    heic_summary: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if info.get("error"):
        errors.append(f"inspect/decode error: {info['error']}")
        return errors, warnings

    hdr = info.get("hdr") or {}
    if not hdr.get("is_hdr"):
        errors.append("decoded output is not HDR (rgb_max <= 1.0)")

    color = info.get("color") or {}
    if case.expected_color:
        for key, expected in case.expected_color.items():
            actual = color.get(key)
            if actual != expected:
                errors.append(f"color {key}={actual}, expected {expected}")

    gainmap = info.get("gainmap") or {}
    if case.expected_gainmap and not gainmap.get("present"):
        errors.append("gainmap metadata not detected")
    if not case.expected_gainmap and gainmap.get("present"):
        warnings.append("gainmap detected although this case is a single-layer HDR output")

    if case.expected_alternate_color:
        alternate = gainmap.get("alternate_color") or {}
        for key, expected in case.expected_alternate_color.items():
            actual = alternate.get(key)
            if actual != expected:
                errors.append(f"alternate color {key}={actual}, expected {expected}")

    warnings.extend(info.get("warnings") or [])
    warnings.extend(case.notes)
    return errors, warnings


def inspect_heic_structure(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() not in {".heic", ".heif"}:
        return None

    from hdr_transcoder.formats.isobmff import (
        find_item_property,
        get_item_bitdepth,
        get_item_colr,
        get_item_dimensions,
        read_heic_container,
    )

    container = read_heic_container(path)
    if container is None:
        return {"present": False, "error": "not a readable HEIC ISOBMFF container"}

    items: dict[str, Any] = {}
    for item_id in sorted(container.get("item_extents") or {}):
        width, height = get_item_dimensions(container, item_id)
        primaries, transfer, matrix = get_item_colr(container, item_id)
        aux = find_item_property(container, item_id, "auxC")
        aux_type = None
        if aux:
            aux_type = aux.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        extent_bytes = sum(length for _offset, length in container["item_extents"][item_id])
        items[str(item_id)] = {
            "width": width,
            "height": height,
            "bitDepth": get_item_bitdepth(container, item_id),
            "cicp": {"primaries": primaries, "transfer": transfer, "matrix": matrix},
            "auxType": aux_type,
            "extentBytes": extent_bytes,
        }

    return {
        "present": True,
        "itemCount": len(items),
        "items": items,
        "propertyAssociations": {
            str(key): value for key, value in (container.get("item_properties") or {}).items()
        },
    }


def _srgb_base_to_bt2020_srgb(sdr_8bit: np.ndarray) -> np.ndarray:
    linear = _srgb_inverse_gamma(sdr_8bit.astype(np.float32) / 255.0)
    bt2020 = clamp_small_negatives(linear_srgb_to_bt2020(linear))
    encoded = _srgb_gamma(bt2020)
    return (encoded * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


def _decode_heic_item_pixels(path: Path, item_id: int) -> np.ndarray:
    from hdr_transcoder.formats.isobmff import (
        build_minimal_heic,
        find_item_property,
        get_item_bitdepth,
        get_item_colr,
        get_item_dimensions,
        read_heic_container,
    )

    container = read_heic_container(path)
    if container is None:
        raise ValueError("not a readable HEIC ISOBMFF container")

    item_extents = container.get("item_extents") or {}
    if item_id not in item_extents:
        raise ValueError(f"HEIC item {item_id} is missing")

    hvcC = find_item_property(container, item_id, "hvcC")
    if hvcC is None:
        raise ValueError(f"HEIC item {item_id} has no hvcC property")

    width, height = get_item_dimensions(container, item_id)
    primaries, transfer, matrix = get_item_colr(container, item_id)
    bits = get_item_bitdepth(container, item_id)
    raw = path.read_bytes()
    offset, length = item_extents[item_id][0]
    minimal = build_minimal_heic(
        hvcC,
        raw[offset:offset + length],
        width,
        height,
        primaries=primaries,
        transfer=transfer,
        matrix=matrix,
        bits_per_channel=bits,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        item_path = tmp / "item.heic"
        npy_path = tmp / "item.npy"
        item_path.write_bytes(minimal)
        code = (
            "import sys, numpy as np, pillow_heif\n"
            "from hdr_transcoder.formats.decoder import _extract_pillow_heif_pixels\n"
            "image = pillow_heif.open_heif(sys.argv[1], convert_hdr_to_8bit=False)[0]\n"
            "np.save(sys.argv[2], _extract_pillow_heif_pixels(image))\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        result = subprocess.run(
            [sys.executable, "-c", code, str(item_path), str(npy_path)],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
            raise ValueError(f"HEIC item {item_id} decode subprocess failed: {detail}")
        return np.load(npy_path)


def verify_heic_bt2020_base_pixels(
    case: OutputCase,
    output_path: Path,
    source_path: Path,
    source_pq_input: bool,
    source_tiff_pq_primaries: int | None,
    cache: dict[str, np.ndarray],
) -> dict[str, Any] | None:
    if case.output_format != "gainmap-heic" or "--heic-apple-gainmap-only" in case.extra_args:
        return None

    from hdr_transcoder.formats.isobmff import get_item_colr, read_heic_container

    container = read_heic_container(output_path)
    if container is None:
        return {"ok": False, "error": "HEIC container is not readable"}

    base_cicp = get_item_colr(container, 1)
    if base_cicp != (CICP_BT2020_PRIMARIES, 13, CICP_BT2020_MATRIX):
        return {"ok": None, "skipped": True, "baseCicp": base_cicp}

    cache_key = f"{source_path}|{source_pq_input}|{source_tiff_pq_primaries}"
    if cache_key not in cache:
        source_pixels, _, _ = decode_to_scrgb(
            source_path,
            pq_input=source_pq_input,
            tiff_pq_primaries=source_tiff_pq_primaries,
        )
        expected_srgb = prepare_base_sdr(source_pixels, headroom=2.0)
        cache[f"{cache_key}:srgb"] = expected_srgb
        cache[f"{cache_key}:bt2020"] = _srgb_base_to_bt2020_srgb(expected_srgb)
        cache[cache_key] = np.array([1], dtype=np.uint8)

    decoded = _decode_heic_item_pixels(output_path, 1)[..., :3]
    expected_bt2020 = cache[f"{cache_key}:bt2020"]
    expected_srgb = cache[f"{cache_key}:srgb"]

    converted_diff = np.abs(decoded.astype(np.int16) - expected_bt2020.astype(np.int16))
    retagged_diff = np.abs(decoded.astype(np.int16) - expected_srgb.astype(np.int16))
    converted_mae = float(np.mean(converted_diff))
    retagged_mae = float(np.mean(retagged_diff))
    converted_p95 = float(np.percentile(converted_diff, 95))
    retagged_p95 = float(np.percentile(retagged_diff, 95))

    ok = converted_mae <= max(3.0, retagged_mae * 0.60)
    return {
        "ok": ok,
        "baseCicp": {"primaries": base_cicp[0], "transfer": base_cicp[1], "matrix": base_cicp[2]},
        "convertedMae": converted_mae,
        "retaggedMae": retagged_mae,
        "convertedP95": converted_p95,
        "retaggedP95": retagged_p95,
        "message": (
            "HEIC BT.2020 base pixels match converted SDR base"
            if ok
            else "HEIC base is tagged BT.2020 but pixels are closer to unconverted sRGB SDR base"
        ),
    }


def external_inspections(log: RunLog, case: OutputCase, path: Path, timeout: int) -> list[dict[str, Any]]:
    checks: list[tuple[str, list[str | Path]]] = []
    suffix = path.suffix.lower()
    if suffix == ".jxl":
        checks.append(("jxlinfo", [JXLINFO, path]))
    if suffix == ".avif":
        checks.append(("avifdec_info", [AVIFDEC, "--info", path]))
        if case.expected_gainmap:
            checks.append(("avif_gainmap_metadata", [AVIFGAINMAPUTIL, "printmetadata", path]))
    if suffix in {".heic", ".heif"}:
        # HEIC structure is inspected through the in-repo ISOBMFF parser.
        return []

    results = []
    for name, cmd in checks:
        results.append(run_command(log, f"inspect:{path.name}:{name}", cmd, ROOT, timeout))
    return results


def output_cases() -> list[OutputCase]:
    return [
        OutputCase(
            name="jxl_master_linear",
            output_format="jxl",
            extension=".jxl",
            fidelity="master",
            expected_color={"transfer": 8},
        ),
        OutputCase(
            name="jxl_display_pq",
            output_format="jxl",
            extension=".jxl",
            fidelity="display",
            extra_args=["--jxl-mode", "rec2020-pq"],
            expected_color={"primaries": 9, "transfer": 16},
        ),
        OutputCase(
            name="avif_display_pq",
            output_format="avif",
            extension=".avif",
            fidelity="display",
            expected_color=BT2020_PQ,
        ),
        OutputCase(
            name="heif_display_pq",
            output_format="heif",
            extension=".heic",
            fidelity="display",
            expected_color=BT2020_PQ,
        ),
        OutputCase(
            name="ultrahdr_jpeg",
            output_format="ultrahdr",
            extension=".jpg",
            fidelity="compat",
            expected_gainmap=True,
            notes=[
                "Ultra HDR JPEG metadata is checked by lightweight JPEG marker/XMP scan."
            ],
        ),
        OutputCase(
            name="avif_iso_gainmap",
            output_format="gainmap",
            extension=".avif",
            fidelity="compat",
            expected_gainmap=True,
            expected_alternate_color=BT2020_PQ,
        ),
        OutputCase(
            name="heic_dual_gainmap",
            output_format="gainmap-heic",
            extension=".heic",
            fidelity="compat",
            expected_gainmap=True,
            expected_alternate_color=BT2020_PQ,
        ),
        OutputCase(
            name="heic_rgb_gainmap_only",
            output_format="gainmap-heic",
            extension=".heic",
            fidelity="compat",
            extra_args=["--heic-rgb-gainmap-only"],
            expected_gainmap=True,
        ),
        OutputCase(
            name="heic_apple_gainmap_only",
            output_format="gainmap-heic",
            extension=".heic",
            fidelity="compat",
            extra_args=["--heic-apple-gainmap-only"],
            expected_gainmap=True,
            notes=[
                "Apple gainmap is checked by XMP/headroom and auxC presence; there is no public Apple encoder conformance tool here."
            ],
        ),
    ]


def smoke_decode_inputs(
    log: RunLog,
    paths: list[tuple[str, Path, bool, int | None]],
    inspect_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    log.section("INPUT DECODER SMOKE TESTS")
    for label, path, pq_input, tiff_pq_primaries in paths:
        entry: dict[str, Any] = {
            "label": label,
            "path": str(path),
            "pqInput": pq_input,
            "tiffPqPrimaries": tiff_pq_primaries,
        }
        log.line(f"Input smoke: {label} -> {path}")
        try:
            stats = source_stats(path, pq_input=pq_input, tiff_pq_primaries=tiff_pq_primaries)
            entry.update(stats)
            entry["ok"] = stats["rgbMax"] > 0
            log.line(
                "  PASS "
                f"fmt={stats['format']} size={stats['width']}x{stats['height']} "
                f"peak={stats['rgbMax']:.4f} headroom={stats['peakHeadroomStops']:.4f}"
            )
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
            log.line(f"  FAIL {exc}")
        write_json(inspect_dir / f"input_{label}.json", entry)
        results.append(entry)
    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the HDR transcoder format matrix.")
    parser.add_argument("--input", help="Optional real input file. Defaults to a generated float scRGB TIFF.")
    parser.add_argument("--pq-input", action="store_true", help="Pass --pq-input when converting --input.")
    parser.add_argument(
        "--bt2020-pq-tiff",
        action="store_true",
        help="Pass --bt2020-pq-tiff when converting --input and decode source stats as BT.2020 PQ TIFF.",
    )
    parser.add_argument("--out-dir", default=str(ROOT / "output" / "format-matrix"))
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=96)
    parser.add_argument("--quality", type=int, default=100)
    parser.add_argument("--speed", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--no-verify-fidelity", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    run_root = Path(args.out_dir) / args.run_id
    sources_dir = run_root / "sources"
    outputs_dir = run_root / "outputs"
    inspect_dir = run_root / "inspect"
    log = RunLog(run_root / "run.log")
    summary: dict[str, Any] = {
        "runRoot": str(run_root),
        "startedAt": datetime.now().isoformat(timespec="seconds"),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "projectRoot": str(ROOT),
        "supportedInputs": SUPPORTED_FORMATS,
        "tools": {},
        "sources": {},
        "inputSmoke": [],
        "outputs": [],
    }

    try:
        log.section("RUNTIME")
        env_report = check_runtime_environment()
        invoke_report = check_tool_invocation()
        summary["tools"]["environment"] = env_report
        summary["tools"]["invocation"] = invoke_report
        log.line(json.dumps(env_report, ensure_ascii=False, default=json_default))
        write_json(inspect_dir / "runtime.json", {"environment": env_report, "invocation": invoke_report})

        reference = make_reference_scrgb(args.width, args.height)
        generated_float_tiff = sources_dir / "reference_linear_scrgb_float.tif"
        generated_pq_tiff = sources_dir / "reference_bt2020_pq_untagged.tif"
        write_float_tiff(generated_float_tiff, reference)
        write_pq_bt2020_tiff(generated_pq_tiff, reference)

        if args.input:
            source_path = Path(args.input).resolve()
            source_pq_input = bool(args.pq_input or args.bt2020_pq_tiff)
            source_tiff_pq_primaries = CICP_BT2020_PRIMARIES if args.bt2020_pq_tiff else None
        else:
            source_path = generated_float_tiff
            source_pq_input = False
            source_tiff_pq_primaries = None

        log.section("SOURCE")
        source_report = source_stats(
            source_path,
            pq_input=source_pq_input,
            tiff_pq_primaries=source_tiff_pq_primaries,
        )
        generated_linear_report = source_stats(generated_float_tiff, pq_input=False)
        generated_pq_report = source_stats(
            generated_pq_tiff,
            pq_input=True,
            tiff_pq_primaries=CICP_BT2020_PRIMARIES,
        )
        summary["sources"] = {
            "active": source_report,
            "generatedLinearScrgb": generated_linear_report,
            "generatedBt2020PqUntagged": generated_pq_report,
        }
        log.line(f"Active source: {source_path}")
        log.line(json.dumps(source_report, ensure_ascii=False, default=json_default))
        if generated_pq_report.get("tiffCicp") == {}:
            log.line(
                "NOTE: generated BT.2020 PQ TIFF is untagged; --bt2020-pq-tiff supplies "
                "BT.2020 primaries, while plain --pq-input only forces PQ transfer."
            )
        write_json(inspect_dir / "sources.json", summary["sources"])

        input_smoke_paths: list[tuple[str, Path, bool, int | None]] = [
            ("active_source", source_path, source_pq_input, source_tiff_pq_primaries),
            ("generated_linear_tiff", generated_float_tiff, False, None),
            ("generated_pq_tiff", generated_pq_tiff, True, CICP_BT2020_PRIMARIES),
        ]
        fixture = ROOT / "tests" / "fixtures" / "test_hdr_fix.jxl"
        if fixture.exists():
            input_smoke_paths.append(("fixture_jxl", fixture, False, None))

        if args.bt2020_pq_tiff:
            source_cli_flags = ["--bt2020-pq-tiff"]
        else:
            source_cli_flags = ["--pq-input"] if source_pq_input else []
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        heic_base_check_cache: dict[str, np.ndarray] = {}

        for case in output_cases():
            output_path = outputs_dir / f"{case.name}{case.extension}"
            cmd = [
                sys.executable,
                ROOT / "hdr2avif.py",
                source_path,
                output_path,
                "--format",
                case.output_format,
                "--fidelity",
                case.fidelity,
                "--quality",
                str(args.quality),
                "--speed",
                str(args.speed),
                "--info-json",
                *source_cli_flags,
                *case.extra_args,
            ]
            if not args.no_verify_fidelity:
                cmd.insert(-len(source_cli_flags) - len(case.extra_args) if (source_cli_flags or case.extra_args) else len(cmd), "--verify-fidelity")
            command_result = run_command(log, f"convert:{case.name}", cmd, ROOT, args.timeout, env=env)
            output_entry: dict[str, Any] = {
                "case": case.__dict__,
                "outputPath": str(output_path),
                "command": command_result,
                "ok": False,
                "errors": [],
                "warnings": [],
            }

            if output_path.exists():
                info = inspect_image(output_path)
                heic_summary = inspect_heic_structure(output_path)
                heic_base_check = verify_heic_bt2020_base_pixels(
                    case,
                    output_path,
                    source_path,
                    source_pq_input,
                    source_tiff_pq_primaries,
                    heic_base_check_cache,
                )
                external = external_inspections(log, case, output_path, timeout=120)
                errors, warnings = validate_inspection(case, info, heic_summary)
                if heic_base_check is not None:
                    if heic_base_check.get("ok") is False:
                        errors.append(heic_base_check["message"])
                    elif heic_base_check.get("ok") is True:
                        log.line(
                            "HEIC base check: "
                            f"{heic_base_check['message']} "
                            f"(converted MAE={heic_base_check['convertedMae']:.3f}, "
                            f"retagged MAE={heic_base_check['retaggedMae']:.3f})"
                        )
                if not command_result["ok"]:
                    errors.insert(0, "conversion command returned non-zero; output was still inspected")
                output_entry.update(
                    {
                        "fileSizeBytes": output_path.stat().st_size,
                        "inspection": info,
                        "heicStructure": heic_summary,
                        "heicBaseCheck": heic_base_check,
                        "externalInspections": external,
                        "errors": errors,
                        "warnings": warnings,
                        "ok": command_result["ok"] and not errors,
                    }
                )
                write_json(inspect_dir / f"{case.name}.inspect.json", output_entry)
                input_smoke_paths.append((f"roundtrip_{case.name}", output_path, False, None))
                log.line(
                    f"RESULT {case.name}: {'PASS' if output_entry['ok'] else 'FAIL'} "
                    f"size={output_entry['fileSizeBytes']} "
                    f"peak={(info.get('hdr') or {}).get('rgb_max')}"
                )
                for warning in warnings:
                    log.line(f"  WARNING: {warning}")
                for error in errors:
                    log.line(f"  ERROR: {error}")
            else:
                output_entry["errors"].append(command_result.get("error") or "conversion command failed")
                log.line(f"RESULT {case.name}: FAIL conversion did not produce usable output")

            summary["outputs"].append(output_entry)
            if args.fail_fast and not output_entry["ok"]:
                break

        summary["inputSmoke"] = smoke_decode_inputs(log, input_smoke_paths, inspect_dir)
        summary["finishedAt"] = datetime.now().isoformat(timespec="seconds")
        summary["ok"] = all(item.get("ok") for item in summary["outputs"]) and all(
            item.get("ok") for item in summary["inputSmoke"]
        )
        write_json(run_root / "summary.json", summary)
        log.section("SUMMARY")
        log.line(f"SUMMARY_JSON: {run_root / 'summary.json'}")
        log.line(f"RUN_LOG: {log.path}")
        log.line(f"OVERALL: {'PASS' if summary['ok'] else 'FAIL'}")
        return 0 if summary["ok"] else 1
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
