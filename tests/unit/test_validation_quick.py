import numpy as np
import pytest

from hdr_transcoder.validation import verify_output


@pytest.mark.quick
def test_ultrahdr_verify_uses_compat_peak_tolerance_stops(monkeypatch, tmp_path):
    source = np.full((2, 2, 3), 7.4126, dtype=np.float32)
    decoded = np.full((2, 2, 3), 6.7852, dtype=np.float32)

    monkeypatch.setattr("hdr_transcoder.validation.verify_ultrahdr_metadata", lambda _path: {"present": True})
    monkeypatch.setattr("hdr_transcoder.validation.decode_to_scrgb", lambda _path: (decoded, 2, 2))

    result = verify_output(source, tmp_path / "out.jpg", "ultrahdr", "rec2020-pq")

    assert result["ok"] is True
    assert result["checks"]["peak"]["deltaStops"] == pytest.approx(0.1276, abs=0.001)
    assert result["checks"]["peak"]["toleranceStops"] == 0.15


@pytest.mark.quick
def test_ultrahdr_verify_rejects_large_peak_drift(monkeypatch, tmp_path):
    source = np.full((2, 2, 3), 7.4126, dtype=np.float32)
    decoded = np.full((2, 2, 3), 5.5, dtype=np.float32)

    monkeypatch.setattr("hdr_transcoder.validation.verify_ultrahdr_metadata", lambda _path: {"present": True})
    monkeypatch.setattr("hdr_transcoder.validation.decode_to_scrgb", lambda _path: (decoded, 2, 2))

    with pytest.raises(ValueError, match="decoded gainmap peak drift"):
        verify_output(source, tmp_path / "out.jpg", "ultrahdr", "rec2020-pq")


@pytest.mark.quick
def test_standard_avif_verify_uses_display_peak_tolerance_stops(monkeypatch, tmp_path):
    source = np.full((2, 2, 3), 12.2861, dtype=np.float32)
    decoded = np.full((2, 2, 3), 12.4158, dtype=np.float32)

    monkeypatch.setattr(
        "hdr_transcoder.validation.verify_avif_metadata",
        lambda _path: {"primaries": 9, "transfer": 16, "matrix": 9},
    )
    monkeypatch.setattr("hdr_transcoder.validation.decode_to_scrgb", lambda _path: (decoded, 2, 2))

    result = verify_output(source, tmp_path / "out.avif", "avif", "rec2020-pq")

    assert result["ok"] is True
    assert result["checks"]["peak"]["deltaStops"] == pytest.approx(0.0152, abs=0.001)
    assert result["checks"]["peak"]["toleranceStops"] == 0.05
