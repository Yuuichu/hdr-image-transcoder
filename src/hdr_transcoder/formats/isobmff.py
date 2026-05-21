"""ISOBMFF box read/write primitives for gainmap HEIC container assembly."""
from __future__ import annotations

import math
import struct
import tempfile
from pathlib import Path

import numpy as np


UINT32_MAX = 0xFFFFFFFF


def build_box(box_type: str, data: bytes = b"") -> bytes:
    """Build a basic ISOBMFF box: [size(u32)][type(4cc)][data...]."""
    size = 8 + len(data)
    return struct.pack(">I", size) + box_type.encode("ascii").ljust(4, b"\x00")[:4] + data


def build_full_box(box_type: str, version: int, flags: int, data: bytes = b"") -> bytes:
    """Build a full ISOBMFF box with version/flags header."""
    header = struct.pack(">I", 12 + len(data)) + box_type.encode("ascii").ljust(4, b"\x00")[:4]
    header += struct.pack(">B", version) + struct.pack(">I", flags)[1:]
    return header + data


def build_ftyp(major_brand: str = "heic", compatible_brands: list[str] | None = None) -> bytes:
    """Build ftyp box for HEIC."""
    brands = compatible_brands or ["mif1", "heic"]
    data = major_brand.encode("ascii").ljust(4, b"\x00")[:4]
    data += struct.pack(">I", 0)
    for brand in brands:
        data += brand.encode("ascii").ljust(4, b"\x00")[:4]
    return build_box("ftyp", data)


def _uint_to_fraction(value: float) -> tuple[int, int]:
    """Convert a float to a uint32 numerator/denominator pair."""
    if not math.isfinite(value) or value < 0 or value > UINT32_MAX:
        raise ValueError(f"Invalid fraction value: {value}")
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


def build_hvcC(config_bytes: bytes) -> bytes:
    """Build hvcC property box from HEVC decoder configuration record."""
    return build_box("hvcC", config_bytes)


def build_ispe(width: int, height: int) -> bytes:
    """Build ispe (Image Spatial Extents) property box."""
    data = struct.pack(">II", width, height)
    return build_full_box("ispe", 0, 0, data)


def build_pixi(channels: list[int]) -> bytes:
    """Build pixi (Pixel Information) property box."""
    data = struct.pack(">B", len(channels)) + bytes(channels)
    return build_full_box("pixi", 0, 0, data)


def build_colr_nclx(
    color_primaries: int,
    transfer_characteristics: int,
    matrix_coefficients: int,
    full_range_flag: int = 1,
) -> bytes:
    """Build colr property box with nclx color type."""
    data = b"nclx" + struct.pack(
        ">HHHB",
        color_primaries,
        transfer_characteristics,
        matrix_coefficients,
        (full_range_flag & 1) << 7,
    )
    return build_box("colr", data)


def build_auxc(aux_type: str) -> bytes:
    """Build auxC property with a null-terminated auxiliary image type."""
    return build_full_box("auxC", 0, 0, aux_type.encode("ascii") + b"\x00")


def build_tmap(base_headroom: float, alternate_headroom: float) -> bytes:
    """Build tmap (Tone Mapping Info) property box for gainmap metadata.

    ISO 21496-1 / ISO 23001-19 tmap box: base + alternate headroom as unsigned fractions.
    """
    base_num, base_den = _uint_to_fraction(base_headroom)
    alt_num, alt_den = _uint_to_fraction(alternate_headroom)
    data = struct.pack(">IIII", base_num, base_den, alt_num, alt_den)
    return build_full_box("tmap", 0, 0, data)


def build_iloc(items: list[dict], offset_size: int = 4, length_size: int = 4) -> bytes:
    """Build iloc (Item Location) box.

    Each item: {id, construction_method, data_ref_idx, base_offset, extents: [{offset, length}]}
    """
    version = 0
    flags = 0
    base_offset_size = offset_size
    header = struct.pack(">BB", (offset_size << 4) | length_size, (base_offset_size << 4))
    item_count = len(items)
    if item_count < 0xFFFF:
        data = header + struct.pack(">H", item_count)
    else:
        data = header + struct.pack(">I", item_count)

    for item in items:
        item_id = item["id"]
        if item_count < 0xFFFF:
            data += struct.pack(">H", item_id)
        else:
            data += struct.pack(">I", item_id)
        flags_data = (item.get("construction_method", 0) & 0xF) << 4
        flags_data |= (item.get("data_ref_idx", 0) & 0xF)
        data += struct.pack(">H", flags_data)
        base_offset = item.get("base_offset", 0)
        data += struct.pack(">I", base_offset)[4 - offset_size:]
        extents = item.get("extents", [])
        data += struct.pack(">H", len(extents))
        for ext in extents:
            ext_offset = ext.get("offset", 0)
            ext_length = ext.get("length", 0)
            data += struct.pack(">I", ext_offset)[4 - offset_size:]
            data += struct.pack(">I", ext_length)[4 - length_size:]

    return build_full_box("iloc", version, flags, data)


def build_iinf(items: list[dict]) -> bytes:
    """Build iinf (Item Information) box.

    Each item: {id, type, name, auxC_type: optional str}
    """
    version = 0
    count = len(items)
    data = struct.pack(">H", count) if count < 0xFFFF else struct.pack(">I", count)
    for item in items:
        infe_data = struct.pack(">H", item["id"])
        item_protection = 0
        infe_data += struct.pack(">H", item_protection)
        item_type = item.get("type", "hvc1")
        infe_data += item_type.encode("ascii").ljust(4, b"\x00")[:4]
        name = item.get("name", "")
        name_bytes = name.encode("utf-8") + b"\x00"
        infe_data += name_bytes
        if item_type == "mime":
            content_type = item.get("content_type", "application/octet-stream")
            infe_data += content_type.encode("ascii") + b"\x00"
            content_encoding = item.get("content_encoding")
            if content_encoding:
                infe_data += content_encoding.encode("ascii") + b"\x00"

        infe_box = build_full_box("infe", 2, item.get("flags", 0), infe_data)

        data += infe_box
    return build_full_box("iinf", version, 0, data)


