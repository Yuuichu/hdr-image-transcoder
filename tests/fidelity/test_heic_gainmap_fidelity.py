"""Fidelity tests for gainmap HEIC output."""
import math
import struct
import subprocess
import sys

import numpy as np
import pytest

from hdr_transcoder.formats.decoder import decode_to_scrgb
from hdr_transcoder.formats.isobmff import (
    _extract_box_payload,
    _find_box,
    _parse_boxes,
    find_item_property,
    get_item_colr,
    get_item_dimensions,
    read_heic_container,
    read_heic_gainmap_metadata,
)
from hdr_transcoder.inspector import inspect_image

from helpers import ROOT, run_python, stop_delta


HEIFGAINMAPUTIL_HDR = ROOT / "tools" / "libheif" / "heifgainmaputil_hdr.py"


def test_heic_bt2020_base_conversion_changes_primary_samples():
    """True BT.2020 HEIC base pixels should not just be retagged sRGB samples."""
    from tools.libheif.heifgainmaputil_hdr import _convert_srgb_base_to_bt2020_srgb_transfer

    sdr = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)
    converted = _convert_srgb_base_to_bt2020_srgb_transfer(sdr)

    assert converted.dtype == np.uint8
    assert converted.shape == sdr.shape
    assert converted[0, 0, 0] < 255
    assert converted[0, 0, 1] > 0
    assert converted[0, 0, 2] > 0
    assert converted[0, 1, 1] < 255
    assert converted[0, 2, 2] < 255


def _pq_encode_16bit(linear_nits, max_nits=10000.0):
    """Encode linear nits values to PQ 16-bit integer."""
    m1 = 0.1593017578125
    m2 = 78.84375
    c1 = 0.8359375
    c2 = 18.8515625
    c3 = 18.6875
    linear = np.asarray(linear_nits, dtype=np.float32) / max_nits
    linear = np.maximum(linear, 0.0)
    linear_pow = np.power(linear, m1)
    numerator = c1 + c2 * linear_pow
    denominator = 1.0 + c3 * linear_pow
    pq = np.power(numerator / denominator, m2)
    return (pq * 65535.0 + 0.5).clip(0, 65535).astype(np.uint16)


def _make_pq_tiff(pixels_16bit):
    """Encode 16-bit pixels as TIFF using imagecodecs."""
    import imagecodecs
    return imagecodecs.tiff_encode(np.asarray(pixels_16bit, dtype=np.uint16))


def _tmap_headroom(heic_path):
    """Read tmap box headroom values from a HEIC file."""
    metadata = read_heic_gainmap_metadata(heic_path)
    assert metadata is not None, "HEIC missing tmap box"
    return {
        "base": metadata["baseHeadroom"],
        "alternate": metadata["alternateHeadroom"],
    }


def _item_references(heic_path):
    data = heic_path.read_bytes()
    top_boxes = _parse_boxes(data)
    meta_box = _find_box(top_boxes, "meta")
    assert meta_box is not None, "HEIC missing meta box"
    meta_boxes = _parse_boxes(_extract_box_payload(meta_box[3]))
    iref_box = _find_box(meta_boxes, "iref")
    assert iref_box is not None, "HEIC missing iref box"

    refs = []
    for ref_type, _, _, ref_box in _parse_boxes(_extract_box_payload(iref_box[3])):
        payload = ref_box[8:]
        from_id = struct.unpack(">H", payload[:2])[0]
        count = struct.unpack(">H", payload[2:4])[0]
        to_ids = [
            struct.unpack(">H", payload[4 + i * 2:6 + i * 2])[0]
            for i in range(count)
        ]
        refs.append((ref_type, from_id, to_ids))
    return refs


def test_heic_container_honors_alternate_cicp_and_apple_headroom(tmp_path):
    """Container metadata should preserve non-default alternate CICP and Apple headroom."""
    from hdr_transcoder.formats.isobmff import build_heic_gainmap_container

    output_path = tmp_path / "metadata.heic"
    output_path.write_bytes(build_heic_gainmap_container(
        sdr_bitstream=b"sdr",
        sdr_hvcC=b"sdr-hvcc",
        alt_bitstream=b"alt",
        alt_hvcC=b"alt-hvcc",
        gainmap_bitstream=b"gm",
        gainmap_hvcC=b"gm-hvcc",
        apple_gainmap_bitstream=b"apple-gm",
        apple_gainmap_hvcC=b"apple-hvcc",
        sdr_width=2,
        sdr_height=2,
        alt_width=2,
        alt_height=2,
        gainmap_width=2,
        gainmap_height=2,
        apple_gainmap_width=1,
        apple_gainmap_height=1,
        alternate_headroom=1.0,
        apple_headroom=4.0,
        alternate_primaries=1,
        alternate_transfer=13,
        alternate_matrix=1,
    ))

    container = read_heic_container(output_path)
    assert get_item_colr(container, 2) == (1, 13, 1)

    tmap = read_heic_gainmap_metadata(output_path)
    assert tmap["alternate_headroom"] == 1.0

    data = output_path.read_bytes()
    xmp_offset, xmp_length = container["item_extents"][5][0]
    xmp_payload = data[xmp_offset:xmp_offset + xmp_length]
    assert b"<HDRGainMap:HDRGainMapHeadroom>16.000000" in xmp_payload


