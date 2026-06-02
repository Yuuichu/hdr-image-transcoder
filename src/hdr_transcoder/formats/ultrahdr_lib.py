"""Optional libultrahdr backend for BT.2020 PQ TIFF to Ultra HDR JPEG."""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import numpy as np

from hdr_transcoder.color import linear_bt2020_to_display_p3
from hdr_transcoder.config import (
    LIBULTRAHDR_DIR,
    ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
)
from hdr_transcoder.processor import _linear_to_pq, _pq_to_linear

UHLIB_ENV_VARS = ("HDR_TRANSCODER_UHDR_DLL", "UHDR_DLL")

UHDR_CODEC_OK = 0
UHDR_IMG_FMT_32BPP_RGBA1010102 = 5
UHDR_IMG_FMT_32BPP_RGBA8888 = 3
UHDR_CG_DISPLAY_P3 = 1
UHDR_CT_PQ = 2
UHDR_CT_SRGB = 3
UHDR_CR_FULL_RANGE = 1
UHDR_HDR_IMG = 0
UHDR_SDR_IMG = 1
UHDR_BASE_IMG = 2
UHDR_GAIN_MAP_IMG = 3

_SDR_WHITE_NITS = np.float32(203.0)
_HDR_WHITE_NITS = np.float32(10000.0)


class UhdrErrorInfo(ctypes.Structure):
    _fields_ = [
        ("error_code", ctypes.c_int),
        ("has_detail", ctypes.c_int),
        ("detail", ctypes.c_char * 256),
    ]


class UhdrRawImage(ctypes.Structure):
    _fields_ = [
        ("fmt", ctypes.c_int),
        ("cg", ctypes.c_int),
        ("ct", ctypes.c_int),
        ("range", ctypes.c_int),
        ("w", ctypes.c_uint),
        ("h", ctypes.c_uint),
        ("planes", ctypes.c_void_p * 3),
        ("stride", ctypes.c_uint * 3),
    ]


class UhdrCompressedImage(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("data_sz", ctypes.c_size_t),
        ("capacity", ctypes.c_size_t),
        ("cg", ctypes.c_int),
        ("ct", ctypes.c_int),
        ("range", ctypes.c_int),
    ]


def candidate_uhdr_dll_paths() -> list[Path]:
    """Return candidate libultrahdr dynamic library paths in load order."""
    candidates: list[Path] = []
    for env_name in UHLIB_ENV_VARS:
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))

    if sys.platform == "win32":
        names = ("uhdr.dll", "libuhdr.dll")
    elif sys.platform == "darwin":
        names = ("libuhdr.dylib", "uhdr.dylib")
    else:
        names = ("libuhdr.so", "uhdr.so")

    candidates.extend(LIBULTRAHDR_DIR / name for name in names)
    return candidates


def find_uhdr_dll() -> Path | None:
    """Find the first existing libultrahdr library path."""
    for path in candidate_uhdr_dll_paths():
        if path.exists():
            return path
    return None


def is_libultrahdr_available() -> bool:
    return find_uhdr_dll() is not None


def _load_uhdr(dll_path: str | os.PathLike | None = None) -> ctypes.CDLL:
    path = Path(dll_path) if dll_path else find_uhdr_dll()
    if path is None:
        searched = ", ".join(str(p) for p in candidate_uhdr_dll_paths())
        raise FileNotFoundError(
            "libultrahdr backend requested but no dynamic library was found. "
            f"Set HDR_TRANSCODER_UHDR_DLL or place uhdr.dll in {LIBULTRAHDR_DIR}. "
            f"Searched: {searched}"
        )

    if sys.platform == "win32":
        os.add_dll_directory(str(path.parent))
    lib = ctypes.CDLL(str(path))
    _configure_uhdr_api(lib)
    return lib