def build_ipco(properties: list[dict]) -> bytes:
    """Build ipco (Item Property Container) box.

    Each property: {type: str, data: bytes}
    Types: hvcC, ispe, pixi, colr, tmap, pasp, auxC
    """
    data = b""
    for prop in properties:
        prop_type = prop["type"]
        prop_data = prop.get("data", b"")
        if prop_type == "hvcC":
            box = build_hvcC(prop_data)
        elif prop_type == "ispe":
            box = build_ispe(prop["width"], prop["height"])
        elif prop_type == "pixi":
            box = build_pixi(prop["bits_per_channel"])
        elif prop_type == "colr":
            box = build_colr_nclx(
                prop.get("primaries", 1),
                prop.get("transfer", 13),
                prop.get("matrix", 1),
                prop.get("full_range", 1),
            )
        elif prop_type == "auxC":
            box = build_auxc(prop["aux_type"])
        elif prop_type == "tmap":
            box = build_tmap(prop.get("base_headroom", 0.0), prop.get("alternate_headroom", 0.0))
        elif prop_type == "pasp":
            box = build_box("pasp", struct.pack(">II", 1, 1))
        else:
            box = build_box(prop_type, prop_data)
        data += box
    return build_box("ipco", data)


def build_ipma(associations: dict[int, list[tuple[int, bool]]]) -> bytes:
    """Build ipma (Item Property Association) box.

    associations: {item_id: [(property_index, essential), ...]}
    """
    version = 0
    flags = 0
    entry_count = len(associations)
    data = struct.pack(">I", entry_count)
    for item_id, prop_entries in associations.items():
        data += struct.pack(">H", item_id)
        data += struct.pack(">B", len(prop_entries))
        for idx, essential in prop_entries:
            essential_bit = 0x80 if essential else 0x00
            data += struct.pack(">B", (idx & 0x7F) | essential_bit)
    return build_full_box("ipma", version, flags, data)


def build_iref(references: list[dict]) -> bytes:
    """Build iref (Item Reference) box.

    Each reference: {type, from, to: [item_id, ...]}.
    """
    data = b""
    for ref in references:
        ref_data = struct.pack(">H", ref["from"])
        to_items = ref.get("to", [])
        ref_data += struct.pack(">H", len(to_items))
        for item_id in to_items:
            ref_data += struct.pack(">H", item_id)
        data += build_box(ref["type"], ref_data)
    return build_full_box("iref", 0, 0, data)


def build_meta(
    primary_item_id: int,
    iloc_data: bytes,
    iinf_data: bytes,
    iprp_data: bytes,
    iref_data: bytes = b"",
) -> bytes:
    """Build meta box containing hdlr, pitm, iloc, iinf, iprp."""
    hdlr_data = b"\x00\x00\x00\x00" + b"pict" + b"\x00" * 12
    hdlr = build_full_box("hdlr", 0, 0, hdlr_data)
    pitm = build_full_box("pitm", 0, 0, struct.pack(">H", primary_item_id))
    content = hdlr + pitm + iloc_data + iinf_data + iref_data + iprp_data
    return build_full_box("meta", 0, 0, content)


def _parse_boxes(data: bytes, offset: int = 0) -> list[tuple[str, int, int, bytes]]:
    """Parse top-level boxes from ISOBMFF data.

    Returns list of (box_type, offset, size, box_data_including_header).
    """
    boxes = []
    pos = offset
    data_len = len(data)
    while pos + 8 <= data_len:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8].decode("ascii", errors="replace")
        if size == 0:
            size = data_len - pos
        if size < 8 or pos + size > data_len:
            break
        boxes.append((box_type, pos, size, data[pos:pos + size]))
        pos += size
    return boxes


def _find_box(boxes: list[tuple[str, int, int, bytes]], target_type: str) -> tuple[str, int, int, bytes] | None:
    for box in boxes:
        if box[0] == target_type:
            return box
    return None


def _extract_box_payload(box_data: bytes) -> bytes:
    """Extract payload from a box, skipping size+type header (and version/flags for full boxes)."""
    box_type = box_data[4:8].decode("ascii", errors="replace")
    if box_type in ("meta", "hdlr", "pitm", "iloc", "iinf", "iref", "ipma", "auxC", "tmap"):
        return box_data[12:]
    return box_data[8:]


def _read_source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def _read_ipco_boxes(meta_boxes: list[tuple[str, int, int, bytes]]) -> list[tuple[str, int, int, bytes]] | None:
    iprp_box = _find_box(meta_boxes, "iprp")
    if iprp_box is None:
        return None
    iprp_boxes = _parse_boxes(_extract_box_payload(iprp_box[3]))

    ipco_box = _find_box(iprp_boxes, "ipco")
    if ipco_box is None:
        return None
    return _parse_boxes(_extract_box_payload(ipco_box[3]))


def _read_ipma_properties(meta_boxes: list[tuple[str, int, int, bytes]]) -> dict[int, list[tuple[int, bool]]]:
    iprp_box = _find_box(meta_boxes, "iprp")
    if iprp_box is None:
        return {}
    iprp_boxes = _parse_boxes(_extract_box_payload(iprp_box[3]))

    ipma_box = _find_box(iprp_boxes, "ipma")
    if ipma_box is None:
        return {}
    payload = _extract_box_payload(ipma_box[3])
    if len(payload) < 4:
        return {}

    entry_count = struct.unpack(">I", payload[:4])[0]
    pos = 4
    item_props: dict[int, list[tuple[int, bool]]] = {}
    for _ in range(entry_count):
        if pos + 3 > len(payload):
            break
        item_id = struct.unpack(">H", payload[pos:pos + 2])[0]
        pos += 2
        assoc_count = payload[pos]
        pos += 1
        props = []
        for _ in range(assoc_count):
            if pos >= len(payload):
                break
            raw_idx = payload[pos]
            pos += 1
            props.append((raw_idx & 0x7F, bool(raw_idx & 0x80)))
        item_props[item_id] = props
    return item_props


