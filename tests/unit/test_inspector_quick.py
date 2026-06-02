import math
import subprocess

import numpy as np
import pytest

from hdr_transcoder.cli import _source_peak_headroom
from hdr_transcoder.inspector import _inspect_color_metadata, inspect_image


@pytest.mark.quick
def test_source_peak_headroom_values():
    assert _source_peak_headroom(np.array([[[0.5, 0.25, 0.1]]], dtype=np.float32)) == 0.0
    assert _source_peak_headroom(np.array([[[1.0, 0.25, 0.1]]], dtype=np.float32)) == 0.0
    assert _source_peak_headroom(np.array([[[2.0, 0.25, 0.1]]], dtype=np.float32)) == 1.0
    assert _source_peak_headroom(np.array([[[4.0, 0.25, 0.1]]], dtype=np.float32)) == 2.0
    assert math.isclose(
        _source_peak_headroom(np.array([[[5.003887, 0.25, 0.1]]], dtype=np.float32)),
        2.323049,
        abs_tol=1e-5,
    )


@pytest.mark.quick
def test_inspector_reports_hdr_fixture_metadata(hdr_jxl_fixture):
    info = inspect_image(hdr_jxl_fixture)

    assert info["error"] is None
    assert info["detected_format"] == "jpegxl"
    assert info["width"] == 30
    assert info["height"] == 20
    assert info["hdr"]["is_hdr"] is True
    assert math.isclose(info["hdr"]["rgb_max"], 5.003887, abs_tol=0.001)
    assert math.isclose(info["hdr"]["peak_headroom"], 2.323049, abs_tol=0.001)
    assert info["color"]["transfer_label"] == "Linear"


@pytest.mark.quick
def test_inspector_infers_jpegxr_scrgb_color_metadata(tmp_path):
    sample = tmp_path / "sample.jxr"
    sample.write_bytes(b"not a real jpeg xr; metadata inference does not decode")
    warnings = []

    color = _inspect_color_metadata(sample, "jpegxr", warnings)

    assert color["primaries"] == 1
    assert color["transfer"] == 8
    assert color["matrix"] == 0
    assert color["primaries_label"] == "BT.709 / sRGB"
    assert color["transfer_label"] == "Linear"
    assert color["matrix_label"] == "RGB identity"
    assert color["source"] == "JPEG XR scRGB linear (inferred)"
    assert color["inferred"] is True
    assert warnings == []


@pytest.mark.quick
@pytest.mark.tools
def test_headroom_helper_advertises_override_options(avifgainmaputil_hdr):
    if not avifgainmaputil_hdr.exists():
        pytest.skip(f"Missing patched helper: {avifgainmaputil_hdr}")

    result = subprocess.run(
        [str(avifgainmaputil_hdr), "combine", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    output = f"{result.stdout}\n{result.stderr}"
    assert "--base-headroom" in output
    assert "--alternate-headroom" in output
