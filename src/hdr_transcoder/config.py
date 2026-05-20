"""Central runtime constants for HDR Transcoder."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
LIBAVIF_DIR = TOOLS_DIR / "libavif"
LIBJXL_DIR = TOOLS_DIR / "libjxl"
LIBHEIF_DIR = TOOLS_DIR / "libheif"

CICP_BT709_PRIMARIES = 1
CICP_BT709_MATRIX = 1
CICP_SRGB_TRANSFER = 13
CICP_BT2020_PRIMARIES = 9
CICP_BT2020_MATRIX = 9
CICP_PQ_TRANSFER = 16

METADATA_TIMEOUT_SECONDS = 30
TRANSCODE_TIMEOUT_SECONDS = 300
JXL_ENCODE_TIMEOUT_SECONDS = 300
GAINMAP_ENCODE_TIMEOUT_SECONDS = 1800

GAINMAP_HEADROOM_TOLERANCE_STOPS = 0.02
GAINMAP_DECODE_PEAK_TOLERANCE_STOPS = 0.05
JXL_MASTER_PEAK_TOLERANCE_SCRGB = 0.02
DISPLAY_PEAK_TOLERANCE_SCRGB = 0.12

BT2020_PQ_CICP = {
    "primaries": CICP_BT2020_PRIMARIES,
    "transfer": CICP_PQ_TRANSFER,
    "matrix": CICP_BT2020_MATRIX,
}

INPUT_EXTENSIONS = {
    ".jxr", ".wdp", ".hdp", ".jxl", ".exr", ".avif",
    ".heic", ".heif", ".hdr", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
}

TIER1_FORMATS = {"jxl", "ultrahdr", "avif", "heif"}
ALL_OUTPUT_FORMATS = {*TIER1_FORMATS, "gainmap", "gainmap-heic"}

GAINMAP_HEADROOM_SOURCE_PEAK = "source-peak"
GAINMAP_HEADROOM_AUTO = "auto"
GAINMAP_HEADROOM_MODES = {GAINMAP_HEADROOM_SOURCE_PEAK, GAINMAP_HEADROOM_AUTO}

FIDELITY_MASTER = "master"
FIDELITY_DISPLAY = "display"
FIDELITY_COMPAT = "compat"
FIDELITIES = {FIDELITY_MASTER, FIDELITY_DISPLAY, FIDELITY_COMPAT}

MASTER_FORMAT = "jxl"
FORMAT_EXTENSIONS = {
    "jxl": ".jxl",
    "ultrahdr": ".jpg",
    "avif": ".avif",
    "heif": ".heic",
    "gainmap": ".avif",
    "gainmap-heic": ".heic",
}

DEFAULT_NAME_PATTERN = "{name}"