def _read_iloc_extents(meta_boxes: list[tuple[str, int, int, bytes]]) -> dict[int, list[tuple[int, int]]]:
    iloc_box = _find_box(meta_boxes, "iloc")
    if iloc_box is None:
        return {}
    version = iloc_box[3][8]
    payload = _extract_box_payload(iloc_box[3])
    if len(payload) < 4:
        return {}

    offset_size = (payload[0] >> 4) & 0xF
    length_size = payload[0] & 0xF
    base_offset_size = (payload[1] >> 4) & 0xF

    if version < 2:
        item_count = struct.unpack(">H", payload[2:4])[0]
        pos = 4
    else:
        if len(payload) < 6:
            return {}
        item_count = struct.unpack(">I", payload[2:6])[0]
        pos = 6

    item_extents: dict[int, list[tuple[int, int]]] = {}
    for _ in range(item_count):
        item_id_size = 2 if version < 2 else 4
        if pos + item_id_size + 2 > len(payload):
            break
        item_id = int.from_bytes(payload[pos:pos + item_id_size], "big")
        pos += item_id_size
        pos += 2
        if pos + base_offset_size + 2 > len(payload):
            break
        base_offset = int.from_bytes(payload[pos:pos + base_offset_size], "big") if base_offset_size else 0
        pos += base_offset_size
        extent_count = struct.unpack(">H", payload[pos:pos + 2])[0]
        pos += 2

        extents = []
        for _ in range(extent_count):
            if pos + offset_size + length_size > len(payload):
                break
            extent_offset = int.from_bytes(payload[pos:pos + offset_size], "big") if offset_size else 0
            pos += offset_size
            extent_length = int.from_bytes(payload[pos:pos + length_size], "big") if length_size else 0
            pos += length_size
            extents.append((base_offset + extent_offset, extent_length))
        item_extents[item_id] = extents
    return item_extents


def read_heic_container(source: bytes | bytearray | memoryview | str | Path) -> dict | None:
    """Read reusable HEIC ISOBMFF state used by gainmap decoding and inspection."""
    data = _read_source_bytes(source)
    top_boxes = _parse_boxes(data)
    meta_box = _find_box(top_boxes, "meta")
    if meta_box is None:
        return None

    meta_boxes = _parse_boxes(_extract_box_payload(meta_box[3]))
    ipco_boxes = _read_ipco_boxes(meta_boxes)
    if ipco_boxes is None:
        return None

    return {
        "data": data,
        "top_boxes": top_boxes,
        "meta_boxes": meta_boxes,
        "ipco_boxes": ipco_boxes,
        "item_properties": _read_ipma_properties(meta_boxes),
        "item_extents": _read_iloc_extents(meta_boxes),
    }


def find_item_property(container: dict, item_id: int, box_type: str) -> bytes | None:
    """Return an item's associated property payload by box type."""
    ipco_boxes = container.get("ipco_boxes") or []
    item_props = container.get("item_properties") or {}
    for prop_index, _essential in item_props.get(item_id, []):
        prop_zero = prop_index - 1
        if 0 <= prop_zero < len(ipco_boxes) and ipco_boxes[prop_zero][0] == box_type:
            return _extract_box_payload(ipco_boxes[prop_zero][3])
    return None


def get_item_dimensions(container: dict, item_id: int) -> tuple[int | None, int | None]:
    payload = find_item_property(container, item_id, "ispe")
    if payload is None or len(payload) < 12:
        return None, None
    width = struct.unpack(">I", payload[4:8])[0]
    height = struct.unpack(">I", payload[8:12])[0]
    return width, height


def get_item_bitdepth(container: dict, item_id: int) -> list[int]:
    payload = find_item_property(container, item_id, "pixi")
    if payload is None or len(payload) < 5:
        return [8, 8, 8]
    channel_count = payload[4]
    return list(payload[5:5 + channel_count])


def get_item_colr(container: dict, item_id: int) -> tuple[int, int, int]:
    payload = find_item_property(container, item_id, "colr")
    if payload is None or len(payload) < 4:
        return 1, 13, 1
    if payload[:4] == b"nclx" and len(payload) >= 11:
        primaries, transfer, matrix = struct.unpack(">HHH", payload[4:10])
        return primaries, transfer, matrix
    return 1, 13, 1


def read_heic_gainmap_metadata_from_container(container: dict) -> dict | None:
    """Read gainmap tmap headroom metadata from a parsed HEIC container."""
    for box_type, _, _, box_data in container.get("ipco_boxes") or []:
        if box_type != "tmap":
            continue
        payload = _extract_box_payload(box_data)
        if len(payload) < 16:
            return None
        base_num, base_den, alt_num, alt_den = struct.unpack(">IIII", payload[:16])
        base_value = base_num / base_den if base_den else 0.0
        alternate_value = alt_num / alt_den if alt_den else 0.0
        return {
            "raw": (
                f"Base headroom:     {base_value:.6f} (as fraction: {base_num}/{base_den})\n"
                f"Alternate headroom: {alternate_value:.6f} (as fraction: {alt_num}/{alt_den})"
            ),
            "baseHeadroom": base_value,
            "alternateHeadroom": alternate_value,
            "base_headroom": base_value,
            "alternate_headroom": alternate_value,
            "base_headroom_fraction": {"numerator": base_num, "denominator": base_den},
            "alternate_headroom_fraction": {"numerator": alt_num, "denominator": alt_den},
        }
    return None


