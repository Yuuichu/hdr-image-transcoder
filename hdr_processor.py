"""
HDR processing helpers.

Converts linear scRGB-like HDR data to an SDR base image, a PQ-encoded HDR
alternate image, and a legacy gain-map representation.
"""
import numpy as np


def _srgb_gamma(linear):
    """Apply sRGB gamma encoding to linear values clamped to [0, 1]."""
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def _srgb_inverse_gamma(encoded):
    """Decode sRGB gamma values to linear values."""
    encoded = np.asarray(encoded)
    if np.issubdtype(encoded.dtype, np.floating):
        enc = np.clip(encoded.astype(np.float32), 0.0, 1.0)
    else:
        info = np.iinfo(encoded.dtype)
        enc = encoded.astype(np.float32) / float(info.max)

    return np.where(
        enc <= 0.04045,
        enc / 12.92,
        np.power((enc + 0.055) / 1.055, 2.4),
    )


def prepare_base_sdr(hdr_linear, headroom=1.0):
    """Tone-map HDR data to an 8-bit sRGB SDR base image."""
    if headroom <= 0:
        raise ValueError("headroom must be > 0")

    hdr_rgb = np.maximum(hdr_linear[..., :3], 0.0)
    max_rgb = hdr_rgb.max(axis=-1, keepdims=True)
    max_rgb_safe = np.maximum(max_rgb, 1e-8)
    scale = np.where(max_rgb > headroom, headroom / max_rgb_safe, 1.0)
    sdr_linear = hdr_rgb * scale
    sdr_gamma = _srgb_gamma(sdr_linear)
    return (sdr_gamma * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


def _linear_to_pq(linear, max_nits=10000.0):
    """Convert linear luminance in nits to ST.2084 PQ values in [0, 1]."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875
    y = np.clip(linear / max_nits, 0.0, 1.0)
    y_pow = np.power(y, m1)
    return np.power((c1 + c2 * y_pow) / (1.0 + c3 * y_pow), m2)


def prepare_alternate_hdr(hdr_linear, sdr_white_nits=100.0):
    """Prepare a PQ-encoded 16-bit HDR alternate image."""
    hdr_rgb = np.maximum(hdr_linear[..., :3], 0.0)
    luminance = hdr_rgb * sdr_white_nits
    pq_vals = _linear_to_pq(luminance)
    return (pq_vals * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)


def _pq_to_linear(pq_values, max_nits=10000.0):
    """Convert ST.2084 PQ values in [0, 1] to linear luminance in nits."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875

    pq = np.clip(pq_values, 0.0, 1.0)
    pq_pow = np.power(pq, 1.0 / m2)
    linear_norm = np.maximum(pq_pow - c1, 0.0) / (c2 - c3 * pq_pow)
    linear_norm = np.power(linear_norm, 1.0 / m1)
    return linear_norm * max_nits


def _hlg_to_linear(hlg_values):
    """Convert HLG values in [0, 1] to relative linear luminance."""
    a = 0.17883277
    b = 1.0 - 4.0 * a
    c = 0.5 - a * np.log(4.0 * a)

    hlg = np.clip(hlg_values, 0.0, 1.0)
    linear = np.where(
        hlg <= 0.5,
        hlg ** 2 / 3.0,
        (np.exp((hlg - c) / a) + b) / 12.0,
    )

    # HLG nominal peak is 12x SDR white.
    return linear * 12.0


def normalize_to_scrgb(pixels, source_info):
    """Normalize decoded pixel data to linear scRGB-like values.

    source_info["color_space"] may be "scRGB", "PQ", "HLG", or "sRGB".
    The output keeps the input channel count.
    """
    color_space = source_info.get("color_space", "scRGB")

    if color_space == "PQ":
        max_nits = source_info.get("max_nits", 10000.0)
        pixels = _pq_to_linear(pixels, max_nits=max_nits) / 100.0
    elif color_space == "HLG":
        pixels = _hlg_to_linear(pixels)
    elif color_space == "sRGB":
        pixels = _srgb_inverse_gamma(pixels)

    return np.maximum(pixels.astype(np.float32), 0.0)


def compute_gainmap(hdr_linear, headroom=1.0):
    """Convert linear HDR data to an SDR base image and uint8 log2 gain map."""
    if headroom <= 0:
        raise ValueError("headroom must be > 0")

    hdr_rgb = np.maximum(hdr_linear[..., :3], 0.0)

    max_rgb = hdr_rgb.max(axis=-1, keepdims=True)
    max_rgb_safe = np.maximum(max_rgb, 1e-8)
    scale = np.where(max_rgb > headroom, headroom / max_rgb_safe, 1.0)
    sdr_linear = hdr_rgb * scale

    sdr_gamma = _srgb_gamma(sdr_linear)
    sdr_8bit = (sdr_gamma * 255.0 + 0.5).clip(0, 255).astype(np.uint8)

    l_hdr = np.maximum(hdr_rgb.max(axis=-1), 1e-6)
    l_sdr = np.maximum(sdr_linear.max(axis=-1), 1e-6)
    gain_log2 = np.log2(l_hdr / l_sdr)

    min_log = -4.0
    max_log = 4.0
    gain_norm = (gain_log2 - min_log) / (max_log - min_log)
    gain_map = (gain_norm * 255.0 + 0.5).clip(0, 255).astype(np.uint8)

    return sdr_8bit, gain_map
