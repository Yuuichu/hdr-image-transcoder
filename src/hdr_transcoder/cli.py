"""
HDR to multi-format converter CLI orchestration.

Entry point for the hdr2avif command-line interface.
"""
import sys
import re
from pathlib import Path

import numpy as np

from hdr_transcoder.config import (
    ALL_OUTPUT_FORMATS,
    DEFAULT_NAME_PATTERN,
    FIDELITIES,
    FIDELITY_COMPAT,
    FIDELITY_MASTER,
    FORMAT_EXTENSIONS,
    GAINMAP_HEADROOM_MODES,
    GAINMAP_HEADROOM_SOURCE_PEAK,
    INPUT_EXTENSIONS,
    MASTER_FORMAT,
    TIER1_FORMATS,
)
from hdr_transcoder.formats.gainmap import encode_gainmap_avif, encode_gainmap_heic
from hdr_transcoder.formats.decoder import SUPPORTED_FORMATS, decode_to_scrgb, probe_format
from hdr_transcoder.formats import (
    EXTENSION_TO_FORMAT,
    JXL_MODE_LINEAR_SRGB,
    JXL_MODE_REC2020_PQ,
    JXL_MODES,
    OUTPUT_FORMATS,
    encode_output,
)
from hdr_transcoder.processor import prepare_alternate_hdr, prepare_base_sdr, prepare_base_sdr_display_p3
from hdr_transcoder.validation import source_peak_headroom as _source_peak_headroom
from hdr_transcoder.validation import verify_output as _verify_output


OUTPUT_EXTENSIONS = {".avif", *EXTENSION_TO_FORMAT.keys()}
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _same_path(left, right):
    """Return True when two paths refer to the same filesystem target."""
    return Path(left).resolve() == Path(right).resolve()


def _converted_name(path):
    """Return a non-destructive default output path for same-extension output."""
    path = Path(path)
    return path.with_name(f"{path.stem}_converted{path.suffix}")


def _number_token(index, start=1, padding=3):
    number = start + index - 1
    if padding > 0:
        return str(number).zfill(padding)
    return str(number)


def _sanitize_output_stem(stem):
    stem = INVALID_FILENAME_RE.sub("_", stem)
    stem = stem.strip().strip(".")
    return stem


def _apply_name_template(stem, index, args):
    """Apply batch output naming rules to a filename stem."""
    name = stem
    if args.name_find:
        name = name.replace(args.name_find, args.name_replace)

    number = _number_token(index, args.name_start, args.name_padding)
    pattern = args.name_pattern or DEFAULT_NAME_PATTERN
    if pattern != DEFAULT_NAME_PATTERN:
        name = pattern.replace("{name}", name).replace("{n}", number)

    name = f"{args.name_prefix}{name}{args.name_suffix}"
    name = _sanitize_output_stem(name)
    if not name:
        name = f"output_{number}"
    return name


def _output_path_for(input_path, output_dir, out_ext, index, args, use_naming=True):
    stem = input_path.stem
    if use_naming:
        stem = _apply_name_template(stem, index, args)
    out_path = output_dir / f"{stem}{out_ext}"
    if _same_path(input_path, out_path):
        out_path = _converted_name(out_path)
    return out_path


def _print_failure_summary(failed_items):
    if not failed_items:
        return

    print(f"\nConversion failed for {len(failed_items)} file(s):")
    for path, error in failed_items:
        print(f"  - {path}: {error}")


def _infer_output_format(output_path):
    ext = Path(output_path).suffix.lower()
    if ext == ".avif":
        return "gainmap"
    return EXTENSION_TO_FORMAT.get(ext)


def _default_output_format(fidelity):
    if fidelity == FIDELITY_COMPAT:
        return "gainmap"
    return MASTER_FORMAT


def _output_ext_for_format(output_format):
    return FORMAT_EXTENSIONS.get(output_format, ".jxl")


def _resolve_jxl_settings(output_format, fidelity, jxl_mode, lossless):
    if output_format != "jxl":
        return jxl_mode or JXL_MODE_REC2020_PQ, lossless
    if fidelity == FIDELITY_MASTER:
        if jxl_mode is not None and jxl_mode != JXL_MODE_LINEAR_SRGB:
            raise ValueError("Master fidelity requires --jxl-mode linear-srgb")
        return JXL_MODE_LINEAR_SRGB, True
    return jxl_mode or JXL_MODE_REC2020_PQ, lossless


