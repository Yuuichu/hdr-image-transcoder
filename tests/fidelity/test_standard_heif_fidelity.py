"""Fidelity tests for standard single-layer HEIF HDR output."""
import numpy as np
import pytest

from hdr_transcoder.formats.decoder import decode_to_scrgb

from helpers import run_python


@pytest.mark.fidelity
@pytest.mark.tools
def test_standard_heif_quality_100_verify_fidelity(tmp_path):
    import imagecodecs

    h, w = 24, 32
    pixels = np.full((h, w, 3), 0.08, dtype=np.float32)
    pixels[4:12, 6:18, :] = 10.0
    pixels[12:20, 18:28, :] = [5.0, 3.0, 0.7]

    input_path = tmp_path / "source.tif"
    output_path = tmp_path / "output.heic"
    input_path.write_bytes(
        imagecodecs.tiff_encode(
            pixels,
            photometric="rgb",
            planarconfig="contig",
        )
    )

    run_python(
        [
            "hdr2avif.py",
            input_path,
            output_path,
            "--format",
            "heif",
            "--fidelity",
            "display",
            "--quality",
            "100",
            "--verify-fidelity",
        ],
        timeout=300,
    )

    decoded, _, _ = decode_to_scrgb(output_path)
    assert abs(float(decoded[..., :3].max()) - 10.0) <= 0.12