def _configure_uhdr_api(lib: ctypes.CDLL) -> None:
    codec_p = ctypes.c_void_p
    lib.uhdr_create_encoder.argtypes = []
    lib.uhdr_create_encoder.restype = codec_p
    lib.uhdr_release_encoder.argtypes = [codec_p]
    lib.uhdr_release_encoder.restype = None
    lib.uhdr_enc_set_raw_image.argtypes = [codec_p, ctypes.POINTER(UhdrRawImage), ctypes.c_int]
    lib.uhdr_enc_set_raw_image.restype = UhdrErrorInfo
    lib.uhdr_enc_set_quality.argtypes = [codec_p, ctypes.c_int, ctypes.c_int]
    lib.uhdr_enc_set_quality.restype = UhdrErrorInfo
    lib.uhdr_enc_set_using_multi_channel_gainmap.argtypes = [codec_p, ctypes.c_int]
    lib.uhdr_enc_set_using_multi_channel_gainmap.restype = UhdrErrorInfo
    lib.uhdr_enc_set_gainmap_scale_factor.argtypes = [codec_p, ctypes.c_int]
    lib.uhdr_enc_set_gainmap_scale_factor.restype = UhdrErrorInfo
    lib.uhdr_enc_set_gainmap_gamma.argtypes = [codec_p, ctypes.c_float]
    lib.uhdr_enc_set_gainmap_gamma.restype = UhdrErrorInfo
    lib.uhdr_enc_set_target_display_peak_brightness.argtypes = [codec_p, ctypes.c_float]
    lib.uhdr_enc_set_target_display_peak_brightness.restype = UhdrErrorInfo
    lib.uhdr_encode.argtypes = [codec_p]
    lib.uhdr_encode.restype = UhdrErrorInfo
    lib.uhdr_get_encoded_stream.argtypes = [codec_p]
    lib.uhdr_get_encoded_stream.restype = ctypes.POINTER(UhdrCompressedImage)


def _check(err: UhdrErrorInfo, where: str) -> None:
    if err.error_code == UHDR_CODEC_OK:
        return
    detail = ""
    if err.has_detail:
        detail = bytes(err.detail).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    raise RuntimeError(f"libultrahdr {where} failed: code={err.error_code} {detail}".rstrip())


def load_bt2020_pq_tiff(path: str | os.PathLike) -> np.ndarray:
    """Load a true BT.2020 PQ TIFF as uint16 RGB samples."""
    import imagecodecs

    pixels = imagecodecs.tiff_decode(Path(path).read_bytes())
    arr = np.asarray(pixels)
    if arr.dtype != np.uint16:
        raise ValueError(f"BT.2020 PQ TIFF path requires uint16 RGB TIFF input; got {arr.dtype}")
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"BT.2020 PQ TIFF path requires shape (H, W, 3); got {arr.shape}")
    if arr.shape[0] < 8 or arr.shape[1] < 8:
        raise ValueError("Ultra HDR JPEG output requires image dimensions of at least 8x8")
    return np.ascontiguousarray(arr)


def _soft_clip_display_p3(linear_p3_nits: np.ndarray) -> np.ndarray:
    """Clamp to the libultrahdr PQ domain while preserving in-gamut samples."""
    p3 = np.asarray(linear_p3_nits, dtype=np.float32)
    p3 = np.where((p3 < 0.0) & (p3 > -1e-3), 0.0, p3)
    p3 = np.maximum(p3, 0.0)
    max_channel = np.max(p3, axis=-1, keepdims=True)
    scale = np.where(max_channel > _HDR_WHITE_NITS, _HDR_WHITE_NITS / max_channel, 1.0)
    return p3 * scale


def bt2020_pq_to_display_p3_pq(rgb16: np.ndarray) -> np.ndarray:
    """Convert uint16 BT.2020 PQ signal values to Display P3 PQ float32."""
    if rgb16.dtype != np.uint16:
        raise TypeError(f"expected uint16 BT.2020 PQ samples, got {rgb16.dtype}")
    if rgb16.ndim != 3 or rgb16.shape[2] != 3:
        raise ValueError(f"expected RGB image shape (H, W, 3), got {rgb16.shape}")

    pq = rgb16.astype(np.float32) * np.float32(1.0 / 65535.0)
    linear_bt2020_nits = _pq_to_linear(pq, max_nits=10000.0)
    linear_p3_nits = linear_bt2020_to_display_p3(linear_bt2020_nits)
    linear_p3_nits = _soft_clip_display_p3(linear_p3_nits)
    return np.ascontiguousarray(_linear_to_pq(linear_p3_nits, max_nits=10000.0).astype(np.float32))


