"""Ultra HDR JPEG encoders."""
import numpy as np

from hdr_transcoder.config import (
    ULTRAHDR_BACKEND_AUTO,
    ULTRAHDR_BACKEND_IMAGECODECS,
    ULTRAHDR_BACKEND_LIBULTRAHDR,
    ULTRAHDR_BACKENDS,
    ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
)
from hdr_transcoder.color import clamp_small_negatives, linear_srgb_to_display_p3
from hdr_transcoder.formats.jxl import as_finite_float32_rgb
from hdr_transcoder.processor import _linear_to_pq


def encode_ultrahdr(
    pixels_rgb,
    output_path,
    quality=100,
    headroom=2.0,
    backend=ULTRAHDR_BACKEND_AUTO,
    gainmap_scale=ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    gainmap_gamma=ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    target_peak_nits=ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
):
    """Encode float32 scRGB pixels as Ultra HDR JPEG."""
    if backend not in ULTRAHDR_BACKENDS:
        raise ValueError(f"Unknown Ultra HDR backend: {backend}")

    if backend in {ULTRAHDR_BACKEND_AUTO, ULTRAHDR_BACKEND_LIBULTRAHDR}:
        from hdr_transcoder.formats.ultrahdr_lib import (
            display_p3_pq_to_sdr_rgba8888,
            encode_raw_p3_ultrahdr,
            is_libultrahdr_available,
            pack_rgba1010102,
        )

        if backend == ULTRAHDR_BACKEND_LIBULTRAHDR or is_libultrahdr_available():
            pixels_rgb = as_finite_float32_rgb(pixels_rgb, "Ultra HDR input")
            p3_linear_nits = clamp_small_negatives(
                linear_srgb_to_display_p3(np.maximum(pixels_rgb[..., :3], 0.0))
            )
            p3_linear_nits = np.maximum(p3_linear_nits, 0.0) * np.float32(100.0)
            p3_pq = _linear_to_pq(p3_linear_nits, max_nits=10000.0).astype(np.float32)
            return encode_raw_p3_ultrahdr(
                pack_rgba1010102(p3_pq),
                display_p3_pq_to_sdr_rgba8888(p3_pq),
                output_path,
                quality=quality,
                gainmap_scale=gainmap_scale,
                gainmap_gamma=gainmap_gamma,
                target_peak_nits=target_peak_nits,
            )

    return encode_ultrahdr_imagecodecs(
        pixels_rgb,
        output_path,
        quality=quality,
        headroom=headroom,
    )


def encode_ultrahdr_imagecodecs(pixels_rgb, output_path, quality=100, headroom=2.0):
    from hdr_transcoder.processor import prepare_base_sdr
    import imagecodecs

    pixels_rgb = as_finite_float32_rgb(pixels_rgb, "Ultra HDR input")
    sdr_8bit = prepare_base_sdr(pixels_rgb, headroom=headroom)
    h, w = sdr_8bit.shape[:2]
    if h < 8 or w < 8:
        raise ValueError("Ultra HDR JPEG output requires image dimensions of at least 8x8")

    sdr_rgba = np.dstack([sdr_8bit, np.full((h, w), 255, dtype=np.uint8)])
    alpha = np.ones((h, w), dtype=np.float16)
    hdr_rgba = np.dstack([pixels_rgb[..., :3].astype(np.float16), alpha])

    data = imagecodecs.ultrahdr_encode(hdr_rgba, sdr=sdr_rgba, level=quality)
    output_path.write_bytes(data)
    return output_path


def encode_ultrahdr_bt2020_pq_tiff(
    input_path,
    output_path,
    quality=95,
    backend=ULTRAHDR_BACKEND_AUTO,
    gainmap_scale=ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    gainmap_gamma=ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    target_peak_nits=ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
):
    """Encode a true BT.2020 PQ TIFF through the Display P3 libultrahdr path."""
    if backend not in ULTRAHDR_BACKENDS:
        raise ValueError(f"Unknown Ultra HDR backend: {backend}")
    if backend == ULTRAHDR_BACKEND_IMAGECODECS:
        raise ValueError(
            "--uhdr-backend imagecodecs cannot use the dedicated BT.2020 PQ TIFF "
            "to Display P3 Ultra HDR pipeline; use --uhdr-backend libultrahdr or auto"
        )

    from hdr_transcoder.formats.ultrahdr_lib import (
        encode_bt2020_pq_tiff_to_ultrahdr,
        is_libultrahdr_available,
    )

    if not is_libultrahdr_available():
        raise FileNotFoundError(
            "Dedicated BT.2020 PQ TIFF Ultra HDR encoding requires libultrahdr. "
            "Set HDR_TRANSCODER_UHDR_DLL or place uhdr.dll in tools/libultrahdr."
        )
    return encode_bt2020_pq_tiff_to_ultrahdr(
        input_path,
        output_path,
        quality=quality,
        gainmap_scale=gainmap_scale,
        gainmap_gamma=gainmap_gamma,
        target_peak_nits=target_peak_nits,
    )
