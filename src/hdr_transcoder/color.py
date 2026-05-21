"""Color-space helpers for HDR encoding and decoding."""
import numpy as np

from hdr_transcoder.config import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_BT709_MATRIX,
    CICP_BT709_PRIMARIES,
    CICP_DISPLAY_P3_PRIMARIES,
    CICP_PQ_TRANSFER,
    CICP_SRGB_TRANSFER,
)


# RGB-to-XYZ matrices for D65 white point.
_SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)

_BT2020_TO_XYZ = np.array(
    [
        [0.6369580, 0.1446169, 0.1688810],
        [0.2627002, 0.6779981, 0.0593017],
        [0.0000000, 0.0280727, 1.0609851],
    ],
    dtype=np.float64,
)

_DISPLAY_P3_TO_XYZ = np.array(
    [
        [0.4865709, 0.2656677, 0.1982173],
        [0.2289746, 0.6917385, 0.0792869],
        [0.0000000, 0.0451134, 1.0439444],
    ],
    dtype=np.float64,
)

_SRGB_TO_BT2020 = np.linalg.inv(_BT2020_TO_XYZ) @ _SRGB_TO_XYZ
_BT2020_TO_SRGB = np.linalg.inv(_SRGB_TO_XYZ) @ _BT2020_TO_XYZ
_SRGB_TO_DISPLAY_P3 = np.linalg.inv(_DISPLAY_P3_TO_XYZ) @ _SRGB_TO_XYZ
_DISPLAY_P3_TO_SRGB = np.linalg.inv(_SRGB_TO_XYZ) @ _DISPLAY_P3_TO_XYZ
_BT2020_TO_DISPLAY_P3 = np.linalg.inv(_DISPLAY_P3_TO_XYZ) @ _BT2020_TO_XYZ


def linear_srgb_to_bt2020(rgb):
    """Convert linear sRGB/scRGB samples to linear BT.2020 samples."""
    return np.asarray(rgb, dtype=np.float32) @ _SRGB_TO_BT2020.T


def linear_bt2020_to_srgb(rgb):
    """Convert linear BT.2020 samples to linear sRGB/scRGB samples."""
    return np.asarray(rgb, dtype=np.float32) @ _BT2020_TO_SRGB.T


def linear_srgb_to_display_p3(rgb):
    """Convert linear sRGB/scRGB samples to linear Display P3 samples."""
    return np.asarray(rgb, dtype=np.float32) @ _SRGB_TO_DISPLAY_P3.T


def linear_display_p3_to_srgb(rgb):
    """Convert linear Display P3 samples to linear sRGB/scRGB samples."""
    return np.asarray(rgb, dtype=np.float32) @ _DISPLAY_P3_TO_SRGB.T


def linear_bt2020_to_display_p3(rgb):
    """Convert linear BT.2020 samples to linear Display P3 samples."""
    return np.asarray(rgb, dtype=np.float32) @ _BT2020_TO_DISPLAY_P3.T


def clamp_small_negatives(rgb, epsilon=1e-6):
    """Remove tiny matrix-rounding negatives while preserving real excursions."""
    rgb = np.asarray(rgb, dtype=np.float32)
    return np.where((rgb < 0.0) & (rgb > -epsilon), 0.0, rgb)
