"""HEIF/HEIC HDR encoder."""
import numpy as np

from hdr_transcoder.config import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_PQ_TRANSFER,
)
from hdr_transcoder.formats.jxl import as_finite_float32_rgb, to_nonnegative_bt2020


def encode_heif_hdr(pixels_rgb, output_path, quality=100):
    from hdr_transcoder.processor import _linear_to_pq
    import pillow_heif

    pixels_rgb = as_finite_float32_rgb(pixels_rgb, "HEIF input")
    bt2020_rgb = to_nonnegative_bt2020(pixels_rgb, "HEIF input")
    luminance = bt2020_rgb * 100.0
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
        color_primaries=CICP_BT2020_PRIMARIES,
        transfer_characteristics=CICP_PQ_TRANSFER,
        matrix_coefficients=CICP_BT2020_MATRIX,
        full_range_flag=1,
    )
    return output_path
