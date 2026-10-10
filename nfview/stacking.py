"""Stacking functionality for NFView."""
from __future__ import annotations
import tempfile
from pathlib import Path
from typing import Callable
import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    import rawpy
except ImportError:
    rawpy = None

from nfview.resources import RAW_EXTENSIONS
from nfview.scanning import _default_reference_path, discover_images
from nfview.imaging import _disk_circle, _feature_alignment_transform

def _full_image_for_stack(path: Path, size: tuple[int, int]) -> np.ndarray:
    if path.suffix.lower() in RAW_EXTENSIONS:
        if rawpy is None:
            raise RuntimeError("RAW support is unavailable. Install dependencies with pip install -r requirements.txt.")
        with rawpy.imread(str(path)) as raw:
            image = raw.postprocess(half_size=False, use_camera_wb=True, no_auto_bright=True, output_bps=8)
        image = np.asarray(image)
    else:
        with Image.open(path) as source:
            image = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
    width, height = size
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

def _alignment_transform(reference: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, int, int, str]:
    try:
        reference_x, reference_y, reference_radius, reference_quality = _disk_circle(reference)
        current_x, current_y, current_radius, current_quality = _disk_circle(current)
    except RuntimeError:
        transform, inliers, matches = _feature_alignment_transform(reference, current)
        return transform, inliers, matches, "features"

    scale = reference_radius / current_radius
    transform = np.array(
        (
            (scale, 0.0, reference_x - scale * current_x),
            (0.0, scale, reference_y - scale * current_y),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    confidence = int(round(min(reference_quality, current_quality) * 1000))
    return transform, confidence, 0, "disk"

def stack_images(
    source: Path,
    output: Path,
    image_paths: list[Path] | None = None,
    reference_path: Path | None = None,
    max_dimension: int = 2400,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int]:
    """Align usable frames and write a chunked median stack as a TIFF."""
    paths = image_paths or discover_images(source)
    paths = [path for path in paths if path.resolve() != output.resolve()]
    if not paths:
        raise RuntimeError(f"No supported images found in {source}.")
    reference_path = reference_path or _default_reference_path(paths)
    if reference_path.suffix.lower() in RAW_EXTENSIONS:
        if rawpy is None:
            raise RuntimeError("RAW support is unavailable. Install dependencies with pip install -r requirements.txt.")
        with rawpy.imread(str(reference_path)) as raw:
            reference_width, reference_height = raw.sizes.width, raw.sizes.height
    else:
        with Image.open(reference_path) as reference_source:
            reference_width, reference_height = ImageOps.exif_transpose(reference_source).size
    scale = min(1.0, max_dimension / max(reference_width, reference_height))
    stack_size = (max(1, round(reference_width * scale)), max(1, round(reference_height * scale)))
    reference = _full_image_for_stack(reference_path, stack_size)
    height, width = reference.shape[:2]
    aligned = 0
    rejected = 0

    with tempfile.TemporaryDirectory(prefix="image-screener-stack-") as temporary_folder:
        frame_store = np.memmap(
            Path(temporary_folder) / "frames.dat",
            mode="w+",
            dtype=np.uint8,
            shape=(len(paths), height, width, 3),
        )
        mask_store = np.memmap(
            Path(temporary_folder) / "masks.dat",
            mode="w+",
            dtype=np.uint8,
            shape=(len(paths), height, width),
        )
        for index, path in enumerate(paths):
            try:
                current = _full_image_for_stack(path, stack_size)
                if path == reference_path:
                    warped = current
                    valid_mask = np.full((height, width), 255, dtype=np.uint8)
                    inliers = 0
                    alignment_model = "reference"
                else:
                    transform, inliers, matches, alignment_model = _alignment_transform(reference, current)
                    warped = cv2.warpPerspective(current, transform, (width, height), flags=cv2.INTER_LINEAR)
                    valid_mask = cv2.warpPerspective(
                        np.full((height, width), 255, dtype=np.uint8),
                        transform,
                        (width, height),
                        flags=cv2.INTER_NEAREST,
                    )
                    if alignment_model == "features" and matches < 16:
                        raise RuntimeError(f"Only {matches} reliable matches")
                frame_store[aligned] = warped
                mask_store[aligned] = valid_mask
                aligned += 1
                if progress:
                    detail = alignment_model if alignment_model != "features" else f"{inliers} inliers"
                    progress(index + 1, len(paths), f"aligned {path.name} ({detail})")
            except Exception as error:
                rejected += 1
                if progress:
                    progress(index + 1, len(paths), f"rejected {path.name}: {error}")

        if aligned < 2:
            raise RuntimeError("Fewer than two images could be aligned for stacking.")
        output.parent.mkdir(parents=True, exist_ok=True)
        stacked = np.zeros((height, width, 3), dtype=np.uint8)
        for start in range(0, height, 64):
            end = min(height, start + 64)
            values = frame_store[:aligned, start:end].astype(np.float32)
            valid = mask_store[:aligned, start:end].astype(bool)
            values[~valid, :] = np.nan
            with np.errstate(invalid="ignore"):
                result = np.nanmedian(values, axis=0)
            result = np.nan_to_num(result, nan=0.0).astype(np.uint8)
            stacked[start:end] = result
        if output.suffix.lower() == ".png":
            Image.fromarray(stacked).save(output, format="PNG")
        else:
            Image.fromarray(stacked).save(output, format="TIFF", compression="tiff_lzw")
        frame_store.flush()
        mask_store.flush()
        del frame_store
        del mask_store
    return aligned, rejected