def read_heic_gainmap_metadata(source: bytes | bytearray | memoryview | str | Path) -> dict | None:
    container = read_heic_container(source)
    if container is None:
        return None
    return read_heic_gainmap_metadata_from_container(container)


def read_heic_gainmap_alternate_cicp_from_container(container: dict) -> dict | None:
    """Read alternate-image CICP from item 2, falling back to any PQ nclx color property."""
    primaries, transfer, matrix = get_item_colr(container, 2)
    if transfer == 16:
        return {"primaries": primaries, "transfer": transfer, "matrix": matrix}

    for box_type, _, _, box_data in container.get("ipco_boxes") or []:
        if box_type != "colr":
            continue
        payload = _extract_box_payload(box_data)
        if payload[:4] == b"nclx" and len(payload) >= 10:
            primaries, transfer, matrix = struct.unpack(">HHH", payload[4:10])
            if transfer == 16:
                return {"primaries": primaries, "transfer": transfer, "matrix": matrix}
    return None


def read_heic_gainmap_alternate_cicp(source: bytes | bytearray | memoryview | str | Path) -> dict | None:
    container = read_heic_container(source)
    if container is None:
        return None
    return read_heic_gainmap_alternate_cicp_from_container(container)


def _parse_iso21496_tmap_metadata(blob: bytes) -> dict | None:
    """Parse ISO 21496-1 binary gainmap metadata blob.

    Returns per-channel parameters or None if parsing fails.
    """
    if len(blob) < 5:
        return None
    min_version = blob[0]
    writer_version = blob[1]
    flags = blob[2]
    bo_enc = struct.unpack("<b", blob[3:4])[0]
    ao_enc = struct.unpack("<b", blob[4:5])[0]

    is_multi_channel = bool(flags & 1)
    use_base_color_space = bool(flags & 2)
    use_common_denom = bool(flags & 8)

    base_offset = bo_enc / 64.0
    alternate_offset = ao_enc / 64.0

    channels = 3 if is_multi_channel else 1
    result = {
        "minVersion": min_version,
        "writerVersion": writer_version,
        "isMultiChannel": is_multi_channel,
        "useBaseColorSpace": use_base_color_space,
        "commonDenominatorMode": use_common_denom,
        "baseOffset": base_offset,
        "alternateOffset": alternate_offset,
    }

    expected_size = 5
    if use_common_denom:
        param_names = ["gainMapMin", "gainMapMax", "gamma", "baseOffset", "alternateOffset"]
        expected_size = 5 + channels * len(param_names) * 4 + len(param_names) * 4
        if len(blob) < expected_size:
            return None
        pos = 5
        all_numerators = []
        for _ in range(channels * len(param_names)):
            all_numerators.append(struct.unpack("<i", blob[pos:pos + 4])[0])
            pos += 4
        denoms = []
        for _ in range(len(param_names)):
            denom = struct.unpack("<I", blob[pos:pos + 4])[0]
            pos += 4
            if denom == 0:
                return None
            denoms.append(denom)
        for p_idx, name in enumerate(param_names):
            numerators = all_numerators[p_idx * channels:(p_idx + 1) * channels]
            result[name] = [n / denoms[p_idx] for n in numerators]
    return result


def read_heic_iso21496_metadata(container: dict) -> dict | None:
    """Read ISO 21496-1 binary gainmap metadata from a HEIC container.

    Reads from the tmap item (item 4 in our container).
    """
    item_extents = container.get("item_extents") or {}
    data = container.get("data")
    if data is None:
        return None

    tmap_item_id = None
    for item_id in item_extents:
        aux_type = find_item_property(container, item_id, "auxC")
        if aux_type and b"urn:iso:std:iso:ts:21496:-1:aux:gainmap" in aux_type:
            for ref_type, from_id, to_ids in _read_iref(container):
                if ref_type == "dimg" and item_id in to_ids:
                    tmap_item_id = from_id
                    break
            if tmap_item_id is not None:
                break

    if tmap_item_id is None:
        for item_id in item_extents:
            refs = _read_iref(container)
            for ref_type, from_id, to_ids in refs:
                if ref_type == "dimg" and ((1 in to_ids and 3 in to_ids) or (2 in to_ids and 3 in to_ids)):
                    tmap_item_id = from_id
                    break
            if tmap_item_id is not None:
                break

    if tmap_item_id is None or tmap_item_id not in item_extents:
        return None

    tmap_offset, tmap_length = item_extents[tmap_item_id][0]
    blob = data[tmap_offset:tmap_offset + tmap_length]
    return _parse_iso21496_tmap_metadata(blob)


def _read_iref(container: dict) -> list[tuple[str, int, list[int]]]:
    """Extract iref references from a parsed HEIC container."""
    meta_boxes = container.get("meta_boxes") or []
    iref_box = _find_box(meta_boxes, "iref")
    if iref_box is None:
        return []

    ref_data = _extract_box_payload(iref_box[3])
    refs = []
    for ref_type, _, _, ref_box in _parse_boxes(ref_data):
        payload = _extract_box_payload(ref_box)
        if len(payload) < 4:
            continue
        from_id = struct.unpack(">H", payload[:2])[0]
        count = struct.unpack(">H", payload[2:4])[0]
        to_ids = [
            struct.unpack(">H", payload[4 + i * 2:6 + i * 2])[0]
            for i in range(count)
        ]
        refs.append((ref_type, from_id, to_ids))
    return refs


