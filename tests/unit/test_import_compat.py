import importlib
import subprocess
import sys

import pytest

from helpers import ROOT, run_python


@pytest.mark.quick
def test_new_package_and_old_src_imports_are_compatible():
    new_cli = importlib.import_module("hdr_transcoder.cli")
    old_cli = importlib.import_module("src.cli")
    new_decoder = importlib.import_module("hdr_transcoder.formats.decoder")
    old_decoder = importlib.import_module("src.decoder")

    assert new_cli.main is old_cli.main
    assert new_decoder.decode_to_scrgb is old_decoder.decode_to_scrgb


@pytest.mark.quick
def test_legacy_entry_points_still_parse():
    run_python(["hdr2avif.py", "--list-formats"], timeout=60)
    run_python(["jxr2avif.py", "--list-output-formats"], timeout=60)


@pytest.mark.quick
def test_module_inspector_entry_point(hdr_jxl_fixture):
    result = subprocess.run(
        [sys.executable, "-m", "hdr_transcoder.inspector", str(hdr_jxl_fixture)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert '"detected_format": "jpegxl"' in result.stdout
