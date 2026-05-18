"""
HDR Image Transcoder multi-format HDR image conversion library.

Decode HDR inputs to float32 linear scRGB, then encode HDR output formats.
"""

from src.processor import prepare_base_sdr, prepare_alternate_hdr, _pq_to_linear
from src.decoder import decode_to_scrgb, probe_format, is_hdr_image, SUPPORTED_FORMATS
from src.encoder import encode_output, OUTPUT_FORMATS
from src.gainmap import encode_gainmap_avif
