"""Headroom-aware wrapper for libavif's avifgainmaputil.

The bundled libavif 1.4.1 avifgainmaputil can compute gain map metadata but
cannot force base/alternate HDR headroom from its CLI. This wrapper preserves
the official combine path, then patches the ISO gain map metadata fractions in
the generated AVIF when --base-headroom or --alternate-headroom is supplied.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path


UINT32_MAX = 0xFFFFFFFF
if getattr(sys, "frozen", False):
    OFFICIAL_TOOL = Path(sys.executable).with_name("avifgainmaputil.exe")
else:
    OFFICIAL_TOOL = Path(__file__).with_name("avifgainmaputil.exe")
FRACTION_RE = re.compile(
    r"\*\s+(Base|Alternate) headroom:\s+"
    r"[^\n]*?\(as fraction:\s+(\d+)/(\d+)\)",
    re.IGNORECASE,
)

OPTIONS_WITH_VALUE = {
    "--downscaling",
    "--qgain-map",
    "--depth-gain-map",
    "--yuv-gain-map",
    "--max-headroom",
    "--cicp-base",
    "--cicp-alternate",
    "--clli-base",
    "--clli-alternate",
    "--speed",
    "-s",
    "--qcolor",
    "-q",
    "--qalpha",
    "--grid",
    "--yuv",
    "-y",
    "--depth",
    "-d",
}

BOOLEAN_OPTIONS = {"--ignore-profile", "-h", "--help"}


class HeadroomPatchError(RuntimeError):
    pass


def _to_uint32_bytes(value: int) -> bytes:
    if value < 0 or value > UINT32_MAX:
        raise HeadroomPatchError(f"Fraction component out of uint32 range: {value}")
    return value.to_bytes(4, "big")


def _double_to_unsigned_fraction(value: float) -> tuple[int, int]:
    if not math.isfinite(value) or value < 0 or value > UINT32_MAX:
        raise HeadroomPatchError(f"Invalid headroom value: {value}")

    max_d = UINT32_MAX if value <= 1 else math.floor(UINT32_MAX / value)
    denominator = 1
    previous_d = 0
    current_v = value - math.floor(value)

    for _ in range(39):
        numerator_double = denominator * value
        numerator = math.floor(numerator_double + 0.5)
        if abs(numerator_double - numerator) == 0.0:
            return numerator, denominator
        if current_v == 0.0:
            return numerator, denominator
        current_v = 1.0 / current_v
        new_d = previous_d + math.floor(current_v) * denominator
        if new_d > max_d:
            return numerator, denominator
        previous_d = denominator
        denominator = int(new_d)
        current_v -= math.floor(current_v)

    return math.floor(denominator * value + 0.5), denominator


def _parse_headroom_overrides(args: list[str]) -> tuple[list[str], float | None, float | None]:
    stripped: list[str] = []
    base_headroom: float | None = None
    alternate_headroom: float | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        for name in ("--base-headroom", "--alternate-headroom"):
            if arg == name:
                if i + 1 >= len(args):
                    raise HeadroomPatchError(f"{name} requires a value")
                value = float(args[i + 1])
                if name == "--base-headroom":
                    base_headroom = value
                else:
                    alternate_headroom = value
                i += 2
                break
            if arg.startswith(f"{name}="):
                value = float(arg.split("=", 1)[1])
                if name == "--base-headroom":
                    base_headroom = value
                else:
                    alternate_headroom = value
                i += 1
                break
        else:
            stripped.append(arg)
            i += 1
            continue
        continue
    return stripped, base_headroom, alternate_headroom


def _extract_output_path(args: list[str]) -> Path | None:
    if not args or args[0] != "combine":
        return None
    positionals: list[str] = []
    i = 1
    while i < len(args):
        arg = args[i]
        if arg in BOOLEAN_OPTIONS:
            i += 1
            continue
        if arg in OPTIONS_WITH_VALUE:
            i += 2
            continue
        if any(arg.startswith(f"{option}=") for option in OPTIONS_WITH_VALUE if option.startswith("--")):
            i += 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        positionals.append(arg)
        i += 1
    if len(positionals) < 3:
        return None
    return Path(positionals[2])


def _read_current_fractions(output_path: Path) -> dict[str, tuple[int, int]]:
    result = subprocess.run(
        [str(OFFICIAL_TOOL), "printmetadata", str(output_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise HeadroomPatchError(f"Cannot read gain map metadata: {detail}")

    fractions: dict[str, tuple[int, int]] = {}
    for match in FRACTION_RE.finditer(result.stdout):
        key = match.group(1).lower()
        fractions[key] = (int(match.group(2)), int(match.group(3)))
    if "base" not in fractions or "alternate" not in fractions:
        raise HeadroomPatchError("Gain map metadata did not include base/alternate headroom fractions")
    return fractions


def _find_metadata_offset(data: bytes, old_sequence: bytes) -> int:
    candidates: list[int] = []
    start = 0
    while True:
        index = data.find(old_sequence, start)
        if index < 0:
            break
        has_tmap_header = index >= 6 and data[index - 6 : index - 1] == b"\x00\x00\x00\x00\x00"
        if has_tmap_header:
            candidates.append(index)
        start = index + 1

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise HeadroomPatchError(f"Found multiple gain map metadata candidates: {candidates}")

    fallback = []
    start = 0
    while True:
        index = data.find(old_sequence, start)
        if index < 0:
            break
        fallback.append(index)
        start = index + 1
    if len(fallback) == 1:
        return fallback[0]
    if not fallback:
        raise HeadroomPatchError("Could not locate gain map headroom metadata bytes")
    raise HeadroomPatchError(f"Found ambiguous headroom byte sequence: {fallback}")


def _patch_headrooms(output_path: Path, base: float | None, alternate: float | None) -> str:
    current = _read_current_fractions(output_path)
    base_fraction = _double_to_unsigned_fraction(base) if base is not None else current["base"]
    alternate_fraction = (
        _double_to_unsigned_fraction(alternate) if alternate is not None else current["alternate"]
    )

    old_sequence = b"".join(
        _to_uint32_bytes(part)
        for fraction in (current["base"], current["alternate"])
        for part in fraction
    )
    new_sequence = b"".join(
        _to_uint32_bytes(part)
        for fraction in (base_fraction, alternate_fraction)
        for part in fraction
    )

    data = output_path.read_bytes()
    offset = _find_metadata_offset(data, old_sequence)
    patched = data[:offset] + new_sequence + data[offset + len(old_sequence) :]
    output_path.write_bytes(patched)

    verified = _read_current_fractions(output_path)
    if verified["base"] != base_fraction or verified["alternate"] != alternate_fraction:
        raise HeadroomPatchError(
            "Patched gain map metadata verification failed: "
            f"base={verified['base']} alternate={verified['alternate']}"
        )

    return (
        "Overrode gain map headroom metadata: "
        f"base={base_fraction[0]}/{base_fraction[1]}, "
        f"alternate={alternate_fraction[0]}/{alternate_fraction[1]}"
    )


def main() -> int:
    if not OFFICIAL_TOOL.exists():
        print(f"Missing official libavif tool: {OFFICIAL_TOOL}", file=sys.stderr)
        return 1

    try:
        stripped_args, base_headroom, alternate_headroom = _parse_headroom_overrides(sys.argv[1:])
    except Exception as exc:
        print(f"avifgainmaputil_hdr: {exc}", file=sys.stderr)
        return 2

    if stripped_args and stripped_args[0] == "combine" and any(arg in {"-h", "--help"} for arg in stripped_args):
        completed = subprocess.run(
            [str(OFFICIAL_TOOL), *stripped_args],
            capture_output=True,
            text=True,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode == 0:
            print("  --base-headroom BASE-HEADROOM")
            print("                    Override base image HDR headroom metadata in log2 stops.")
            print("  --alternate-headroom ALTERNATE-HEADROOM")
            print("                    Override alternate image HDR headroom metadata in log2 stops.")
        return completed.returncode

    completed = subprocess.run([str(OFFICIAL_TOOL), *stripped_args])
    if completed.returncode != 0:
        return completed.returncode

    if not stripped_args or stripped_args[0] != "combine":
        return 0
    if base_headroom is None and alternate_headroom is None:
        return 0

    output_path = _extract_output_path(stripped_args)
    if output_path is None:
        print("avifgainmaputil_hdr: cannot find combine output path", file=sys.stderr)
        return 2

    try:
        message = _patch_headrooms(output_path, base_headroom, alternate_headroom)
    except Exception as exc:
        print(f"avifgainmaputil_hdr: {exc}", file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
