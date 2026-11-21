"""Image preparation, EXIF orientation handling, coordinate transforms, and preview generation for Module 2 (YOLO)."""

from __future__ import annotations

import hashlib
import math
import os
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.yolo.exceptions import (
    DetectorError,
    IntegrityError,
    InvalidPhotoError,
)
from src.yolo.models import DetectionCandidate

# Color coding by candidate review disposition:
# Unreviewed: Yellow (amber)
# Confirmed: Green
# Dismissed: Grey
DISPOSITION_COLORS: dict[str, tuple[int, int, int]] = {
    "unreviewed": (255, 215, 0),
    "confirmed": (46, 204, 113),
    "dismissed": (149, 165, 166),
}


def read_exif_orientation(data: bytes) -> int | None:
    """Pure-stdlib JPEG EXIF Orientation reader.

    Parses APP1 (0xFFE1) Exif\\x00\\x00 TIFF header (both little-endian II and
    big-endian MM) for IFD0 tag 0x0112. Returns integer 1..8 or None.
    """
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None

    offset = 2
    data_len = len(data)

    while offset < data_len - 1:
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < data_len and data[offset] == 0xFF:
            offset += 1
        if offset >= data_len:
            break
        marker = data[offset]
        offset += 1

        # End of image or start of scan (no more metadata)
        if marker in (0xD9, 0xDA):
            break

        # Standalone markers with no length
        if marker in (0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8):
            continue

        if offset + 2 > data_len:
            break
        seg_len = struct.unpack(">H", data[offset : offset + 2])[0]
        seg_start = offset + 2
        seg_end = offset + seg_len

        # Check for APP1 (0xE1) segment
        if marker == 0xE1 and seg_len >= 14:
            if data[seg_start : seg_start + 6] == b"Exif\x00\x00":
                tiff_start = seg_start + 6
                if tiff_start + 8 <= data_len:
                    endian_bytes = data[tiff_start : tiff_start + 2]
                    if endian_bytes == b"II":
                        endian = "<"
                    elif endian_bytes == b"MM":
                        endian = ">"
                    else:
                        offset = seg_end
                        continue

                    # Verify TIFF magic 42 (0x002A)
                    magic = struct.unpack(endian + "H", data[tiff_start + 2 : tiff_start + 4])[0]
                    if magic == 42:
                        ifd0_offset = struct.unpack(endian + "I", data[tiff_start + 4 : tiff_start + 8])[0]
                        ifd0_start = tiff_start + ifd0_offset
                        if ifd0_start + 2 <= data_len:
                            num_entries = struct.unpack(endian + "H", data[ifd0_start : ifd0_start + 2])[0]
                            entry_start = ifd0_start + 2
                            for _ in range(num_entries):
                                if entry_start + 12 > data_len:
                                    break
                                tag_id = struct.unpack(endian + "H", data[entry_start : entry_start + 2])[0]
                                if tag_id == 0x0112:  # Orientation tag
                                    val = struct.unpack(endian + "H", data[entry_start + 8 : entry_start + 10])[0]
                                    if 1 <= val <= 8:
                                        return val
                                entry_start += 12

        offset = seg_end

    return None


@dataclass
class ImagePrepMetadata:
    raw_width: int
    raw_height: int
    exif_orientation: int
    display_width: int
    display_height: int
    target_size: int
    scale: float
    pad_x: float
    pad_y: float
    letterboxed: bool


