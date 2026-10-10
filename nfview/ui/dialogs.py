"""Ui Dialogs functionality for NFView."""
from __future__ import annotations
import base64
import webbrowser
import io
import time
import json
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk


from nfview.resources import APP_ICON_PNG, CACHE_FILENAME, CONFIG_FILENAME
from nfview.exporting import export_report

class DialogsMixin:
    def _mouse_preferences(self):
        dialog=tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.configure(bg="#1c222c")
        dialog.transient(self.root)
        dialog.resizable(False,False)
        body=ttk.Frame(dialog,padding=18)
        body.pack(fill="both",expand=True)
        values={}
        choices=(("Left-drag tool","left_tool",("zoom","pan")),
                 ("Right button","right_action",("Pan + click to fit","Pan only","Fit only")),
                 ("Double left-click","double_click",("50% zoom","Fit","No action")))
        for row,(label,key,options) in enumerate(choices):
            ttk.Label(body,text=label).grid(row=row,column=0,sticky="w",padx=(0,18),pady=7)
            values[key]=tk.StringVar(value=self.preview_tool.get() if key=="left_tool" else self.mouse_settings[key])
            ttk.Combobox(body,textvariable=values[key],values=options,state="readonly",width=24).grid(row=row,column=1,sticky="ew",pady=7)
        wheel=tk.BooleanVar(value=self.mouse_settings["wheel_zoom"])
        ttk.Checkbutton(body,text="Mouse wheel zooms toward the pointer",variable=wheel).grid(row=3,column=0,columnspan=2,sticky="w",pady=10)
        ttk.Label(body,text="Middle-drag always pans. Fit button and 0 always reset zoom.").grid(row=4,column=0,columnspan=2,pady=8)
        ttk.Separator(body).grid(row=5,column=0,columnspan=2,sticky="ew",pady=10)
        ttk.Label(body,text="Open photos with").grid(row=6,column=0,sticky="w")
        editor_value=tk.StringVar(value=self.editor_path)
        editor_field=ttk.Entry(body,textvariable=editor_value,width=38)
        editor_field.grid(row=6,column=1,sticky="ew",pady=5)
        editor_actions=ttk.Frame(body);editor_actions.grid(row=7,column=1,sticky="w")
        def choose_editor():
            chosen=filedialog.askopenfilename(title="Choose photo application",filetypes=[("Applications","*.exe"),("All files","*.*")],parent=dialog)
            if chosen:editor_value.set(chosen)
        ttk.Button(editor_actions,text="Choose app…",command=choose_editor).pack(side="left",padx=(0,4))
        ttk.Button(editor_actions,text="Default: Photoshop",command=lambda:editor_value.set("")).pack(side="left")
        ttk.Label(body,text="Leave blank for automatic Photoshop detection and association fallback.").grid(row=8,column=0,columnspan=2,pady=8)
        actions=ttk.Frame(body);actions.grid(row=9,column=0,columnspan=2,sticky="e",pady=(12,0))
        def apply():
            chosen=editor_value.get().strip()
            if chosen and (not Path(chosen).is_file() or (sys.platform=="win32" and Path(chosen).suffix.lower()!=".exe")):
                messagebox.showerror("Choose an application","Choose an existing application (.exe), or leave blank to use Photoshop.",parent=dialog)
                return
            self.editor_path=chosen
            self.mouse_settings.update({key:value.get() for key,value in values.items()})
            self.mouse_settings["wheel_zoom"]=wheel.get()
            self.preview_tool.set(self.mouse_settings["left_tool"])
            self._set_preview_tool()
            self._sync_controls()
            self._save_settings()
            dialog.destroy()
        ttk.Button(actions,text="Cancel",command=dialog.destroy).pack(side="left",padx=4)
        ttk.Button(actions,text="Save",command=apply).pack(side="left",padx=4)
        dialog.bind("<Escape>",lambda e:dialog.destroy())
        dialog.grab_set()

    def _cache_age(self):
        try:
            hours = max(0,(time.time()-(self.source/CACHE_FILENAME).stat().st_mtime)/3600)
            self.cache_text.set(f"Cache: {hours:.1f}h old")
        except OSError:
            self.cache_text.set("No folder cache yet")

    def _save_settings(self):
        self.settings.update(editor_path=self.editor_path,show_grid=self.show_grid.get(),show_reference=self.show_reference.get(),mouse_controls=dict(self.mouse_settings,left_tool=self.preview_tool.get()),details_width=self.details_width,last_folder=str(self.source),keep_percent=self.keep_percent,mode=self.mode,geometry=self.root.geometry(),filmstrip_visible=self.filmstrip_visible,sort_by=self.sort_by.get(),sort_order=self.sort_order.get())
        try:
            target = self.source/CONFIG_FILENAME
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.settings,indent=2),encoding="utf-8")
            temporary.replace(target)
            # A small launch locator restores the last folder when no CLI folder is supplied.
            locator = Path(sys.executable if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[2] / "image_screener.py").parent/CONFIG_FILENAME
            if locator != target:
                locator.write_text(json.dumps(self.settings,indent=2),encoding="utf-8")
        except OSError:
            self.cache_text.set("Settings not saved: folder is read-only")

    def _close(self):
        self._save_settings()
        self.closed = True
        self.cancel_event.set()
        # Tk retains timer scripts after destroying widgets; remove them first.
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(job)
        self.thumb_pool.shutdown(wait=False,cancel_futures=True)
        self.preview_pool.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()

    def _export(self):
        if self.busy or not self.results:
            messagebox.showinfo("Export report","Finish a scan before exporting a report.")
            return
        filename = filedialog.asksaveasfilename(title="Choose report name",initialdir=str(self.source),initialfile="culling-report.csv",defaultextension=".csv",filetypes=[("CSV report","*.csv")])
        if filename:
            try:
                path = Path(filename)
                reports = export_report(self.results,self.cutoff,path.with_suffix(""),self.mode,report_base=path.with_suffix(""))
                # export_report adds a descriptive suffix for copy destinations.
                messagebox.showinfo("Report saved", "\n".join(map(str,reports)))
            except OSError as error:
                messagebox.showerror("Could not save report",str(error))

    def _help(self,tab="Start here"):
        existing=getattr(self,"help_window",None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            self.help_tabs.select(self.help_pages[tab])
            return
        dialog=tk.Toplevel(self.root)
        self.help_window=dialog
        dialog.title("NFView — User guide")
        dialog.configure(bg="#1c222c")
        dialog.transient(self.root)
        width=min(round(760*self.display_scale),dialog.winfo_screenwidth()-80)
        height=min(round(560*self.display_scale),dialog.winfo_screenheight()-100)
        dialog.geometry(f"{width}x{height}")
        dialog.minsize(min(width,600),min(height,420))
        header=ttk.Frame(dialog,padding=(20,16,20,10));header.pack(fill="x")
        ttk.Label(header,text="NFView",font=("Segoe UI",20,"bold")).pack(anchor="w")
        ttk.Label(header,text="Review quickly. Keep the photos that matter.",font=("Segoe UI",12)).pack(anchor="w",pady=(4,0))
        footer=ttk.Frame(dialog,padding=(16,4,16,12));footer.pack(side="bottom",fill="x")
        ttk.Button(footer,text="Close",command=dialog.destroy).pack(side="right")
        tabs=ttk.Notebook(dialog,style="Guide.TNotebook")
        tabs.pack(fill="both",expand=True,padx=16,pady=8)
        self.help_tabs=tabs;self.help_pages={}
        pages={
            "Start here": [
                ("1  Open a folder","File → Open folder, or Ctrl+O. Photos in subfolders are included."),
                ("2  Review your photos","Choose a recommendation percentage. Browse every photo, or use Focused Only to see recommendations. Sort and filter without rescanning."),
                ("3  Keep your picks","Copy photos creates a new folder containing recommended originals. Favourites and custom lists help organise your review; they do not change what Copy photos includes."),
                ("Deleting a photo","Select a photo and press Delete. Confirm to move its original to the Recycle Bin. Unlock protected photos first.")],
            "Controls": [
                ("Zoom and pan","Choose Zoom or Pan beside the zoom controls. Zoom: left-drag down to enlarge, up to reduce. Pan: left-drag to move an enlarged photo. Release keeps the view."),
                ("Default mouse controls","Wheel zooms toward the pointer. Double-click jumps to 50%. Middle- or right-drag pans. A right-click without dragging fits the photo."),
                ("Make it yours","Edit → Settings changes mouse controls and the application used to open originals. Photoshop is the default."),
                ("Adjust your workspace","Drag the divider beside Photo details to resize it. Hide the browser with Hide previews. View → Panels restores hidden panels.")],
            "Shortcuts": [
                ("Browse","← / →  Previous / next photo\nCtrl+O  Open folder     S  Rescan\nF  Recommended-only filter     Esc  Deselect"),
                ("Inspect","+ / −  Zoom in / out     0  Fit photo\nC  Start / end swipe comparison     ?  User guide"),
                ("Organise","P  Favourite     L  Lock / unlock\nDelete  Move selected original to Recycle Bin (confirmation required)")],
            "Review tools": [
                ("Swipe compare","Select a photo and click Swipe compare (C). It becomes reference A; browse a second photo B. Drag the centre divider to reveal either photo. Double-click the small reference preview to centre the divider; × hides the preview."),
                ("Favourites, locks and lists","Show filters favourites, locked photos and custom lists. Lists manages memberships. Lock protects favourite status and list memberships; unlock before editing or deleting."),
                ("Understanding scores","A higher sharpness score means more fine contrast in the photo centre. Compare similar photos: texture and noise can also raise scores. The percentage controls recommendations; ties are included."),
                ("Stacking and cache","Tools → Ranking method offers stacking suitability using ORB + RANSAC. Unchanged photos reuse cached scores. Cancel stops after the current photo. Optional reports, full reanalysis and stack creation remain in Tools."),
                ("Histogram and guides","The RGB histogram shows dark pixels on the left and bright pixels on the right. Grid lines and recorded focus points are viewing aids; they do not change scores.")],
            "About": [("NFView","A desktop photo-review and culling app. RAW analysis uses embedded previews; copying preserves originals. Deleting is an explicit, confirmed Recycle Bin action."),
                      ("GitHub","https://github.com/harrymings")]
        }
        for name,sections in pages.items():
            page=ttk.Frame(tabs,padding=12)
            tabs.add(page,text=name);self.help_pages[name]=page
            if name=="About":
                self.help_about_icon=ImageTk.PhotoImage(Image.open(io.BytesIO(base64.b64decode(APP_ICON_PNG))).resize((round(80*self.display_scale),round(80*self.display_scale)),Image.Resampling.LANCZOS))
                ttk.Label(page,image=self.help_about_icon).pack(anchor="w",pady=(0,8))
                ttk.Button(page,text="GitHub · harrymings ↗",command=lambda:webbrowser.open("https://github.com/harrymings")).pack(anchor="w",pady=(0,10))
            scroll=ttk.Scrollbar(page)
            scroll.pack(side="right",fill="y")
            text=tk.Text(page,wrap="word",bg="#1c222c",fg="#e7ecf4",font=("Segoe UI",12),relief="flat",highlightthickness=0,padx=6,pady=6,spacing1=3,spacing3=9,yscrollcommand=scroll.set,cursor="arrow")
            text.pack(fill="both",expand=True);scroll.configure(command=text.yview)
            text.tag_configure("heading",font=("Segoe UI",13,"bold"),foreground="#88c5ff",spacing1=12,spacing3=5)
            for heading,body in sections:
                text.insert("end",heading+"\n","heading")
                text.insert("end",body+"\n\n")
            text.configure(state="disabled")
        tabs.select(self.help_pages[tab])
        dialog.bind("<Escape>",lambda e:dialog.destroy())

    def _setup_drop(self):
        try:
            import tkinterdnd2
            from tkinterdnd2 import DND_FILES
            self.root.TkdndVersion = tkinterdnd2.TkinterDnD._require(self.root)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", lambda e: self._open_folder(Path(self.root.tk.splitlist(e.data)[0])))
        except (ImportError, tk.TclError, RuntimeError):
            pass


