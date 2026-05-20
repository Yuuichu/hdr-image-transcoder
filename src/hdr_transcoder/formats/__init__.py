"""HDR output encoder dispatch."""
from pathlib import Path

from hdr_transcoder.formats.avif import encode_avif_hdr
from hdr_transcoder.formats.heif import encode_heif_hdr
from hdr_transcoder.formats.jxl import (
    JXL_MODE_LINEAR_SRGB,
    JXL_MODE_REC2020_PQ,
    JXL_MODES,
    as_finite_float32_rgb,
    encode_jxl,
)
from hdr_transcoder.formats.ultrahdr import encode_ultrahdr

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
    "jxl": encode_jxl,
    "ultrahdr": encode_ultrahdr,
    "avif": encode_avif_hdr,
    "heif": encode_heif_hdr,
}


def encode_output(pixels, output_path, format=None, quality=100, speed=0,
                  lossless=False, effort=7, headroom=2.0,
                  jxl_mode=JXL_MODE_REC2020_PQ):
    """Encode float32 scRGB (H, W, >=3) to a Tier-1 HDR output format."""
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
    rgb = as_finite_float32_rgb(rgb, "encoder input")

    if format == "jxl":
        return encoder(
            rgb,
            output_path,
            quality=quality,
            lossless=lossless,
            effort=effort,
            mode=jxl_mode,
        )
    if format == "avif":
        return encoder(rgb, output_path, quality=quality, speed=speed)
    if format == "ultrahdr":
        return encoder(rgb, output_path, quality=quality, headroom=headroom)
    return encoder(rgb, output_path, quality=quality)