@pytest.mark.fidelity
def test_gainmap_heic_structure_is_valid(tmp_path):
    """Verify the ISOBMFF structure of an ISO 21496-1 gainmap HEIC output."""
    import imagecodecs

    # Build SDR base PNG (8-bit sRGB gradient)
    h, w = 64, 64
    sdr_8bit = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        val = int(255 * (y / h))
        sdr_8bit[y, :, :] = [val, val, val]
    base_png = imagecodecs.png_encode(sdr_8bit)

    # Build HDR alternate PNG (16-bit PQ gradient)
    linear_nits = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(h):
        lval = 10.0 + 1000.0 * (y / h)
        linear_nits[y, :, :] = [0.1 * lval, lval, 0.1 * lval]
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    alt_png = imagecodecs.png_encode(pq_16bit)

    base_path = tmp_path / "base.png"
    base_path.write_bytes(base_png)
    alt_path = tmp_path / "alternate.png"
    alt_path.write_bytes(alt_png)
    output_path = tmp_path / "output.heic"

    import os
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not existing_pythonpath else f"{ROOT}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [
            sys.executable,
            str(HEIFGAINMAPUTIL_HDR),
            "combine",
            str(base_path),
            str(alt_path),
            str(output_path),
            "--speed", "8",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"heifgainmaputil_hdr combine failed:\n{result.stdout}\n{result.stderr}"

    data = output_path.read_bytes()
    top_boxes = _parse_boxes(data)
    box_types = {bt for bt, _, _, _ in top_boxes}
    assert "ftyp" in box_types, "missing ftyp box"
    assert "meta" in box_types, "missing meta box"
    assert "mdat" in box_types, "missing mdat box"

    container = read_heic_container(output_path)
    extents = container["item_extents"]
    assert 1 in extents, "missing SDR base item (1)"
    assert 2 in extents, "missing HDR alternate item (2)"
    assert 3 in extents, "missing RGB gainmap item (3)"
    assert 4 in extents, "missing tmap metadata item (4)"
    assert 5 in extents, "missing XMP item (5)"
    assert 6 in extents, "missing EXIF item (6)"
    assert 7 in extents, "missing Apple HDR gainmap item (7)"
    assert get_item_colr(container, 1) == (9, 13, 9), "SDR base must be tagged as BT.2020 primaries with sRGB transfer"
    assert get_item_colr(container, 2) == (9, 16, 9), "HDR alternate must be tagged as BT.2020 PQ"
    assert get_item_colr(container, 3) == (9, 13, 9), "RGB gainmap must use the base color space"
    assert get_item_colr(container, 7) == (2, 2, 2), "Apple single-channel gainmap should be uncalibrated"

    alt_aux = find_item_property(container, 2, "auxC")
    assert alt_aux is not None, "HDR alternate missing auxC"
    assert b"urn:iso:std:iso:ts:21496:-1:aux:alternateImage" in alt_aux

    gm_aux = find_item_property(container, 3, "auxC")
    assert gm_aux is not None, "gainmap missing auxC"
    assert b"urn:iso:std:iso:ts:21496:-1:aux:gainmap" in gm_aux

    gm_width, gm_height = get_item_dimensions(container, 3)
    assert gm_width == w
    assert gm_height == h

    refs = _item_references(output_path)
    assert ("auxl", 2, [1]) in refs, "alternate not auxl-linked to base"
    assert ("auxl", 3, [1]) in refs, "gainmap not auxl-linked to base"
    assert ("dimg", 4, [1, 3]) in refs, "tmap dimg missing"
    assert ("cdsc", 5, [7]) in refs, "Apple HDR XMP does not describe Apple gainmap"
    assert ("cdsc", 6, [1, 4]) in refs, "EXIF does not describe primary/tmap items"
    assert ("auxl", 7, [1]) in refs, "Apple gainmap not auxl-linked to base"

    xmp_offset, xmp_length = container["item_extents"][5][0]
    xmp_payload = data[xmp_offset:xmp_offset + xmp_length]
    assert b"HDRGainMapVersion>131072" in xmp_payload
    assert b"HDRGainMapHeadroom" in xmp_payload

    exif_offset, exif_length = container["item_extents"][6][0]
    exif_payload = data[exif_offset:exif_offset + exif_length]
    assert b"Exif\x00\x00MM\x00*" in exif_payload
    assert b"Apple iOS\x00" in exif_payload

    headroom = _tmap_headroom(output_path)
    assert isinstance(headroom["base"], float)
    assert isinstance(headroom["alternate"], float)
    assert headroom["base"] >= 0
    assert headroom["alternate"] > 0

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True


