"""Unit tests for the optional libultrahdr Ultra HDR pipeline."""
import numpy as np
import pytest

from hdr_transcoder.formats.ultrahdr import encode_ultrahdr_bt2020_pq_tiff
from hdr_transcoder.formats.ultrahdr_lib import (
    bt2020_pq_to_display_p3_pq,
    display_p3_pq_to_sdr_rgba8888,
    load_bt2020_pq_tiff,
    pack_rgba1010102,
)


def _pq_encoded_16bit(linear_nits, max_nits=10000.0):
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875
    linear = np.asarray(linear_nits, dtype=np.float32) / max_nits
    linear_pow = np.power(np.maximum(linear, 0.0), m1)
    pq = np.power((c1 + c2 * linear_pow) / (1.0 + c3 * linear_pow), m2)
    return (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)


def test_load_bt2020_pq_tiff_requires_uint16_rgb(tmp_path):
    import imagecodecs

    bad_path = tmp_path / "bad.tif"
    bad_path.write_bytes(imagecodecs.tiff_encode(np.zeros((8, 8, 3), dtype=np.uint8)))

    with pytest.raises(ValueError, match="requires uint16 RGB TIFF"):
        load_bt2020_pq_tiff(bad_path)


def test_bt2020_pq_to_display_p3_preserves_neutral_gray():
    linear_nits = np.full((8, 8, 3), 203.0, dtype=np.float32)
    pq16 = _pq_encoded_16bit(linear_nits)

    p3_pq = bt2020_pq_to_display_p3_pq(pq16)

    assert p3_pq.dtype == np.float32
    assert p3_pq.shape == (8, 8, 3)
    assert np.isfinite(p3_pq).all()
    assert np.max(np.abs(p3_pq[..., 0] - p3_pq[..., 1])) < 0.001
    assert np.max(np.abs(p3_pq[..., 1] - p3_pq[..., 2])) < 0.001


def test_pack_rgba1010102_bit_layout():
    rgb = np.array([[[1.0, 0.0, 0.5]]], dtype=np.float32)

    packed = pack_rgba1010102(rgb)

    red = packed[0, 0] & np.uint32(0x3FF)
    green = (packed[0, 0] >> np.uint32(10)) & np.uint32(0x3FF)
    blue = (packed[0, 0] >> np.uint32(20)) & np.uint32(0x3FF)
    alpha = (packed[0, 0] >> np.uint32(30)) & np.uint32(0x3)
    assert int(red) == 1023
    assert int(green) == 0
    assert int(blue) == 512
    assert int(alpha) == 3


def test_display_p3_pq_to_sdr_rgba8888_outputs_opaque_words():
    p3_pq = np.full((8, 8, 3), 0.5, dtype=np.float32)

    packed = display_p3_pq_to_sdr_rgba8888(p3_pq)

    assert packed.dtype == np.uint32
    assert packed.shape == (8, 8)
    assert np.all((packed >> np.uint32(24)) == np.uint32(255))


def test_dedicated_pq_tiff_rejects_imagecodecs_backend(tmp_path):
    output_path = tmp_path / "out.jpg"

    with pytest.raises(ValueError, match="cannot use the dedicated BT.2020 PQ TIFF"):
        encode_ultrahdr_bt2020_pq_tiff(
            tmp_path / "missing.tif",
            output_path,
            backend="imagecodecs",
        )


def test_ultrahdr_decoder_normalizes_legacy_hdrgm_white_point(monkeypatch):
    import imagecodecs

    from hdr_transcoder.formats.decoder import _decode_ultrahdr

    decoded = np.ones((2, 2, 4), dtype=np.float16) * np.float16(5.0)
    monkeypatch.setattr(imagecodecs, "ultrahdr_decode", lambda raw: decoded)

    pixels = _decode_ultrahdr(b"not-a-jpeg hdrgm:Version='1.0'")

    assert float(pixels[..., :3].max()) == 10.0
