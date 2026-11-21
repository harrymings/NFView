"""Ui Navigation functionality for NFView."""
from __future__ import annotations
import time
import math
import tkinter as tk
from tkinter import ttk



class NavigationMixin:
    def _shortcut(self,event,action):
        if isinstance(event.widget,(tk.Entry,ttk.Entry,ttk.Combobox)) and event.keysym != "Escape":
            return
        self._dismiss_hint()
        action()
        return "break"

    def _toggle_filter(self):
        if self.busy:
            return
        self.focused_only.set(not self.focused_only.get())
        self._refresh_grid()

    def _show_all_photos(self):
        """Clear both recommendation and collection filters without scanning."""
        self.collection.set("All photos")
        self.focused_only.set(False)
        self.page_index=0
        self._refresh_grid()
        self._status("Showing all photos" if not self.busy else "Scanning; showing all completed photos")

    def _navigate(self,direction):
        items = self._browse_results()
        if not items:
            return
        index = next((i for i,r in enumerate(items) if self.current and r.path==self.current.path),-1)
        index = max(0,min(len(items)-1,index+direction))
        self._select(items[index])

    def _ensure_visible(self):
        index = self.browser_indices.get(self.current.path) if self.current else None
        if index is None:
            return
        top = (index // self.browser_columns) * self.card_row_height
        bottom = top + self.card_row_height
        rows = (len(self.browser_items) + self.browser_columns - 1) // self.browser_columns
        height = rows * self.card_row_height
        start = self.film_canvas.canvasy(0)
        viewport = self.film_canvas.winfo_height()
        if top < start:
            self.film_canvas.yview_moveto(top / height)
        elif bottom > start + viewport:
            self.film_canvas.yview_moveto(max(0, bottom - viewport) / height)

    def _deselect(self):
        self.preview_token += 1
        self.current = self.selected_image = None
        self.histogram_data=None
        self.histogram_message="Select a photo"
        self._draw_histogram()
        self._reset_zoom()
        self.main_view.delete("all")
        self.info_text.set("Select a thumbnail to inspect a photograph.")
        for result in self.results:
            self._style_card(result)
        self._status("Scanning" if self.busy else "Ready")

    def _animate_zoom(self,target,anchor=None,restore_offset=None,duration=0.22):
        if self.selected_image is None:
            return
        self._dismiss_hint()
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
        low,high=self._zoom_limits()
        target=min(high,max(low,target))
        self.zoom_target=target
        start=self.zoom
        old_offset=self.offset
        anchor=anchor or (self.main_view.winfo_width()/2,self.main_view.winfo_height()/2)
        ax=anchor[0]-self.main_view.winfo_width()/2
        ay=anchor[1]-self.main_view.winfo_height()/2
        began=time.monotonic()
        token=self.preview_token
        def frame():
            if token!=self.preview_token or self.selected_image is None or self.closed:
                self.zoom_job=None
                return
            t=min(1,(time.monotonic()-began)/duration)
            eased=1-(1-t)**3
            self.zoom=start*math.exp(math.log(target/start)*eased)
            ratio=self.zoom/start
            self.offset=(ax-(ax-old_offset[0])*ratio,ay-(ay-old_offset[1])*ratio) if abs(target-1)>.005 else (old_offset[0]*(1-eased),old_offset[1]*(1-eased))
            if restore_offset is not None:
                self.offset=tuple(old_offset[i]+(restore_offset[i]-old_offset[i])*eased for i in range(2))
            self.zoom_job=self.root.after(16,frame) if t<1 else None
            self._fit_main_preview()
        frame()

    def _dismiss_hint(self):
        if not self.settings.get("hint_seen"):
            self.settings["hint_seen"] = True
            self.settings["gesture_version"] = 5
            def fade(step=0):
                if self.closed:
                    return
                if step>=8:
                    self.hint.pack_forget()
                    return
                value = 180-step*18
                self.hint.configure(fg=f"#{value:02x}{value:02x}{value:02x}")
                self.root.after(45,lambda:fade(step+1))
            fade()