def pack_rgba1010102(rgb_f32: np.ndarray) -> np.ndarray:
    """Pack RGB float32 [0, 1] values to libultrahdr RGBA1010102 words."""
    rgb = np.clip(np.asarray(rgb_f32, dtype=np.float32), 0.0, 1.0)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected RGB image shape (H, W, 3), got {rgb.shape}")
    u32 = (rgb * np.float32(1023.0) + np.float32(0.5)).astype(np.uint32)
    u32[..., 1] <<= np.uint32(10)
    u32[..., 2] <<= np.uint32(20)
    packed = np.empty(rgb.shape[:2], dtype=np.uint32)
    np.bitwise_or(u32[..., 0], u32[..., 1], out=packed)
    np.bitwise_or(packed, u32[..., 2], out=packed)
    packed |= np.uint32(0xC0000000)
    return np.ascontiguousarray(packed)


def display_p3_pq_to_sdr_rgba8888(p3_pq_f32: np.ndarray) -> np.ndarray:
    """Tone-map Display P3 PQ signal values to packed RGBA8888 SDR."""
    pq = np.clip(np.asarray(p3_pq_f32, dtype=np.float32), 0.0, 1.0)
    if pq.ndim != 3 or pq.shape[2] != 3:
        raise ValueError(f"expected RGB image shape (H, W, 3), got {pq.shape}")

    linear_norm = _pq_to_linear(pq, max_nits=10000.0) / _HDR_WHITE_NITS
    headroom = _HDR_WHITE_NITS / _SDR_WHITE_NITS
    y = linear_norm * headroom
    y_max = np.max(y, axis=-1, keepdims=True)
    y_max_sdr = y_max * (np.float32(1.0) + y_max / (headroom * headroom)) / (
        np.float32(1.0) + y_max
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        scale = np.where(y_max > np.float32(0.0), y_max_sdr / y_max, np.float32(0.0))
    sdr = np.clip(y * scale, np.float32(0.0), np.float32(1.0))
    sdr_gamma = np.power(sdr, np.float32(1.0 / 2.2))
    rgb8 = (sdr_gamma * np.float32(255.0) + np.float32(0.5)).clip(0, 255).astype(np.uint32)

    packed = np.empty(pq.shape[:2], dtype=np.uint32)
    np.bitwise_or(rgb8[..., 0], rgb8[..., 1] << np.uint32(8), out=packed)
    np.bitwise_or(packed, rgb8[..., 2] << np.uint32(16), out=packed)
    packed |= np.uint32(0xFF000000)
    return np.ascontiguousarray(packed)


def _raw_image(fmt: int, color_gamut: int, transfer: int, packed: np.ndarray) -> UhdrRawImage:
    if not packed.flags.c_contiguous:
        raise ValueError("libultrahdr raw image buffers must be C-contiguous")
    height, width = packed.shape
    img = UhdrRawImage()
    img.fmt = fmt
    img.cg = color_gamut
    img.ct = transfer
    img.range = UHDR_CR_FULL_RANGE
    img.w = width
    img.h = height
    img.planes[0] = packed.ctypes.data_as(ctypes.c_void_p).value
    img.planes[1] = 0
    img.planes[2] = 0
    img.stride[0] = width
    img.stride[1] = 0
    img.stride[2] = 0
    return img


def encode_raw_p3_ultrahdr(
    packed_p3_hdr: np.ndarray,
    packed_p3_sdr: np.ndarray,
    output_path: str | os.PathLike,
    *,
    quality: int = 95,
    gainmap_scale: int = ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    gainmap_gamma: float = ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    target_peak_nits: float = ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
    dll_path: str | os.PathLike | None = None,
) -> Path:
    """Encode packed Display P3 HDR/SDR images as Ultra HDR JPEG."""
    lib = _load_uhdr(dll_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    packed_p3_hdr = np.ascontiguousarray(packed_p3_hdr)
    packed_p3_sdr = np.ascontiguousarray(packed_p3_sdr)

    hdr_img = _raw_image(
        UHDR_IMG_FMT_32BPP_RGBA1010102,
        UHDR_CG_DISPLAY_P3,
        UHDR_CT_PQ,
        packed_p3_hdr,
    )
    sdr_img = _raw_image(
        UHDR_IMG_FMT_32BPP_RGBA8888,
        UHDR_CG_DISPLAY_P3,
        UHDR_CT_SRGB,
        packed_p3_sdr,
    )

    enc = lib.uhdr_create_encoder()
    if not enc:
        raise RuntimeError("libultrahdr uhdr_create_encoder returned NULL")
    try:
        _check(lib.uhdr_enc_set_raw_image(enc, ctypes.byref(hdr_img), UHDR_HDR_IMG), "set_raw_image(HDR)")
        _check(lib.uhdr_enc_set_raw_image(enc, ctypes.byref(sdr_img), UHDR_SDR_IMG), "set_raw_image(SDR)")
        _check(lib.uhdr_enc_set_using_multi_channel_gainmap(enc, 1), "set_multi_channel_gainmap")
        _check(lib.uhdr_enc_set_gainmap_scale_factor(enc, int(gainmap_scale)), "set_gainmap_scale_factor")
        _check(lib.uhdr_enc_set_gainmap_gamma(enc, float(gainmap_gamma)), "set_gainmap_gamma")
        _check(lib.uhdr_enc_set_quality(enc, int(quality), UHDR_BASE_IMG), "set_quality(base)")
        _check(lib.uhdr_enc_set_quality(enc, int(quality), UHDR_GAIN_MAP_IMG), "set_quality(gainmap)")
        _check(
            lib.uhdr_enc_set_target_display_peak_brightness(enc, float(target_peak_nits)),
            "set_target_display_peak_brightness",
        )
        _check(lib.uhdr_encode(enc), "encode")
        encoded = lib.uhdr_get_encoded_stream(enc)
        if not encoded:
            raise RuntimeError("libultrahdr uhdr_get_encoded_stream returned NULL")
        data = ctypes.string_at(encoded.contents.data, encoded.contents.data_sz)
    finally:
        lib.uhdr_release_encoder(enc)

    output_path.write_bytes(data)
    return output_path


def encode_bt2020_pq_tiff_to_ultrahdr(
    input_path: str | os.PathLike,
    output_path: str | os.PathLike,
    *,
    quality: int = 95,
    gainmap_scale: int = ULTRAHDR_DEFAULT_GAINMAP_SCALE,
    gainmap_gamma: float = ULTRAHDR_DEFAULT_GAINMAP_GAMMA,
    target_peak_nits: float = ULTRAHDR_DEFAULT_TARGET_PEAK_NITS,
    dll_path: str | os.PathLike | None = None,
) -> Path:
    """Encode a true BT.2020 PQ TIFF as Display P3 Ultra HDR JPEG."""
    rgb16 = load_bt2020_pq_tiff(input_path)
    p3_pq = bt2020_pq_to_display_p3_pq(rgb16)
    packed_hdr = pack_rgba1010102(p3_pq)
    packed_sdr = display_p3_pq_to_sdr_rgba8888(p3_pq)
    return encode_raw_p3_ultrahdr(
        packed_hdr,
        packed_sdr,
        output_path,
        quality=quality,
        gainmap_scale=gainmap_scale,
        gainmap_gamma=gainmap_gamma,
        target_peak_nits=target_peak_nits,
        dll_path=dll_path,
    )