def _enforce_fidelity_policy(output_format, fidelity, allow_non_master, jxl_mode, lossless):
    if fidelity not in FIDELITIES:
        raise ValueError(f"Unknown fidelity mode: {fidelity}")
    if output_format not in ALL_OUTPUT_FORMATS:
        raise ValueError(f"Unknown output format: {output_format}")
    if fidelity != FIDELITY_MASTER:
        return
    is_master_jxl = output_format == "jxl" and jxl_mode == JXL_MODE_LINEAR_SRGB and lossless
    if is_master_jxl:
        return
    if allow_non_master:
        print(
            f"  Warning: {output_format} is not a strict master format; continuing because --allow-non-master was set."
        )
        return
    raise ValueError(
        "Master fidelity only supports lossless linear-srgb JPEG XL. "
        "Use --fidelity display/compat or --allow-non-master for delivery formats."
    )


def _ensure_finite_hdr(pixels, input_path):
    invalid = ~np.isfinite(pixels)
    if invalid.any():
        count = int(np.count_nonzero(invalid))
        raise ValueError(f"Decoded image contains {count} NaN or Infinity sample(s): {input_path}")


def _write_info_json(output_path, output_format, jxl_mode, fidelity, verify_result):
    import json

    from hdr_transcoder.inspector import inspect_image

    info = inspect_image(output_path)
    color = info.get("color") or {}
    gainmap = info.get("gainmap") or {}
    hdr = info.get("hdr") or {}
    payload = {
        "path": str(output_path),
        "format": output_format,
        "jxlMode": jxl_mode,
        "fidelity": fidelity,
        "cicp": {
            "primaries": color.get("primaries"),
            "transfer": color.get("transfer"),
            "matrix": color.get("matrix"),
        },
        "gainmap": {
            "present": gainmap.get("present", False),
            "baseHeadroom": gainmap.get("base_headroom"),
            "alternateHeadroom": gainmap.get("alternate_headroom"),
            "alternateCicp": {
                "primaries": (gainmap.get("alternate_color") or {}).get("primaries"),
                "transfer": (gainmap.get("alternate_color") or {}).get("transfer"),
                "matrix": (gainmap.get("alternate_color") or {}).get("matrix"),
            },
        },
        "peak": {
            "rgbMax": hdr.get("rgb_max"),
            "headroom": hdr.get("peak_headroom"),
        },
        "verify": verify_result,
        "inspector": info,
    }
    info_path = Path(output_path).with_suffix(".info.json")
    info_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return info_path


