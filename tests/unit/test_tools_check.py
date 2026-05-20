import pytest

from hdr_transcoder.tools import REQUIRED_TOOLS, check_runtime_environment, check_tool_invocation


@pytest.mark.quick
@pytest.mark.tools
def test_runtime_self_check_reports_bundled_tools():
    result = check_runtime_environment()
    assert result["ok"] is True
    assert result["missingTools"] == []
    assert {item for item in REQUIRED_TOOLS} == {
        "avifgainmaputil.exe",
        "avifgainmaputil_hdr.exe",
        "avifdec.exe",
        "cjxl.exe",
        "jxlinfo.exe",
    }


@pytest.mark.quick
@pytest.mark.tools
def test_bundled_tools_advertise_help():
    result = check_tool_invocation()
    for name in REQUIRED_TOOLS:
        assert result[name]["ok"] is True, result[name]
    helper_output = f"{result['avifgainmaputil_hdr.exe']['stdout']}\n{result['avifgainmaputil_hdr.exe']['stderr']}"
    assert "--base-headroom" in helper_output
    assert "--alternate-headroom" in helper_output
