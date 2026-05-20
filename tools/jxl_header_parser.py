"""Parse JPEG XL codestream header to inspect color encoding metadata."""
import struct
import sys
from pathlib import Path


def read_varint(data, pos):
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            return result, pos
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            break
    return result, pos


# Enum tables from ISO/IEC 18181-2
TRANSFER_NAMES = {
    0: "BT.709 (SDR)",
    1: "Unknown",
    2: "Unknown",
    3: "BT.601",
    4: "Density",

    5: "Unknown (5)",
    6: "Unknown (6)",
    7: "Unknown (7)",
    8: "Linear",
    9: "Unknown (9)",
    10: "Unknown (10)",
    11: "sRGB",
    12: "Unknown (12)",
    13: "Unknown (13)",
    14: "PQ (ST.2084)",
    15: "Unknown (15)",
    16: "HLG",
    17: "Unknown (17)",
    18: "DCI P3",
}


def parse_header(filepath):
    with open(filepath, "rb") as f:
        data = f.read(512)

    pos = 0
    container = False
    if data[:2] == bytes([0xFF, 0x0A]):
        print("Format: Raw codestream (0xFF0A)")
        pos = 2
    elif len(data) > 12 and data[4:8] == b"JXL ":
        print("Format: ISOBMFF container")
        container = True
        # Skip 12-byte JXL signature box to reach codestream
        # Box: [4B size][4B 'JXL '][4B marker 0x0D0A870A]
        pos = 12
        if data[pos:pos+2] == bytes([0xFF, 0x0A]):
            pos += 2
        else:
            # Might have additional boxes before codestream
            # For now, search for 0xFF0A
            idx = data.find(bytes([0xFF, 0x0A]), 12)
            if idx == -1:
                print("Cannot find codestream in container")
                return
            pos = idx + 2
    else:
        print(f"Unknown magic: {data[:16].hex()}")
        return

    header_size, pos = read_varint(data, pos)
    print(f"Header size field: {header_size}")

    if pos >= len(data):
        return

    flags = data[pos]
    all_default = (flags & 0x01) != 0
    extra_fields = (flags & 0x02) != 0
    print(f"Flags: 0x{flags:02X}, all_default={all_default}, extra_fields={extra_fields}")

    if all_default and not extra_fields:
        print("=> Color encoding: DEFAULT (sRGB transfer, sRGB primaries)")
        print("=> No HDR signaling in header!")
        return

    pos += 1
    orientation = (data[pos] >> 5) & 0x07
    pos += 1  # skip rest of orientation byte

    # Read xsize, ysize (variable-length)
    xsize, pos = read_varint(data, pos)
    ysize, pos = read_varint(data, pos)
    print(f"Dimensions: {xsize}x{ysize}")

    if pos >= len(data):
        return

    # Check if xyb_encoded
    xyb_encoded = (data[pos] & 0x01) != 0
    print(f"XYB encoded: {xyb_encoded}")

    pos += 1

    # Read color encoding
    all_default_ce = (data[pos] & 0x01) != 0
    if all_default_ce:
        print("=> Color encoding: DEFAULT (sRGB transfer, sRGB primaries)")
        print("=> No explicit HDR color encoding in file!")
        return

    pos += 1
    # Not all_default: read color encoding
    # color_encoding is a bundle: mode(1), then depending on mode...
    want_icc = (data[pos] & 0x01) != 0
    if want_icc:
        print("=> Custom ICC profile (skipping)")
        return

    pos += 1
    # Enum color encoding
    ce_byte = data[pos]
    transfer = (ce_byte >> 4) & 0x0F
    primaries = ce_byte & 0x0F
    pos += 1

    transfer_name = TRANSFER_NAMES.get(transfer, f"Unknown({transfer})")
    print(f"Color encoding enum byte: 0x{ce_byte:02X}")
    print(f"  Transfer: {transfer} => {transfer_name}")
    print(f"  Primaries: {primaries}")

    if transfer in (8, 14, 16):
        print("=> HDR transfer function signaled! (Linear/PQ/HLG)")
    else:
        print("=> Transfer is SDR — display will NOT enter HDR mode!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <file.jxl>")
        sys.exit(1)
    parse_header(sys.argv[1])
