"""Scanning functionality for NFView."""
from __future__ import annotations
import json
import sys
import threading
from pathlib import Path
from typing import Callable


from nfview.resources import CACHE_FILENAME, CACHE_VERSION, SUPPORTED_EXTENSIONS
from nfview.models import ImageScore, ScanCancelled
from nfview.imaging import _disk_circle, preview_for, sharpness_score, stacking_score

def folder_signature(source, reference=None):
    """File identity checks for UI session reuse; scoring cache remains version 3."""
    entries=[]
    for path in discover_images(source):
        try:
            stat=path.stat()
            entries.append((str(path),stat.st_size,stat.st_mtime_ns))
        except OSError:
            entries.append((str(path),None,None))
    if reference is not None:
        stat=reference.stat()
        entries.append(("reference:"+str(reference),stat.st_size,stat.st_mtime_ns))
    return tuple(entries)

def discover_images(source: Path) -> list[Path]:
    return sorted(
        path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

def _default_reference_path(paths: list[Path], cancel: threading.Event | None = None) -> Path:
    for path in paths:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled()
        try:
            _disk_circle(preview_for(path))
            return path
        except Exception:
            continue
    return paths[0]

def load_score_cache(source: Path) -> dict[str, dict[str, object]]:
    cache_path = source / CACHE_FILENAME
    try:
        with cache_path.open(encoding="utf-8") as cache_file:
            cache = json.load(cache_file)
        if cache.get("version") != CACHE_VERSION:
            return {}
        return cache.get("files", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}

def save_score_cache(source: Path, entries: dict[str, dict[str, object]]) -> None:
    cache_path = source / CACHE_FILENAME
    temporary_path = cache_path.with_suffix(".tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as cache_file:
            json.dump({"version": CACHE_VERSION, "files": entries}, cache_file, indent=2)
        temporary_path.replace(cache_path)
    except OSError as error:
        pass  # Read-only folders remain usable; GUI reports settings persistence errors.

def scan_folder(
    source: Path,
    keep_percent: float,
    progress: Callable[[int, int, bool], None] | None = None,
    mode: str = "sharpness",
    reference_path: Path | None = None,
    cancel: threading.Event | None = None,
    on_result: Callable[[ImageScore], None] | None = None,
    force: bool = False,
) -> tuple[list[ImageScore], float]:
    images = discover_images(source)
    if mode == "stacking" and images:
        if reference_path is None:
            reference_path = _default_reference_path(images, cancel)
        reference_image = preview_for(reference_path)
    else:
        reference_image = None
    original_entries = load_score_cache(source)
    cached_entries = {} if force else original_entries
    cache_entries: dict[str, dict[str, object]] = {}
    results: list[ImageScore] = []
    cached_count = 0
    for index, path in enumerate(images, start=1):
        if cancel is not None and cancel.is_set():
            save_score_cache(source, {**original_entries, **cache_entries})
            raise ScanCancelled()
        relative_path = str(path.relative_to(source))
        try:
            stat = path.stat()
            metadata = {"size": stat.st_size, "modified_ns": stat.st_mtime_ns}
        except OSError as error:
            result = ImageScore(path, 0, f"File unavailable: {error}")
            results.append(result)
            if on_result:
                on_result(result)
            if progress:
                progress(index, len(images), False)
            continue
        cached = cached_entries.get(relative_path)
        cache_mode = cached.get("mode") if cached else None
        cache_reference = cached.get("reference") if cached else None
        reference_matches = mode != "stacking" or cache_reference == str(reference_path)
        if (
            cached
            and cached.get("size") == metadata["size"]
            and cached.get("modified_ns") == metadata["modified_ns"]
            and cache_mode == mode
            and reference_matches
        ):
            result = ImageScore(path, float(cached.get("score", 0)), str(cached.get("error", "")))
            cached_count += 1
            results.append(result)
            cache_entries[relative_path] = {
                **metadata,
                "score": result.score,
                "error": result.error,
                "mode": mode,
                "reference": str(reference_path) if reference_path else "",
            }
            if on_result:
                on_result(result)
            if progress:
                progress(index, len(images), True)
            continue
        try:
            if mode == "stacking":
                score = 1_000_000_000.0 if path == reference_path else stacking_score(
                    path, reference_image
                )
            else:
                score = sharpness_score(path)
            result = ImageScore(path, score)
            results.append(result)
            cache_entries[relative_path] = {
                **metadata,
                "score": score,
                "error": "",
                "mode": mode,
                "reference": str(reference_path) if reference_path else "",
            }
            if sys.stdout is not None:
                print(f"[{index}/{len(images)}] {score:10.2f}  {path.name}")
        except Exception as error:
            result = ImageScore(path, 0, str(error))
            results.append(result)
            cache_entries[relative_path] = {
                **metadata,
                "score": 0,
                "error": str(error),
                "mode": mode,
                "reference": str(reference_path) if reference_path else "",
            }
            if sys.stdout is not None:
                print(f"[{index}/{len(images)}] ERROR       {path.name}: {error}", file=sys.stderr)
        if on_result:
            on_result(result)
        if progress:
            progress(index, len(images), False)

    save_score_cache(source, cache_entries)
    if sys.stdout is not None:
        print(f"Used cached scores for {cached_count} of {len(images)} images.")

    successful = sorted((result for result in results if not result.error), key=lambda result: result.score, reverse=True)
    keep_count = max(1, round(len(successful) * keep_percent / 100)) if successful else 0
    cutoff = successful[keep_count - 1].score if keep_count else float("inf")
    return sorted(results, key=lambda result: result.score, reverse=True), cutoff
