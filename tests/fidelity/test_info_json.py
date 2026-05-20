import json
import math

import pytest

from hdr_transcoder.inspector import inspect_image
from helpers import require_tool, run_python


@pytest.mark.fidelity
@pytest.mark.tools
def test_info_json_matches_inspector(hdr_jxl_fixture, tmp_path, cjxl):
    require_tool(cjxl)

    output = tmp_path / "master_info.jxl"
    info_json = tmp_path / "master_info.info.json"
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
            "--info-json",
        ],
        timeout=300,
    )

    payload = json.loads(info_json.read_text(encoding="utf-8"))
    inspector = inspect_image(output)

    assert payload["format"] == "jxl"
    assert payload["verify"]["ok"] is True
    assert payload["inspector"]["detected_format"] == inspector["detected_format"]
    assert math.isclose(payload["peak"]["rgbMax"], inspector["hdr"]["rgb_max"], abs_tol=1e-6)
