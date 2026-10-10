"""Ui Viewer functionality for NFView."""
from __future__ import annotations
from pathlib import Path
import cv2
import exifread
import numpy as np
from PIL import Image, ImageTk


from nfview.models import ImageScore
from nfview.imaging import preview_for
from nfview.metadata import recorded_focus_boxes

class ViewerMixin:
    def _toggle_grid(self):
        self._fit_main_preview()
        self._save_settings()

    def _hide_reference(self):
        self.show_reference.set(False)
        self._reference_visibility()

    def _reference_visibility(self):
        self._sync_reference_preview()
        self._save_settings()

    def _sync_reference_preview(self):
        if self.compare_image is None or not self.show_reference.get() or self.view_var.get()=="grid":
            self.reference_panel.place_forget()
            return
        if self.reference_thumbnail_source is not self.compare_image:
            thumbnail=self.compare_image.copy()
            thumbnail.thumbnail((round(150*self.display_scale),round(105*self.display_scale)),Image.Resampling.LANCZOS)
            self.reference_thumbnail=ImageTk.PhotoImage(thumbnail)
            self.reference_preview.configure(image=self.reference_thumbnail)
            self.reference_thumbnail_source=self.compare_image
        self.reference_caption.configure(text="A · "+self.compare_name)
        self.reference_panel.place(relx=1,rely=1,x=-12,y=-12,anchor="se")
        self.reference_panel.lift()

    def _center_compare(self,event=None):
        if self.compare_image is not None:
            self.compare_split=max(.02,min(.98,.5+self.offset[0]/max(1,self.main_view.winfo_width())))
            self._fit_main_preview()
        return "break"

    def _toggle_compare(self):
        if self.compare_image is not None:
            self.compare_image=None;self.compare_name="";self.compare_drag=False
        elif self.selected_image is not None and self.current is not None:
            self.compare_image=self.selected_image
            self.compare_name=self.current.path.name
            self.compare_split=0.5
            if self.view_var.get()=="grid":
                self.view_var.set("photo");self._change_view()
            items=self._browse_results()
            if len(items)>1:
                index=next((i for i,r in enumerate(items) if r.path==self.current.path),-1)
                self._select(items[(index+1)%len(items)])
        self._fit_main_preview()
        self._sync_controls()

    def _select(self, result):
        if self.current and self.current.path==result.path and self.selected_image is not None:
            return
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job=None
        self.hold_view=None
        self.compare_drag=False
        if self.main_view.grab_current()==self.main_view:
            self.main_view.grab_release()
        self.last_fit=None
        self.preview_rgb=None
        self.preview_item=None
        self.focus_boxes=[]
        self.focus_note="Loading recorded autofocus information…"
        self.zoom_target=1.0
        self.pending_zoom=None
        self.current = result
        self.histogram_data=None
        self.histogram_message="Loading histogram…"
        self._draw_histogram()
        self.selected_image = None
        self.zoom = 1.0
        self.offset = (0.0,0.0)
        self.main_view.delete("all")
        self.info_text.set("Loading photo and camera settings…")
        self._status("Scanning" if self.busy else "Ready")
        self.preview_token += 1
        token = self.preview_token
        def load():
            if token != self.preview_token or self.closed:
                return
            try:
                image = Image.fromarray(preview_for(result.path))
                info = self._image_info(result)
                focus=recorded_focus_boxes(result.path,image.size)
                self.events.put(("preview", (token,result,image,info,focus)))
                pixels=np.asarray(image.convert("RGB"))
                counts=[np.bincount(pixels[:,:,channel].ravel(),minlength=256) for channel in range(3)]
                self.events.put(("histogram",(token,counts)))
            except Exception as error:
                self.events.put(("preview_error", (token,str(error))))
        self.preview_pool.submit(load)
        for item in self.results:
            self._style_card(item)
        self.root.after_idle(self._ensure_visible)

    def _image_info(self, result: ImageScore) -> str:
        try:
            file_size = result.path.stat().st_size / (1024 * 1024)
            try:
                with Image.open(result.path) as image:
                    dimensions = f"{image.width} x {image.height}"
            except Exception:
                height, width = preview_for(result.path).shape[:2]
                dimensions = f"{width} x {height} preview"
        except Exception:
            file_size = 0
            dimensions = "RAW preview dimensions unavailable"
        focus_state = "Recommended for stacking" if self.mode == "stacking" and not result.error and result.score >= self.cutoff else (
            "Recommended" if not result.error and result.score >= self.cutoff else "Review"
        )
        metadata = self._metadata_text(result.path)
        return (
            f"{result.path.name}\n\n"
            f"Recommendation: {focus_state}\n"
            f"{('Alignment' if self.mode == 'stacking' else 'Sharpness')} score: {result.score:.2f}\n"
            f"Dimensions: {dimensions}\n"
            f"File size: {file_size:.1f} MB\n\n"
            f"{metadata}"
        )

    def _metadata_text(self, path: Path) -> str:
        try:
            with path.open("rb") as image_file:
                tags = exifread.process_file(image_file, details=False, stop_tag="UNDEF")
        except (OSError, ValueError):
            return "Camera metadata unavailable"

        fields = (
            ("Image DateTime", "EXIF DateTimeOriginal"),
            ("Camera", "Image Model"),
            ("Lens", "EXIF LensModel"),
            ("Focal Length", "EXIF FocalLength"),
            ("Focus Mode", "MakerNote FocusMode"),
            ("Aperture", "EXIF FNumber"),
            ("Shutter Speed", "EXIF ExposureTime"),
            ("ISO", "EXIF ISOSpeedRatings"),
        )
        def readable(tag, value):
            text = str(value)
            try:
                values = value.values
                first = values[0] if isinstance(values, list) else values
                number = float(first.num) / first.den if hasattr(first, "num") else float(first)
                if tag == "EXIF FNumber":
                    return f"f/{number:g}"
                if tag == "EXIF FocalLength":
                    return f"{number:g} mm"
                if tag == "EXIF ExposureTime":
                    return f"1/{round(1/number)} s" if 0 < number < 1 else f"{number:g} s"
            except (AttributeError, ValueError, TypeError, ZeroDivisionError):
                pass
            if tag == "EXIF DateTimeOriginal" and len(text) >= 10:
                return text[:10].replace(":", "-") + text[10:]
            return text
        lines = [f"{label}: {readable(tag,tags[tag])}" for label, tag in fields if tag in tags]
        return "\n".join(lines) if lines else "Camera metadata unavailable"

    def _load_large_preview(self, result: ImageScore) -> None:
        try:
            image = Image.fromarray(preview_for(result.path))
            self.events.put(("preview", (self.preview_token, result, image, self._image_info(result))))
        except Exception:
            self.events.put(("preview_error", (self.preview_token,"Preview unavailable")))

    def _set_large_preview(self, result: ImageScore, image: Image.Image) -> None:
        if self.current is None or self.current.path != result.path:
            return
        self.selected_image = image
        if getattr(self,"pending_zoom",None)==result.path:
            self.pending_zoom=None
            self._animate_zoom(2)
        self._fit_main_preview()
        self._sync_controls()

    def _fit_main_preview(self):
        if self.selected_image is None or self.current is None:
            return

        self._clamp_pan()
        w,h=max(1,self.main_view.winfo_width()),max(1,self.main_view.winfo_height())
        iw,ih=self.selected_image.size
        fit=min(max(1,w-20)/iw,max(1,h-20)/ih,1.0)
        if self.last_fit is not None and abs(fit-self.last_fit)>1e-8 and abs(self.zoom-1)>.005 and not self.zoom_job:
            ratio=self.last_fit/fit
            self.zoom*=ratio
            self.zoom_target=self.zoom
            if self.hold_view:
                saved=self.hold_view
                self.hold_view=(saved[0]*ratio,*saved[1:])
        self.last_fit=fit
        scale=fit*self.zoom
        self.zoom_text.set("Fit" if abs(self.zoom-1)<.005 else f"{scale*100:.0f}%")
        left=w/2+self.offset[0]-iw*scale/2
        top=h/2+self.offset[1]-ih*scale/2
        if self.preview_rgb is None:
            self.preview_rgb=np.asarray(self.selected_image.convert("RGB"))
        transform=np.array(((scale,0,left),(0,scale,top)),dtype=np.float64)
        pixels=cv2.warpAffine(self.preview_rgb,transform,(w,h),
            flags=cv2.INTER_LINEAR if self.zoom_job or self.pan_origin or self.hold_view or self.compare_drag else cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,borderValue=(8,10,14))
        if self.compare_image is not None:
            rw,rh=self.compare_image.size
            reference_scale=min(max(1,w-20)/rw,max(1,h-20)/rh,1.0)*self.zoom
            reference_transform=np.array(((reference_scale,0,w/2+self.offset[0]-rw*reference_scale/2),(0,reference_scale,h/2+self.offset[1]-rh*reference_scale/2)),dtype=np.float64)
            reference=cv2.warpAffine(np.asarray(self.compare_image.convert("RGB")),reference_transform,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(8,10,14))
            boundary=round(w*self.compare_split)
            pixels[:,:boundary]=reference[:,:boundary]
        # Keep one stable, opaque canvas-sized image. Replace it before releasing
        # the previous PhotoImage, so Windows never sees an empty/partial frame.
        image=ImageTk.PhotoImage(Image.fromarray(pixels))
        item=getattr(self,"preview_item",None)
        if item is None or not self.main_view.type(item):
            item=self.main_view.create_image(0,0,image=image,anchor="nw",tags="photo")
            self.preview_item=item
        else:
            self.main_view.itemconfigure(item,image=image)
        self.selected_preview=image
        self.main_view.tag_lower(item)
        self._draw_focus_points(left,top,iw*scale,ih*scale)
        self.main_view.delete("photo-grid")
        if self.show_grid.get():
            for fraction in (1/3,2/3):
                x=left+iw*scale*fraction;y=top+ih*scale*fraction
                for color,width in (("#080a0e",3),("#dce3eb",1)):
                    self.main_view.create_line(x,max(0,top),x,min(h,top+ih*scale),fill=color,width=width,tags="photo-grid")
                    self.main_view.create_line(max(0,left),y,min(w,left+iw*scale),y,fill=color,width=width,tags="photo-grid")
        self.main_view.delete("compare-overlay")
        if self.compare_image is not None:
            boundary=round(w*self.compare_split)
            self.main_view.create_line(boundary,0,boundary,h,fill="#ecf4ff",width=2,tags="compare-overlay")
            self.main_view.create_text(14,14,anchor="nw",text="A · "+self.compare_name,fill="white",tags="compare-overlay")
            self.main_view.create_text(w-14,14,anchor="ne",text="B · "+self.current.path.name,fill="white",tags="compare-overlay")
            self.main_view.create_rectangle(boundary-10,h/2-20,boundary+10,h/2+20,fill="#2869a6",outline="white",tags="compare-overlay")

    def _draw_histogram(self):
        if not hasattr(self,"histogram"):return
        canvas=self.histogram
        canvas.delete("all")
        w=max(100,canvas.winfo_width());h=max(60,canvas.winfo_height())
        left,right,top,bottom=8,w-8,24,h-18
        if self.histogram_data is None:
            canvas.create_text(w/2,h/2,text=self.histogram_message,fill="#8490a1")
            return
        maximum=max(1,max(int(channel.max()) for channel in self.histogram_data))
        for fraction in (.25,.5,.75):
            y=bottom-(bottom-top)*fraction
            canvas.create_line(left,y,right,y,fill="#28303c")
        for index,(values,color,label) in enumerate(zip(self.histogram_data,("#ef6464","#63c685","#5c9aee"),("R","G","B"))):
            points=[]
            for value,count in enumerate(values):
                points.extend((left+(right-left)*value/255,bottom-(bottom-top)*float(count)/maximum))
            canvas.create_line(*points,fill=color,width=1.5)
            canvas.create_text(left+index*36,10,text=label,anchor="w",fill=color)
        canvas.create_line(left,bottom,right,bottom,fill="#596474")
        canvas.create_text(left,h-7,text="0",anchor="w",fill="#8490a1",font=("Segoe UI",8))
        canvas.create_text(right,h-7,text="255",anchor="e",fill="#8490a1",font=("Segoe UI",8))

    def _show_preview_error(self) -> None:
        self.histogram_data=None
        self.histogram_message="Preview unavailable"
        self._draw_histogram()
        self.main_view.delete("all")
        self.main_view.create_text(
            self.main_view.winfo_width() // 2,
            self.main_view.winfo_height() // 2,
            text="Preview unavailable",
            fill="#d8dee9",
        )

    def _zoom_in(self, event):
        self._animate_zoom(self.zoom*1.35, (event.x,event.y))
        return "break"

    def _reset_zoom(self, event=None):
        self._set_magnifier_cursor()
        self.hold_view=None
        self.compare_drag=False
        if self.main_view.grab_current()==self.main_view:
            self.main_view.grab_release()
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job = None
        self.zoom = 1.0
        self.zoom_target=1.0
        self.offset = (0.0,0.0)
        if event is not None:
            self._dismiss_hint()
        self._fit_main_preview()
        return "break"

    def _zoom_wheel(self,event):
        if not self.mouse_settings["wheel_zoom"]:return "break"
        target=self.zoom_target if self.zoom_job else self.zoom
        self._animate_zoom(target*(1.2 if event.delta>0 else 1/1.2),(event.x,event.y))
        return "break"

    def _draw_focus_points(self,left,top,width,height):
        self.main_view.delete("af-overlay")
        if not self.show_focus.get():
            return
        if not self.focus_boxes:
            self.main_view.create_text(14,14,anchor="nw",text=self.focus_note,fill="#ffbf89",font=("Segoe UI",10),width=max(100,self.main_view.winfo_width()-28),tags="af-overlay")
            return
        for x0,y0,x1,y1 in self.focus_boxes:
            rect=(left+x0*width,top+y0*height,left+x1*width,top+y1*height)
            if rect[2]<0 or rect[3]<0 or rect[0]>self.main_view.winfo_width() or rect[1]>self.main_view.winfo_height():
                continue
            self.main_view.create_rectangle(*rect,outline="#ff3838",width=max(2,round(self.display_scale*1.5)),tags="af-overlay")


