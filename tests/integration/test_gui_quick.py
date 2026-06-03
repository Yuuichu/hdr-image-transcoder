import re

import pytest


@pytest.mark.quick
@pytest.mark.gui
def test_renderer_dom_references_exist(repo_root):
    html = (repo_root / "electron" / "renderer" / "index.html").read_text(encoding="utf-8")
    app = (repo_root / "electron" / "renderer" / "app.js").read_text(encoding="utf-8")

    ids = set(re.findall(r'id="([^"]+)"', html))
    refs = re.findall(r'getElementById\("([^"]+)"\)', app)
    missing = sorted({ref for ref in refs if ref not in ids})

    assert missing == []


@pytest.mark.quick
@pytest.mark.gui
def test_electron_wires_debug_overlay_and_inspector(repo_root):
    main_js = (repo_root / "electron" / "main.js").read_text(encoding="utf-8")
    preload_js = (repo_root / "electron" / "preload.js").read_text(encoding="utf-8")
    app_js = (repo_root / "electron" / "renderer" / "app.js").read_text(encoding="utf-8")

    assert '"--debug-overlay"' in main_js
    assert '"--info-json"' in main_js
    assert 'ipcMain.handle("image:inspect"' in main_js
    assert 'ipcMain.handle("runtime:check"' in main_js
    assert "inspectImages" in preload_js
    assert "checkRuntime" in preload_js
    assert "inspectImages" in app_js
    assert "debugOverlayInput" in app_js
    assert "infoJsonInput" in app_js
    assert "runtimeStatus" in app_js


@pytest.mark.quick
@pytest.mark.gui
def test_electron_wires_ultrahdr_workbench_options(repo_root):
    html = (repo_root / "electron" / "renderer" / "index.html").read_text(encoding="utf-8")
    main_js = (repo_root / "electron" / "main.js").read_text(encoding="utf-8")
    preload_js = (repo_root / "electron" / "preload.js").read_text(encoding="utf-8")
    app_js = (repo_root / "electron" / "renderer" / "app.js").read_text(encoding="utf-8")

    assert "queueList" in html
    assert "helpContent" in html
    assert "bt2020PqTiffInput" in html
    assert "uhdrBackendSelect" in html
    assert "verifyFidelityInput" in html
    assert "verifyLayersInput" in html
    assert "dumpValidationLayersInput" in html
    assert "formatStatusNote" in html
    assert "readInfoJson" in preload_js
    assert '"--bt2020-pq-tiff"' in main_js
    assert '"--uhdr-backend"' in main_js
    assert '"--gainmap-scale"' in main_js
    assert '"--target-peak-nits"' in main_js
    assert '"--verify-fidelity"' in main_js
    assert '"--verify-layers"' in main_js
    assert '"--dump-validation-layers"' in main_js
    assert '"--validation-report"' in main_js
    assert "allowedInfoJsonSidecars" in main_js
    assert "allowedInfoJsonSidecars = new Map()" in main_js
    assert "MAX_INFO_JSON_BYTES" in main_js
    assert "outputDir = outputDir || dirPath" in main_js
    assert "!canceled && (options.infoJson || options.verifyLayers || options.dumpValidationLayers)" in main_js
    assert "conversionStartedAtMs" in main_js
    assert "scanInfoJsonLogChunk" in main_js
    assert "writtenInfoJsonPaths" in main_js
    assert "expectedSidecars.has(sidecar)" in main_js
    assert "Number.isFinite(uhdrTargetPeakNits)" in main_js
    assert "Number.isFinite(options.headroom)" in main_js
    assert 'ipcMain.handle("conversion:readInfoJson"' in main_js
    assert "activeHelpTopic" in app_js
    assert "logFilter" in app_js
    assert "autoDefaults" in app_js
    assert "applyAutoDefaultsFromInspector" in app_js
    assert "inspectedHdrDefaults" in app_js
    assert "renderFormatStatusNote" in app_js
    assert "formatStatus" in app_js
    assert "layerValidation" in app_js
    assert "layerStatusText" in app_js
    assert "const validationStatus = layerValidation.status" in app_js
    assert "const verifyLayers = elements.verifyLayersInput.checked" in app_js
    assert "dumpValidationLayers" in app_js
    assert "Experimental compatibility" in app_js
    assert "targetPeakNits: clampNumber(Math.ceil(peak * 100), 203, 10000)" in app_js
    assert "state.autoDefaults.headroom = false" in app_js
    assert "state.autoDefaults.targetPeak = false" in app_js
    assert 'bt2020PqTiff: elements.formatSelect.value === "ultrahdr"' in app_js


@pytest.mark.quick
@pytest.mark.gui
def test_renderer_supports_chinese_language_option(repo_root):
    html = (repo_root / "electron" / "renderer" / "index.html").read_text(encoding="utf-8")
    app_js = (repo_root / "electron" / "renderer" / "app.js").read_text(encoding="utf-8")

    assert "languageSelect" in html
    assert 'value="zh-Hans"' in html
    assert ">中文<" in html
    assert "HDR 图像转码器" in html
    assert "const I18N" in app_js
    assert "setLanguage" in app_js
    assert "messages.pqTiffWarning" in app_js
