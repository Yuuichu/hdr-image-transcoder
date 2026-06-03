import argparse
import math
from types import SimpleNamespace

import pytest

from hdr_transcoder.cli import _validate_args
from hdr_transcoder.config import GAINMAP_HEADROOM_SOURCE_PEAK, ULTRAHDR_BACKEND_AUTO, ULTRAHDR_PROFILE_APPLE_P3


def _valid_args(**overrides):
    values = {
        "quality": 100,
        "speed": 0,
        "max_headroom": None,
        "headroom": 2.0,
        "fidelity": "compat",
        "jxl_mode": None,
        "gainmap_headroom_mode": GAINMAP_HEADROOM_SOURCE_PEAK,
        "heic_rgb_gainmap_only": False,
        "heic_apple_gainmap_only": False,
        "format": "ultrahdr",
        "uhdr_backend": ULTRAHDR_BACKEND_AUTO,
        "uhdr_profile": ULTRAHDR_PROFILE_APPLE_P3,
        "uhdr_gainmap_scale": 2,
        "uhdr_gainmap_gamma": 1.0,
        "uhdr_target_peak_nits": 1000.0,
        "name_start": 1,
        "name_padding": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.quick
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_headroom", math.nan),
        ("headroom", math.nan),
        ("uhdr_gainmap_gamma", math.nan),
        ("uhdr_target_peak_nits", math.nan),
    ],
)
def test_validate_args_rejects_nan_float_options(field, value):
    parser = argparse.ArgumentParser()
    args = _valid_args(**{field: value})

    with pytest.raises(SystemExit):
        _validate_args(parser, args)
