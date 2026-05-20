"""Ultra HDR JPEG encoder."""
import numpy as np

from hdr_transcoder.formats.jxl import as_finite_float32_rgb


def encode_ultrahdr(pixels_rgb, output_path, quality=100, headroom=2.0):
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
