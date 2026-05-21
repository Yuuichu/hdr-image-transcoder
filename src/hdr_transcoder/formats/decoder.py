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

from hdr_transcoder.color import (
    CICP_BT2020_MATRIX,
    CICP_BT2020_PRIMARIES,
    CICP_BT709_PRIMARIES,
    CICP_PQ_TRANSFER,
    clamp_small_negatives,
    linear_bt2020_to_srgb,
)
from hdr_transcoder.config import METADATA_TIMEOUT_SECONDS, TRANSCODE_TIMEOUT_SECONDS
from hdr_transcoder.tools import AVIFDEC, JXLINFO


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
HEADROOM_FLOAT_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


class UnsafeMetadataError(RuntimeError):
    """Raised when decoding would require guessing HDR transfer metadata."""


def _warn(message):
    print(f"Warning: {message}", file=sys.stderr)


def _process_detail(result):
    from textwrap import indent

    detail = ""
    if result.stderr:
        detail += f"\nSTDERR:\n{indent(result.stderr.strip(), '  ')}"
    if result.stdout:
        detail += f"\nSTDOUT:\n{indent(result.stdout.strip(), '  ')}"
    return detail


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
        _warn(f"dropping extra image channels: got {pixels.shape[2]}, keeping RGBA")
        pixels = pixels[..., :4]

    if pixels.shape[2] != 4:
        raise ValueError(f"Expected 1, 3, or 4 channels, got {pixels.shape[2]}")

    return pixels


def _to_float32(pixels, preserve_negative=False):
    """Convert pixel arrays to non-negative float32 values."""
    pixels = np.asarray(pixels)

    if np.issubdtype(pixels.dtype, np.floating):
        out = pixels.astype(np.float32)
        return out if preserve_negative else np.maximum(out, 0.0)
    if pixels.dtype == np.bool_:
        return pixels.astype(np.float32)
    if not np.issubdtype(pixels.dtype, np.integer):
        raise TypeError(f"Unsupported pixel dtype: {pixels.dtype}")

    info = np.iinfo(pixels.dtype)
    return np.maximum(pixels.astype(np.float32) / float(info.max), 0.0)


def _decode_jpegxr(raw):
    import imagecodecs

    return _to_float32(imagecodecs.jpegxr_decode(raw), preserve_negative=True)


def _decode_jpegxl(raw):
    import imagecodecs

    info = _read_jxl_info(raw)
    pixels = imagecodecs.jpegxl_decode(raw)
    if info.get("transfer") == "pq":
        pq_norm = _normalize_pq_pixels(pixels)
        return _decode_pq(pq_norm, primaries=info.get("primaries"))
    return _to_float32(pixels, preserve_negative=True)


def _decode_exr(raw):
    import imagecodecs

    return _to_float32(imagecodecs.exr_decode(raw), preserve_negative=True)


def _is_uint10_payload(pixels):
    """Return True when a reliable metadata path says this uint16 payload is 10-bit."""
    if pixels.dtype != np.uint16:
        return False
    if pixels.size == 0:
        return False
    return pixels.max() <= 1023


def _normalize_pq_pixels(pixels):
    pixels = np.asarray(pixels)
    if np.issubdtype(pixels.dtype, np.floating):
        return np.clip(pixels.astype(np.float32), 0.0, 1.0)
    if not np.issubdtype(pixels.dtype, np.integer):
        raise TypeError(f"Unsupported PQ pixel dtype: {pixels.dtype}")

    info = np.iinfo(pixels.dtype)
    return pixels.astype(np.float32) / float(info.max)


def _convert_hdr_rgb_to_scrgb(linear_rgb, primaries=None):
    """Convert decoded linear HDR RGB samples to the internal scRGB space."""
    if primaries == CICP_BT2020_PRIMARIES:
        return clamp_small_negatives(linear_bt2020_to_srgb(linear_rgb))
    return linear_rgb


def _decode_pq(pq_values, primaries=None):
    """Convert normalized PQ pixels to float32 scRGB."""
    from hdr_transcoder.processor import _pq_to_linear

    linear_nits = _pq_to_linear(pq_values, max_nits=10000.0)
    linear = linear_nits / 100.0
    if linear.ndim == 3 and linear.shape[2] >= 3:
        converted = linear.copy()
        converted[..., :3] = _convert_hdr_rgb_to_scrgb(converted[..., :3], primaries)
        return converted
    return _convert_hdr_rgb_to_scrgb(linear, primaries)


