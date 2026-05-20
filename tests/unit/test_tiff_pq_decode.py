"""Unit tests for TIFF PQ decode support."""
import struct

import numpy as np
import pytest

from hdr_transcoder.formats.decoder import _read_tiff_cicp, _decode_tiff, decode_to_scrgb


def _build_minimal_tiff_with_cicp(transfer=16, primaries=9, matrix=9):
    """Build a minimal TIFF binary containing only a 0xC761 CICP tag IFD entry."""
    cicp_text = (
        f"Transfer Characteristics: {transfer}\r\n"
        f"Color Primaries: {primaries}\r\n"
        f"Matrix Coefficients: {matrix}\r\n"
    )
    cicp_bytes = cicp_text.encode("ascii") + b"\x00"
    # TIFF header: "II" (little-endian) + magic 42 + IFD offset
    ifd_offset = 8
    # IFD: 1 entry + next_ifd_offset(0)
    # Entry: tag(2) + dtype(2=ASCII) + count(4) + value_offset(4)
    # ASCII data > 4 bytes, so value_offset points to string location
    string_offset = ifd_offset + 2 + 12 + 4  # after header + count + entry + next_offset
    entry = struct.pack("<HHI", 0xC761, 2, len(cicp_bytes))  # tag, ASCII, count
    entry += struct.pack("<I", string_offset)
    ifd = struct.pack("<H", 1) + entry + struct.pack("<I", 0)
    cicp_data = cicp_bytes
    header = b"II\x2a\x00" + struct.pack("<I", ifd_offset)
    return header + ifd + cicp_data


def _build_tiff_16bit_image(pixels_16bit):
    """Encode a 16-bit RGB image as TIFF using imagecodecs, return TIFF bytes."""
    import imagecodecs

    return imagecodecs.tiff_encode(np.asarray(pixels_16bit, dtype=np.uint16))


def _pq_encoded_16bit(linear_values, max_nits=10000.0):
    """Encode linear nits values to PQ 16-bit integer."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875

    linear = np.asarray(linear_values, dtype=np.float32) / max_nits
    linear = np.maximum(linear, 0.0)
    linear_pow = np.power(linear, m1)
    numerator = c1 + c2 * linear_pow
    denominator = 1.0 + c3 * linear_pow
    pq = np.power(numerator / denominator, m2)
    return (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)


class TestReadTiffCicp:
    def test_parses_transfer_characteristics(self):
        raw = _build_minimal_tiff_with_cicp(transfer=16, primaries=9, matrix=9)
        cicp = _read_tiff_cicp(raw)
        assert cicp["transfer"] == 16

    def test_parses_color_primaries(self):
        raw = _build_minimal_tiff_with_cicp(transfer=16, primaries=9, matrix=9)
        cicp = _read_tiff_cicp(raw)
        assert cicp["primaries"] == 9

    def test_parses_matrix_coefficients(self):
        raw = _build_minimal_tiff_with_cicp(transfer=16, primaries=9, matrix=9)
        cicp = _read_tiff_cicp(raw)
        assert cicp["matrix"] == 9

    def test_returns_empty_for_non_tiff(self):
        raw = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        cicp = _read_tiff_cicp(raw)
        assert cicp == {}

    def test_returns_empty_when_no_cicp_tag(self):
        raw = _build_minimal_tiff_with_cicp(transfer=16, primaries=9, matrix=9)
        # Modify tag to something else
        raw_modified = raw[:10] + struct.pack("<H", 0xC762) + raw[12:]
        cicp = _read_tiff_cicp(raw_modified)
        assert cicp == {}

    def test_handles_big_endian_tiff(self):
        # Build big-endian version
        cicp_text = "Transfer Characteristics: 16\r\nColor Primaries: 9\r\nMatrix Coefficients: 9\r\n"
        cicp_bytes = cicp_text.encode("ascii") + b"\x00"
        ifd_offset = 8
        string_offset = ifd_offset + 2 + 12 + 4
        entry = struct.pack(">HHI", 0xC761, 2, len(cicp_bytes)) + struct.pack(">I", string_offset)
        ifd = struct.pack(">H", 1) + entry + struct.pack(">I", 0)
        header = b"MM\x00\x2a" + struct.pack(">I", ifd_offset)
        raw = header + ifd + cicp_bytes
        cicp = _read_tiff_cicp(raw)
        assert cicp["transfer"] == 16
        assert cicp["primaries"] == 9

    def test_handles_alternate_key_format(self):
        # Some DNG writers use different delimiters/spacing
        cicp_text = "Transfer Char: 16,Color Primaries=9;Matrix Coeffs: 9"
        cicp_bytes = cicp_text.encode("ascii") + b"\x00"
        ifd_offset = 8
        string_offset = ifd_offset + 2 + 12 + 4
        entry = struct.pack("<HHI", 0xC761, 2, len(cicp_bytes)) + struct.pack("<I", string_offset)
        ifd = struct.pack("<H", 1) + entry + struct.pack("<I", 0)
        header = b"II\x2a\x00" + struct.pack("<I", ifd_offset)
        raw = header + ifd + cicp_bytes
        cicp = _read_tiff_cicp(raw)
        assert cicp["transfer"] == 16
        assert cicp["primaries"] == 9
        assert cicp["matrix"] == 9


class TestDecodeTiffPQ:
    def test_pq_input_flag_decodes_solid_grey(self):
        # Create a solid grey at ~100 nits linear → PQ encode to 16-bit
        linear_nits = np.full((4, 4, 3), 100.0, dtype=np.float32)
        pq_16bit = _pq_encoded_16bit(linear_nits, max_nits=10000.0)
        raw = _build_tiff_16bit_image(pq_16bit)
        result = _decode_tiff(raw, pq_input=True)
        # 100 nits / 100 = 1.0 scRGB (SDR white)
        peak = float(result[..., :3].max())
        assert 0.9 < peak < 1.2

    def test_pq_input_flag_decodes_high_brightness(self):
        # Create a bright pixel at ~1000 nits
        linear_nits = np.full((4, 4, 3), 1000.0, dtype=np.float32)
        pq_16bit = _pq_encoded_16bit(linear_nits, max_nits=10000.0)
        raw = _build_tiff_16bit_image(pq_16bit)
        result = _decode_tiff(raw, pq_input=True)
        # 1000 nits / 100 = ~10 scRGB
        peak = float(result[..., :3].max())
        assert 9.0 < peak < 11.0

    def test_without_pq_input_is_passthrough(self):
        # Without pq_input, 16-bit data is treated as linear normalized to 1.0
        data = np.full((4, 4, 3), 32768, dtype=np.uint16)
        raw = _build_tiff_16bit_image(data)
        result = _decode_tiff(raw, pq_input=False)
        # 32768/65535 ≈ 0.5 in linear
        peak = float(result[..., :3].max())
        assert 0.4 < peak < 0.6

    def test_decode_to_scrgb_with_pq_input(self, tmp_path):
        linear_nits = np.full((4, 4, 3), 500.0, dtype=np.float32)
        pq_16bit = _pq_encoded_16bit(linear_nits, max_nits=10000.0)
        raw = _build_tiff_16bit_image(pq_16bit)
        tiff_path = tmp_path / "test_pq.tif"
        tiff_path.write_bytes(raw)
        pixels, w, h = decode_to_scrgb(str(tiff_path), pq_input=True)
        peak = float(pixels[..., :3].max())
        # 500 nits / 100 = ~5 scRGB
        assert 4.5 < peak < 5.5
        assert w == 4
        assert h == 4
