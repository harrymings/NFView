"""Ui Interactions functionality for NFView."""
from __future__ import annotations
import io
import math
import struct
import tempfile
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageDraw



class InteractionsMixin:
    def _thumbnail_zoom(self,result):
        if self.view_var.get()=="grid":
            self.view_var.set("photo")
            self._change_view()
            self._select(result)
        elif self.current and self.current.path==result.path and self.selected_image is not None:
            self._animate_zoom(2)
        else:
            self._select(result)
            self.pending_zoom=result.path

    def _toggle_filmstrip(self):
        if self.view_var.get()=="grid":
            return
        self.filmstrip_visible=not self.filmstrip_visible
        if self.filmstrip_visible:
            self.film_panel.grid()
            self.root.after_idle(self._ensure_visible)
        else:
            self.film_panel.grid_remove()
        self.filmstrip_text.set("⌄ Hide previews" if self.filmstrip_visible else "⌃ Show previews")
        self._save_settings()

    def _hold_zoom_start(self,event):
        """Left-button vertical drag controls persistent zoom at the press point."""
        if self.selected_image is None or self.hold_view is not None:
            return "break"
        self._dismiss_hint()
        if self.compare_image is not None and abs(event.x-self.main_view.winfo_width()*self.compare_split)<22*self.display_scale:
            self.compare_drag=True
            self.main_view.grab_set()
            self.main_view.configure(cursor="sb_h_double_arrow")
            return "break"
        if self.preview_tool.get()=="pan":
            self.main_view.grab_set()
            return self._pan_start(event)
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job=None
        self.hold_view=(self.zoom,self.offset,self.preview_token,event.x,event.y)
        self.main_view.grab_set()
        self._set_magnifier_cursor()
        return "break"

    def _hold_zoom_move(self,event):
        if self.preview_tool.get()=="pan" and not self.compare_drag:
            return self._pan_move(event)
        if self.compare_drag:
            self.compare_split=max(0.02,min(0.98,event.x/max(1,self.main_view.winfo_width())))
            self._fit_main_preview()
            return "break"
        saved=self.hold_view
        if saved and saved[2]==self.preview_token:
            # Down enlarges, up reduces. Use the original press coordinates,
            # rather than accumulating mouse events, to avoid zoom drift.
            distance=max(-1200,min(1200,event.y-saved[4]))
            low,high=self._zoom_limits()
            self.zoom=min(high,max(low,saved[0]*math.exp(distance/(140*self.display_scale))))
            self.zoom_target=self.zoom
            ratio=self.zoom/saved[0]
            ax=saved[3]-self.main_view.winfo_width()/2
            ay=saved[4]-self.main_view.winfo_height()/2
            self.offset=(ax-(ax-saved[1][0])*ratio,ay-(ay-saved[1][1])*ratio)
            self._schedule_drag_render()
        return "break"

    def _hold_zoom_end(self,event):
        self.pan_origin=None
        self.compare_drag=False
        self.hold_view=None
        self.compare_drag=False
        if self.main_view.grab_current()==self.main_view:
            self.main_view.grab_release()
        self._set_magnifier_cursor()
        if self.drag_render_job:
            self.root.after_cancel(self.drag_render_job)
            self.drag_render_job=None
        self._fit_main_preview()
        return "break"

    def _right_start(self,event):
        self.right_origin=(event.x,event.y)
        self.right_dragged=False
        if self.mouse_settings["right_action"]!="Fit only":
            self._pan_start(event)
        self.main_view.grab_set()
        return "break"

    def _right_move(self,event):
        start=getattr(self,"right_origin",None)
        if start and max(abs(event.x-start[0]),abs(event.y-start[1]))>4*self.display_scale:
            self.right_dragged=True
        if self.right_dragged and self.mouse_settings["right_action"]!="Fit only":
            self._pan_move(event)
        return "break"

    def _right_end(self,event):
        action=self.mouse_settings["right_action"]
        if self.main_view.grab_current()==self.main_view:
            self.main_view.grab_release()
        self.pan_origin=None
        if action=="Fit only" or (action=="Pan + click to fit" and not getattr(self,"right_dragged",False)):
            self._reset_zoom()
        else:
            self._set_magnifier_cursor()
            self._fit_main_preview()
        self.right_origin=None
        return "break"

    def _pan_start(self,event):
        self._dismiss_hint()
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job=None
        self.pan_origin=(event.x,event.y,self.offset)
        self.main_view.configure(cursor="fleur")
        return "break"

    def _pan_move(self,event):
        if self.selected_image is not None and self.zoom>1 and getattr(self,"pan_origin",None):
            x,y,offset=self.pan_origin
            self.offset=(offset[0]+event.x-x,offset[1]+event.y-y)
            self._clamp_pan()
            self._fit_main_preview()
        return "break"

    def _pan_end(self,event):
        self.pan_origin=None
        self._set_magnifier_cursor()
        self._fit_main_preview()
        return "break"

    def _set_preview_tool(self):
        self.hold_view=None
        self.pan_origin=None
        self._set_magnifier_cursor()

    def _set_magnifier_cursor(self):
        """Use the active tool cursor; middle-drag temporarily uses the pan cursor."""
        if hasattr(self,"preview_tool") and self.preview_tool.get()=="pan":
            self.main_view.configure(cursor="fleur")
            return
        try:
            if not hasattr(self,"magnifier_cursor"):
                path=Path(tempfile.gettempdir())/"image-screener-magnifier-v1.cur"
                cursor=Image.new("RGBA",(32,32),(0,0,0,0))
                draw=ImageDraw.Draw(cursor)
                draw.ellipse((2,2,21,21),outline="black",width=5)
                draw.ellipse((3,3,20,20),outline="white",width=2)
                draw.line((19,19,28,28),fill="black",width=7)
                draw.line((19,19,28,28),fill="white",width=3)
                data=io.BytesIO();cursor.save(data,format="ICO",sizes=[(32,32)],bitmap_format="bmp")
                blob=bytearray(data.getvalue());struct.pack_into("<H",blob,2,2);struct.pack_into("<HH",blob,10,11,11)
                path.write_bytes(blob)
                self.magnifier_cursor="@"+path.as_posix()
            self.main_view.configure(cursor=self.magnifier_cursor)
        except (OSError,tk.TclError):
            self.main_view.configure(cursor="crosshair")

    def _preview_fit_scale(self):
        if self.selected_image is None:return 1.0
        iw,ih=self.selected_image.size
        return min(max(1,self.main_view.winfo_width()-20)/iw,max(1,self.main_view.winfo_height()-20)/ih,1.0)

    def _zoom_limits(self):
        fit=self._preview_fit_scale()
        return min(1.0,0.05/fit),max(4.0,4.0/fit)

    def _schedule_drag_render(self):
        # Coalesce mouse messages: never queue old animations behind the pointer.
        if self.drag_render_job is None:
            def render():
                self.drag_render_job=None
                self._fit_main_preview()
            self.drag_render_job=self.root.after(16,render)

    def _double_zoom(self,event):
        action=self.mouse_settings["double_click"]
        if action=="No action":return "break"
        if action=="Fit":return self._reset_zoom(event)
        self.hold_view=None;self.compare_drag=False
        if self.main_view.grab_current()==self.main_view:self.main_view.grab_release()
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job);self.zoom_job=None
        self.last_fit=self._preview_fit_scale()
        target=0.5/self.last_fit
        ratio=target/self.zoom
        ax=event.x-self.main_view.winfo_width()/2;ay=event.y-self.main_view.winfo_height()/2
        self.offset=(ax-(ax-self.offset[0])*ratio,ay-(ay-self.offset[1])*ratio)
        self.zoom=self.zoom_target=target
        self._fit_main_preview()
        self._set_magnifier_cursor()
        return "break"

    def _clamp_pan(self):
        if self.selected_image is None:
            return
        w,h=self.main_view.winfo_width(),self.main_view.winfo_height()
        iw,ih=self.selected_image.size
        fit=min(max(1,w-20)/iw,max(1,h-20)/ih,1.0)
        limit_x=max(0,(iw*fit*self.zoom-w)/2)
        limit_y=max(0,(ih*fit*self.zoom-h)/2)
        self.offset=(max(-limit_x,min(limit_x,self.offset[0])),max(-limit_y,min(limit_y,self.offset[1])))

    def _toggle_focus_points(self):
        self._fit_main_preview()


