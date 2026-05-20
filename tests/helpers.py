import math
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
LIBAVIF_DIR = ROOT / "tools" / "libavif"
LIBJXL_DIR = ROOT / "tools" / "libjxl"


def require_tool(path):
    if not Path(path).exists():
        pytest.skip(f"Missing required tool: {path}")


def run_python(args, timeout=300):
    result = subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"Command failed: python {' '.join(map(str, args))}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return result


def stop_delta(left_peak, right_peak):
    assert left_peak > 0
    assert right_peak > 0
    return abs(math.log2(right_peak / left_peak))
