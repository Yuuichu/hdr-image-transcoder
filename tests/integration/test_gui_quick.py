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