def _decode_pq_10bit(pixels, primaries=None):
    """Convert 10-bit uint16 PQ pixels to float32 scRGB."""
    pq_norm = pixels.astype(np.float32) / 1023.0
    return _decode_pq(pq_norm, primaries=primaries)


def _decode_reliable_pq(pixels, primaries=None):
    """Decode PQ only when metadata or a controlled tool invocation says it is PQ."""
    if _is_uint10_payload(pixels):
        return _decode_pq_10bit(pixels, primaries=primaries)
    return _decode_pq(_normalize_pq_pixels(pixels), primaries=primaries)


def _read_avif_cicp(raw):
    """Read AVIF CICP metadata with bundled libavif, if available."""
    if not AVIFDEC.exists():
        _warn(f"cannot read AVIF CICP metadata because avifdec.exe is missing: {AVIFDEC}")
        return {}

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.avif"
        input_path.write_bytes(raw)
        try:
            result = subprocess.run(
                [str(AVIFDEC), "--info", str(input_path)],
                capture_output=True,
                text=True,
                timeout=METADATA_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _warn(f"avifdec.exe --info timed out after {METADATA_TIMEOUT_SECONDS}s")
            return {}
    if result.returncode != 0:
        _warn(f"avifdec.exe --info failed with code {result.returncode}{_process_detail(result)}")
        return {}

    text = f"{result.stdout}\n{result.stderr}"
    fields = {}
    patterns = {
        "primaries": r"Color Primaries:\s*(\d+)",
        "transfer": r"Transfer Char\.\s*:\s*(\d+)",
        "matrix": r"Matrix Coeffs\.\s*:\s*(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[key] = int(match.group(1))
    return fields


def _read_jxl_info(raw):
    """Read JPEG XL metadata with bundled jxlinfo.

    JPEG XL can carry linear, sRGB, or PQ transfer metadata. Decoding without
    that metadata silently corrupts PQ HDR, so this path fails loud instead of
    falling back to guessed interpretation.
    """
    if not JXLINFO.exists():
        raise UnsafeMetadataError(
            f"Missing JPEG XL metadata tool: {JXLINFO}. "
            f"Cannot safely decode JXL without transfer metadata."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.jxl"
        input_path.write_bytes(raw)
        try:
            result = subprocess.run(
                [str(JXLINFO), str(input_path)],
                capture_output=True,
                text=True,
                timeout=METADATA_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise UnsafeMetadataError(
                f"jxlinfo.exe timed out after {METADATA_TIMEOUT_SECONDS}s"
            ) from exc
    if result.returncode != 0:
        raise UnsafeMetadataError(
            f"jxlinfo.exe exited with code {result.returncode}{_process_detail(result)}"
        )

    text = f"{result.stdout}\n{result.stderr}"
    info = {}
    bt2020_label = r"(Rec\.? ?2100|Rec\.? ?2020|BT\.? ?2020|ITU-R BT\.?2020)"
    bt709_label = r"(sRGB|Rec\.? ?709|BT\.? ?709)"
    if re.search(rf"({bt2020_label}.{{0,80}}primaries|primaries.{{0,80}}{bt2020_label})", text, re.IGNORECASE):
        info["primaries"] = CICP_BT2020_PRIMARIES
    elif re.search(rf"({bt709_label}.{{0,80}}primaries|primaries.{{0,80}}{bt709_label})", text, re.IGNORECASE):
        info["primaries"] = CICP_BT709_PRIMARIES

    pq_label = r"(PQ|ST\.? ?2084|Perceptual Quantizer)"
    if re.search(rf"({pq_label}.{{0,80}}transfer|transfer.{{0,80}}{pq_label})", text, re.IGNORECASE):
        info["transfer"] = "pq"
    elif re.search(r"(Linear.{0,80}transfer|transfer.{0,80}Linear)", text, re.IGNORECASE):
        info["transfer"] = "linear"
    elif re.search(r"(sRGB.{0,80}transfer|transfer.{0,80}sRGB)", text, re.IGNORECASE):
        info["transfer"] = "srgb"

    if "transfer" not in info:
        raise UnsafeMetadataError("jxlinfo.exe did not report a recognized JPEG XL transfer function")
    return info


def _decode_gainmap_avif(raw):
    """Decode an AVIF gain map by tone-mapping it to its HDR alternate."""
    from hdr_transcoder.formats.gainmap import AVIFGAINMAPUTIL

    if not AVIFGAINMAPUTIL.exists():
        _warn(f"cannot inspect AVIF gain map because avifgainmaputil.exe is missing: {AVIFGAINMAPUTIL}")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_path = tmp / "input.avif"
        output_path = tmp / "tonemapped.avif"
        input_path.write_bytes(raw)

        try:
            metadata = subprocess.run(
                [str(AVIFGAINMAPUTIL), "printmetadata", str(input_path)],
                capture_output=True,
                text=True,
                timeout=METADATA_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _warn(f"avifgainmaputil printmetadata timed out after {METADATA_TIMEOUT_SECONDS}s")
            return None
        if metadata.returncode != 0:
            _warn(
                "AVIF gain map metadata not available; trying standard AVIF decode "
                f"(avifgainmaputil code {metadata.returncode})"
            )
            return None

        text = f"{metadata.stdout}\n{metadata.stderr}"
        match = re.search(rf"Alternate headroom:\s*({HEADROOM_FLOAT_RE})", text)
        if not match:
            _warn("AVIF gain map metadata does not contain Alternate headroom")
            return None

        alternate_headroom = float(match.group(1))
        if alternate_headroom <= 0:
            _warn(f"AVIF gain map Alternate headroom must be > 0, got {alternate_headroom}")
            return None

        try:
            result = subprocess.run(
                [
                    str(AVIFGAINMAPUTIL),
                    "tonemap",
                    str(input_path),
                    str(output_path),
                    "--headroom",
                    f"{alternate_headroom:.6f}",
                    "--cicp-output",
                    f"{CICP_BT2020_PRIMARIES}/{CICP_PQ_TRANSFER}/{CICP_BT2020_MATRIX}",
                    "-d",
                    "10",
                    "-y",
                    "444",
                    "-q",
                    "95",
                ],
                capture_output=True,
                text=True,
                timeout=TRANSCODE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"avifgainmaputil tonemap timed out after {TRANSCODE_TIMEOUT_SECONDS}s"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise ValueError(f"Cannot decode AVIF gain map: {detail}")

        import imagecodecs

        pixels = imagecodecs.avif_decode(output_path.read_bytes())
        return _decode_reliable_pq(pixels, primaries=CICP_BT2020_PRIMARIES)


def _decode_avif(raw):
    import imagecodecs

    gainmap = _decode_gainmap_avif(raw)
    if gainmap is not None:
        return gainmap

    cicp = _read_avif_cicp(raw)
    pixels = imagecodecs.avif_decode(raw)
    if cicp.get("transfer") == CICP_PQ_TRANSFER:
        return _decode_reliable_pq(pixels, primaries=cicp.get("primaries"))
    if not cicp and _is_uint10_payload(pixels):
        raise UnsafeMetadataError(
            "AVIF decoded as ambiguous 10-bit uint16 data but CICP metadata was unavailable; "
            "cannot safely infer SDR vs PQ HDR"
        )
    return _to_float32(pixels)


def _decode_heif_with_pillow(raw):
    import pillow_heif

    heif_file = pillow_heif.open_heif(BytesIO(raw), convert_hdr_to_8bit=False)
    image = heif_file[0]
    pixels = _extract_pillow_heif_pixels(image)

    dtype = np.uint16 if image.mode.endswith(";16") else np.uint8
    nclx = image.info.get("nclx_profile") or {}
    if nclx.get("transfer_characteristics") == CICP_PQ_TRANSFER:
        info = np.iinfo(dtype)
        pq_norm = pixels.astype(np.float32) / float(info.max)
        return _decode_pq(pq_norm, primaries=nclx.get("color_primaries"))
    if not nclx and _is_uint10_payload(pixels):
        raise UnsafeMetadataError(
            "HEIF decoded as ambiguous 10-bit uint16 data but nclx metadata was unavailable; "
            "cannot safely infer SDR vs PQ HDR"
        )

    return _to_float32(pixels)


def _srgb_to_linear(srgb_pixels):
    """Convert sRGB gamma-encoded values to linear light."""
    srgb = np.asarray(srgb_pixels, dtype=np.float32)
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return linear


def _rec709_to_linear(rec709_pixels):
    """Convert Rec.709 OETF-encoded values to linear light."""
    rec709 = np.asarray(rec709_pixels, dtype=np.float32)
    rec709 = np.clip(rec709, 0.0, 1.0)
    return np.where(rec709 < 0.081, rec709 / 4.5, np.power((rec709 + 0.099) / 1.099, 1.0 / 0.45))


def _resize_gainmap_values(values, target_shape):
    """Resize 2D or 3D gain map values to the SDR image shape."""
    if values.shape[:2] == target_shape:
        return values

    from PIL import Image

    target_size = (target_shape[1], target_shape[0])
    if values.ndim == 2:
        image = Image.fromarray(values.astype(np.float32), mode="F")
        return np.asarray(image.resize(target_size, Image.Resampling.BILINEAR), dtype=np.float32)

    channels = [
        np.asarray(
            Image.fromarray(values[..., channel].astype(np.float32), mode="F").resize(
                target_size, Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
        for channel in range(values.shape[2])
    ]
    return np.stack(channels, axis=-1)


def _decode_gainmap_heif(raw):
    """Decode an ISO 21496-1 gainmap HEIC by applying the gainmap to the SDR base."""
    from hdr_transcoder.formats.isobmff import (
        build_minimal_heic,
        find_item_property,
        get_item_bitdepth,
        get_item_colr,
        get_item_dimensions,
        read_heic_container,
        read_heic_gainmap_metadata_from_container,
    )

    container = read_heic_container(raw)
    if container is None:
        return None

    metadata = read_heic_gainmap_metadata_from_container(container)
    if metadata is None:
        return None

    alternate_headroom = metadata["alternateHeadroom"]
    if alternate_headroom <= 0:
        _warn(f"Gainmap HEIC alternate headroom must be > 0, got {alternate_headroom}")
        return None

    item_extents = container["item_extents"]
    if 1 not in item_extents:
        _warn("Gainmap HEIC missing item 1 (SDR base)")
        return None

    sdr_hvcC = find_item_property(container, 1, "hvcC")
    if sdr_hvcC is None:
        _warn("Gainmap HEIC missing hvcC for SDR base")
        return None

    gainmap_item_id = None
    is_apple_gainmap = False
    is_iso21496 = False
    iso_meta = None
    for item_id in sorted(item_extents):
        aux_type = find_item_property(container, item_id, "auxC")
        if aux_type and b"urn:iso:std:iso:ts:21496:-1:aux:gainmap" in aux_type:
            if find_item_property(container, item_id, "hvcC") is None:
                continue
            gainmap_item_id = item_id
            is_iso21496 = True
            from hdr_transcoder.formats.isobmff import read_heic_iso21496_metadata
            iso_meta = read_heic_iso21496_metadata(container)
            break
    if gainmap_item_id is None:
        for item_id in sorted(item_extents):
            aux_type = find_item_property(container, item_id, "auxC")
            if aux_type and b"urn:com:apple:photo:2020:aux:hdrgainmap" in aux_type:
                if find_item_property(container, item_id, "hvcC") is None:
                    continue
                gainmap_item_id = item_id
                is_apple_gainmap = True
                break

    if gainmap_item_id is None:
        _warn("Gainmap HEIC missing gain map item")
        return None

    gm_hvcC = find_item_property(container, gainmap_item_id, "hvcC")
    if gm_hvcC is None:
        _warn("Gainmap HEIC missing hvcC for gainmap")
        return None

    sdr_width, sdr_height = get_item_dimensions(container, 1)
    gm_width, gm_height = get_item_dimensions(container, gainmap_item_id)
    if sdr_width is None or gm_width is None:
        _warn("Gainmap HEIC missing ispe for SDR base or gainmap")
        return None

    sdr_bpc = get_item_bitdepth(container, 1)
    gm_bpc = get_item_bitdepth(container, gainmap_item_id)
    sdr_primaries, sdr_transfer, sdr_matrix = get_item_colr(container, 1)
    gm_primaries, gm_transfer, gm_matrix = get_item_colr(container, gainmap_item_id)

    sdr_offset, sdr_length = item_extents[1][0]
    gm_offset, gm_length = item_extents[gainmap_item_id][0]
    sdr_bitstream = raw[sdr_offset:sdr_offset + sdr_length]
    gm_bitstream = raw[gm_offset:gm_offset + gm_length]

    import pillow_heif

    sdr_heic = build_minimal_heic(
        sdr_hvcC, sdr_bitstream, sdr_width, sdr_height,
        primaries=sdr_primaries, transfer=sdr_transfer, matrix=sdr_matrix,
        bits_per_channel=sdr_bpc,
    )
    heif_file = pillow_heif.open_heif(BytesIO(sdr_heic), convert_hdr_to_8bit=False)
    sdr_image = heif_file[0]
    sdr_pixels = _extract_pillow_heif_pixels(sdr_image)
    sdr_float = _to_float32(sdr_pixels)

    gm_heic = build_minimal_heic(
        gm_hvcC, gm_bitstream, gm_width, gm_height,
        primaries=gm_primaries, transfer=gm_transfer, matrix=gm_matrix,
        bits_per_channel=gm_bpc,
    )
    heif_file = pillow_heif.open_heif(BytesIO(gm_heic), convert_hdr_to_8bit=False)
    gm_image = heif_file[0]
    gm_pixels = _extract_pillow_heif_pixels(gm_image)
    gm_float = _to_float32(gm_pixels)

    if gm_float.ndim == 3 and gm_float.shape[2] >= 3:
        gm_values = gm_float[..., :3]
    elif gm_float.ndim == 3 and gm_float.shape[2] == 1:
        gm_values = gm_float[..., 0]
    else:
        gm_values = gm_float

    gm_values = _resize_gainmap_values(gm_values, sdr_float.shape[:2])

    sdr_linear = _srgb_to_linear(sdr_float[..., :3])

    if is_apple_gainmap:
        gain = _rec709_to_linear(gm_values)
        gain = np.expand_dims(gain, axis=-1) if gain.ndim == 2 else gain
        headroom = 2.0 ** max(alternate_headroom, 0.0)
        hdr_rgb = sdr_linear * (1.0 + (headroom - 1.0) * gain)
    elif is_iso21496 and iso_meta is not None and gm_values.ndim == 3 and gm_values.shape[2] >= 3:
        gm_norm = np.clip(gm_values, 0.0, 1.0)
        gm_min = np.array(iso_meta["gainMapMin"], dtype=np.float32).reshape(1, 1, 3)
        gm_max = np.array(iso_meta["gainMapMax"], dtype=np.float32).reshape(1, 1, 3)
        gamma = np.array(iso_meta["gamma"], dtype=np.float32).reshape(1, 1, 3)
        base_off = np.array(iso_meta["baseOffset"], dtype=np.float32).reshape(1, 1, 3)
        alt_off = np.array(iso_meta["alternateOffset"], dtype=np.float32).reshape(1, 1, 3)
        gain_norm = np.power(np.maximum(gm_norm, 0.0), gamma)
        gain_log = gain_norm * (gm_max - gm_min) + gm_min
        gain = np.power(2.0, gain_log)
        hdr_rgb = (sdr_linear + base_off) * gain - alt_off
    else:
        gain_log = gm_values * 16.0 - 8.0
        gain = np.power(2.0, gain_log)
        gain = np.expand_dims(gain, axis=-1) if gain.ndim == 2 else gain
        hdr_rgb = sdr_linear * gain
    if sdr_primaries == CICP_BT2020_PRIMARIES:
        hdr_rgb = clamp_small_negatives(linear_bt2020_to_srgb(hdr_rgb))
    hdr_rgba = np.zeros((*hdr_rgb.shape[:2], 4), dtype=np.float32)
    hdr_rgba[..., :3] = hdr_rgb
    hdr_rgba[..., 3] = 1.0

    return hdr_rgba


def _extract_pillow_heif_pixels(image):
    """Extract numpy pixel array from a pillow_heif Image object."""
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
    return row_pixels[:, :width * channels].reshape(height, width, channels)


def _decode_heif(raw):
    gainmap_result = _decode_gainmap_heif(raw)
    if gainmap_result is not None:
        return gainmap_result
    try:
        return _decode_heif_with_pillow(raw)
    except UnsafeMetadataError:
        raise
    except Exception as primary_error:
        _warn(
            "HEIF Pillow decoder failed; falling back to imagecodecs without "
            f"nclx HDR metadata: {primary_error}"
        )
        import imagecodecs

        pixels = imagecodecs.heif_decode(raw)
        if _is_uint10_payload(pixels):
            raise UnsafeMetadataError(
                "HEIF decoded as ambiguous 10-bit uint16 data after nclx metadata was lost; "
                "cannot safely infer SDR vs PQ HDR"
            ) from primary_error
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


def _read_tiff_cicp(raw):
    """Extract CICP-like color metadata from TIFF IFD/EXIF tags.

    Returns a dict with keys primaries, transfer, matrix (all int or None).
    Returns empty dict if no recognizable CICP metadata is found.
    """
    import struct

    if len(raw) < 8:
        return {}

    byte_order = raw[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return {}

    magic = struct.unpack(f"{endian}H", raw[2:4])[0]
    if magic not in (42, 0x2A):
        return {}

    ifd_offset = struct.unpack(f"{endian}I", raw[4:8])[0]
    if ifd_offset <= 0 or ifd_offset + 2 > len(raw):
        return {}

    result = {}

    for _ in range(8):
        if ifd_offset + 2 > len(raw):
            break
        num_entries = struct.unpack(f"{endian}H", raw[ifd_offset:ifd_offset + 2])[0]
        entry_base = ifd_offset + 2
        entry_end = entry_base + num_entries * 12
        if entry_end > len(raw):
            break

        for i in range(num_entries):
            pos = entry_base + i * 12
            if pos + 12 > len(raw):
                break
            tag, dtype, count, value_or_offset = struct.unpack(
                f"{endian}HHII", raw[pos:pos + 12]
            )

            if tag == 0xC761:
                byte_count = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 11: 4}.get(dtype, 1) * count
                if byte_count <= 4:
                    value_bytes = raw[pos + 8:pos + 8 + byte_count]
                else:
                    vo = value_or_offset
                    if vo + byte_count <= len(raw):
                        value_bytes = raw[vo:vo + byte_count]
                    else:
                        value_bytes = b""
                if value_bytes:
                    try:
                        text = value_bytes.decode("ascii", errors="ignore")
                    except Exception:
                        text = ""
                    for match in re.finditer(
                        r"Transfer\s*Char(?:acteristics)?\s*[:=]?\s*(\d+)",
                        text, re.IGNORECASE,
                    ):
                        result["transfer"] = int(match.group(1))
                    for match in re.finditer(
                        r"Color\s*Primaries\s*[:=]?\s*(\d+)",
                        text, re.IGNORECASE,
                    ):
                        result["primaries"] = int(match.group(1))
                    for match in re.finditer(
                        r"Matrix\s*Coeff(?:icient)?s?\s*[:=]?\s*(\d+)",
                        text, re.IGNORECASE,
                    ):
                        result["matrix"] = int(match.group(1))

        next_offset_field = entry_end
        if next_offset_field + 4 > len(raw):
            break
        next_offset = struct.unpack(f"{endian}I", raw[next_offset_field:next_offset_field + 4])[0]
        if next_offset <= 0:
            break
        ifd_offset = next_offset

    return result


def _decode_tiff(raw, pq_input=False):
    import imagecodecs

    cicp = _read_tiff_cicp(raw)
    pixels = imagecodecs.tiff_decode(raw)

    if cicp.get("transfer") == CICP_PQ_TRANSFER or pq_input:
        pq_norm = _normalize_pq_pixels(pixels)
        return _decode_pq(pq_norm, primaries=cicp.get("primaries"))

    return _to_float32(pixels, preserve_negative=True)


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


def decode_to_scrgb(filepath, pq_input=False):
    """Decode a supported image to float32 linear RGBA data."""
    path = Path(filepath)
    fmt = probe_format(filepath)
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"Cannot decode empty file: {filepath}")

    decoder = _DECODERS.get(fmt)
    primary_message = ""

    if decoder is not None:
        try:
            try:
                pixels = _ensure_rgba(decoder(raw, pq_input=pq_input))
            except TypeError:
                pixels = _ensure_rgba(decoder(raw))
            height, width = pixels.shape[:2]
            return pixels, width, height
        except UnsafeMetadataError as primary_error:
            raise ValueError(
                f"Cannot decode safely: {filepath} (detected: {fmt}; {primary_error})"
            ) from primary_error
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
