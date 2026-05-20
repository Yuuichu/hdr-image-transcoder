import pytest
from PIL import Image

from helpers import require_tool, run_python


@pytest.mark.fidelity
@pytest.mark.tools
def test_debug_overlay_creates_sidecar_png(
    hdr_jxl_fixture,
    tmp_path,
    avifgainmaputil,
    avifgainmaputil_hdr,
):
    require_tool(avifgainmaputil)
    require_tool(avifgainmaputil_hdr)

    output = tmp_path / "overlay_gainmap.avif"
    overlay = tmp_path / "overlay_gainmap_debug.png"
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
            "--debug-overlay",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    assert output.exists()
    assert overlay.exists()
    assert output.stat().st_size > 0
    assert overlay.stat().st_size > 0

    with Image.open(overlay) as image:
        assert image.mode == "RGB"
        assert image.size == (30, 20)