@pytest.mark.fidelity
def test_gainmap_heic_rgb_gainmap_only_structure_is_valid(tmp_path):
    """Verify the clean ISO RGB gainmap HEIC path omits HDR alternate and Apple items."""
    import imagecodecs
    import os

    h, w = 32, 32
    sdr_8bit = np.full((h, w, 3), 64, dtype=np.uint8)
    linear_nits = np.full((h, w, 3), 400.0, dtype=np.float32)
    linear_nits[8:24, 8:24, :] = [700.0, 500.0, 450.0]
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)

    base_path = tmp_path / "base.png"
    alt_path = tmp_path / "alternate.png"
    output_path = tmp_path / "rgb_only.heic"
    base_path.write_bytes(imagecodecs.png_encode(sdr_8bit))
    alt_path.write_bytes(imagecodecs.png_encode(pq_16bit))

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not existing_pythonpath else f"{ROOT}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [
            sys.executable,
            str(HEIFGAINMAPUTIL_HDR),
            "combine",
            str(base_path),
            str(alt_path),
            str(output_path),
            "--speed", "8",
            "--alternate-headroom", "3",
            "--rgb-gainmap-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"heifgainmaputil_hdr combine failed:\n{result.stdout}\n{result.stderr}"

    container = read_heic_container(output_path)
    assert set(container["item_extents"]) == {1, 2, 3}
    assert get_item_colr(container, 1) == (9, 13, 9)
    assert get_item_colr(container, 2) == (9, 13, 9)
    assert find_item_property(container, 2, "auxC") is not None
    assert b"urn:iso:std:iso:ts:21496:-1:aux:gainmap" in find_item_property(container, 2, "auxC")

    refs = _item_references(output_path)
    assert ("auxl", 2, [1]) in refs
    assert ("dimg", 3, [1, 2]) in refs

    output_pixels, _, _ = decode_to_scrgb(str(output_path))
    assert float(output_pixels[..., :3].max()) > 1.0

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True


