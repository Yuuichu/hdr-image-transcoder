"""Repository-root import shim for the src-layout hdr_transcoder package."""
from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "hdr_transcoder"
if _SRC_PACKAGE.exists():
    __path__.append(str(_SRC_PACKAGE))

from hdr_transcoder.processor import prepare_alternate_hdr, prepare_base_sdr, _pq_to_linear
from hdr_transcoder.formats.decoder import SUPPORTED_FORMATS, decode_to_scrgb, is_hdr_image, probe_format
from hdr_transcoder.formats import OUTPUT_FORMATS, encode_output
from hdr_transcoder.formats.gainmap import encode_gainmap_avif

__all__ = [
    "OUTPUT_FORMATS",
    "SUPPORTED_FORMATS",
    "_pq_to_linear",
    "decode_to_scrgb",
    "encode_gainmap_avif",
    "encode_output",
    "is_hdr_image",
    "prepare_alternate_hdr",
    "prepare_base_sdr",
    "probe_format",
]