def encode_and_extract_hevc(
    pixels: np.ndarray,
    color_primaries: int = 1,
    transfer_characteristics: int = 13,
    matrix_coefficients: int = 1,
    full_range_flag: int = 1,
    quality: int = 100,
    chroma: str = "444",
) -> tuple[bytes, bytes, int, int, list[int]]:
    """Encode pixels via pillow_heif, extract hvcC config and HEVC bitstream.

    Returns (hvcC_bytes, bitstream_bytes, width, height, bits_per_channel).
    """
    import pillow_heif

    height, width = pixels.shape[:2]
    if pixels.ndim == 2 and pixels.dtype == np.uint8:
        mode = "L"
    elif pixels.dtype == np.uint8:
        mode = "RGB"
    elif pixels.dtype == np.uint16:
        mode = "RGB;16"
    else:
        raise ValueError(f"Unsupported pixel dtype: {pixels.dtype}")

    heif_file = pillow_heif.HeifFile()
    heif_file.add_frombytes(mode, (width, height), pixels.tobytes())
    with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
        temp_path = f.name
    try:
        heif_file.save(
            temp_path,
            quality=quality,
            chroma=chroma,
            save_nclx_profile=True,
            color_primaries=color_primaries,
            transfer_characteristics=transfer_characteristics,
            matrix_coefficients=matrix_coefficients,
            full_range_flag=full_range_flag,
        )
        data = Path(temp_path).read_bytes()
    finally:
        Path(temp_path).unlink(missing_ok=True)

    top_boxes = _parse_boxes(data)
    meta_box = _find_box(top_boxes, "meta")
    if meta_box is None:
        raise ValueError("HEIC missing meta box")
    meta_data = meta_box[3][12:]
    meta_boxes = _parse_boxes(meta_data)

    iprp_box = _find_box(meta_boxes, "iprp")
    if iprp_box is None:
        raise ValueError("HEIC missing iprp box")
    iprp_data = _extract_box_payload(iprp_box[3])
    iprp_boxes = _parse_boxes(iprp_data)

    ipco_box = _find_box(iprp_boxes, "ipco")
    if ipco_box is None:
        raise ValueError("HEIC missing ipco box")
    ipco_data = _extract_box_payload(ipco_box[3])
    ipco_boxes = _parse_boxes(ipco_data)

    hvcC_box = _find_box(ipco_boxes, "hvcC")
    if hvcC_box is None:
        raise ValueError("HEIC missing hvcC box")
    hvcC_bytes = _extract_box_payload(hvcC_box[3])

    iloc_box = _find_box(meta_boxes, "iloc")
    if iloc_box is None:
        raise ValueError("HEIC missing iloc box")
    iloc_version = iloc_box[3][8]
    iloc_data = _extract_box_payload(iloc_box[3])

    offset_size = (iloc_data[0] >> 4) & 0xF
    length_size = iloc_data[0] & 0xF
    base_offset_size = (iloc_data[1] >> 4) & 0xF
    # index_size/reserved = iloc_data[1] & 0xF

    if iloc_version < 2:
        item_count = struct.unpack(">H", iloc_data[2:4])[0]
        pos = 4
    else:
        item_count = struct.unpack(">I", iloc_data[2:6])[0]
        pos = 6

    bitstreams: list[bytes] = []
    for _ in range(item_count):
        if iloc_version < 2:
            _item_id = struct.unpack(">H", iloc_data[pos:pos + 2])[0]
            pos += 2
        else:
            _item_id = struct.unpack(">I", iloc_data[pos:pos + 4])[0]
            pos += 4
        if iloc_version in (1, 2):
            _construction_method = (iloc_data[pos] >> 4) & 0xF
            _data_ref_index = struct.unpack(">H", iloc_data[pos:pos + 2])[0] & 0x0FFF
            pos += 2
        else:
            _data_ref_index = struct.unpack(">H", iloc_data[pos:pos + 2])[0]
            pos += 2
        if base_offset_size:
            _base_offset = int.from_bytes(iloc_data[pos:pos + base_offset_size], "big")
            pos += base_offset_size
        extent_count = struct.unpack(">H", iloc_data[pos:pos + 2])[0]
        pos += 2
        for _ in range(extent_count):
            if offset_size:
                ext_offset = int.from_bytes(iloc_data[pos:pos + offset_size], "big")
                pos += offset_size
            else:
                ext_offset = 0
            if length_size:
                ext_length = int.from_bytes(iloc_data[pos:pos + length_size], "big")
                pos += length_size
            else:
                ext_length = 0

            mdat_box = _find_box(top_boxes, "mdat")
            if mdat_box is None:
                raise ValueError("HEIC missing mdat box")
            mdat_offset = mdat_box[1]
            mdat_payload_start = 8
            bitstreams.append(data[mdat_offset + mdat_payload_start + ext_offset:
                                   mdat_offset + mdat_payload_start + ext_offset + ext_length])

    if not bitstreams:
        raise ValueError("No HEVC bitstreams extracted from HEIC")

    pixi_box = _find_box(ipco_boxes, "pixi")
    if pixi_box is not None:
        pixi_payload = _extract_box_payload(pixi_box[3])
        if len(pixi_payload) >= 5:
            channel_count = pixi_payload[4]
            bits_per_channel = list(pixi_payload[5:5 + channel_count])
        else:
            bits_per_channel = [8, 8, 8] if pixels.ndim == 3 else [8]
    else:
        bits_per_channel = [8, 8, 8] if pixels.ndim == 3 else [8]

    return hvcC_bytes, bitstreams[0], width, height, bits_per_channel


