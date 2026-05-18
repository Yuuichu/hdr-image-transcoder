"""
Multi-format HDR decoder.

Decodes JXR, JXL, EXR, AVIF, HEIC, Ultra HDR, Radiance HDR, and common
raster formats to float32 linear scRGB-like pixel data.
"""
import re
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np


EXTENSION_MAP = {
    ".jxr": "jpegxr",
    ".wdp": "jpegxr",
    ".hdp": "jpegxr",
    ".jxl": "jpegxl",
    ".exr": "exr",
    ".avif": "avif",
    ".heic": "heif",
    ".heif": "heif",
    ".hdr": "rgbe",
    ".jpg": "ultrahdr",
    ".jpeg": "ultrahdr",
    ".png": "png",
    ".tif": "tiff",
    ".tiff": "tiff",
}

MAGIC_BYTES = {
    b"\x00\x00\x00\x0c\x6a\x50\x20\x20": "jpegxl",
    b"\xff\x0a": "jpegxl",
    b"\x76\x2f\x31\x01": "exr",
    b"\x23\x3f\x52\x41\x44\x49\x41\x4e\x43\x45": "rgbe",
    b"II\x2a\x00": "tiff",
    b"MM\x00\x2a": "tiff",
    b"II\x2b\x00": "tiff",
    b"MM\x00\x2b": "tiff",
    b"\x89PNG": "png",
}

AVIF_BRANDS = {b"avif", b"avis"}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}


def probe_format(filepath):
    """Detect image format by magic bytes, falling back to extension."""
    path = Path(filepath)
    ext = path.suffix.lower()

    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
    except OSError as e:
        if not isinstance(e, FileNotFoundError):
            raise
        if ext in {".jxr", ".wdp", ".hdp"}:
            return "jpegxr"
        return EXTENSION_MAP.get(ext)

    if len(header) >= 12 and header[4:8] == b"ftyp":
        brands = {header[8:12]}
        brands.update(header[i:i + 4] for i in range(16, len(header), 4))
        if brands & AVIF_BRANDS:
            return "avif"
        if brands & HEIF_BRANDS:
            return "heif"

    for magic, fmt in MAGIC_BYTES.items():
        if header.startswith(magic):
            return fmt

    if ext in {".jxr", ".wdp", ".hdp"}:
        return "jpegxr"

    return EXTENSION_MAP.get(ext)


def _ensure_rgba(pixels):
    """Ensure pixels have RGBA channels (H, W, 4)."""
    pixels = np.asarray(pixels)

    if pixels.ndim == 2:
        pixels = pixels[..., np.newaxis]
    if pixels.ndim != 3:
        raise ValueError(f"Expected 2D or 3D image data, got shape {pixels.shape}")

    channels = pixels.shape[2]
    if channels == 1:
        pixels = np.repeat(pixels, 3, axis=2)
    if pixels.shape[2] == 3:
        alpha = np.ones((*pixels.shape[:2], 1), dtype=pixels.dtype)
        pixels = np.concatenate([pixels, alpha], axis=2)
    elif pixels.shape[2] > 4:
        pixels = pixels[..., :4]

    if pixels.shape[2] != 4:
        raise ValueError(f"Expected 1, 3, or 4 channels, got {pixels.shape[2]}")

    return pixels


def _to_float32(pixels):
    """Convert pixel arrays to non-negative float32 values."""
    pixels = np.asarray(pixels)

    if np.issubdtype(pixels.dtype, np.floating):
        return np.maximum(pixels.astype(np.float32), 0.0)
    if pixels.dtype == np.bool_:
        return pixels.astype(np.float32)
    if not np.issubdtype(pixels.dtype, np.integer):
        raise TypeError(f"Unsupported pixel dtype: {pixels.dtype}")

    info = np.iinfo(pixels.dtype)
    return np.maximum(pixels.astype(np.float32) / float(info.max), 0.0)


def _decode_jpegxr(raw):
    import imagecodecs

    return _to_float32(imagecodecs.jpegxr_decode(raw))


def _decode_jpegxl(raw):
    import imagecodecs

    return _to_float32(imagecodecs.jpegxl_decode(raw))


