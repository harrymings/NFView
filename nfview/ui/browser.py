"""Ui Browser functionality for NFView."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
import threading
import exifread
from PIL import Image, ImageTk


from nfview.models import ImageScore
from nfview.imaging import preview_for

@dataclass
class ThumbnailCard:
    tag: str
    background: int
    image: int
    message: int
    badge: int
    photo: ImageTk.PhotoImage | None = None


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
        if self.closed:
            return
        canvas = self.film_canvas
        columns = self.browser_columns
        stride = self.card_row_height
        top = max(0, int(canvas.canvasy(0)))
        first = max(0, top // stride - 1) * columns
        stop = ((top + canvas.winfo_height()) // stride + 2) * columns
        visible = self.browser_items[first:stop]
        wanted = {item.path for item in visible}
        for path in self.card_widgets.keys() - wanted:
            canvas.delete(self.card_widgets.pop(path).tag)
            self.thumb_states.pop(path)
            key = self.thumb_keys.pop(path, None)
            future = self.thumb_pending.get(key)
            if future is not None and future.cancel():
                del self.thumb_pending[key]
        missing = []
        for index, item in enumerate(visible, first):
            row, column = divmod(index, columns)
            x = 4 + column * self.card_column_width
            y = 4 + row * stride
            card = self.card_widgets.get(item.path)
            if card is None:
                self._create_thumbnail_card(item, x, y)
                missing.append(item)
            else:
                old_x, old_y = canvas.coords(card.background)[:2]
                if (old_x, old_y) != (x, y):
                    canvas.move(card.tag, x - old_x, y - old_y)
        self._load_thumbnails(missing, self.thumbnail_generation)
        self._thumbnail_status()

    def _reorder_cards(self):
        self.browser_items = self._browse_results()
        self.browser_indices = {item.path: index for index, item in enumerate(self.browser_items)}
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
        self.film_canvas.delete("thumbnail")
        self.film_canvas.delete("empty-state")
        self.card_widgets.clear()
        for key, future in list(self.thumb_pending.items()):
            if future.cancel():
                del self.thumb_pending[key]
        self.thumb_keys.clear()
        self.thumb_states.clear()
        self.thumbnail_generation += 1
        self._load_sort_dates()
        self.film_canvas.yview_moveto(0)
        self._reorder_cards()
        count = len(self.browser_items)
        self.count_text.set(f"{count} shown / {len(self.results)} scanned")
        self.page_text.set(f"{count} photos · scroll to browse")
        if not count:
            text="No photos match these filters. Choose All photos to see the full folder."
            if self.collection.get().startswith("List: "):
                text="This list is empty. Select a photo and use Lists → Add current photo to."
            self.film_canvas.create_text(20,24,anchor="nw",text=text,fill="#b8c4d5",width=max(200,self.film_canvas.winfo_width()-40),tags="empty-state")

    def _visible_page_count(self) -> int:
        visible_count = sum(
            1 for result in self.results
            if not self.focused_only.get() or (not result.error and result.score >= self.cutoff)
        )
        return max(1, (visible_count + self.page_size - 1) // self.page_size)

    def _previous_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh_grid()

    def _next_page(self) -> None:
        if self.page_index + 1 < self._visible_page_count():
            self.page_index += 1
            self._refresh_grid()

    def _thumbnail_click(self, event, enlarge=False):
        canvas = self.film_canvas
        x = int(canvas.canvasx(event.x)) - 4
        y = int(canvas.canvasy(event.y)) - 4
        column, dx = divmod(x, self.card_column_width)
        row, dy = divmod(y, self.card_row_height)
        if not (0 <= column < self.browser_columns and row >= 0):
            return
        index = row * self.browser_columns + column
        if dx >= self.card_column_width - 8 or dy >= self.card_row_height - 8 or index >= len(self.browser_items):
            return
        item = self.browser_items[index]
        self._dismiss_hint()
        if enlarge:
            self._thumbnail_zoom(item)
        else:
            self._select(item)

    def _create_thumbnail_card(self, result, x, y):
        canvas = self.film_canvas
        scale = self.display_scale
        canvas.delete("empty-state")
        background = canvas.create_rectangle(x, y, x + self.card_column_width - 8,
                                              y + self.card_row_height - 8, width=0, tags="thumbnail")
        tag = f"card-{background}"
        canvas.addtag_withtag(tag, background)
        tags = ("thumbnail", tag)
        center = x + round(102 * scale)
        image_y = y + round(64 * scale)
        image = canvas.create_image(center, image_y, tags=tags)
        message = canvas.create_text(center, image_y, text="Loading…", fill="#afb4b5", tags=tags)
        name = result.path.name
        if len(name) > 25:
            name = result.path.stem[:20] + "…" + result.path.suffix
        canvas.create_text(center, y + round(146 * scale), text=f"{name}\n{result.score:.2f}",
                           justify="center", fill="#edf3fc", font=("Segoe UI", 10), tags=tags)
        badge = canvas.create_text(center, y + round(181 * scale), fill="#edf3fc",
                                   font=("Segoe UI", 9, "bold"), tags=tags)
        canvas.create_text(x + round(185 * scale), y + round(17 * scale), text="🔒",
                           fill="white", tags=(*tags, tag + "-lock"))
        self.card_widgets[result.path] = ThumbnailCard(tag, background, image, message, badge)
        self.thumb_states[result.path] = "loading"
        self._style_card(result)

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
                self.thumb_pending[key] = self.thumb_pool.submit(load,result,key)

    def _set_thumbnail(self, result: ImageScore, image: Image.Image, generation: int) -> None:
        if generation != self.thumbnail_generation:
            return
        card = self.card_widgets.get(result.path)
        if card is None:
            return
        card.photo = ImageTk.PhotoImage(image)
        self.film_canvas.itemconfigure(card.image, image=card.photo)
        self.film_canvas.itemconfigure(card.message, text="")
        self.thumb_states[result.path]="ready"
        self._thumbnail_status()

    def _set_thumbnail_error(self, result: ImageScore, generation: int) -> None:
        if generation != self.thumbnail_generation:
            return
        card = self.card_widgets.get(result.path)
        if card is not None:
            self.film_canvas.itemconfigure(card.message, text="Preview unavailable")
            self.thumb_states[result.path]="error"
            self._thumbnail_status()

    def _thumbnail_status(self):
        ready=sum(state=="ready" for state in self.thumb_states.values())
        failed=sum(state=="error" for state in self.thumb_states.values())
        total=len(self.thumb_states)
        self.thumbnail_progress.set(f"Visible previews: {ready}/{total}"+(f" · {failed} unavailable" if failed else ""))

    def _style_card(self, result: ImageScore) -> None:
        card_entry = self.card_widgets.get(result.path)
        if card_entry is None:
            return
        card = card_entry
        selected = self.current is not None and self.current.path == result.path
        focused = not result.error and result.score >= self.cutoff
        card_color = "#3f5140" if selected else ("#203c32" if focused else "#24282b")
        self.film_canvas.itemconfigure(card.background, fill=card_color)
        recommended = "STACKABLE" if self.mode == "stacking" else "FOCUSED"
        state="SELECTED" if selected else (recommended if focused else "")
        key=self._photo_key(result.path)
        flags="★ " if key in self.favourites else ""
        self.film_canvas.itemconfigure(card.tag + "-lock", state="normal" if key in self.locked_photos else "hidden")
        self.film_canvas.itemconfigure(card.badge, text=flags + state)
