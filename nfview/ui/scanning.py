"""Ui Scanning functionality for NFView."""
from __future__ import annotations
import threading
from tkinter import messagebox


from nfview.models import ScanCancelled
from nfview.scanning import folder_signature, scan_folder

class ScanningMixin:
    def _scan(self, force=False):
        if self.busy:
            return
        if not self.source.is_dir():
            messagebox.showinfo("Folder unavailable", "This folder is missing or offline. Choose an available photo folder.")
            return
        if not self._apply_keep(refresh=False):
            return
        self.operation=None
        self.busy = True
        self.cancel_event.clear()
        self.cache_hits = self.analyzed = 0
        self.results = []
        self.focused_only.set(False)
        self._deselect()
        self._refresh_grid()
        self.scan_button.state(["disabled"])
        self.open_button.state(["disabled"])
        self.cancel_button.state(["!disabled"])
        self.progress.configure(value=0, maximum=1)
        self._status("Scanning")
        self._save_settings()
        source, keep, mode, reference = self.source, self.keep_percent, self.mode, self.reference_path
        def worker():
            try:
                signature=folder_signature(source,reference)
                results, cutoff = scan_folder(source, keep, self._scan_progress, mode, reference,
                    cancel=self.cancel_event, on_result=lambda r:self.events.put(("result",r)), force=force)
                self.events.put(("finished", (results,cutoff,signature)))
            except ScanCancelled:
                self.events.put(("cancelled", None))
            except Exception as error:
                self.events.put(("failed", str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def _scan_progress(self, completed, total, from_cache):
        self.events.put(("progress", (completed,total,from_cache)))

    def _update_scan_progress(self, completed, total, from_cache):
        self.cache_hits += int(from_cache)
        self.analyzed += int(not from_cache)
        self.progress.configure(maximum=max(1,total), value=completed)
        self._status(f"Scanning {completed}/{total}")

    def _scan_finished(self, results, cutoff, signature=None):
        if signature is not None:
            self.ranking_sessions[self._ranking_key()]=(list(results),signature,self.cache_hits,self.analyzed)
        self.results, self.cutoff = results, cutoff
        self.sort_token+=1;self.sort_task=None;self.sort_dates.clear()
        self._end_busy()
        self.page_index = 0
        self._refresh_grid()
        item = next((r for r in results if not r.error), None)
        if item:
            self._select(item)
        self._load_sort_dates(preload=True)
        self._status("Scan complete")
        errors = [r for r in results if r.error]
        if errors:
            messagebox.showinfo("Some files were skipped", f"{len(errors)} of {len(results)} files were unavailable or could not be analyzed. Originals were untouched.\n\n" + "\n".join(r.path.name + ": " + r.error for r in errors[:5]))
        elif not results:
            messagebox.showinfo("No photos found", "No supported photographs were found in this folder or its subfolders.")