def _decode_exr(raw):
    import imagecodecs

    return _to_float32(imagecodecs.exr_decode(raw))


def _is_10bit_pq(pixels):
    """Heuristic: 10-bit PQ data decoded as uint16 with values in [0, 1023].

    WARNING: Value-range heuristic alone can misidentify dark 16-bit SDR as PQ.
    """
    if pixels.dtype != np.uint16:
        return False
    if pixels.size == 0:
        return False
    return pixels.max() <= 1023


def _decode_pq(pq_values):
    """Convert normalized PQ pixels to float32 scRGB."""
    from src.processor import _pq_to_linear

    linear_nits = _pq_to_linear(pq_values, max_nits=10000.0)
    return linear_nits / 100.0


def _decode_pq_10bit(pixels):
    """Convert 10-bit uint16 PQ pixels to float32 scRGB."""
    pq_norm = pixels.astype(np.float32) / 1023.0
    return _decode_pq(pq_norm)


def _decode_gainmap_avif(raw):
    """Decode an AVIF gain map by tone-mapping it to its HDR alternate."""
    from src.gainmap import AVIFGAINMAPUTIL

    if not AVIFGAINMAPUTIL.exists():
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / "input.avif"
        output_path = tmp / "tonemapped.avif"
        input_path.write_bytes(raw)

        metadata = subprocess.run(
            [str(AVIFGAINMAPUTIL), "printmetadata", str(input_path)],
            capture_output=True,
            text=True,
        )
        if metadata.returncode != 0:
            return None

        text = f"{metadata.stdout}\n{metadata.stderr}"
        match = re.search(r"Alternate headroom:\s*([0-9.+-]+)", text)
        if not match:
            return None

        alternate_headroom = float(match.group(1))
        if alternate_headroom <= 0:
            return None

        result = subprocess.run(
            [
                str(AVIFGAINMAPUTIL),
                "tonemap",
                str(input_path),
                str(output_path),
                "--headroom",
                f"{alternate_headroom:.6f}",
                "--cicp-output",
                "1/16/0",
                "-d",
                "10",
                "-y",
                "444",
                "-q",
                "95",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise ValueError(f"Cannot decode AVIF gain map: {detail}")

        import imagecodecs

        pixels = imagecodecs.avif_decode(output_path.read_bytes())
        if _is_10bit_pq(pixels):
            return _decode_pq_10bit(pixels)
        return _to_float32(pixels)


def _decode_avif(raw):
    import imagecodecs

    gainmap = _decode_gainmap_avif(raw)
    if gainmap is not None:
        return gainmap

    pixels = imagecodecs.avif_decode(raw)
    if _is_10bit_pq(pixels):
        return _decode_pq_10bit(pixels)
    return _to_float32(pixels)


def _decode_heif_with_pillow(raw):
    import pillow_heif

    heif_file = pillow_heif.open_heif(BytesIO(raw), convert_hdr_to_8bit=False)
    image = heif_file[0]
    width, height = image.size
    mode = image.mode

    if mode.endswith(";16"):
        base_mode = mode[:-3]
        dtype = np.uint16
        bytes_per_sample = 2
    else:
        base_mode = mode
        dtype = np.uint8
        bytes_per_sample = 1

    channels = len(base_mode)
    row_values = image.stride // bytes_per_sample
    row_pixels = np.frombuffer(image.data, dtype=dtype).reshape(height, row_values)
    pixels = row_pixels[:, :width * channels].reshape(height, width, channels)

    nclx = image.info.get("nclx_profile") or {}
    if nclx.get("transfer_characteristics") == 16:
        info = np.iinfo(dtype)
        pq_norm = pixels.astype(np.float32) / float(info.max)
        return _decode_pq(pq_norm)

    return _to_float32(pixels)


def _decode_heif(raw):
    try:
        return _decode_heif_with_pillow(raw)
    except Exception:
        import imagecodecs

        pixels = imagecodecs.heif_decode(raw)
        if _is_10bit_pq(pixels):
            return _decode_pq_10bit(pixels)
        return _to_float32(pixels)


def _decode_rgbe(raw):
    import imagecodecs

    return _to_float32(imagecodecs.rgbe_decode(raw))


def _decode_ultrahdr(raw):
    """Decode Ultra HDR JPEG and reconstruct a best-effort HDR image."""
    import imagecodecs

    result = imagecodecs.ultrahdr_decode(raw)
    if isinstance(result, tuple):
        sdr_base = _to_float32(result[0])
        gainmap = _to_float32(result[1]) if len(result) > 1 else None
        if gainmap is not None:
            return sdr_base * gainmap
        return sdr_base
    return _to_float32(result)


def _decode_png(raw):
    import imagecodecs

    return _to_float32(imagecodecs.png_decode(raw))


def _decode_tiff(raw):
    import imagecodecs

    return _to_float32(imagecodecs.tiff_decode(raw))


def _decode_wic(raw):
    import imagecodecs

    return _to_float32(imagecodecs.wic_decode(raw))


_DECODERS = {
    "jpegxr": _decode_jpegxr,
    "jpegxl": _decode_jpegxl,
    "exr": _decode_exr,
    "avif": _decode_avif,
    "heif": _decode_heif,
    "rgbe": _decode_rgbe,
    "ultrahdr": _decode_ultrahdr,
    "png": _decode_png,
    "tiff": _decode_tiff,
}


def decode_to_scrgb(filepath):
    """Decode a supported image to float32 linear RGBA data."""
    path = Path(filepath)
    fmt = probe_format(filepath)
    raw = path.read_bytes()

    decoder = _DECODERS.get(fmt)
    primary_message = ""

    if decoder is not None:
        try:
            pixels = _ensure_rgba(decoder(raw))
            height, width = pixels.shape[:2]
            return pixels, width, height
        except Exception as primary_error:
            primary_message = str(primary_error)
    else:
        primary_message = f"no decoder for detected format '{fmt}'"

    if primary_message:
        print(f"Warning: primary decoder failed, falling back to WIC: {primary_message}", file=sys.stderr)
    try:
        pixels = _ensure_rgba(_decode_wic(raw))
        height, width = pixels.shape[:2]
        return pixels, width, height
    except Exception as fallback_error:
        raise ValueError(
            f"Cannot decode: {filepath} (detected: {fmt}; "
            f"primary: {primary_message}; wic: {fallback_error})"
        ) from fallback_error


def is_hdr_image(filepath):
    """Return True if any RGB channel exceeds SDR white."""
    pixels, _, _ = decode_to_scrgb(filepath)
    return bool((pixels[..., :3].max(axis=-1) > 1.0).any())


SUPPORTED_FORMATS = {
    "jpegxr": ("JPEG XR", [".jxr", ".wdp", ".hdp"]),
    "jpegxl": ("JPEG XL", [".jxl"]),
    "exr": ("OpenEXR", [".exr"]),
    "avif": ("AVIF", [".avif"]),
    "heif": ("HEIF/HEIC", [".heic", ".heif"]),
    "rgbe": ("Radiance HDR", [".hdr"]),
    "ultrahdr": ("Ultra HDR (JPEG)", [".jpg", ".jpeg"]),
    "png": ("PNG", [".png"]),
    "tiff": ("TIFF", [".tif", ".tiff"]),
}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python src/decoder.py <file>")
        print()
        print("Supported formats:")
        for key, (name, exts) in SUPPORTED_FORMATS.items():
            print(f"  {name}: {', '.join(exts)}")
        sys.exit(1)

    fpath = sys.argv[1]
    print(f"File: {fpath}")
    print(f"Detected: {probe_format(fpath)}")
    print(f"Has HDR: {is_hdr_image(fpath)}")

    pixels, w, h = decode_to_scrgb(fpath)
    print(f"Resolution: {w}x{h}")
    print(f"Shape: {pixels.shape}, dtype: {pixels.dtype}")
    print(f"RGB range: [{pixels[..., :3].min():.4f}, {pixels[..., :3].max():.4f}]")
    above = (pixels[..., :3].max(axis=-1) > 1.0).sum()
    total = w * h
    print(f"HDR pixels (>1.0 RGB): {above}/{total} ({100 * above / total:.1f}%)")
