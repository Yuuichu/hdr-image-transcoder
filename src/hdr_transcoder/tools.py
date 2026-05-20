"""Bundled tool paths and runtime self-checks."""
import importlib
import json
import platform
import subprocess
import sys
from pathlib import Path

from hdr_transcoder.config import LIBAVIF_DIR, LIBJXL_DIR, PROJECT_ROOT

AVIFGAINMAPUTIL = LIBAVIF_DIR / "avifgainmaputil.exe"
AVIFGAINMAPUTIL_HDR = LIBAVIF_DIR / "avifgainmaputil_hdr.exe"
AVIFDEC = LIBAVIF_DIR / "avifdec.exe"
AVIFENC = LIBAVIF_DIR / "avifenc.exe"
CJXL = LIBJXL_DIR / "cjxl.exe"
DJXL = LIBJXL_DIR / "djxl.exe"
JXLINFO = LIBJXL_DIR / "jxlinfo.exe"

REQUIRED_TOOLS = {
    "avifgainmaputil.exe": AVIFGAINMAPUTIL,
    "avifgainmaputil_hdr.exe": AVIFGAINMAPUTIL_HDR,
    "avifdec.exe": AVIFDEC,
    "cjxl.exe": CJXL,
    "jxlinfo.exe": JXLINFO,
}

DEPENDENCIES = {
    "numpy": "numpy",
    "imagecodecs": "imagecodecs",
    "Pillow": "PIL",
    "pillow-heif": "pillow_heif",
}


def missing_tools(required=None):
    required = required or REQUIRED_TOOLS
    return [
        {"name": name, "path": str(path)}
        for name, path in required.items()
        if not Path(path).exists()
    ]


def dependency_errors(dependencies=None):
    dependencies = dependencies or DEPENDENCIES
    errors = []
    for package, module in dependencies.items():
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append({"package": package, "module": module, "error": str(exc)})
    return errors


def python_version():
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "prefix": sys.prefix,
    }


def check_runtime_environment():
    missing = missing_tools()
    dep_errors = dependency_errors()
    return {
        "ok": not missing and not dep_errors,
        "projectRoot": str(PROJECT_ROOT),
        "pythonVersion": python_version(),
        "missingTools": missing,
        "dependencyErrors": dep_errors,
    }


def _run_help(path, args):
    if not Path(path).exists():
        return {"ok": False, "error": f"missing: {path}"}
    try:
        result = subprocess.run(
            [str(path), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    output = f"{result.stdout}\n{result.stderr}"
    ok = (
        result.returncode == 0
        or "Usage:" in output
        or "Usage: " in output
        or "Tool to manipulate AVIF images" in output
    )
    return {
        "ok": ok,
        "returnCode": result.returncode,
        "stdout": result.stdout[:4000],
        "stderr": result.stderr[:4000],
    }


def check_tool_invocation():
    return {
        "cjxl.exe": _run_help(CJXL, ["--help"]),
        "jxlinfo.exe": _run_help(JXLINFO, ["--help"]),
        "avifdec.exe": _run_help(AVIFDEC, ["--help"]),
        "avifgainmaputil.exe": _run_help(AVIFGAINMAPUTIL, ["--help"]),
        "avifgainmaputil_hdr.exe": _run_help(AVIFGAINMAPUTIL_HDR, ["combine", "--help"]),
    }


def main(argv=None):
    argv = list(argv or [])
    payload = check_runtime_environment()
    if "--invoke" in argv:
        payload["toolInvocation"] = check_tool_invocation()
    pretty = "--pretty" in argv
    print(json.dumps(payload, indent=2 if pretty else None))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
