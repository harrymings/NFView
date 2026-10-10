"""Ui Browser functionality for NFView."""
from __future__ import annotations
from datetime import datetime
import hashlib
import json
import os
import threading
import tkinter as tk
import exifread
from PIL import Image, ImageTk


from nfview.models import ImageScore
from nfview.imaging import preview_for

class BrowserMixin:
    def _browse_results(self):
        """Order the browser only; recommendation and analysis order stay intact."""
        items=[r for r in self.results if not self.focused_only.get() or (not r.error and r.score>=self.cutoff)]
        if hasattr(self,"collection"):
            collection=self.collection.get()
            if collection=="Favourites":
                items=[r for r in items if self._photo_key(r.path) in self.favourites]
            elif collection=="Locked":
                items=[r for r in items if self._photo_key(r.path) in self.locked_photos]
            elif collection.startswith("List: "):
                members=self.custom_lists.get(collection[6:],set())
                items=[r for r in items if self._photo_key(r.path) in members]
        method=self.sort_by.get()
        reverse=self.sort_order.get()=="Descending"
        if method=="Score":
            key=lambda r:(r.score,r.path.name.casefold(),str(r.path).casefold())
        elif method=="Filename":
            key=lambda r:(r.path.name.casefold(),str(r.path).casefold())
        else:
            position=0 if method=="Capture date / time" else 1
            key=lambda r:(self.sort_dates.get(r.path,(0,0))[position],r.path.name.casefold())
        return sorted(items,key=key,reverse=reverse)

    def _change_sort(self):
        self._load_sort_dates()
        self._reorder_cards()
        self.root.after(60,self._ensure_visible)
        self._save_settings()

    def _film_xscroll(self,first,last):
        self.film_scroll.set(first,last)
        self._schedule_film_visibility()

    def _schedule_film_visibility(self):
        if not self.closed and self.film_visibility_job is None:
            self.film_visibility_job=self.root.after_idle(self._update_visible_film_windows)

    def _update_visible_film_windows(self):
        self.film_visibility_job=None
        if self.closed or self.view_var.get()=="grid":return
        left=self.film_canvas.canvasx(0)
        right=left+self.film_canvas.winfo_width()
        card_width=round(204*self.display_scale)
        visible={path for path,x in self.photo_positions.items() if x+card_width>=left-card_width and x<=right+card_width}
        for path in self.visible_film_windows-visible:
            window=self.card_windows.get(path)
            if window:self.film_canvas.itemconfigure(window,state="hidden")
        for path in visible-self.visible_film_windows:
            window=self.card_windows.get(path)
            if window:self.film_canvas.itemconfigure(window,state="normal")
        self.visible_film_windows=visible

    def _reorder_cards(self):
        items=self._browse_results()
        for path in self.visible_film_windows:
            window=self.card_windows.get(path)
            if window:self.film_canvas.itemconfigure(window,state="hidden")
        self.visible_film_windows.clear()
        self.card_widgets={r.path:self.card_widgets[r.path] for r in items if r.path in self.card_widgets}
        self._arrange_thumbnails()
        self._sync_controls()

    def _load_sort_dates(self,preload=False):
        if not preload and self.sort_by.get() not in ("Capture date / time","File modified"):
            return
        capture=True
        missing=[r.path for r in self.results if r.path not in self.sort_dates or (capture and self.sort_dates[r.path][2] is False)]
        if not missing or self.sort_task is not None:
            return
        self.sort_token+=1
        token=self.sort_token
        self.sort_task=token
        self.sort_status.set("Reading dates…")
        def worker():
            dates={}
            target=self.source/".image-screener-dates.json"
            try:
                saved=json.loads(target.read_text(encoding="utf-8"))
            except (OSError,ValueError):
                saved={}
            updated=dict(saved) if isinstance(saved,dict) else {}
            for path in missing:
                if self.closed or token!=self.sort_token:
                    return
                try:
                    info=path.stat()
                    modified=info.st_mtime
                    signature=[info.st_size,info.st_mtime_ns]
                except OSError:
                    modified=0;signature=None
                key=self._photo_key(path)
                cached=updated.get(key,{})
                if isinstance(cached,dict) and signature is not None and cached.get("signature")==signature and isinstance(cached.get("taken"),(int,float)):
                    dates[path]=(cached["taken"],modified,True)
                    continue
                taken=modified
                if capture:
                    try:
                        with path.open("rb") as file:
                            tags=exifread.process_file(file,details=False,stop_tag="DateTimeOriginal")
                        value=tags.get("EXIF DateTimeOriginal",tags.get("Image DateTime"))
                        if value:
                            taken=datetime.strptime(str(value)[:19],"%Y:%m:%d %H:%M:%S").timestamp()
                    except (OSError,ValueError,TypeError,OverflowError):
                        pass
                dates[path]=(taken,modified,True)
                updated[key]={"signature":signature,"taken":taken}
            if token!=self.sort_token or self.closed:return
            try:
                temporary=target.with_suffix(".tmp")
                temporary.write_text(json.dumps(updated),encoding="utf-8")
                temporary.replace(target)
            except OSError:
                pass
            self.events.put(("sort_dates",(token,dates)))
        threading.Thread(target=worker,daemon=True).start()

    def _refresh_grid(self) -> None:
        for card,widgets in self.card_widgets.values():
            card.destroy()
        self.film_canvas.delete("thumbnail-window")
        self.visible_film_windows.clear()
        self.film_canvas.delete("empty-state")
        self.photo_positions={}
        self.card_windows={}
        self.thumbnail_images.clear()
        self.thumbnail_labels.clear()
        self.card_widgets.clear()
        self.thumb_states.clear()
        self.thumbnail_generation += 1
        generation = self.thumbnail_generation
        self._load_sort_dates()
        visible_results = self._browse_results()
        page_count = max(1, (len(visible_results) + self.page_size - 1) // self.page_size)
        self.page_index = min(self.page_index, page_count - 1)
        start = self.page_index * self.page_size
        page_results = visible_results
        self.count_text.set(f"{len(visible_results)} shown / {len(self.results)} scanned")
        self.page_text.set(f"{len(visible_results)} photos · scroll to browse")
        self.film_canvas.xview_moveto(0)
        self._sync_controls()
        if not page_results:
            text="No photos match these filters. Choose All photos to see the full folder."
            if self.collection.get().startswith("List: "):
                text="This list is empty. Select a photo and use Lists → Add current photo to."
            self.film_canvas.create_text(20,24,anchor="nw",text=text,fill="#b8c4d5",width=max(200,self.film_canvas.winfo_width()-40),tags="empty-state")
        self._build_card_batches(page_results,generation)
        self._schedule_arrange()

    def _visible_page_count(self) -> int:
        visible_count = sum(
            1 for result in self.results
            if not self.focused_only.get() or (not result.error and result.score >= self.cutoff)
        )
        return max(1, (visible_count + self.page_size - 1) // self.page_size)

    def _build_card_batches(self,results,generation,start=0):
        """Build a long gallery in short UI slices, so scrolling/Cancel stay live."""
        if self.closed or generation!=self.thumbnail_generation:
            return
        batch=results[start:start+24]
        batch=[result for result in batch if result.path not in self.card_widgets]
        self._populate_grid(batch)
        self._load_thumbnails(batch,generation)
        self._schedule_arrange()
        if start+24<len(results):
            self.root.after(12,lambda:self._build_card_batches(results,generation,start+24))
        else:
            self._reorder_cards()

    def _previous_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh_grid()

    def _next_page(self) -> None:
        if self.page_index + 1 < self._visible_page_count():
            self.page_index += 1
            self._refresh_grid()

    def _populate_grid(self, visible_results):
        scale=self.display_scale
        if visible_results:
            self.film_canvas.delete("empty-state")
        columns=max(1,self.film_canvas.winfo_width()//round(212*scale)) if self.view_var.get()=="grid" else self.page_size
        for index,result in enumerate(visible_results,start=len(self.card_widgets)):
            card=tk.Frame(self.grid if self.view_var.get()=="grid" else self.film_canvas,bg="#202733",bd=0,width=round(204*scale),height=round(196*scale),highlightthickness=2,highlightbackground="#202733")
            if self.view_var.get()=="grid":
                card.grid(row=index//columns,column=index%columns,padx=4,pady=4,sticky="nsew")
            else:
                x=index*(round(204*scale)+8)+4
                self.photo_positions[result.path]=x
                self.card_windows[result.path]=self.film_canvas.create_window(x,4,window=card,anchor="nw",tags="thumbnail-window",state="hidden")

            card.pack_propagate(False)
            card.grid_propagate(False)
            # Explicit pixel geometry from the first frame prevents text->image
            # unit changes from moving/repainting neighboring thumbnail widgets.
            placeholder=ImageTk.PhotoImage(Image.new("RGB",(round(184*scale),round(116*scale)),"#080a0e"))
            self.thumbnail_images.append(placeholder)
            image_label=tk.Label(card,image=placeholder,text="Loading…",compound="center",fg="#aeb9c8",bg="#080a0e",bd=0,cursor="hand2")
            image_label.place(x=round(8*scale),y=round(6*scale),width=round(184*scale),height=round(116*scale))
            self.thumbnail_labels[result.path]=image_label
            self.thumb_states[result.path]="loading"
            name=result.path.name if len(result.path.name)<=25 else result.path.stem[:20]+"…"+result.path.suffix
            label=tk.Label(card,text=f"{name}\n{result.score:.2f}",bg="#202733",fg="#edf3fc",font=("Segoe UI",10),cursor="hand2",bd=0)
            label.place(x=round(6*scale),y=round(126*scale),width=round(188*scale),height=round(40*scale))
            badge=tk.Label(card,text="",font=("Segoe UI",9,"bold"),bg="#202733",fg="#edf3fc",bd=0,cursor="hand2")
            badge.place(x=round(6*scale),y=round(172*scale),width=round(188*scale),height=round(18*scale))
            card.lock_badge=tk.Canvas(card,width=round(22*scale),height=round(24*scale),bg="#17202b",highlightthickness=0,cursor="hand2")
            card.lock_badge.create_arc(6*scale,3*scale,16*scale,17*scale,start=0,extent=180,style="arc",outline="#f1f5fa",width=max(2,round(2*scale)))
            card.lock_badge.create_rectangle(4*scale,10*scale,18*scale,21*scale,fill="#f1f5fa",outline="")
            card.lock_badge.create_line(11*scale,14*scale,11*scale,18*scale,fill="#17202b",width=max(1,round(2*scale)))
            card.lock_badge.bind("<Button-1>",lambda event,item=result:self._select(item))
            self._bind_filmstrip_scroll(card.lock_badge)
            self._tooltip(card.lock_badge,"Locked: favourite status and list memberships are protected; unlock before editing or deleting")
            widgets=[card,image_label,label,badge]
            self.card_widgets[result.path]=(card,widgets)
            for widget in widgets:
                self._bind_filmstrip_scroll(widget)
                widget.bind("<Button-1>",lambda event,item=result:(self._dismiss_hint(),self._select(item)))
                widget.bind("<Double-Button-1>",lambda event,item=result:self._thumbnail_zoom(item))
            self._style_card(result)
            self._tooltip(card,result.path.name+" · Select (← / →); double-click to enlarge")

    def _load_thumbnails(self, visible_results, generation):
        cache_root=self.source/".image-screener-previews"
        def load(result,key):
            try:
                name=hashlib.sha256(repr(key).encode("utf-8")).hexdigest()
                cached_path=cache_root/(name+".thumb")
                try:
                    with Image.open(cached_path) as cached:
                        image=cached.convert("RGB")
                except (OSError,ValueError):
                    image=Image.fromarray(preview_for(result.path))
                    image.thumbnail((round(184*self.display_scale),round(116*self.display_scale)),Image.Resampling.LANCZOS)
                    try:
                        cache_root.mkdir(exist_ok=True)
                        temporary=cached_path.with_name(name+f".{os.getpid()}.{threading.get_ident()}.tmp")
                        image.save(temporary,format="PNG")
                        temporary.replace(cached_path)
                    except OSError:
                        pass  # Read-only photo folders still support memory caching.
                # .thumb files cannot enter discover_images' supported extensions.
                # This display cache is independent of version 3 analysis scores.
                self.events.put(("thumb_cached",(result,key,image)))
            except Exception as error:
                self.events.put(("thumb_failed",(result,key,str(error))))
        for result in visible_results:
            try:
                stat=result.path.stat()
                key=(result.path,stat.st_size,stat.st_mtime_ns,round(self.display_scale,2))
            except OSError:
                self._set_thumbnail_error(result,generation)
                continue
            self.thumb_keys[result.path]=key
            cached=self.thumb_cache.get(key)
            if cached is not None:
                self._set_thumbnail(result,cached,generation)
            elif key in self.thumb_errors:
                self._set_thumbnail_error(result,generation)
            elif key not in self.thumb_pending:
                self.thumb_pending.add(key)
                self.thumb_pool.submit(load,result,key)

    def _set_thumbnail(self, result: ImageScore, image: Image.Image, generation: int) -> None:
        if generation != self.thumbnail_generation:
            return
        label = self.thumbnail_labels.get(result.path)
        if label is None or not label.winfo_exists():
            return
        background=Image.new("RGB",(round(184*self.display_scale),round(116*self.display_scale)),"#080a0e")
        background.paste(image,((background.width-image.width)//2,(background.height-image.height)//2))
        thumbnail = ImageTk.PhotoImage(background)
        self.thumbnail_images.append(thumbnail)
        label.configure(image=thumbnail, text="", width=round(184*self.display_scale), height=round(116*self.display_scale))
        self.thumb_states[result.path]="ready"
        self._thumbnail_status()

    def _set_thumbnail_error(self, result: ImageScore, generation: int) -> None:
        if generation != self.thumbnail_generation:
            return
        label = self.thumbnail_labels.get(result.path)
        if label is not None and label.winfo_exists():
            label.configure(text="Preview unavailable", image="")
            self.thumb_states[result.path]="error"
            self._thumbnail_status()

    def _thumbnail_status(self):
        ready=sum(state=="ready" for state in self.thumb_states.values())
        failed=sum(state=="error" for state in self.thumb_states.values())
        total=len(self.thumb_states)
        self.thumbnail_progress.set(f"Previews: {ready}/{total}"+(f" · {failed} unavailable" if failed else ""))

    def _style_card(self, result: ImageScore) -> None:
        card_entry = self.card_widgets.get(result.path)
        if card_entry is None:
            return
        card, widgets = card_entry
        selected = self.current is not None and self.current.path == result.path
        focused = not result.error and result.score >= self.cutoff
        card_color = "#2878d8" if selected else ("#203c32" if focused else "#202733")
        text_color = "#edf3fc"
        card.configure(bg=card_color,highlightbackground=card_color)
        for widget in widgets[1:]:
            widget.configure(bg=card_color, fg=text_color)
        recommended = "STACKABLE" if self.mode == "stacking" else "FOCUSED"
        state="SELECTED" if selected else (recommended if focused else "")
        key=self._photo_key(result.path)
        flags="★ " if key in self.favourites else ""
        if key in self.locked_photos:
            card.lock_badge.place(x=round(166*self.display_scale),y=round(10*self.display_scale))
            tk.Misc.lift(card.lock_badge)
        else:
            card.lock_badge.place_forget()
        widgets[-1].configure(text=flags+state)


