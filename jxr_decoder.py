"""
JXR (JPEG XR) HDR decoder using imagecodecs.

Decodes JXR files to non-negative float32 linear RGBA data.
"""
from pathlib import Path

import numpy as np


def _to_float32(pixels):
    if np.issubdtype(pixels.dtype, np.floating):
        return np.maximum(pixels.astype(np.float32), 0.0)
    info = np.iinfo(pixels.dtype)
    return np.maximum(pixels.astype(np.float32) / float(info.max), 0.0)


def _ensure_rgba(pixels):
    if pixels.ndim == 2:
        pixels = pixels[..., np.newaxis]
    if pixels.shape[2] == 1:
        pixels = np.repeat(pixels, 3, axis=2)
    if pixels.shape[2] == 3:
        alpha = np.ones((*pixels.shape[:2], 1), dtype=pixels.dtype)
        pixels = np.concatenate([pixels, alpha], axis=2)
    elif pixels.shape[2] > 4:
        pixels = pixels[..., :4]
    return pixels


def decode_jxr(filepath):
    """Decode a JXR file to float32 RGBA data.

    Returns: (pixels_float32, width, height)
      pixels: ndarray (H, W, 4), float32, linear scRGB-like values
    """
    import imagecodecs

    raw = Path(filepath).read_bytes()
    pixels = _ensure_rgba(_to_float32(imagecodecs.jpegxr_decode(raw)))
    height, width = pixels.shape[:2]
    return pixels, width, height


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python jxr_decoder.py <file.jxr>")
        sys.exit(1)

    pixels, w, h = decode_jxr(sys.argv[1])
    print(f"Decoded: {w}x{h}")
    print(f"Shape: {pixels.shape}, dtype: {pixels.dtype}")
    print(f"RGB range: [{pixels[..., :3].min():.4f}, {pixels[..., :3].max():.4f}]")
    print(f"Alpha range: [{pixels[..., 3].min():.4f}, {pixels[..., 3].max():.4f}]")
    above_sdr = (pixels[..., :3].max(axis=-1) > 1.0).sum()
    print(f"HDR pixels (>1.0 RGB): {above_sdr} / {w * h} ({100 * above_sdr / (w * h):.1f}%)")