def compute_letterbox_metadata(
    raw_width: int,
    raw_height: int,
    target_size: int = 640,
    exif_orientation: int | None = None,
) -> ImagePrepMetadata:
    """Computes aspect-preserving letterbox scale and padding accounting for EXIF orientation."""
    if raw_width <= 0 or raw_height <= 0:
        raise ValueError(f"Image dimensions must be positive, got {raw_width}x{raw_height}")
    if target_size <= 0:
        raise ValueError(f"target_size must be positive, got {target_size}")

    orientation = exif_orientation if (exif_orientation is not None and 1 <= exif_orientation <= 8) else 1

    # For EXIF orientations 5, 6, 7, 8, the image is rotated 90 or 270 degrees
    if orientation in (5, 6, 7, 8):
        disp_w = raw_height
        disp_h = raw_width
    else:
        disp_w = raw_width
        disp_h = raw_height

    scale = min(target_size / disp_w, target_size / disp_h)
    scaled_w = disp_w * scale
    scaled_h = disp_h * scale
    pad_x = (target_size - scaled_w) / 2.0
    pad_y = (target_size - scaled_h) / 2.0
    letterboxed = (pad_x > 0.0 or pad_y > 0.0)

    return ImagePrepMetadata(
        raw_width=raw_width,
        raw_height=raw_height,
        exif_orientation=orientation,
        display_width=disp_w,
        display_height=disp_h,
        target_size=target_size,
        scale=scale,
        pad_x=pad_x,
        pad_y=pad_y,
        letterboxed=letterboxed,
    )


def prepare_image_metadata(image_path: Path | str, target_size: int = 640) -> ImagePrepMetadata:
    """Reads raw image header dimensions and EXIF orientation without modifying the file."""
    img_p = Path(image_path)
    if not img_p.is_file():
        raise InvalidPhotoError(f"Image file not found: {image_path}")

    try:
        data = img_p.read_bytes()
    except Exception as exc:
        raise InvalidPhotoError(f"Failed to read image file '{image_path}': {exc}") from exc

    if not data:
        raise InvalidPhotoError("Image file is empty (0 bytes)")

    # Read dimensions via pure stdlib
    from src.yolo.store import YoloCaseStore

    temp_store = YoloCaseStore()
    try:
        _fmt, raw_w, raw_h = temp_store._inspect_image_header(data)
    except Exception as exc:
        raise InvalidPhotoError(f"Failed to parse image header for '{image_path}': {exc}") from exc

    orientation = read_exif_orientation(data)
    return compute_letterbox_metadata(
        raw_width=raw_w,
        raw_height=raw_h,
        target_size=target_size,
        exif_orientation=orientation,
    )


def reverse_letterbox_bbox(
    bbox_xyxy: tuple[float, float, float, float],
    meta: ImagePrepMetadata,
) -> tuple[float, float, float, float]:
    """Maps letterboxed inference coordinates back to original display-oriented coordinates."""
    if not isinstance(bbox_xyxy, (tuple, list)) or len(bbox_xyxy) != 4:
        raise DetectorError(f"bbox_xyxy must have 4 coordinates, got {bbox_xyxy}")

    x1, y1, x2, y2 = (float(c) for c in bbox_xyxy)
    if not all(math.isfinite(c) for c in (x1, y1, x2, y2)):
        raise DetectorError(f"Non-finite bounding box coordinates: {(x1, y1, x2, y2)}")

    orig_x1 = (x1 - meta.pad_x) / meta.scale
    orig_y1 = (y1 - meta.pad_y) / meta.scale
    orig_x2 = (x2 - meta.pad_x) / meta.scale
    orig_y2 = (y2 - meta.pad_y) / meta.scale

    # Clip to [0.0, display_width] and [0.0, display_height]
    cx1 = max(0.0, min(float(meta.display_width), orig_x1))
    cy1 = max(0.0, min(float(meta.display_height), orig_y1))
    cx2 = max(0.0, min(float(meta.display_width), orig_x2))
    cy2 = max(0.0, min(float(meta.display_height), orig_y2))

    if cx2 <= cx1 or cy2 <= cy1:
        raise DetectorError(
            f"Collapsed or zero-area bounding box after coordinate reversal: ({cx1}, {cy1}, {cx2}, {cy2})"
        )

    return (cx1, cy1, cx2, cy2)


