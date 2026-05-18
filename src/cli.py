"""
HDR to multi-format converter CLI orchestration.

Entry point for the hdr2avif command-line interface.
"""
import sys
from pathlib import Path

from src.gainmap import encode_gainmap_avif
from src.decoder import SUPPORTED_FORMATS, decode_to_scrgb, probe_format
from src.encoder import EXTENSION_TO_FORMAT, OUTPUT_FORMATS, encode_output
from src.processor import prepare_alternate_hdr, prepare_base_sdr


INPUT_EXTENSIONS = {
    ".jxr", ".wdp", ".hdp", ".jxl", ".exr", ".avif",
    ".heic", ".heif", ".hdr", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
}

TIER1_FORMATS = {"jxl", "ultrahdr", "avif", "heif"}
FORMAT_EXTENSIONS = {
    "jxl": ".jxl",
    "ultrahdr": ".jpg",
    "avif": ".avif",
    "heif": ".heic",
}
OUTPUT_EXTENSIONS = {".avif", *EXTENSION_TO_FORMAT.keys()}


def _same_path(left, right):
    """Return True when two paths refer to the same filesystem target."""
    return Path(left).resolve() == Path(right).resolve()


def _converted_name(path):
    """Return a non-destructive default output path for same-extension output."""
    path = Path(path)
    return path.with_name(f"{path.stem}_converted{path.suffix}")


def convert_single(input_path, output_path, quality=95, speed=6, max_headroom=0,
                   format=None, lossless=False, headroom=2.0):
    """Convert a single HDR image to the specified output format."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if _same_path(input_path, output_path):
        raise ValueError(f"Output would overwrite input: {output_path}")

    fmt = probe_format(str(input_path))
    fmt_name = SUPPORTED_FORMATS.get(fmt, (fmt or "unknown", []))[0]

    print(f"Decoding: {input_path.name} [{fmt_name}]")
    hdr, width, height = decode_to_scrgb(str(input_path))
    rgb_max = hdr[..., :3].max()
    print(f"  Resolution: {width}x{height}, HDR peak: {rgb_max:.3f}")

    if format in TIER1_FORMATS:
        label = OUTPUT_FORMATS[format][0]
        print(f"  Encoding {label} (quality={quality})...")
        encode_output(
            hdr,
            str(output_path),
            format=format,
            quality=quality,
            speed=speed,
            lossless=lossless,
            headroom=headroom,
        )
    else:
        print(f"  Computing SDR base (headroom={headroom}) and HDR alternate...")
        sdr = prepare_base_sdr(hdr, headroom=headroom)
        alt = prepare_alternate_hdr(hdr)
        print(
            f"  Encoding Gainmap AVIF "
            f"(quality={quality}, max_headroom={max_headroom})..."
        )
        encode_gainmap_avif(
            sdr,
            alt,
            str(output_path),
            quality=quality,
            speed=speed,
            max_headroom=max_headroom,
        )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Output: {output_path} ({size_mb:.1f} MB)")


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
    if args.max_headroom < 0:
        parser.error("--max-headroom must be >= 0")
    if args.headroom <= 0:
        parser.error("--headroom must be > 0")


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
    parser.add_argument("--quality", "-q", type=int, default=95,
                        help="Quality 0-100 (default: 95)")
    parser.add_argument("--speed", "-s", type=int, default=6,
                        help="Encoder speed 0-10 (default: 6)")
    parser.add_argument("--max-headroom", type=float, default=0,
                        help="Max gain headroom log2, 0=auto (gainmap AVIF only)")
    parser.add_argument("--headroom", type=float, default=2.0,
                        help="SDR base headroom in stops, default 2.0 (gainmap/Ultra HDR)")
    parser.add_argument("--format", "-f", choices=["jxl", "avif", "ultrahdr", "heif"],
                        help="Output format: jxl, avif (standard HDR), ultrahdr, heif")
    parser.add_argument("--lossless", action="store_true",
                        help="Lossless encoding (JXL only)")
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
        print(f"  {'Format':<20} {'Extensions':<14} {'HDR strategy':<20} {'Best for'}")
        print(f"  {'-' * 20} {'-' * 14} {'-' * 20} {'-' * 20}")
        print(
            f"  {'Gainmap AVIF':<20} {'.avif':<14} "
            f"{'gainmap (adaptive)':<20} {'modern web, compression'}"
        )
        for key, (name, exts) in OUTPUT_FORMATS.items():
            if key == "ultrahdr":
                strategy = "gainmap (adaptive)"
                best = "max compatibility"
            elif key == "jxl":
                strategy = "native float32"
                best = "compression/lossless"
            elif key == "heif":
                strategy = "10-bit PQ HEVC"
                best = "Apple ecosystem"
            else:
                strategy = "10-bit PQ"
                best = "broadest browser"
            print(f"  {name:<20} {', '.join(exts):<14} {strategy:<20} {best}")
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

        if args.format in TIER1_FORMATS:
            out_ext = FORMAT_EXTENSIONS[args.format]
        else:
            out_ext = ".avif"

        files = sorted(
            f for f in input_dir.iterdir()
            if f.suffix.lower() in INPUT_EXTENSIONS and f.is_file()
        )
        if not files:
            print(f"No supported image files found in {input_dir}")
            sys.exit(1)

        print(f"Found {len(files)} image(s) in {input_dir}")
        failures = 0
        for i, img_path in enumerate(files, 1):
            out_path = output_dir / f"{img_path.stem}{out_ext}"
            if _same_path(img_path, out_path):
                out_path = _converted_name(out_path)

            print(f"\n[{i}/{len(files)}] {img_path.name}")
            try:
                convert_single(
                    img_path,
                    out_path,
                    args.quality,
                    args.speed,
                    args.max_headroom,
                    format=args.format,
                    lossless=args.lossless,
                    headroom=args.headroom,
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                failures += 1
        if failures:
            sys.exit(1)

    # Multi-file or single-file mode
    else:
        output_dir = Path(args.output_dir) if args.output_dir else input_paths[0].parent

        if args.format in TIER1_FORMATS:
            out_ext = FORMAT_EXTENSIONS[args.format]
        else:
            out_ext = ".avif"

        failures = 0
        for i, img_path in enumerate(input_paths, 1):
            if not img_path.is_file():
                print(f"Skipping non-file input: {img_path}")
                failures += 1
                continue

            if len(input_paths) == 1 and output_arg:
                out_path = output_arg
            else:
                out_path = output_dir / f"{img_path.stem}{out_ext}"

            if _same_path(img_path, out_path):
                out_path = _converted_name(out_path)

            output_format = args.format
            if output_arg and output_format is None:
                output_format = EXTENSION_TO_FORMAT.get(out_path.suffix.lower())

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
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                failures += 1
        if failures:
            sys.exit(1)


if __name__ == "__main__":
    main()
