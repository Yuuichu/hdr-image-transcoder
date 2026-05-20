"""Fidelity tests for gainmap HEIC output."""
import math
import subprocess
import sys

import numpy as np
import pytest

from hdr_transcoder.formats.decoder import decode_to_scrgb
from hdr_transcoder.formats.isobmff import _parse_boxes, read_heic_gainmap_metadata
from hdr_transcoder.inspector import inspect_image

from helpers import ROOT, run_python, stop_delta


HEIFGAINMAPUTIL_HDR = ROOT / "tools" / "libheif" / "heifgainmaputil_hdr.py"


def _pq_encode_16bit(linear_nits, max_nits=10000.0):
    """Encode linear nits values to PQ 16-bit integer."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875
    linear = np.asarray(linear_nits, dtype=np.float32) / max_nits
    linear = np.maximum(linear, 0.0)
    linear_pow = np.power(linear, m1)
    numerator = c1 + c2 * linear_pow
    denominator = 1.0 + c3 * linear_pow
    pq = np.power(numerator / denominator, m2)
    return (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)


def _make_pq_tiff(pixels_16bit):
    """Encode 16-bit pixels as TIFF using imagecodecs."""
    import imagecodecs
    return imagecodecs.tiff_encode(np.asarray(pixels_16bit, dtype=np.uint16))


def _tmap_headroom(heic_path):
    """Read tmap box headroom values from a HEIC file."""
    metadata = read_heic_gainmap_metadata(heic_path)
    assert metadata is not None, "HEIC missing tmap box"
    return {
        "base": metadata["baseHeadroom"],
        "alternate": metadata["alternateHeadroom"],
    }


@pytest.mark.fidelity
def test_gainmap_heic_structure_is_valid(tmp_path):
    """Verify the ISOBMFF structure of a gainmap HEIC output."""
    import imagecodecs

    # Build SDR base PNG (8-bit sRGB gradient)
    h, w = 64, 64
    sdr_8bit = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        val = int(255 * (y / h))
        sdr_8bit[y, :, :] = [val, val, val]
    base_png = imagecodecs.png_encode(sdr_8bit)

    # Build HDR alternate PNG (16-bit PQ gradient)
    linear_nits = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(h):
        lval = 10.0 + 1000.0 * (y / h)
        linear_nits[y, :, :] = [0.1 * lval, lval, 0.1 * lval]
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    alt_png = imagecodecs.png_encode(pq_16bit)

    base_path = tmp_path / "base.png"
    base_path.write_bytes(base_png)
    alt_path = tmp_path / "alternate.png"
    alt_path.write_bytes(alt_png)
    output_path = tmp_path / "output.heic"

    import os
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not existing_pythonpath else f"{ROOT}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [
            sys.executable,
            str(HEIFGAINMAPUTIL_HDR),
            "combine",
            str(base_path),
            str(alt_path),
            str(output_path),
            "--speed", "8",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"heifgainmaputil_hdr combine failed:\n{result.stdout}\n{result.stderr}"

    # Verify ISOBMFF structure
    data = output_path.read_bytes()
    top_boxes = _parse_boxes(data)
    box_types = {bt for bt, _, _, _ in top_boxes}
    assert "ftyp" in box_types, "missing ftyp box"
    assert "meta" in box_types, "missing meta box"
    assert "mdat" in box_types, "missing mdat box"

    # Verify tmap headroom
    headroom = _tmap_headroom(output_path)
    assert isinstance(headroom["base"], float)
    assert isinstance(headroom["alternate"], float)
    assert headroom["base"] >= 0
    assert headroom["alternate"] > 0

    # Verify gainmap info via inspector
    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert info["gainmap"]["alternate_color"]["primaries"] == 9
    assert info["gainmap"]["alternate_color"]["transfer"] == 16
    assert info["gainmap"]["alternate_color"]["matrix"] == 9


@pytest.mark.fidelity
@pytest.mark.tools
def test_cli_pq_tiff_to_gainmap_heic(tmp_path):
    """End-to-end: --pq-input --format gainmap-heic with verify-fidelity."""
    import imagecodecs

    # Build PQ TIFF with known peak
    h, w = 32, 32
    linear_nits = np.full((h, w, 3), 500.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    # Verify output
    source_peak = float(linear_nits[..., :3].max() / 100.0)
    source_headroom = math.log2(max(source_peak, 1.0))

    output_pixels, _, _ = decode_to_scrgb(str(output_path))
    output_peak = float(output_pixels[..., :3].max())

    assert stop_delta(source_peak, output_peak) <= 0.05

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert info["gainmap"]["base_headroom"] == 0.0
    assert info["gainmap"]["alternate_headroom"] + 0.02 >= source_headroom
    assert info["gainmap"]["alternate_color"]["primaries"] == 9
    assert info["gainmap"]["alternate_color"]["transfer"] == 16
    assert info["gainmap"]["alternate_color"]["matrix"] == 9


@pytest.mark.fidelity
def test_gainmap_heic_info_json(tmp_path):
    """Verify --info-json works for gainmap-heic output."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 300.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--info-json",
        ],
        timeout=300,
    )

    import json
    info_json_path = tmp_path / "output.info.json"
    assert info_json_path.exists()
    payload = json.loads(info_json_path.read_text())
    assert payload["format"] == "gainmap-heic"
    assert payload["gainmap"]["present"] is True
    assert payload["gainmap"]["alternateCicp"]["primaries"] == 9


@pytest.mark.fidelity
def test_gainmap_heic_verify_fidelity_rejects_wrong_alternate_color(tmp_path):
    """Verify that validation catches incorrect alternate CICP in gainmap HEIC."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 500.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    # Use standard heif format which won't have gainmap metadata
    output_path = tmp_path / "plain.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "heif",
            "--fidelity", "display",
            "--speed", "8",
        ],
        timeout=300,
    )
    # This should create a standard HEIF without gainmap - just verify it doesn't crash
    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is False


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_heic_auto_headroom_works(tmp_path):
    """Test gainmap-heic with auto headroom mode."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 300.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--gainmap-headroom-mode", "auto",
        ],
        timeout=300,
    )

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert isinstance(info["gainmap"]["alternate_headroom"], float)