def validate_and_clip_bbox(
    bbox_xyxy: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """Validates finite coordinates and clips to image boundaries."""
    if not isinstance(bbox_xyxy, (tuple, list)) or len(bbox_xyxy) != 4:
        raise ValueError(f"bbox_xyxy must have 4 coordinates, got {bbox_xyxy}")
    x1, y1, x2, y2 = (float(c) for c in bbox_xyxy)
    if not all(math.isfinite(c) for c in (x1, y1, x2, y2)):
        raise ValueError(f"Coordinates must be finite, got {(x1, y1, x2, y2)}")
    if image_width <= 0 or image_height <= 0:
        raise ValueError(f"Invalid image bounds: {image_width}x{image_height}")

    cx1 = max(0.0, min(float(image_width), x1))
    cy1 = max(0.0, min(float(image_height), y1))
    cx2 = max(0.0, min(float(image_width), x2))
    cy2 = max(0.0, min(float(image_height), y2))

    if cx2 <= cx1 or cy2 <= cy1:
        raise ValueError(f"Bounding box has zero or negative area after clipping: ({cx1}, {cy1}, {cx2}, {cy2})")

    return (cx1, cy1, cx2, cy2)


def normalize_bbox_xyxy(
    bbox_xyxy: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """Normalizes bounding box coordinates to [0.0, 1.0] relative to image dimensions."""
    x1, y1, x2, y2 = validate_and_clip_bbox(bbox_xyxy, image_width, image_height)
    return (
        x1 / float(image_width),
        y1 / float(image_height),
        x2 / float(image_width),
        y2 / float(image_height),
    )


@dataclass
class PreviewResult:
    preview_path: str
    original_sha256: str
    candidate_count: int
    rendered_with: str
    width: int
    height: int


def _render_stdlib_png(
    width: int,
    height: int,
    candidates: list[DetectionCandidate],
) -> bytes:
    """Renders a minimal annotated PNG preview using pure Python standard library."""
    # Create dark neutral canvas (RGB: 30, 30, 30)
    row_bytes = bytearray(b"\x1e\x1e\x1e" * width)
    raster = [bytearray(row_bytes) for _ in range(height)]

    # Draw color-coded bounding box rectangles (thickness 2)
    for cand in candidates:
        color = DISPOSITION_COLORS.get(cand.disposition, (255, 215, 0))
        r, g, b = color
        color_bytes = bytes([r, g, b])

        x1 = max(0, min(width - 1, int(cand.bbox_xyxy[0])))
        y1 = max(0, min(height - 1, int(cand.bbox_xyxy[1])))
        x2 = max(0, min(width - 1, int(cand.bbox_xyxy[2])))
        y2 = max(0, min(height - 1, int(cand.bbox_xyxy[3])))

        # Draw top and bottom horizontal borders
        for t in range(2):
            yt = min(height - 1, y1 + t)
            yb = max(0, y2 - t)
            for x in range(x1, x2 + 1):
                idx = x * 3
                raster[yt][idx : idx + 3] = color_bytes
                raster[yb][idx : idx + 3] = color_bytes

        # Draw left and right vertical borders
        for t in range(2):
            xl = min(width - 1, x1 + t)
            xr = max(0, x2 - t)
            for y in range(y1, y2 + 1):
                idx_l = xl * 3
                idx_r = xr * 3
                raster[y][idx_l : idx_l + 3] = color_bytes
                raster[y][idx_r : idx_r + 3] = color_bytes

    # Encode to PNG
    sig = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, 8 bit depth, 2 color type (truecolor RGB), 0 comp, 0 filter, 0 interlace
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # Prefix each scanline with filter byte 0x00
    raw_data = b"".join(b"\x00" + bytes(row) for row in raster)
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return sig + ihdr + idat + iend


def render_annotated_preview(
    original_path: Path | str,
    output_path: Path | str,
    candidates: list[DetectionCandidate],
    *,
    exif_orientation: int | None = None,
    _pil_loader: Callable[[], Any] | None = None,
) -> PreviewResult:
    """Renders a separate annotated candidate preview without modifying the original photo.

    Enforces forensic immutability:
    1. Rejects output_path == original_path with IntegrityError.
    2. Validates original SHA-256 is unaltered after rendering.
    3. Atomically writes preview to output_path.
    """
    orig_p = Path(original_path).resolve()
    out_p = Path(output_path).resolve()

    if not orig_p.is_file():
        raise InvalidPhotoError(f"Original photo file not found: {original_path}")

    if orig_p == out_p:
        raise IntegrityError(f"output_path cannot overwrite original photo: {original_path}")

    # Compute original SHA-256 before rendering
    orig_bytes = orig_p.read_bytes()
    sha256_before = hashlib.sha256(orig_bytes).hexdigest()

    # Determine display dimensions
    from src.yolo.store import YoloCaseStore

    temp_store = YoloCaseStore()
    _fmt, raw_w, raw_h = temp_store._inspect_image_header(orig_bytes)
    orientation = exif_orientation or read_exif_orientation(orig_bytes) or 1
    if orientation in (5, 6, 7, 8):
        disp_w, disp_h = raw_h, raw_w
    else:
        disp_w, disp_h = raw_w, raw_h

    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp_file: Path | None = None

    # Check for Pillow
    pil_mod: Any = None
    if _pil_loader is not None:
        try:
            pil_mod = _pil_loader()
        except Exception:
            pil_mod = None
    else:
        try:
            import PIL  # pyrefly: ignore [missing-import]
            import PIL.Image  # pyrefly: ignore [missing-import]
            import PIL.ImageDraw  # pyrefly: ignore [missing-import]
            import PIL.ImageOps  # pyrefly: ignore [missing-import]
            pil_mod = PIL
        except (ImportError, ModuleNotFoundError):
            pil_mod = None

    rendered_with = "stdlib_copy"
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=out_p.parent,
            delete=False,
        ) as f:
            temp_file = Path(f.name)

            if pil_mod is not None:
                # Pillow rendering path
                image_cls = getattr(pil_mod, "Image", getattr(getattr(pil_mod, "PIL", None), "Image", None))
                draw_mod = getattr(pil_mod, "ImageDraw", getattr(getattr(pil_mod, "PIL", None), "ImageDraw", None))
                ops_mod = getattr(pil_mod, "ImageOps", getattr(getattr(pil_mod, "PIL", None), "ImageOps", None))

                if image_cls is not None and draw_mod is not None:
                    img = image_cls.open(orig_p)
                    if ops_mod is not None and hasattr(ops_mod, "exif_transpose"):
                        img = ops_mod.exif_transpose(img)
                    if getattr(img, "mode", "RGB") != "RGB":
                        img = img.convert("RGB")

                    draw = draw_mod.Draw(img)
                    for cand in candidates:
                        color = DISPOSITION_COLORS.get(cand.disposition, (255, 215, 0))
                        x1, y1, x2, y2 = cand.bbox_xyxy
                        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                        label = f"{cand.ref} {cand.class_name} {cand.confidence:.2f} ({cand.disposition})"
                        draw.text((x1, max(0.0, y1 - 12)), label, fill=color)

                    save_fmt = "PNG" if out_p.suffix.lower() == ".png" else "JPEG"
                    img.save(f, format=save_fmt)
                    f.flush()
                    rendered_with = "pillow"
                    disp_w, disp_h = img.width, img.height
                else:
                    # Fallback if image_cls or draw_mod missing
                    if len(candidates) == 0:
                        f.write(orig_bytes)
                        f.flush()
                        rendered_with = "stdlib_copy"
                    else:
                        png_bytes = _render_stdlib_png(disp_w, disp_h, candidates)
                        f.write(png_bytes)
                        f.flush()
                        rendered_with = "stdlib_png"
            else:
                # Pure stdlib fallback path
                if len(candidates) == 0:
                    f.write(orig_bytes)
                    f.flush()
                    rendered_with = "stdlib_copy"
                else:
                    png_bytes = _render_stdlib_png(disp_w, disp_h, candidates)
                    f.write(png_bytes)
                    f.flush()
                    rendered_with = "stdlib_png"

        os.replace(temp_file, out_p)
    except Exception as exc:
        if temp_file and temp_file.is_file():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise exc

    # Forensic verification: original must remain completely untouched
    sha256_after = hashlib.sha256(orig_p.read_bytes()).hexdigest()
    if sha256_after != sha256_before:
        raise IntegrityError(f"Original photo altered during preview rendering! {orig_p}")

    return PreviewResult(
        preview_path=str(out_p),
        original_sha256=sha256_before,
        candidate_count=len(candidates),
        rendered_with=rendered_with,
        width=disp_w,
        height=disp_h,
    )