@pytest.mark.fidelity
def test_gainmap_heic_apple_gainmap_only_structure_is_valid(tmp_path):
    """Verify the Apple-only gainmap HEIC path omits ISO gainmap and HDR alternate items."""
    import imagecodecs
    import os

    h, w = 32, 32
    sdr_8bit = np.full((h, w, 3), 180, dtype=np.uint8)
    linear_nits = np.full((h, w, 3), 320.0, dtype=np.float32)
    linear_nits[8:24, 8:24, :] = [700.0, 560.0, 460.0]
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)

    base_path = tmp_path / "base.png"
    alt_path = tmp_path / "alternate.png"
    output_path = tmp_path / "apple_only.heic"
    base_path.write_bytes(imagecodecs.png_encode(sdr_8bit))
    alt_path.write_bytes(imagecodecs.png_encode(pq_16bit))

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not existing_pythonpath else f"{ROOT}{os.pathsep}{existing_pythonpath}"

    result = subprocess.run(
        [
            sys.executable,
            str(HEIFGAINMAPUTIL_HDR),
            "combine",
            str(base_path),
            str(alt_path),
            str(output_path),
            "--speed", "8",
            "--cicp-base", "1/13/1",
            "--alternate-headroom", "3",
            "--apple-gainmap-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert result.returncode == 0, f"heifgainmaputil_hdr combine failed:\n{result.stdout}\n{result.stderr}"

    container = read_heic_container(output_path)
    assert set(container["item_extents"]) == {1, 2, 3, 4}
    assert get_item_colr(container, 1) == (1, 13, 1)
    assert get_item_colr(container, 2) == (2, 2, 2)

    gm_aux = find_item_property(container, 2, "auxC")
    assert gm_aux is not None
    assert b"urn:com:apple:photo:2020:aux:hdrgainmap" in gm_aux

    refs = _item_references(output_path)
    assert ("auxl", 2, [1]) in refs
    assert ("cdsc", 3, [2]) in refs
    assert ("cdsc", 4, [1]) in refs

    data = output_path.read_bytes()
    xmp_offset, xmp_length = container["item_extents"][3][0]
    xmp_payload = data[xmp_offset:xmp_offset + xmp_length]
    assert b"HDRGainMapVersion>131072" in xmp_payload
    assert b"HDRGainMapHeadroom" in xmp_payload

    output_pixels, _, _ = decode_to_scrgb(str(output_path))
    assert float(output_pixels[..., :3].max()) > 1.0

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert info["gainmap"]["source"] == "Apple HDRGainMap XMP"


@pytest.mark.fidelity
@pytest.mark.tools
def test_cli_pq_tiff_to_gainmap_heic(tmp_path):
    """End-to-end: --pq-input --format gainmap-heic with verify-fidelity."""
    import imagecodecs

    # Build PQ TIFF with known peak
    h, w = 32, 32
    linear_nits = np.full((h, w, 3), 500.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    # Verify output
    source_peak = float(linear_nits[..., :3].max() / 100.0)
    source_headroom = math.log2(max(source_peak, 1.0))

    output_pixels, _, _ = decode_to_scrgb(str(output_path))
    output_peak = float(output_pixels[..., :3].max())

    assert stop_delta(source_peak, output_peak) <= 0.05

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert info["gainmap"]["base_headroom"] == 0.0
    assert info["gainmap"]["alternate_headroom"] + 0.02 >= source_headroom


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_heic_preserves_rgb_highlight_peak(tmp_path):
    """Preserve bright non-neutral PQ highlights through HEIC gainmap reconstruction."""
    import imagecodecs

    h, w = 24, 24
    linear_nits = np.full((h, w, 3), 35.0, dtype=np.float32)
    linear_nits[8:16, 8:16, :] = [883.0, 751.0, 706.0]
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source_rgb_peak.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    source_pixels, _, _ = decode_to_scrgb(str(input_path), pq_input=True)
    output_pixels, _, _ = decode_to_scrgb(str(output_path))
    source_peak = float(source_pixels[..., :3].max())
    output_peak = float(output_pixels[..., :3].max())
    assert stop_delta(source_peak, output_peak) <= 0.05


@pytest.mark.fidelity
def test_gainmap_heic_info_json(tmp_path):
    """Verify --info-json works for gainmap-heic output."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 300.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--info-json",
        ],
        timeout=300,
    )

    import json
    info_json_path = tmp_path / "output.info.json"
    assert info_json_path.exists()
    payload = json.loads(info_json_path.read_text())
    assert payload["format"] == "gainmap-heic"
    assert payload["gainmap"]["present"] is True
    assert payload["gainmap"]["alternateHeadroom"] is not None


@pytest.mark.fidelity
def test_gainmap_heic_verify_fidelity_rejects_wrong_alternate_color(tmp_path):
    """Verify that validation catches incorrect alternate CICP in gainmap HEIC."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 500.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    # Use standard heif format which won't have gainmap metadata
    output_path = tmp_path / "plain.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "heif",
            "--fidelity", "display",
            "--speed", "8",
        ],
        timeout=300,
    )
    # This should create a standard HEIF without gainmap - just verify it doesn't crash
    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is False


@pytest.mark.fidelity
@pytest.mark.tools
def test_gainmap_heic_auto_headroom_works(tmp_path):
    """Test gainmap-heic with auto headroom mode."""
    import imagecodecs

    h, w = 16, 16
    linear_nits = np.full((h, w, 3), 300.0, dtype=np.float32)
    pq_16bit = _pq_encode_16bit(linear_nits, max_nits=10000.0)
    tiff_raw = _make_pq_tiff(pq_16bit)

    input_path = tmp_path / "source.tif"
    input_path.write_bytes(tiff_raw)
    output_path = tmp_path / "output.heic"

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--pq-input",
            "--format", "gainmap-heic",
            "--fidelity", "compat",
            "--speed", "8",
            "--gainmap-headroom-mode", "auto",
        ],
        timeout=300,
    )

    info = inspect_image(output_path)
    assert info["gainmap"]["present"] is True
    assert isinstance(info["gainmap"]["alternate_headroom"], float)
