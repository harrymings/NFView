"""Ui App functionality for NFView."""
from __future__ import annotations
import base64
import queue
import io
import ctypes
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import threading
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk


from nfview.resources import APP_ICON_ICO, APP_ICON_PNG, APP_NAME, CONFIG_FILENAME
from nfview.models import ImageScore
from nfview.platform import configure_display, open_in_photoshop
from nfview.exporting import copy_ranked_images, export_report
from nfview.scanning import folder_signature
from nfview.stacking import stack_images

from nfview.ui.layout import LayoutMixin
from nfview.ui.collections import CollectionsMixin
from nfview.ui.viewer import ViewerMixin
from nfview.ui.browser import BrowserMixin
from nfview.ui.scanning import ScanningMixin
from nfview.ui.interactions import InteractionsMixin
from nfview.ui.dialogs import DialogsMixin
from nfview.ui.layout_extra import LayoutExtraMixin
from nfview.ui.lifecycle import LifecycleMixin
from nfview.ui.panels import PanelsMixin
from nfview.ui.navigation import NavigationMixin

class PreviewApp(LayoutMixin, CollectionsMixin, ViewerMixin, BrowserMixin, ScanningMixin, InteractionsMixin, DialogsMixin, LayoutExtraMixin, LifecycleMixin, PanelsMixin, NavigationMixin):
    def __init__(self, source: Path, keep_percent: float, mode: str, reference_path: Path | None) -> None:
        self.source = source
        self.keep_percent = keep_percent
        self.mode = mode
        self.reference_path = reference_path
        self.results: list[ImageScore] = []
        self.cutoff = float("inf")
        self.settings = {}
        try:
            self.settings = json.loads((source/CONFIG_FILENAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.favourites=set()
        self.locked_photos=set()
        self.custom_lists={}
        self.compare_image=None
        self.compare_name=""
        self.compare_split=0.5
        self.compare_drag=False
        self._load_review_state()
        self.sort_dates={}
        self.sort_task=None
        self.sort_token=0
        self.ranking_sessions={}
        self.mouse_settings={"left_tool":"zoom","right_action":"Pan + click to fit","double_click":"50% zoom","wheel_zoom":True}
        self.mouse_settings.update(self.settings.get("mouse_controls",{}))
        self.editor_path=str(self.settings.get("editor_path",""))
        self.details_visible=True
        self.details_width=max(220,int(self.settings.get("details_width",300)))
        self.filmstrip_visible=self.settings.get("filmstrip_visible",True)
        self.hold_view=None
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = self.closed = False
        self.cache_hits = self.analyzed = self.preview_token = 0
        self.offset = (0.0,0.0)
        self.zoom_job = None
        self.zoom_target=1.0
        self.film_visibility_job=None
        self.visible_film_windows=set()
        self.drag_render_job=None
        self.last_fit=None
        self.preview_rgb=None
        self.preview_item=None
        self.pan_origin=None
        self.histogram_data=None
        self.histogram_message="Select a photo"
        self.focus_boxes=[]
        self.focus_note="Select a photo to see recorded autofocus points."
        self.thumb_pool = ThreadPoolExecutor(max_workers=2)
        self.preview_pool = ThreadPoolExecutor(max_workers=1)
        configure_display()
        self.root = tk.Tk()
        self.display_scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.title(APP_NAME)
        self.app_icon=ImageTk.PhotoImage(Image.open(io.BytesIO(base64.b64decode(APP_ICON_PNG))))
        self.root.iconphoto(True,self.app_icon)
        if sys.platform=="win32":
            try:
                icon_path=Path(tempfile.gettempdir())/"nfview-app-v3.ico"
                icon_path.write_bytes(base64.b64decode(APP_ICON_ICO))
                self.root.iconbitmap(str(icon_path))
                self.root.after(150,lambda:self._set_native_window_icons(icon_path))
            except (OSError,tk.TclError):
                pass
        try:
            self.root.geometry(self.settings.get("geometry", "1500x950"))
        except tk.TclError:
            self.root.geometry("1500x950")
        self.root.minsize(round(850*self.display_scale), round(600*self.display_scale))
        self.thumbnail_images: list[ImageTk.PhotoImage] = []
        self.thumbnail_labels: dict[Path, tk.Label] = {}
        self.thumbnail_generation = 0
        self.thumb_cache={}
        self.thumb_pending=set()
        self.thumb_errors={}
        self.thumb_keys={}
        self.arrange_job=None
        self.thumb_states={}
        self.page_size = 24
        self.page_index = 0
        self.current: ImageScore | None = None
        self.selected_preview: ImageTk.PhotoImage | None = None
        self.selected_image: Image.Image | None = None
        self.zoom = 1.0
        self.card_widgets: dict[Path, tuple[tk.Frame, list[tk.Widget]]] = {}
        self.focused_only = tk.BooleanVar(value=False)
        self.show_focus=tk.BooleanVar(value=False)
        self.view_var=tk.StringVar(value="photo")
        self.mode_var = tk.StringVar(value=mode)
        self.filter_text = tk.StringVar(value="Stackable Only" if mode == "stacking" else "Focused Only")
        self.copy_button_text = tk.StringVar(value="Copy Stackable To..." if mode == "stacking" else "Copy Focused To...")
        self.status = tk.StringVar(value=f"Ready to scan {self.source} ({self.mode} mode).")
        self.count_text = tk.StringVar()
        self.scan_button: ttk.Button
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=1)
        self._build_ui()
        self.root.after(20, self._poll)
        self.root.after(100, self._scan)
        self._setup_drop()

    def _set_native_window_icons(self,path):
        """Give Windows native icons sized for this monitor, avoiding 16/32px stretching."""
        if self.closed:return
        user32=ctypes.windll.user32
        user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        user32.GetAncestor.restype=ctypes.c_void_p
        user32.LoadImageW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
        user32.LoadImageW.restype=ctypes.c_void_p
        user32.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_void_p]
        user32.SendMessageW.restype=ctypes.c_ssize_t
        window=user32.GetAncestor(self.root.winfo_id(),2)
        dpi=round(96*self.display_scale)
        if hasattr(user32,"GetDpiForWindow"):
            user32.GetDpiForWindow.argtypes=[ctypes.c_void_p]
            user32.GetDpiForWindow.restype=ctypes.c_uint
            dpi=user32.GetDpiForWindow(window) or dpi
        self.native_icon_handles=[]
        for kind,logical in ((0,16),(1,32)):
            size=round(logical*dpi/96)
            handle=user32.LoadImageW(None,str(path),1,size,size,0x10)
            if handle:
                self.native_icon_handles.append(handle)
                user32.SendMessageW(window,0x80,kind,handle)
        self.native_icon_dpi=dpi

    def _change_mode(self,event=None):
        selected=self.mode_var.get()
        if self.busy:
            self.mode_var.set(self.mode)
            return
        if selected==self.mode:
            return
        self.mode=selected
        self.filter_text.set("Stackable Only" if selected=="stacking" else "Focused Only")
        self.focused_only.set(False)
        self.busy=True
        self.operation="switch"
        self._status("Checking saved ranking…")
        source,reference=self.source,self.reference_path
        key=self._ranking_key()
        snapshot=self.ranking_sessions.get(key)
        def worker():
            try:
                signature=folder_signature(source,reference)
                reusable=snapshot if snapshot and snapshot[1]==signature else None
                self.events.put(("mode_restore",reusable))
            except Exception as error:
                self.events.put(("failed",str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def _choose_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(initialdir=str(self.source) if self.source.is_dir() else None, title="Choose photo folder")
        if folder:
            self._open_folder(Path(folder))

    def _copy_ranked(self):
        if self.busy or not any(not r.error and r.score>=self.cutoff for r in self.results):
            return
        dialog=tk.Toplevel(self.root)
        dialog.title("Copy recommended photos")
        dialog.configure(bg="#1c222c")
        dialog.transient(self.root)
        dialog.resizable(False,False)
        body=ttk.Frame(dialog,padding=20)
        body.pack(fill="both",expand=True)
        count=sum(not r.error and r.score>=self.cutoff for r in self.results)
        ttk.Label(body,text=f"Copy {count} original photos to a new folder",font=("Segoe UI",12,"bold")).grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(body,text="Your original folder stays untouched. Existing files are never replaced.").grid(row=1,column=0,columnspan=2,sticky="w",pady=(5,16))
        parent_var=tk.StringVar(value=str(self.source.parent))
        default_name=self.source.name+("-stackable" if self.mode=="stacking" else "-focused")
        name_var=tk.StringVar(value=default_name)
        ttk.Label(body,text="Save inside").grid(row=2,column=0,sticky="w")
        ttk.Entry(body,textvariable=parent_var,width=52).grid(row=3,column=0,sticky="ew",pady=5)
        def browse():
            folder=filedialog.askdirectory(parent=dialog,title="Choose where to create the new folder",initialdir=parent_var.get())
            if folder:
                parent_var.set(folder)
        browse_button=ttk.Button(body,text="Browse…",command=browse)
        browse_button.grid(row=3,column=1,padx=(8,0))
        self._tooltip(browse_button,"Choose the parent folder for your copied photos")
        ttk.Label(body,text="New folder name").grid(row=4,column=0,sticky="w",pady=(8,0))
        name_entry=ttk.Entry(body,textvariable=name_var,width=52)
        name_entry.grid(row=5,column=0,columnspan=2,sticky="ew",pady=5)
        reports_var=tk.BooleanVar(value=False)
        reports=ttk.Checkbutton(body,text="Also save a CSV and HTML report",variable=reports_var)
        reports.grid(row=6,column=0,columnspan=2,sticky="w",pady=(10,0))
        self._tooltip(reports,"Optional list of scores and recommendations; not needed to copy photos")
        validation=tk.StringVar()
        ttk.Label(body,textvariable=validation,foreground="#ffc58a",wraplength=470).grid(row=7,column=0,columnspan=2,sticky="w",pady=8)
        def confirm():
            name=name_var.get().strip()
            parent=Path(parent_var.get().strip())
            if not parent.is_dir():
                validation.set("Choose an existing parent folder.")
                return
            reserved={"CON","PRN","AUX","NUL"}|{f"COM{i}" for i in range(1,10)}|{f"LPT{i}" for i in range(1,10)}
            if not name or name in (".","..") or name.split(".")[0].upper() in reserved or any(c in name for c in '<>:"/\\|?*') or name.endswith(("."," ")):
                validation.set("Enter a folder name without special characters.")
                return
            destination=parent/name
            if destination.exists():
                validation.set("That folder already exists. Choose a new name to keep this export separate.")
                return
            if destination.resolve()==self.source.resolve() or self.source.resolve() in destination.resolve().parents:
                validation.set("Choose a location outside the source photo folder so copies are not scanned again.")
                return
            dialog.destroy()
            self._copy_to_folder(destination,reports_var.get())
        buttons=ttk.Frame(body)
        buttons.grid(row=8,column=0,columnspan=2,sticky="e")
        ttk.Button(buttons,text="Cancel",command=dialog.destroy).pack(side="left",padx=6)
        go=ttk.Button(buttons,text=f"Create folder and copy {count} photos",command=confirm,style="Primary.TButton")
        go.pack(side="left")
        self._tooltip(go,"Create the named folder and copy the recommended original files")
        dialog.bind("<Escape>",lambda e:dialog.destroy())
        dialog.bind("<Return>",lambda e:confirm())
        dialog.grab_set()
        name_entry.focus_set()
        name_entry.selection_range(0,"end")

    def _create_stack(self) -> None:
        if self.busy:
            return
        if self.mode != "stacking":
            messagebox.showinfo("Create stack", "Select stacking mode before creating a stack.")
            return
        stack_paths = [result.path for result in self.results if not result.error and result.score >= self.cutoff]
        if len(stack_paths) < 2:
            messagebox.showinfo("Create stack", "At least two stackable images are required.")
            return
        output_name = filedialog.asksaveasfilename(
            initialdir=str(self.source),
            initialfile="stacked_moon.tif",
            defaultextension=".tif",
            filetypes=(("TIFF image", "*.tif"), ("PNG image", "*.png")),
            title="Save stacked image",
        )
        if not output_name:
            return
        output = Path(output_name)
        self.operation="stack"
        self.busy = True
        self._status(f"Aligning and stacking {len(stack_paths)} images")

        def worker() -> None:
            try:
                aligned, rejected = stack_images(
                    self.source,
                    output,
                    image_paths=stack_paths,
                    reference_path=self.reference_path,
                    progress=lambda completed,total,detail: self.events.put(("stack_progress",(completed,total,detail))),
                )
            except Exception as error:
                self.events.put(("failed",str(error)))
                return
            self.events.put(("operation_done",f"Aligned {aligned} images; rejected {rejected}.\n\nSaved to: {output}"))

        threading.Thread(target=worker, daemon=True).start()

    def _bind_filmstrip_scroll(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._scroll_filmstrip, add="+")
        widget.bind("<Shift-MouseWheel>", self._scroll_filmstrip, add="+")
        widget.bind("<Button-4>", self._scroll_filmstrip, add="+")
        widget.bind("<Button-5>", self._scroll_filmstrip, add="+")

    def _scroll_filmstrip(self, event: tk.Event) -> str:
        if getattr(event, "num", None) == 4:
            amount = -3
        elif getattr(event, "num", None) == 5:
            amount = 3
        else:
            amount = -int(event.delta / 120) if event.delta else 0
            if not amount:
                amount = -1 if event.delta > 0 else 1
        if self.view_var.get()=="grid":
            self.film_canvas.yview_scroll(amount,"units")
        else:
            self.film_canvas.xview_scroll(amount, "units")
        return "break"

    def _open(self, result: ImageScore) -> None:
        self._select(result)
        self._open_current()

    def _open_current(self) -> None:
        if self.current is None:
            messagebox.showinfo("Open image", "Select an image first.")
            return
        try:
            if not self.current.path.is_file():
                raise FileNotFoundError("This photo is missing or offline. Reconnect its drive or choose another photo.")
            if self.editor_path:
                editor=Path(self.editor_path)
                if not editor.is_file():
                    raise FileNotFoundError("Your chosen application is unavailable. Choose another application in Edit → Settings, or restore the Photoshop default.")
                subprocess.Popen([str(editor),str(self.current.path.resolve())])
            else:
                open_in_photoshop(self.current.path)
        except OSError as error:
            messagebox.showerror("Could not open image", str(error))

    def _update_info_view(self):
        self.info_view.configure(state="normal")
        self.info_view.delete("1.0","end")
        self.info_view.insert("1.0",self.info_text.get())
        self.info_view.configure(state="disabled")

    def _sync_controls(self):
        if not hasattr(self,"more_menu"):
            return
        recommended=sum(not r.error and r.score>=self.cutoff for r in self.results)
        self.photoshop_button.configure(text=(Path(self.editor_path).stem[:22] if self.editor_path else "Photoshop"))
        self.copy_button_text.set(f"Copy {recommended} photos…" if recommended else "Copy photos…")
        self.count_text.set(f"{recommended} recommended of {len(self.results)}" if self.results else "Open a folder to start")
        for widget,enabled in ((self.copy_button,not self.busy and recommended>0),(self.photoshop_button,self.current is not None),(self.open_button,not self.busy),(self.scan_button,not self.busy),(self.keep_entry,not self.busy),(self.filter_button,not self.busy)):
            widget.state(["!disabled"] if enabled else ["disabled"])
        self.cancel_button.state(["!disabled"] if self.busy and self.scan_button.instate(["disabled"]) and not getattr(self,"operation",None) and not self.cancel_event.is_set() else ["disabled"])
        if hasattr(self,"file_menu"):
            self.file_menu.entryconfigure("Cancel scan",state="normal" if self.busy else "disabled")
            self.file_menu.entryconfigure("Rescan",state="disabled" if self.busy else "normal")
            self.file_menu.entryconfigure("Open folder…",state="disabled" if self.busy else "normal")
            self.file_menu.entryconfigure("Copy recommended photos…",state="normal" if recommended and not self.busy else "disabled")
            self.file_menu.entryconfigure("Open in editor",state="normal" if self.current else "disabled")
            self.file_menu.entryconfigure("Export report…",state="normal" if self.results and not self.busy else "disabled")
        self.more_menu.entryconfigure("Ranking method",state="disabled" if self.busy else "normal")
        self.more_menu.entryconfigure("Create stacked image…",state="normal" if self.mode=="stacking" and recommended>=2 and not self.busy else "disabled")
        self.more_menu.entryconfigure("Export CSV / HTML report…",state="normal" if self.results and not self.busy else "disabled")
        self.more_menu.entryconfigure("Reanalyze every photo…",state="disabled" if self.busy else "normal")
        gallery=self.view_var.get()=="grid"
        self.details_button.state(["disabled"] if gallery else ["!disabled"])
        for tool in self.preview_tool_buttons:
            tool.state(["disabled"] if gallery else ["!disabled"])
        self.fit_button.state(["disabled"] if gallery else ["!disabled"])
        if hasattr(self,"favourite_button"):
            key=self._photo_key(self.current.path) if self.current else None
            self.favourite_button.configure(text="★ Favourite" if key in self.favourites else "☆ Favourite")
            self.lock_button.configure(text="Unlock" if key in self.locked_photos else "Lock")
            self.compare_button.configure(text="End compare" if self.compare_image is not None else "Swipe compare")
            for widget in (self.favourite_button,self.lock_button):
                widget.state(["!disabled"] if self.current else ["disabled"])
            self.compare_button.state(["!disabled"] if (self.selected_image is not None and len(self.results)>1) or self.compare_image is not None else ["disabled"])
        self.keep_label.configure(text="Recommend the most stackable" if self.mode=="stacking" else "Recommend the sharpest")
        self.photo_title.set(self.current.path.name if self.current else "Choose a photo below")
        self.filmstrip_button.state(["disabled"] if gallery else ["!disabled"])
        for control in (self.zoom_in_button,self.zoom_out_button):
            control.state(["!disabled"] if not gallery and self.selected_image is not None else ["disabled"])
        self._sync_reference_preview()
        self.grid_button.state(["disabled"] if gallery else ["!disabled"])
        items=self._browse_results()
        index=next((i for i,r in enumerate(items) if self.current and r.path==self.current.path),-1)
        self.previous_photo_button.state(["!disabled"] if items and index!=0 else ["disabled"])
        self.next_photo_button.state(["!disabled"] if items and index<len(items)-1 else ["disabled"])

    def _scan_info(self):
        self._cache_age()
        messagebox.showinfo("Scan information",f"Folder: {self.source}\n\nMode: {self.mode}\n{self.cache_text.get()}\nReused scores: {self.cache_hits}\nNewly analyzed: {self.analyzed}\n\nRescan checks for changed photos. Reanalyze every photo ignores saved scores. Originals stay untouched.",parent=self.root)

    def _force_rescan(self):
        if messagebox.askokcancel("Reanalyze every photo?","This checks every photo again and may take longer. Your originals stay untouched.",parent=self.root):
            self._scan(force=True)

    def _copy_to_folder(self,destination,include_reports=False):
        results,cutoff,mode=list(self.results),self.cutoff,self.mode
        self.operation="copy"
        self.busy=True
        self._status("Copying photos…")
        def worker():
            try:
                copied,skipped=copy_ranked_images(results,cutoff,destination)
                details=f"Copied {copied} original photos.\n\nNew folder: {destination}"
                if skipped:
                    details+=f"\n{skipped} files with matching names were skipped; nothing was overwritten."
                if include_reports:
                    try:
                        export_report(results,cutoff,destination,mode)
                        details+="\n\nCSV and HTML reports were saved beside the new folder."
                    except OSError:
                        details+="\n\nPhotos were copied, but the optional reports could not be saved."
                self.events.put(("copy_done",(details,destination)))
            except Exception as error:
                self.events.put(("failed",str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


