"""
HDR processing helpers.

Converts linear scRGB-like HDR data to an SDR base image, a PQ-encoded HDR
alternate image, and a legacy gain-map representation.
"""
import numpy as np

from hdr_transcoder.color import clamp_small_negatives, linear_srgb_to_bt2020, linear_srgb_to_display_p3


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
    """Tone-map HDR data to an 8-bit sRGB SDR base image.

    headroom is expressed in stops. The tone mapper uses at least that white
    point, but expands to the image peak so the SDR base avoids hard clipping.
    """
    if headroom <= 0:
        raise ValueError("headroom must be > 0")

    hdr_rgb = np.maximum(hdr_linear[..., :3], 0.0)
    peak = float(np.max(hdr_rgb)) if hdr_rgb.size else 1.0
    white_point = max(2.0 ** headroom, peak, 1.0)
    sdr_linear = hdr_rgb * (1.0 + hdr_rgb / (white_point * white_point)) / (1.0 + hdr_rgb)
    sdr_gamma = _srgb_gamma(sdr_linear)
    return (sdr_gamma * 255.0 + 0.5).clip(0, 255).astype(np.uint8)


def prepare_base_sdr_display_p3(hdr_linear, headroom=1.0, saturation=1.18, contrast=1.08):
    """Tone-map HDR data to an 8-bit Display P3 SDR base image.

    The tone curve is applied to luminance and then reused as an RGB scale so
    hue/chroma survive better than per-channel SDR tone mapping.
    """
    if headroom <= 0:
        raise ValueError("headroom must be > 0")

    hdr_p3 = clamp_small_negatives(linear_srgb_to_display_p3(hdr_linear[..., :3]))
    hdr_p3 = np.maximum(hdr_p3, 0.0)
    lum_weights = np.array([0.2289746, 0.6917385, 0.0792869], dtype=np.float32)
    luminance = np.sum(hdr_p3 * lum_weights, axis=-1, keepdims=True)
    peak = float(np.max(luminance)) if luminance.size else 1.0
    white_point = max(2.0 ** headroom, peak, 1.0)
    mapped_luminance = luminance * (1.0 + luminance / (white_point * white_point)) / (1.0 + luminance)
    scale = mapped_luminance / np.maximum(luminance, 1e-8)
    sdr_p3 = hdr_p3 * scale

    if contrast != 1.0:
        pivot = np.float32(0.18)
        sdr_p3 = pivot * np.power(np.maximum(sdr_p3, 0.0) / pivot, contrast)
    if saturation != 1.0:
        sdr_luminance = np.sum(sdr_p3 * lum_weights, axis=-1, keepdims=True)
        sdr_p3 = sdr_luminance + (sdr_p3 - sdr_luminance) * saturation
        sdr_p3 = np.maximum(sdr_p3, 0.0)

    max_channel = np.max(sdr_p3, axis=-1, keepdims=True)
    sdr_p3 = np.where(max_channel > 1.0, sdr_p3 / np.maximum(max_channel, 1e-8), sdr_p3)
    sdr_gamma = _srgb_gamma(sdr_p3)
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


def prepare_alternate_hdr(hdr_linear, sdr_white_nits=100.0, target_primaries="bt2020"):
    """Prepare a PQ-encoded 16-bit HDR alternate image."""
    hdr_rgb = hdr_linear[..., :3]
    if target_primaries == "bt2020":
        hdr_rgb = clamp_small_negatives(linear_srgb_to_bt2020(hdr_rgb))
    elif target_primaries not in {"srgb", "bt709"}:
        raise ValueError(f"Unsupported HDR alternate primaries: {target_primaries}")

    hdr_rgb = np.maximum(hdr_rgb, 0.0)
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