def build_minimal_heic(
    hvcC_bytes: bytes,
    bitstream: bytes,
    width: int,
    height: int,
    primaries: int = 1,
    transfer: int = 13,
    matrix: int = 1,
    bits_per_channel: list[int] | None = None,
) -> bytes:
    """Build a minimal single-image HEIC for decoding with pillow_heif."""
    if bits_per_channel is None:
        bits_per_channel = [8, 8, 8]

    ipco = build_ipco([
        {"type": "hvcC", "data": hvcC_bytes},
        {"type": "ispe", "width": width, "height": height},
        {"type": "pixi", "bits_per_channel": bits_per_channel},
        {"type": "colr", "primaries": primaries, "transfer": transfer, "matrix": matrix, "full_range": 1},
    ])
    ipma = build_ipma({1: [(1, True), (2, False), (3, False), (4, False)]})
    iprp = build_box("iprp", ipco + ipma)

    iinf = build_iinf([{"id": 1, "type": "hvc1", "name": "Image"}])
    ftyp = build_ftyp("heic", ["mif1", "heic"])

    iloc_placeholder = build_iloc([
        {"id": 1, "extents": [{"offset": 0, "length": len(bitstream)}]}
    ])
    meta_placeholder = build_meta(1, iloc_placeholder, iinf, iprp)
    mdat_payload_start = len(ftyp) + len(meta_placeholder) + 8

    iloc = build_iloc([
        {"id": 1, "extents": [{"offset": mdat_payload_start, "length": len(bitstream)}]}
    ])
    meta = build_meta(1, iloc, iinf, iprp)
    mdat = build_box("mdat", bitstream)

    return ftyp + meta + mdat


def _rational64s(value: float, denominator: int = 1_000_000) -> tuple[int, int]:
    """Convert a finite float to a signed rational pair for EXIF/MakerApple."""
    if not math.isfinite(value):
        value = 0.0
    numerator = int(round(value * denominator))
    return numerator, denominator


def _apple_hdr_gain_from_headroom_stops(stops: float) -> float:
    """Return MakerApple HDRGain value that maps to the requested headroom."""
    if not math.isfinite(stops):
        stops = 0.0
    stops = max(stops, 0.0)
    return (3.0 - stops) / 70.0


def build_apple_makernote_exif(headroom_stops: float) -> bytes:
    """Build a minimal EXIF item carrying MakerApple HDR gain map tags."""
    hdr_headroom = 1.01
    hdr_gain = _apple_hdr_gain_from_headroom_stops(headroom_stops)

    maker_entries = [
        (0x0001, 9, 1, 16),  # MakerNoteVersion
        (0x0021, 10, 1, None),  # HDRHeadroom
        (0x0030, 10, 1, None),  # HDRGain
    ]
    maker_ifd_offset = 14
    maker_data_offset = maker_ifd_offset + 2 + len(maker_entries) * 12 + 4
    maker = bytearray(b"Apple iOS\x00\x00\x01MM")
    maker += struct.pack(">H", len(maker_entries))
    rational_data = bytearray()
    for tag, field_type, count, value in maker_entries:
        if tag == 0x0021:
            value = maker_data_offset + len(rational_data)
            rational_data += struct.pack(">ii", *_rational64s(hdr_headroom))
        elif tag == 0x0030:
            value = maker_data_offset + len(rational_data)
            rational_data += struct.pack(">ii", *_rational64s(hdr_gain))
        maker += struct.pack(">HHII", tag, field_type, count, int(value))
    maker += struct.pack(">I", 0)
    maker += rational_data
    maker_note = bytes(maker)

    make = b"Apple\x00"
    software = b"HDR Transcoder\x00"
    ifd0_entry_count = 3
    ifd0_offset = 8
    ifd0_data_offset = ifd0_offset + 2 + ifd0_entry_count * 12 + 4
    make_offset = ifd0_data_offset
    software_offset = make_offset + len(make)
    exif_ifd_offset = software_offset + len(software)
    if exif_ifd_offset % 2:
        software += b"\x00"
        exif_ifd_offset += 1

    exif_entry_count = 1
    maker_note_offset = exif_ifd_offset + 2 + exif_entry_count * 12 + 4

    tiff = bytearray(b"MM\x00*\x00\x00\x00\x08")
    tiff += struct.pack(">H", ifd0_entry_count)
    tiff += struct.pack(">HHII", 0x010F, 2, len(make), make_offset)
    tiff += struct.pack(">HHII", 0x0131, 2, len(software.rstrip(b'\x00')) + 1, software_offset)
    tiff += struct.pack(">HHII", 0x8769, 4, 1, exif_ifd_offset)
    tiff += struct.pack(">I", 0)
    tiff += make
    tiff += software
    tiff += struct.pack(">H", exif_entry_count)
    tiff += struct.pack(">HHII", 0x927C, 7, len(maker_note), maker_note_offset)
    tiff += struct.pack(">I", 0)
    tiff += maker_note

    return struct.pack(">I", 6) + b"Exif\x00\x00" + bytes(tiff)