def convert_single(input_path, output_path, quality=100, speed=0, max_headroom=None,
                   format=None, lossless=False, headroom=2.0,
                   jxl_mode=None, fidelity=FIDELITY_MASTER,
                   allow_non_master=False, verify_fidelity=False,
                   gainmap_headroom_mode=GAINMAP_HEADROOM_SOURCE_PEAK,
                   debug_overlay=False, info_json=False,
                   pq_input=False, heic_rgb_gainmap_only=False,
                   heic_apple_gainmap_only=False):
    """Convert a single HDR image to the specified output format."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if _same_path(input_path, output_path):
        raise ValueError(f"Output would overwrite input: {output_path}")

    output_format = format or _infer_output_format(output_path) or _default_output_format(fidelity)
    jxl_mode, lossless = _resolve_jxl_settings(output_format, fidelity, jxl_mode, lossless)
    _enforce_fidelity_policy(output_format, fidelity, allow_non_master, jxl_mode, lossless)

    fmt = probe_format(str(input_path))
    fmt_name = SUPPORTED_FORMATS.get(fmt, (fmt or "unknown", []))[0]

    print(f"Decoding: {input_path.name} [{fmt_name}]")
    hdr, width, height = decode_to_scrgb(str(input_path), pq_input=pq_input)
    _ensure_finite_hdr(hdr, input_path)
    rgb_max = hdr[..., :3].max()
    print(f"  Resolution: {width}x{height}, HDR peak: {rgb_max:.3f}")

    if output_format in TIER1_FORMATS:
        label = OUTPUT_FORMATS[output_format][0]
        fidelity_label = "master" if output_format == "jxl" and jxl_mode == JXL_MODE_LINEAR_SRGB and lossless else fidelity
        print(f"  Encoding {label} (quality={quality}, fidelity={fidelity_label})...")
        encode_output(
            hdr,
            str(output_path),
            format=output_format,
            quality=quality,
            speed=speed,
            lossless=lossless,
            headroom=headroom,
            jxl_mode=jxl_mode,
        )
    else:
        if gainmap_headroom_mode not in GAINMAP_HEADROOM_MODES:
            raise ValueError(f"Unknown gainmap headroom mode: {gainmap_headroom_mode}")
        print(f"  Computing SDR base (headroom={headroom}) and HDR alternate...")
        sdr = (
            prepare_base_sdr_display_p3(hdr, headroom=headroom)
            if output_format == "gainmap-heic" and heic_apple_gainmap_only
            else prepare_base_sdr(hdr, headroom=headroom)
        )
        alt = prepare_alternate_hdr(hdr)
        base_headroom = None
        alternate_headroom = None
        if gainmap_headroom_mode == GAINMAP_HEADROOM_SOURCE_PEAK:
            base_headroom = 0.0
            alternate_headroom = _source_peak_headroom(hdr)
            headroom_label = f"source-peak alternate_headroom={alternate_headroom:.3f}"
        else:
            headroom_label = "auto metadata"
        if output_format == "gainmap-heic":
            label = "Gainmap HEIC"
            encoder = encode_gainmap_heic
        else:
            label = "Gainmap AVIF"
            encoder = encode_gainmap_avif
        print(
            f"  Encoding {label} "
            f"(quality={quality}, speed={speed}, headroom_mode={headroom_label})..."
        )
        encoder(
            sdr,
            alt,
            str(output_path),
            quality=quality,
            speed=speed,
            max_headroom=max_headroom,
            base_headroom=base_headroom,
            alternate_headroom=alternate_headroom,
            **({
                "rgb_gainmap_only": heic_rgb_gainmap_only,
                "apple_gainmap_only": heic_apple_gainmap_only,
            } if output_format == "gainmap-heic" else {}),
        )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Output: {output_path} ({size_mb:.1f} MB)")
    verify_result = {"requested": bool(verify_fidelity), "ok": None, "error": None}
    if verify_fidelity:
        try:
            verify_result = {"requested": True, **_verify_output(hdr, output_path, output_format, jxl_mode)}
        except Exception as exc:
            verify_result = {"requested": True, "ok": False, "error": str(exc)}
            if info_json:
                info_path = _write_info_json(output_path, output_format, jxl_mode, fidelity, verify_result)
                print(f"  Info JSON: {info_path}")
            raise
    if debug_overlay:
        from hdr_transcoder.inspector import create_debug_overlay

        overlay_path = create_debug_overlay(output_path)
        print(f"  Debug overlay: {overlay_path}")
    if info_json:
        info_path = _write_info_json(output_path, output_format, jxl_mode, fidelity, verify_result)
        print(f"  Info JSON: {info_path}")


def _split_path_args(path_args, output_dir):
    """Keep backward-compatible `input output` while supporting multi-input."""
    paths = [Path(p) for p in path_args]
    if len(paths) == 2 and output_dir is None:
        maybe_output = paths[1]
        if maybe_output.suffix.lower() in OUTPUT_EXTENSIONS:
            return [paths[0]], maybe_output
    return paths, None


def _validate_args(parser, args):
    if not 0 <= args.quality <= 100:
        parser.error("--quality must be between 0 and 100")
    if not 0 <= args.speed <= 10:
        parser.error("--speed must be between 0 and 10")
    if args.max_headroom is not None and args.max_headroom < 0:
        parser.error("--max-headroom must be >= 0")
    if args.headroom <= 0:
        parser.error("--headroom must be > 0")
    if args.fidelity not in FIDELITIES:
        parser.error(f"--fidelity must be one of: {', '.join(sorted(FIDELITIES))}")
    if args.jxl_mode is not None and args.jxl_mode not in JXL_MODES:
        parser.error(f"--jxl-mode must be one of: {', '.join(sorted(JXL_MODES))}")
    if args.gainmap_headroom_mode not in GAINMAP_HEADROOM_MODES:
        parser.error(f"--gainmap-headroom-mode must be one of: {', '.join(sorted(GAINMAP_HEADROOM_MODES))}")
    if args.heic_rgb_gainmap_only and args.format not in (None, "gainmap-heic"):
        parser.error("--heic-rgb-gainmap-only can only be used with --format gainmap-heic")
    if args.heic_apple_gainmap_only and args.format not in (None, "gainmap-heic"):
        parser.error("--heic-apple-gainmap-only can only be used with --format gainmap-heic")
    if args.heic_rgb_gainmap_only and args.heic_apple_gainmap_only:
        parser.error("--heic-rgb-gainmap-only and --heic-apple-gainmap-only are mutually exclusive")
    if args.name_start < 0:
        parser.error("--name-start must be >= 0")
    if args.name_padding < 0:
        parser.error("--name-padding must be >= 0")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Convert HDR images to Gainmap AVIF, JPEG XL, "
            "Ultra HDR JPEG, AVIF HDR, or HEIF HDR"
        )
    )
    parser.add_argument("paths", nargs="*", help="HDR image file(s), directory, or input/output pair")
    parser.add_argument("--output-dir", "-o", help="Output directory (batch mode)")
    parser.add_argument("--quality", "-q", type=int, default=100,
                        help="Quality 0-100 (default: 100)")
    parser.add_argument("--speed", "-s", type=int, default=0,
                        help="Encoder speed 0-10, 0=slowest/best compression efficiency, 10=fastest (default: 0)")
    parser.add_argument("--max-headroom", type=float, default=None,
                        help="Legacy libavif max headroom cap in log2 stops (gainmap AVIF only)")
    parser.add_argument("--gainmap-headroom-mode", choices=sorted(GAINMAP_HEADROOM_MODES),
                        default=GAINMAP_HEADROOM_SOURCE_PEAK,
                        help="Gainmap AVIF metadata mode: source-peak writes source peak headroom; auto keeps libavif metadata")
    parser.add_argument("--headroom", type=float, default=2.0,
                        help="SDR base headroom in stops, default 2.0 (gainmap/Ultra HDR)")
    parser.add_argument("--format", "-f", choices=["gainmap", "gainmap-heic", "jxl", "avif", "ultrahdr", "heif"],
                        help="Output format: gainmap (AVIF), gainmap-heic, jxl, avif (standard HDR), ultrahdr, heif")
    parser.add_argument("--lossless", action="store_true",
                        help="Lossless encoding (JXL only)")
    parser.add_argument("--jxl-mode", choices=sorted(JXL_MODES), default=None,
                        help="JPEG XL HDR mode: rec2020-pq for display HDR, linear-srgb for archive")
    parser.add_argument("--fidelity", choices=sorted(FIDELITIES), default=FIDELITY_MASTER,
                        help="Fidelity policy: master defaults to lossless linear JXL; display/compat allow delivery formats")
    parser.add_argument("--allow-non-master", action="store_true",
                        help="Allow non-master formats while --fidelity master is active")
    parser.add_argument("--verify-fidelity", action="store_true",
                        help="Decode/check the written file for HDR peak/headroom and metadata regressions")
    parser.add_argument("--debug-overlay", action="store_true",
                        help="Create a sidecar SDR PNG with output image debug information overlaid")
    parser.add_argument("--info-json", action="store_true",
                        help="Write a sidecar output.info.json file with inspector and verify metadata")
    parser.add_argument("--pq-input", action="store_true",
                        help="Treat TIFF input as PQ HDR (when CICP metadata is absent)")
    parser.add_argument("--heic-rgb-gainmap-only", action="store_true",
                        help="For gainmap-heic, write only SDR base + ISO RGB gainmap + tmap metadata")
    parser.add_argument("--heic-apple-gainmap-only", action="store_true",
                        help="For gainmap-heic, write only SDR base + Apple HDR gainmap + XMP/EXIF metadata")
    parser.add_argument("--name-prefix", default="",
                        help="Prefix added to batch output filenames")
    parser.add_argument("--name-suffix", default="",
                        help="Suffix added to batch output filenames")
    parser.add_argument("--name-find", default="",
                        help="Text to find in batch output filenames")
    parser.add_argument("--name-replace", default="",
                        help="Replacement text for --name-find")
    parser.add_argument("--name-pattern", default=DEFAULT_NAME_PATTERN,
                        help="Batch rename pattern using {name} and {n} (default: {name})")
    parser.add_argument("--name-start", type=int, default=1,
                        help="Starting number for {n} in batch rename patterns (default: 1)")
    parser.add_argument("--name-padding", type=int, default=3,
                        help="Zero padding width for {n} in batch rename patterns (default: 3)")
    parser.add_argument("--list-formats", action="store_true",
                        help="List supported input formats and exit")
    parser.add_argument("--list-output-formats", action="store_true",
                        help="List supported output formats and exit")

    args = parser.parse_args()
    _validate_args(parser, args)

    if args.list_formats:
        print("Supported input formats:")
        for key, (name, exts) in SUPPORTED_FORMATS.items():
            print(f"  {name}: {', '.join(exts)}")
        return

    if args.list_output_formats:
        print("Output formats:")
        print(f"  {'Format':<20} {'Extensions':<14} {'Fidelity':<14} {'Best for'}")
        print(f"  {'-' * 20} {'-' * 14} {'-' * 14} {'-' * 20}")
        print(f"  {'JPEG XL Master':<20} {'.jxl':<14} {'Master':<14} {'archive / reprocessing'}")
        print(
            f"  {'Gainmap AVIF':<20} {'.avif':<14} "
            f"{'Compat':<14} {'modern web, compression'}"
        )
        for key, (name, exts) in OUTPUT_FORMATS.items():
            if key == "ultrahdr":
                strategy = "Compat"
                best = "max compatibility"
            elif key == "gainmap-heic":
                strategy = "Compat"
                best = "Apple ecosystem, HEIF gainmap"
            elif key == "jxl":
                strategy = "Display"
                best = "HDR display/archive"
            elif key == "heif":
                strategy = "Display"
                best = "Apple ecosystem"
            else:
                strategy = "Display"
                best = "broadest browser"
            print(f"  {name:<20} {', '.join(exts):<14} {strategy:<14} {best}")
        return

    if not args.paths:
        parser.print_help()
        return

    input_paths, output_arg = _split_path_args(args.paths, args.output_dir)

    # Directory mode: single directory path
    if len(input_paths) == 1 and input_paths[0].is_dir():
        input_dir = input_paths[0]
        output_dir = Path(args.output_dir) if args.output_dir else input_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        batch_format = args.format or _default_output_format(args.fidelity)
        out_ext = _output_ext_for_format(batch_format)

        files = sorted(
            f for f in input_dir.iterdir()
            if f.suffix.lower() in INPUT_EXTENSIONS and f.is_file()
        )
        if not files:
            print(f"No supported image files found in {input_dir}")
            sys.exit(1)

        print(f"Found {len(files)} image(s) in {input_dir}")
        failed_items = []
        for i, img_path in enumerate(files, 1):
            out_path = _output_path_for(img_path, output_dir, out_ext, i, args)

            print(f"\n[{i}/{len(files)}] {img_path.name}")
            try:
                convert_single(
                    img_path,
                    out_path,
                    args.quality,
                    args.speed,
                    args.max_headroom,
                    format=batch_format,
                    lossless=args.lossless,
                    headroom=args.headroom,
                    jxl_mode=args.jxl_mode,
                    fidelity=args.fidelity,
                    allow_non_master=args.allow_non_master,
                    verify_fidelity=args.verify_fidelity,
                    gainmap_headroom_mode=args.gainmap_headroom_mode,
                    debug_overlay=args.debug_overlay,
                    info_json=args.info_json,
                    pq_input=args.pq_input,
                    heic_rgb_gainmap_only=args.heic_rgb_gainmap_only,
                    heic_apple_gainmap_only=args.heic_apple_gainmap_only,
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                failed_items.append((img_path, exc))
        if failed_items:
            _print_failure_summary(failed_items)
            sys.exit(1)

    # Multi-file or single-file mode
    else:
        output_dir = Path(args.output_dir) if args.output_dir else input_paths[0].parent

        default_format = args.format or _default_output_format(args.fidelity)
        out_ext = _output_ext_for_format(default_format)

        failed_items = []
        for i, img_path in enumerate(input_paths, 1):
            if not img_path.is_file():
                message = "not a file"
                print(f"Skipping non-file input: {img_path}")
                failed_items.append((img_path, message))
                continue

            if len(input_paths) == 1 and output_arg:
                out_path = output_arg
            else:
                out_path = _output_path_for(img_path, output_dir, out_ext, i, args)

            output_format = args.format
            if output_arg and output_format is None:
                output_format = _infer_output_format(out_path)
            if output_format is None:
                output_format = default_format

            if len(input_paths) > 1:
                print(f"\n[{i}/{len(input_paths)}] {img_path.name}")

            try:
                convert_single(
                    img_path,
                    out_path,
                    args.quality,
                    args.speed,
                    args.max_headroom,
                    format=output_format,
                    lossless=args.lossless,
                    headroom=args.headroom,
                    jxl_mode=args.jxl_mode,
                    fidelity=args.fidelity,
                    allow_non_master=args.allow_non_master,
                    verify_fidelity=args.verify_fidelity,
                    gainmap_headroom_mode=args.gainmap_headroom_mode,
                    debug_overlay=args.debug_overlay,
                    info_json=args.info_json,
                    pq_input=args.pq_input,
                    heic_rgb_gainmap_only=args.heic_rgb_gainmap_only,
                    heic_apple_gainmap_only=args.heic_apple_gainmap_only,
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                failed_items.append((img_path, exc))
        if failed_items:
            _print_failure_summary(failed_items)
            sys.exit(1)


if __name__ == "__main__":
    main()
