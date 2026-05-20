import math
import re
import subprocess
import sys

import pytest

from hdr_transcoder.formats.decoder import decode_to_scrgb
from hdr_transcoder.inspector import inspect_image

from helpers import ROOT, require_tool, run_python, stop_delta


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_source_peak_headroom_and_decoded_peak(
    hdr_jxl_fixture,
    tmp_path,
    avifgainmaputil,
    avifgainmaputil_hdr,
):
    require_tool(avifgainmaputil)
    require_tool(avifgainmaputil_hdr)

    output = tmp_path / "test_gainmap.avif"
    run_python(
        [
            "hdr2avif.py",
            hdr_jxl_fixture,
            output,
            "--format",
            "gainmap",
            "--fidelity",
            "compat",
            "--speed",
            "8",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    source_pixels, _, _ = decode_to_scrgb(str(hdr_jxl_fixture))
    output_pixels, _, _ = decode_to_scrgb(str(output))
    source_peak = float(source_pixels[..., :3].max())
    output_peak = float(output_pixels[..., :3].max())
    source_headroom = math.log2(max(source_peak, 1.0))

    info = inspect_image(output)
    alternate_headroom = info["gainmap"]["alternate_headroom"]

    assert info["gainmap"]["present"] is True
    assert info["gainmap"]["base_headroom"] == 0.0
    assert alternate_headroom + 0.02 >= source_headroom
    assert stop_delta(source_peak, output_peak) <= 0.05
    assert info["gainmap"]["alternate_color"]["primaries"] == 9
    assert info["gainmap"]["alternate_color"]["transfer"] == 16
    assert info["gainmap"]["alternate_color"]["matrix"] == 9


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_auto_mode_remains_observable_for_comparison(
    hdr_jxl_fixture,
    tmp_path,
    avifgainmaputil,
    avifgainmaputil_hdr,
):
    require_tool(avifgainmaputil)
    require_tool(avifgainmaputil_hdr)

    output = tmp_path / "test_gainmap_auto.avif"
    run_python(
        [
            "hdr2avif.py",
            hdr_jxl_fixture,
            output,
            "--format",
            "gainmap",
            "--fidelity",
            "compat",
            "--speed",
            "8",
            "--gainmap-headroom-mode",
            "auto",
        ],
        timeout=300,
    )

    info = inspect_image(output)
    assert info["gainmap"]["present"] is True
    assert isinstance(info["gainmap"]["alternate_headroom"], float)


@pytest.mark.fidelity
@pytest.mark.tools
def test_verify_fidelity_rejects_low_auto_gainmap_headroom(
    hdr_jxl_fixture,
    tmp_path,
    avifgainmaputil,
    avifgainmaputil_hdr,
):
    require_tool(avifgainmaputil)
    require_tool(avifgainmaputil_hdr)

    output = tmp_path / "test_gainmap_auto_verify.avif"
    result = subprocess.run(
        [
            sys.executable,
            "hdr2avif.py",
            str(hdr_jxl_fixture),
            str(output),
            "--format",
            "gainmap",
            "--fidelity",
            "compat",
            "--speed",
            "8",
            "--gainmap-headroom-mode",
            "auto",
            "--verify-fidelity",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode != 0
    output_text = f"{result.stdout}\n{result.stderr}"
    assert "source_peak_headroom=" in output_text
    assert "actual_headroom=" in output_text
    assert "delta=" in output_text
    assert "tolerance=0.0200 stops" in output_text


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_printmetadata_reports_source_peak_headroom(
    hdr_jxl_fixture,
    tmp_path,
    avifgainmaputil,
    avifgainmaputil_hdr,
):
    require_tool(avifgainmaputil)
    require_tool(avifgainmaputil_hdr)

    output = tmp_path / "test_gainmap_metadata.avif"
    run_python(
        [
            "hdr2avif.py",
            hdr_jxl_fixture,
            output,
            "--format",
            "gainmap",
            "--fidelity",
            "compat",
            "--speed",
            "8",
        ],
        timeout=300,
    )

    result = subprocess.run(
        [str(avifgainmaputil), "printmetadata", str(output)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    match = re.search(r"Alternate headroom:\s*([0-9.]+)", result.stdout)
    assert match
    assert float(match.group(1)) >= 2.32


@pytest.mark.fidelity
@pytest.mark.tools
def test_jxl_master_stays_linear_with_low_peak_error(hdr_jxl_fixture, tmp_path, cjxl):
    require_tool(cjxl)

    output = tmp_path / "master.jxl"
    run_python(
        [
            "hdr2avif.py",
            hdr_jxl_fixture,
            output,
            "--format",
            "jxl",
            "--fidelity",
            "master",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    source_pixels, _, _ = decode_to_scrgb(str(hdr_jxl_fixture))
    output_pixels, _, _ = decode_to_scrgb(str(output))
    source_peak = float(source_pixels[..., :3].max())
    output_peak = float(output_pixels[..., :3].max())
    info = inspect_image(output)

    assert info["detected_format"] == "jpegxl"
    assert info["color"]["transfer_label"] == "Linear"
    assert abs(output_peak - source_peak) <= 0.02


@pytest.mark.fidelity
@pytest.mark.tools
def test_standard_avif_writes_rec2020_pq_cicp(hdr_jxl_fixture, tmp_path, avifdec):
    require_tool(avifdec)

    output = tmp_path / "standard_hdr.avif"
    run_python(
        [
            "hdr2avif.py",
            hdr_jxl_fixture,
            output,
            "--format",
            "avif",
            "--fidelity",
            "display",
            "--speed",
            "8",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    info = inspect_image(output)
    assert info["detected_format"] == "avif"
    assert info["color"]["primaries"] == 9
    assert info["color"]["transfer"] == 16
    assert info["color"]["matrix"] == 9
