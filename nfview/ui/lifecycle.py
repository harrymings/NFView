"""Ui Lifecycle functionality for NFView."""
from __future__ import annotations
import queue
import time
import os
from tkinter import messagebox



class LifecycleMixin:
    def _poll(self):
        if self.closed:
            return
        deadline = time.monotonic()+0.012
        dirty = False
        while time.monotonic()<deadline:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "result":
                self.results.append(data)
                dirty = True
            elif kind == "progress":
                self._update_scan_progress(*data)
            elif kind == "finished":
                dirty = False
                self._scan_finished(*data)
            elif kind == "mode_restore":
                selected_path=self.current.path if self.current else None
                self._end_busy()
                if data is None:
                    self._scan()
                else:
                    self.results=list(data[0])
                    self.current=None
                    self.cache_hits,self.analyzed=data[2:4]
                    self._apply_keep(refresh=False)
                    self.page_index=0
                    self._refresh_grid()
                    item=next((r for r in self.results if r.path==selected_path),None) or next((r for r in self.results if not r.error),None)
                    if item:
                        self._select(item)
                    self._status("Saved ranking restored; no rescan")
                    self._save_settings()
            elif kind == "cancelled":
                self._end_busy()
                self._apply_keep()
                self._status("Cancelled; partial results available")
                dirty = False
            elif kind == "failed":
                self._end_busy()
                messagebox.showerror("Could not finish", data)
                self._status("Ready")
            elif kind == "thumb_cached":
                result,key,preview=data
                self.thumb_pending.discard(key)
                self.thumb_cache[key]=preview
                if self.thumb_keys.get(result.path)==key:
                    self._set_thumbnail(result,preview,self.thumbnail_generation)
            elif kind == "thumb_failed":
                result,key,error=data
                self.thumb_pending.discard(key)
                self.thumb_errors[key]=error
                if self.thumb_keys.get(result.path)==key:
                    self._set_thumbnail_error(result,self.thumbnail_generation)
            elif kind == "thumb":
                self._set_thumbnail(*data)
            elif kind == "thumb_error":
                self._set_thumbnail_error(*data)
            elif kind == "sort_dates":
                token,dates=data
                if token==self.sort_token:
                    self.sort_task=None
                    self.sort_dates.update(dates)
                    self.sort_status.set("")
                    if self.sort_by.get() in ("Capture date / time","File modified"):
                        self._reorder_cards()
                        self.root.after(60,self._ensure_visible)
            elif kind == "preview":
                token,result,image,info,*focus = data
                if token == self.preview_token:
                    if focus:
                        self.focus_boxes,self.focus_note=focus[0]
                        info+="\n\nAutofocus: "+self.focus_note
                    self.info_text.set(info)
                    self._set_large_preview(result,image)
            elif kind == "histogram":
                token,counts=data
                if token==self.preview_token:
                    self.histogram_data=counts
                    self._draw_histogram()
            elif kind == "preview_error":
                if data[0] == self.preview_token:
                    self._show_preview_error()
                    self.info_text.set("Photo unavailable or offline.\n\n"+data[1])
            elif kind == "photo_deleted":
                self._finish_photo_delete(data)
            elif kind == "delete_error":
                self._end_busy()
                self._status("Photo was not deleted")
                messagebox.showerror("Could not move photo to Recycle Bin",data+"\n\nNo permanent-delete fallback was attempted.",parent=self.root)
            elif kind == "copy_done":
                self._end_busy()
                self._status("Photos copied")
                if messagebox.askyesno("Photos copied",data[0]+"\n\nOpen the new folder?",parent=self.root):
                    try:
                        os.startfile(str(data[1]))
                    except OSError as error:
                        messagebox.showerror("Folder unavailable",str(error),parent=self.root)
            elif kind == "operation_done":
                self._end_busy()
                self._status("Complete")
                messagebox.showinfo("Complete",data)
            elif kind == "stack_progress":
                done,total,detail = data
                self.progress.configure(maximum=max(1,total),value=done)
                self._status(f"Stacking {done}/{total}: {detail}")
        if dirty:
            self._sync_controls()
        if dirty:
            visible = self._browse_results()
            added = [r for r in visible if r.path not in self.thumbnail_labels][:24]
            if added:
                self._populate_grid(added)
                self._load_thumbnails(added,self.thumbnail_generation)
                self._schedule_arrange()
        self.root.after(20,self._poll)

    def _status(self, state):
        selected=f" · {self.current.path.name}" if self.current else ""
        self.status.set(f"{state} · {self.source.name} · {len(self.results)} photos{selected}")
        self._sync_controls()

    def _end_busy(self):
        self.busy = False
        self.operation=None
        self.scan_button.state(["!disabled"])
        self.open_button.state(["!disabled"])
        self.cancel_button.state(["disabled"])
        self._cache_age()

    def _cancel(self):
        self.cancel_event.set()
        self.cancel_button.state(["disabled"])
        self._status("Cancelling after current file")

    def _apply_keep(self, refresh=True):
        try:
            value = float(self.keep_var.get())
            if not 0<value<=100:
                raise ValueError()
        except ValueError:
            messagebox.showinfo("Keep percentage", "Enter a number greater than 0 and up to 100.")
            return False
        self.keep_percent = value
        good = sorted((r.score for r in self.results if not r.error),reverse=True)
        self.cutoff = good[max(1,round(len(good)*value/100))-1] if good else float("inf")
        if refresh:
            self._refresh_grid()
            self._save_settings()
        return True

    def _open_folder(self, path):
        if self.busy or not path.is_dir():
            return
        self.thumb_cache.clear()
        self.thumb_errors.clear()
        self.source = path
        self._load_review_state()
        self.collection.set("All photos")
        self._update_collections()
        self.compare_image=None
        self.sort_token+=1;self.sort_task=None;self.sort_dates.clear();self.sort_status.set("")
        self.reference_path = None
        self.page_index = 0
        self._scan()