def build_apple_hdr_gainmap_xmp(headroom_stops: float) -> bytes:
    """Build primary XMP metadata used by Apple HDR gain map readers."""
    headroom = 2.0 ** max(headroom_stops, 0.0)
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="HDR Transcoder">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:HDRGainMap="http://ns.apple.com/HDRGainMap/1.0/">
      <HDRGainMap:HDRGainMapVersion>131072</HDRGainMap:HDRGainMapVersion>
      <HDRGainMap:HDRGainMapHeadroom>{headroom:.6f}</HDRGainMap:HDRGainMapHeadroom>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>""".encode("utf-8")


def _encode_iso21496_signed_rational(value: float, denominator: int = 1_000_000) -> int:
    """Encode a signed float as numerator for a shared-denominator rational."""
    return int(round(np.clip(value, -2_147_483_648 / denominator, 2_147_483_647 / denominator) * denominator))


def _encode_iso21496_unsigned_rational(value: float, denominator: int = 1_000_000) -> int:
    """Encode an unsigned float as numerator for a shared-denominator rational."""
    return int(round(np.clip(value, 0.0, 4_294_967_295 / denominator) * denominator))


def build_iso21496_tmap_metadata(
    gain_map_min: np.ndarray,
    gain_map_max: np.ndarray,
    gamma: float,
    base_offset: float,
    alternate_offset: float,
    base_headroom: float = 0.0,
    alternate_headroom: float = 3.0,
) -> bytes:
    """Build ISO 21496-1 binary gainmap metadata blob (85 bytes).

    Uses common_denominator_mode (flags bit 3) for compact encoding.
    gain_map_min/max are float32 arrays of shape (3,), per-channel log2 boost values.
    gamma, base_offset, alternate_offset are scalars shared across channels.
    """
    DENOM = 1_000_000

    flags = 0
    flags |= 1  # bit 0: is_multi_channel (RGB)
    flags |= 2  # bit 1: use_base_color_space
    flags |= 8  # bit 3: common_denominator_mode

    bo_enc = int(round(np.clip(base_offset * 64.0, -128, 127)))
    ao_enc = int(round(np.clip(alternate_offset * 64.0, -128, 127)))

    header = struct.pack("<BBBBB", 0, 0, flags, bo_enc & 0xFF, ao_enc & 0xFF)

    channels = 3
    channel_numerators = []
    for ch in range(channels):
        channel_numerators.append(_encode_iso21496_signed_rational(float(gain_map_min[ch]), DENOM))
    for ch in range(channels):
        channel_numerators.append(_encode_iso21496_signed_rational(float(gain_map_max[ch]), DENOM))
    for ch in range(channels):
        channel_numerators.append(_encode_iso21496_unsigned_rational(float(gamma), DENOM))
    for ch in range(channels):
        channel_numerators.append(_encode_iso21496_unsigned_rational(float(base_offset), DENOM))
    for ch in range(channels):
        channel_numerators.append(_encode_iso21496_unsigned_rational(float(alternate_offset), DENOM))

    body = b"".join(struct.pack("<i", n) for n in channel_numerators)
    body += struct.pack("<I", DENOM)  # gainMapMin denominator
    body += struct.pack("<I", DENOM)  # gainMapMax denominator
    body += struct.pack("<I", DENOM)  # gamma denominator
    body += struct.pack("<I", DENOM)  # baseOffset denominator
    body += struct.pack("<I", DENOM)  # alternateOffset denominator

    return header + body


def build_heic_gainmap_container(
    sdr_bitstream: bytes,
    sdr_hvcC: bytes,
    alt_bitstream: bytes,
    alt_hvcC: bytes,
    gainmap_bitstream: bytes,
    gainmap_hvcC: bytes,
    apple_gainmap_bitstream: bytes,
    apple_gainmap_hvcC: bytes,
    sdr_width: int,
    sdr_height: int,
    alt_width: int,
    alt_height: int,
    gainmap_width: int,
    gainmap_height: int,
    apple_gainmap_width: int,
    apple_gainmap_height: int,
    base_headroom: float = 0.0,
    alternate_headroom: float = 3.0,
    apple_headroom: float | None = None,
    base_primaries: int = 9,
    base_transfer: int = 13,
    base_matrix: int = 9,
    alternate_primaries: int = 9,
    alternate_transfer: int = 16,
    alternate_matrix: int = 9,
    tmap_metadata: bytes = b"",
    alt_bits_per_channel: list[int] | None = None,
    gainmap_bits_per_channel: list[int] | None = None,
) -> bytes:
    """Build a complete ISO 21496-1 + Apple gainmap HEIC ISOBMFF container.

    Items:
      1 (primary): SDR base image (8-bit sRGB)
      2: HDR alternate image (10-bit BT.2020 PQ), ISO 21496-1 aux alternateImage
      3: RGB gain map image (8-bit), ISO 21496-1 aux gainmap
      4: ISO 21496-1 tmap binary metadata item
      5: XMP metadata (Apple HDR trigger)
      6: EXIF metadata (MakerApple HDR headroom/gain tags)
      7: Apple single-channel gain map (only when apple_gainmap_bitstream is non-empty)
    """
    if alt_bits_per_channel is None:
        alt_bits_per_channel = [10, 10, 10]
    if gainmap_bits_per_channel is None:
        gainmap_bits_per_channel = [8, 8, 8]

    has_apple_gm = bool(apple_gainmap_bitstream)
    apple_metadata_headroom = alternate_headroom if apple_headroom is None else apple_headroom

    xmp_data = build_apple_hdr_gainmap_xmp(apple_metadata_headroom)
    exif_data = build_apple_makernote_exif(apple_metadata_headroom)

    mdat_content = (
        sdr_bitstream + alt_bitstream + gainmap_bitstream +
        tmap_metadata + xmp_data + exif_data +
        (apple_gainmap_bitstream if has_apple_gm else b"")
    )
    mdat = build_box("mdat", mdat_content)

    sdr_in_mdat = 0
    alt_in_mdat = len(sdr_bitstream)
    gainmap_in_mdat = alt_in_mdat + len(alt_bitstream)
    tmap_meta_in_mdat = gainmap_in_mdat + len(gainmap_bitstream)
    xmp_in_mdat = tmap_meta_in_mdat + len(tmap_metadata)
    exif_in_mdat = xmp_in_mdat + len(xmp_data)
    apple_gm_in_mdat = exif_in_mdat + len(exif_data)

    iinf_items = [
        {"id": 1, "type": "hvc1", "name": "Primary"},
        {"id": 2, "type": "hvc1", "name": "Alternate"},
        {"id": 3, "type": "hvc1", "name": "GainMap"},
        {"id": 4, "type": "tmap", "name": ""},
        {"id": 5, "type": "mime", "name": "", "content_type": "application/rdf+xml", "flags": 1},
        {"id": 6, "type": "Exif", "name": "", "flags": 1},
    ]
    if has_apple_gm:
        iinf_items.append({"id": 7, "type": "hvc1", "name": "AppleGainMap"})

    iinf = build_iinf(iinf_items)

    # Property indices (1-based for ipma):
    #   1-5:  SDR base (hvcC, ispe, pixi, colr, pasp)
    #   6:    tmap (shared headroom)
    #   7-11: Alternate (hvcC, ispe, pixi, colr, auxC)
    #   12-16: Gainmap (hvcC, ispe, pixi, colr, auxC)
    #   17-21: Apple gainmap (hvcC, ispe, pixi, colr, auxC), only when present
    properties = [
        # 1-5: SDR base
        {"type": "hvcC", "data": sdr_hvcC},
        {"type": "ispe", "width": sdr_width, "height": sdr_height},
        {"type": "pixi", "bits_per_channel": [8, 8, 8]},
        {"type": "colr", "primaries": base_primaries, "transfer": base_transfer, "matrix": base_matrix, "full_range": 1},
        {"type": "pasp"},
        # 6: tmap headroom property
        {"type": "tmap", "base_headroom": base_headroom, "alternate_headroom": alternate_headroom},
        # 7-11: Alternate image
        {"type": "hvcC", "data": alt_hvcC},
        {"type": "ispe", "width": alt_width, "height": alt_height},
        {"type": "pixi", "bits_per_channel": alt_bits_per_channel},
        {"type": "colr", "primaries": alternate_primaries, "transfer": alternate_transfer, "matrix": alternate_matrix, "full_range": 1},
        {"type": "auxC", "aux_type": "urn:iso:std:iso:ts:21496:-1:aux:alternateImage"},
        # 12-16: Gain map
        {"type": "hvcC", "data": gainmap_hvcC},
        {"type": "ispe", "width": gainmap_width, "height": gainmap_height},
        {"type": "pixi", "bits_per_channel": gainmap_bits_per_channel},
        {"type": "colr", "primaries": base_primaries, "transfer": base_transfer, "matrix": base_matrix, "full_range": 1},
        {"type": "auxC", "aux_type": "urn:iso:std:iso:ts:21496:-1:aux:gainmap"},
    ]
    apple_prop_start = len(properties) + 1  # 1-based index of first Apple GM property
    if has_apple_gm:
        properties.extend([
            {"type": "hvcC", "data": apple_gainmap_hvcC},
            {"type": "ispe", "width": apple_gainmap_width, "height": apple_gainmap_height},
            {"type": "pixi", "bits_per_channel": [8]},
            {"type": "colr", "primaries": 2, "transfer": 2, "matrix": 2, "full_range": 1},
            {"type": "auxC", "aux_type": "urn:com:apple:photo:2020:aux:hdrgainmap"},
        ])
    ipco = build_ipco(properties)

    ipma_mapping = {
        1: [(1, True), (2, False), (3, False), (4, False), (5, False), (6, False)],
        2: [(7, True), (8, False), (9, False), (10, False), (11, True)],
        3: [(12, True), (13, False), (14, False), (15, False), (16, True)],
        4: [(6, False), (2, False), (9, False), (10, False)],
    }
    if has_apple_gm:
        ipma_mapping[7] = [
            (apple_prop_start, True),
            (apple_prop_start + 1, False),
            (apple_prop_start + 2, False),
            (apple_prop_start + 3, False),
            (apple_prop_start + 4, True),
        ]
    ipma = build_ipma(ipma_mapping)
    iprp = build_box("iprp", ipco + ipma)

    iref_entries = [
        {"type": "auxl", "from": 2, "to": [1]},
        {"type": "auxl", "from": 3, "to": [1]},
        {"type": "dimg", "from": 4, "to": [1, 3]},
        {"type": "cdsc", "from": 5, "to": [7 if has_apple_gm else 3]},
        {"type": "cdsc", "from": 6, "to": [1, 4]},
    ]
    if has_apple_gm:
        iref_entries.append({"type": "auxl", "from": 7, "to": [1]})
    iref = build_iref(iref_entries)

    ftyp = build_ftyp("heic", ["mif1", "MiHB", "MiHA", "heix", "MiHE", "MiPr", "miaf", "heic", "tmap"])

    iloc_entries = [
        {"id": 1, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(sdr_bitstream)}]},
        {"id": 2, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(alt_bitstream)}]},
        {"id": 3, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(gainmap_bitstream)}]},
        {"id": 4, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(tmap_metadata)}]},
        {"id": 5, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(xmp_data)}]},
        {"id": 6, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
         "extents": [{"offset": 0, "length": len(exif_data)}]},
    ]
    if has_apple_gm:
        iloc_entries.append(
            {"id": 7, "construction_method": 0, "data_ref_idx": 0, "base_offset": 0,
             "extents": [{"offset": 0, "length": len(apple_gainmap_bitstream)}]},
        )
    iloc_placeholder = build_iloc(iloc_entries)
    meta_placeholder = build_meta(primary_item_id=1, iloc_data=iloc_placeholder, iinf_data=iinf, iref_data=iref, iprp_data=iprp)
    mdat_payload_start = len(ftyp) + len(meta_placeholder) + 8

    iloc_offsets = [
        mdat_payload_start + sdr_in_mdat,
        mdat_payload_start + alt_in_mdat,
        mdat_payload_start + gainmap_in_mdat,
        mdat_payload_start + tmap_meta_in_mdat,
        mdat_payload_start + xmp_in_mdat,
        mdat_payload_start + exif_in_mdat,
    ]
    if has_apple_gm:
        iloc_offsets.append(mdat_payload_start + apple_gm_in_mdat)
    iloc_entries_final = []
    for i, entry in enumerate(iloc_entries):
        new_entry = dict(entry)
        new_entry["extents"] = [{"offset": iloc_offsets[i], "length": entry["extents"][0]["length"]}]
        iloc_entries_final.append(new_entry)
    iloc = build_iloc(iloc_entries_final)
    meta = build_meta(primary_item_id=1, iloc_data=iloc, iinf_data=iinf, iref_data=iref, iprp_data=iprp)

    return ftyp + meta + mdat
