"""Imaging functionality for NFView."""
from __future__ import annotations
import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    import rawpy
except ImportError:
    rawpy = None

from nfview.resources import RAW_EXTENSIONS

def preview_for(path: Path) -> np.ndarray:
    """Return a small RGB image, favoring the camera's embedded RAW preview."""
    if path.suffix.lower() not in RAW_EXTENSIONS:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1600, 1600))
            return np.asarray(image)

    if rawpy is None:
        raise RuntimeError("RAW support is unavailable. Install dependencies with pip install -r requirements.txt.")

    with rawpy.imread(str(path)) as raw:
        try:
            thumbnail = raw.extract_thumb()
            if thumbnail.format == rawpy.ThumbFormat.JPEG:
                import io

                with Image.open(io.BytesIO(thumbnail.data)) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((1600, 1600))
                    return np.asarray(image)
            return thumbnail.data
        except rawpy.LibRawNoThumbnailError:
            image = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=True)
            return image

def sharpness_score(path: Path) -> float:
    image = preview_for(path)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    border_y = max(1, height // 20)
    border_x = max(1, width // 20)
    center = gray[border_y : height - border_y, border_x : width - border_x]
    return float(cv2.Laplacian(center, cv2.CV_64F).var())

def _feature_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (1200, 1200), interpolation=cv2.INTER_AREA)

def _disk_circle(image: np.ndarray) -> tuple[float, float, float, float]:
    """Find a bright, roughly circular disk against a darker background."""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("Could not detect a bright disk")

    contour = max(contours, key=cv2.contourArea)
    height, width = gray.shape
    area = cv2.contourArea(contour)
    (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
    if (
        area < height * width * 0.005
        or radius < min(height, width) * 0.03
        or center_x - radius <= 1
        or center_y - radius <= 1
        or center_x + radius >= width - 1
        or center_y + radius >= height - 1
    ):
        raise RuntimeError("Could not detect a complete lunar disk")
    quality = min(1.0, area / (np.pi * radius * radius))
    if quality < 0.55:
        raise RuntimeError("Bright subject is not sufficiently disk-shaped")
    return float(center_x), float(center_y), float(radius), float(quality)

def _feature_alignment_transform(reference: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, int, int]:
    reference_features = _feature_image(reference)
    current_features = _feature_image(current)
    orb = cv2.ORB_create(nfeatures=2400)
    reference_keypoints, reference_descriptors = orb.detectAndCompute(reference_features, None)
    current_keypoints, current_descriptors = orb.detectAndCompute(current_features, None)
    if reference_descriptors is None or current_descriptors is None:
        raise RuntimeError("Too few trackable features")
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(current_descriptors, reference_descriptors, k=2)
    good = [first for first, second in pairs if first.distance < 0.75 * second.distance]
    if len(good) < 12:
        raise RuntimeError(f"Only {len(good)} reliable feature matches")
    current_points = np.float32([current_keypoints[match.queryIdx].pt for match in good]).reshape(-1, 1, 2)
    reference_points = np.float32([reference_keypoints[match.trainIdx].pt for match in good]).reshape(-1, 1, 2)
    transform, inlier_mask = cv2.findHomography(current_points, reference_points, cv2.RANSAC, 5.0)
    if transform is None or inlier_mask is None:
        raise RuntimeError("Could not calculate a stable alignment")
    inliers = int(inlier_mask.sum())
    if inliers < 12:
        raise RuntimeError(f"Only {inliers} geometric inliers")

    current_height, current_width = current.shape[:2]
    reference_height, reference_width = reference.shape[:2]
    current_scale = np.diag((1200 / current_width, 1200 / current_height, 1.0))
    reference_scale = np.diag((1200 / reference_width, 1200 / reference_height, 1.0))
    transform = np.linalg.inv(reference_scale) @ transform @ current_scale
    return transform, inliers, len(good)

def stacking_score(path: Path, reference: np.ndarray) -> float:
    """Score how reliably a frame can be aligned to the stacking reference."""
    image = preview_for(path)
    try:
        _, _, _, reference_quality = _disk_circle(reference)
        _, _, _, image_quality = _disk_circle(image)
        return 1_000_000.0 + min(reference_quality, image_quality) * 10_000
    except RuntimeError:
        pass

    _, inliers, matches = _feature_alignment_transform(reference, image)
    return float(inliers * 100 + matches)
