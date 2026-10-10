"""Cli functionality for NFView."""
from __future__ import annotations
import argparse
import base64
import io
import json
import sys
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk


from nfview.resources import APP_ICON_ICO, APP_ICON_PNG, APP_NAME, CONFIG_FILENAME
from nfview.ui.app import PreviewApp
from nfview.platform import configure_display
from nfview.exporting import copy_ranked_images, export_report
from nfview.scanning import scan_folder
from nfview.stacking import stack_images

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank images by focus sharpness without deleting originals.")
    parser.add_argument("source", type=Path, nargs="?", default=Path.home()/"Pictures", help="Folder containing images, searched recursively.")
    parser.add_argument("--mode", choices=("sharpness", "stacking"), default="sharpness", help="Rank by focus sharpness or alignment suitability.")
    parser.add_argument("--reference", type=Path, help="Reference image for stacking alignment checks. Defaults to the first usable frame.")
    parser.add_argument("--keep-percent", type=float, default=60, help="Keep the sharpest percentage (default: 60).")
    parser.add_argument("--copy-to", type=Path, help="Copy selected originals to this folder. Omit for a dry run.")
    parser.add_argument("--stack-to", type=Path, help="Create an aligned median TIFF from the selected stacking frames.")
    return parser.parse_args()

def main() -> int:
    configure_display()
    args = parse_args()
    launch_config = Path(sys.executable if getattr(sys,"frozen",False) else Path(__file__).resolve().parent.parent / "image_screener.py").parent/CONFIG_FILENAME
    try:
        settings = json.loads(launch_config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    options_with_value = {"--mode", "--reference", "--keep-percent", "--copy-to", "--stack-to"}
    remaining = iter(sys.argv[1:])
    explicit_folder = False
    def supplied(option):
        return any(value == option or value.startswith(option + "=") for value in sys.argv[1:])
    for value in remaining:
        if value in options_with_value:
            next(remaining, None)
        elif not value.startswith("-"):
            explicit_folder = True
    if not explicit_folder:
        args.source = Path(settings.get("last_folder",str(args.source)))
        if not supplied("--keep-percent"):
            args.keep_percent = settings.get("keep_percent",args.keep_percent)
        if not supplied("--mode"):
            args.mode = settings.get("mode",args.mode)
    try:
        folder_settings = json.loads((args.source/CONFIG_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        folder_settings = {}
    if not supplied("--keep-percent"):
        args.keep_percent = folder_settings.get("keep_percent", args.keep_percent)
    if not supplied("--mode") and not args.reference:
        args.mode = folder_settings.get("mode", args.mode)
    if (not args.source.is_dir() or (not explicit_folder and not settings.get("last_folder"))) and not (args.copy_to or args.stack_to):
        chooser = tk.Tk()
        chooser.withdraw()
        chooser.title(APP_NAME)
        # Native dialogs inherit the owner's default icon, including on first launch.
        chooser_icon = ImageTk.PhotoImage(
            Image.open(io.BytesIO(base64.b64decode(APP_ICON_PNG))), master=chooser
        )
        chooser.iconphoto(True, chooser_icon)
        if sys.platform == "win32":
            icon_path = Path(tempfile.gettempdir()) / "nfview-app-v3.ico"
            try:
                icon_path.write_bytes(base64.b64decode(APP_ICON_ICO))
                chooser.iconbitmap(default=str(icon_path))
                chooser.iconbitmap(str(icon_path))
            except (OSError, tk.TclError):
                pass
        chooser.update_idletasks()
        try:
            folder = filedialog.askdirectory(parent=chooser, title="Choose your photo folder")
        finally:
            chooser.destroy()
        if not folder:
            return 0
        args.source = Path(folder)
    if not args.source.is_dir():
        print(f"Source folder does not exist: {args.source}", file=sys.stderr)
        return 2
    if not 0 < args.keep_percent <= 100:
        print("--keep-percent must be greater than 0 and no more than 100.", file=sys.stderr)
        return 2
    if args.reference and (args.mode != "stacking" or not args.reference.is_file()):
        print("--reference requires an existing file and --mode stacking.", file=sys.stderr)
        return 2

    if args.copy_to or args.stack_to:
        results, cutoff = scan_folder(args.source, args.keep_percent, mode=args.mode, reference_path=args.reference)
        if args.copy_to:
            copied, skipped = copy_ranked_images(results, cutoff, args.copy_to)
            export_report(results, cutoff, args.copy_to, args.mode)
            print(f"Copied {copied} selected images to {args.copy_to}; skipped {skipped} existing files.")
        if args.stack_to:
            if args.mode != "stacking":
                print("--stack-to requires --mode stacking.", file=sys.stderr)
                return 2
            stack_paths = [result.path for result in results if not result.error and result.score >= cutoff]
            aligned, rejected = stack_images(
                args.source,
                args.stack_to,
                image_paths=stack_paths,
                reference_path=args.reference,
            )
            print(f"Stacked {aligned} images and rejected {rejected}; saved to {args.stack_to}")
    PreviewApp(args.source, args.keep_percent, args.mode, args.reference).run()
    return 0
