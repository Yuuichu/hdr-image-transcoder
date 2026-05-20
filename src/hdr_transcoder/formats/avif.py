"""Standard 10-bit PQ AVIF encoder."""
from pathlib import Path

import numpy as np

from hdr_transcoder.config import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_PQ_TRANSFER,
)
from hdr_transcoder.formats.jxl import as_finite_float32_rgb, to_nonnegative_bt2020


def encode_avif_hdr(pixels_rgb, output_path, quality=100, speed=0):
    from hdr_transcoder.processor import _linear_to_pq
    import imagecodecs

    pixels_rgb = as_finite_float32_rgb(pixels_rgb, "AVIF input")
    bt2020_rgb = to_nonnegative_bt2020(pixels_rgb, "AVIF input")
    luminance = bt2020_rgb * 100.0
    pq = _linear_to_pq(luminance)
    pq_10bit = (pq * 1023.0 + 0.5).clip(0, 1023).astype(np.uint16)

    data = imagecodecs.avif_encode(
        pq_10bit,
        level=quality,
        bitspersample=10,
        speed=speed,
        primaries=CICP_BT2020_PRIMARIES,
        transfer=CICP_PQ_TRANSFER,
        matrix=CICP_BT2020_MATRIX,
    )
    Path(output_path).write_bytes(data)
    return output_path
