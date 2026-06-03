import numpy as np

from hdr_transcoder import layer_validation as lv


def _layer(name, status=lv.STATUS_PASS):
    layer = lv._new_layer(name)
    lv._add_check(layer, "check", status, f"{name} {status}")
    return lv._finalize_layer(layer)


def test_layer_validation_writes_report_and_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(lv, "_validate_sdr_base", lambda *args, **kwargs: _layer("SDR Base"))
    monkeypatch.setattr(lv, "_validate_gainmap", lambda *args, **kwargs: _layer("Gainmap"))
    monkeypatch.setattr(lv, "_validate_reconstruction", lambda *args, **kwargs: _layer("HDR Reconstruction"))
    monkeypatch.setattr(lv, "_validate_metadata", lambda *args, **kwargs: _layer("Metadata"))

    report_path = tmp_path / "report.md"
    result = lv.validate_layers(
        np.ones((2, 2, 3), dtype=np.float32),
        tmp_path / "out.avif",
        "gainmap",
        validation_report=report_path,
    )

    assert result["ok"] is True
    assert result["status"] == lv.STATUS_PASS
    assert result["layers"]["sdrBase"]["status"] == lv.STATUS_PASS
    assert report_path.exists()
    assert (tmp_path / "metrics.json").exists()
    assert "SDR Base: pass" in report_path.read_text(encoding="utf-8")


def test_layer_validation_directory_report_uses_per_output_run_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(lv, "_validate_sdr_base", lambda *args, **kwargs: _layer("SDR Base"))
    monkeypatch.setattr(lv, "_validate_gainmap", lambda *args, **kwargs: _layer("Gainmap"))
    monkeypatch.setattr(lv, "_validate_reconstruction", lambda *args, **kwargs: _layer("HDR Reconstruction"))
    monkeypatch.setattr(lv, "_validate_metadata", lambda *args, **kwargs: _layer("Metadata"))

    result = lv.validate_layers(
        np.ones((2, 2, 3), dtype=np.float32),
        tmp_path / "out.avif",
        "gainmap",
        validation_report=tmp_path / "reports",
    )

    assert result["reportPath"].endswith("report.md")
    assert "reports" in result["reportPath"]
    assert result["runDir"] != str(tmp_path / "reports")
    assert "out" in result["runDir"]


def test_json_validation_report_argument_is_treated_as_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(lv, "_validate_sdr_base", lambda *args, **kwargs: _layer("SDR Base"))
    monkeypatch.setattr(lv, "_validate_gainmap", lambda *args, **kwargs: _layer("Gainmap"))
    monkeypatch.setattr(lv, "_validate_reconstruction", lambda *args, **kwargs: _layer("HDR Reconstruction"))
    monkeypatch.setattr(lv, "_validate_metadata", lambda *args, **kwargs: _layer("Metadata"))

    result = lv.validate_layers(
        np.ones((2, 2, 3), dtype=np.float32),
        tmp_path / "out.avif",
        "gainmap",
        validation_report=tmp_path / "reports.json",
    )

    assert result["reportPath"].endswith("report.md")
    assert "reports.json" in result["reportPath"]


def test_layer_validation_reports_failing_layer(monkeypatch, tmp_path):
    monkeypatch.setattr(lv, "_validate_sdr_base", lambda *args, **kwargs: _layer("SDR Base"))
    monkeypatch.setattr(lv, "_validate_gainmap", lambda *args, **kwargs: _layer("Gainmap", lv.STATUS_WARNING))
    monkeypatch.setattr(lv, "_validate_reconstruction", lambda *args, **kwargs: _layer("HDR Reconstruction"))
    monkeypatch.setattr(lv, "_validate_metadata", lambda *args, **kwargs: _layer("Metadata", lv.STATUS_FAIL))

    result = lv.validate_layers(
        np.ones((2, 2, 3), dtype=np.float32),
        tmp_path / "out.jpg",
        "ultrahdr",
        validation_report=tmp_path / "report.md",
    )

    assert result["ok"] is False
    assert result["status"] == lv.STATUS_FAIL
    assert result["layers"]["gainmap"]["status"] == lv.STATUS_WARNING
    assert result["layers"]["metadata"]["status"] == lv.STATUS_FAIL


def test_skipped_layer_stays_skipped():
    layer = lv._new_layer("Gainmap")
    lv._add_check(layer, "not-applicable", lv.STATUS_SKIPPED, "No gainmap layer")

    assert lv._finalize_layer(layer)["status"] == lv.STATUS_SKIPPED
