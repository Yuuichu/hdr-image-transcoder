"""
Multi-format HDR output encoder.

Encodes float32 scRGB to Tier-1 HDR output formats:
- JPEG XL (JXL): native float32, best compression
- Ultra HDR JPEG: gainmap HDR, best backward compatibility
- Standard AVIF HDR: 10-bit PQ, broadest browser support
- HEIF/HEIC HDR: 10-bit PQ HEVC
"""
import numpy as np
from pathlib import Path


def _encode_jxl(pixels_rgb, output_path, quality=95, lossless=False, effort=7):
    import imagecodecs

    if lossless:
        data = imagecodecs.jpegxl_encode(
            pixels_rgb, lossless=True, effort=effort, usecontainer=True
        )
    else:
        distance = max((100 - quality) / 20.0, 0.0)
        data = imagecodecs.jpegxl_encode(
            pixels_rgb, distance=distance, effort=effort, usecontainer=True
        )

    Path(output_path).write_bytes(data)
    return output_path


def _encode_ultrahdr(pixels_rgb, output_path, quality=95):
    from hdr_processor import prepare_base_sdr
    import imagecodecs

    sdr_8bit = prepare_base_sdr(pixels_rgb)
    h, w = sdr_8bit.shape[:2]

    sdr_rgba = np.dstack([sdr_8bit, np.full((h, w), 255, dtype=np.uint8)])
    alpha = np.ones((h, w), dtype=np.float16)
    hdr_rgba = np.dstack([pixels_rgb[..., :3].astype(np.float16), alpha])

    data = imagecodecs.ultrahdr_encode(hdr_rgba, sdr=sdr_rgba, level=quality)
    Path(output_path).write_bytes(data)
    return output_path


def _encode_avif_hdr(pixels_rgb, output_path, quality=95, speed=6):
    from hdr_processor import _linear_to_pq
    import imagecodecs

    luminance = pixels_rgb * 100.0
    pq = _linear_to_pq(luminance)
    pq_10bit = (pq * 1023.0 + 0.5).clip(0, 1023).astype(np.uint16)

    data = imagecodecs.avif_encode(
        pq_10bit,
        level=quality,
        bitspersample=10,
        speed=speed,
        primaries=1,
        transfer=16,
        matrix=0,
    )
    Path(output_path).write_bytes(data)
    return output_path


def _encode_heif_hdr(pixels_rgb, output_path, quality=95):
    from hdr_processor import _linear_to_pq
    import pillow_heif

    luminance = pixels_rgb * 100.0
    pq = _linear_to_pq(luminance)
    pq_16bit = (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)

    heif_file = pillow_heif.HeifFile()
    height, width = pq_16bit.shape[:2]
    heif_file.add_frombytes("RGB;16", (width, height), pq_16bit.tobytes())
    heif_file.save(
        output_path,
        quality=quality,
        chroma="444",
        save_nclx_profile=True,
        color_primaries=1,
        transfer_characteristics=16,
        matrix_coefficients=0,
        full_range_flag=1,
    )
    return output_path


OUTPUT_FORMATS = {
    "jxl": ("JPEG XL HDR", [".jxl"]),
    "avif": ("Standard AVIF HDR", [".avif"]),
    "ultrahdr": ("Ultra HDR JPEG", [".jpg", ".jpeg"]),
    "heif": ("HEIF HDR", [".heic", ".heif"]),
}

EXTENSION_TO_FORMAT = {
    ".jxl": "jxl",
    ".jpg": "ultrahdr",
    ".jpeg": "ultrahdr",
    ".heic": "heif",
    ".heif": "heif",
}

_ENCODERS = {
    "jxl": _encode_jxl,
    "ultrahdr": _encode_ultrahdr,
    "avif": _encode_avif_hdr,
    "heif": _encode_heif_hdr,
}


def encode_output(pixels, output_path, format=None, quality=95, speed=6,
                  lossless=False, effort=7):
    """Encode float32 scRGB (H, W, >=3) to a Tier-1 HDR output format.

    Args:
        pixels: ndarray (H, W, 3|4) float32, linear scRGB
        output_path: output file path
        format: 'jxl', 'ultrahdr', 'avif', or 'heif' (auto-detect from extension)
        quality: 0-100
        speed: 0-10 (AVIF only)
        lossless: JXL lossless mode
        effort: JXL encoding effort 1-10

    Returns:
        Path to the output file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format is None:
        ext = output_path.suffix.lower()
        format = EXTENSION_TO_FORMAT.get(ext)
        if format is None:
            raise ValueError(
                f"Cannot infer output format from extension '{ext}'. "
                f"Use --format to specify: jxl, avif, ultrahdr, heif"
            )

    encoder = _ENCODERS.get(format)
    if encoder is None:
        raise ValueError(
            f"Unknown output format: {format}. "
            f"Supported: {', '.join(_ENCODERS)}"
        )

    rgb = pixels[..., :3].copy() if pixels.shape[2] >= 3 else pixels.copy()

    if format == "jxl":
        return encoder(rgb, output_path, quality=quality, lossless=lossless, effort=effort)
    elif format == "avif":
        return encoder(rgb, output_path, quality=quality, speed=speed)
    else:
        return encoder(rgb, output_path, quality=quality)
