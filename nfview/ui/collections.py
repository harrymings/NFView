"""Ui Collections functionality for NFView."""
from __future__ import annotations
import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from send2trash import send2trash



class CollectionsMixin:
    def _photo_key(self,path):
        try:
            return path.relative_to(self.source).as_posix()
        except ValueError:
            return str(path)

    def _load_review_state(self):
        try:
            state=json.loads((self.source/".image-screener-review.json").read_text(encoding="utf-8"))
            self.favourites=set(state.get("favourites",[]))
            self.locked_photos=set(state.get("locked",[]))
            self.custom_lists={name:set(members) for name,members in state.get("lists",{}).items()}
        except (OSError,ValueError,TypeError,AttributeError):
            self.favourites=set();self.locked_photos=set();self.custom_lists={}

    def _save_review_state(self):
        state={"version":1,"favourites":sorted(self.favourites),"locked":sorted(self.locked_photos),"lists":{name:sorted(members) for name,members in self.custom_lists.items()}}
        target=self.source/".image-screener-review.json"
        try:
            temporary=target.with_suffix(".tmp")
            temporary.write_text(json.dumps(state,indent=2),encoding="utf-8")
            temporary.replace(target)
            return True
        except OSError:
            messagebox.showerror("Could not save review choices","This folder is offline or read-only. Your originals are unchanged; review choices could not be saved.",parent=self.root)
            return False

    def _update_collections(self):
        values=["All photos","Favourites","Locked"]+["List: "+name for name in sorted(self.custom_lists,key=str.casefold)]
        self.collection_picker.configure(values=values)
        if self.collection.get() not in values:
            self.collection.set("All photos")
        self.list_menu.delete(0,"end")
        self.list_menu.add_command(label="Create list…",command=self._create_list)
        add=tk.Menu(self.list_menu,tearoff=False,bg="#1c222c",fg="#e7ecf4")
        for name in sorted(self.custom_lists,key=str.casefold):
            add.add_command(label=name,command=lambda name=name:self._add_to_list(name))
        self.list_menu.add_cascade(label="Add current photo to",menu=add,state="normal" if self.custom_lists else "disabled")
        self.list_menu.add_command(label="Remove current photo from this list",command=self._remove_from_list)
        self.list_menu.add_separator()
        self.list_menu.add_command(label="Rename this list…",command=self._rename_list)
        self.list_menu.add_command(label="Delete this list…",command=self._delete_list)

    def _review_changed(self):
        self._save_review_state()
        self._update_collections()
        if {r.path for r in self._browse_results()}==set(self.card_widgets):
            for result in self.results:self._style_card(result)
            self._reorder_cards()
        else:
            self._refresh_grid()
        self.root.after(60,self._ensure_visible)

    def _can_edit_review(self):
        if self.current is None:
            return False
        if self._photo_key(self.current.path) in self.locked_photos:
            messagebox.showinfo("Photo locked","Unlock this photo before changing its favourite status or list memberships.",parent=self.root)
            return False
        return True

    def _toggle_favourite(self):
        if not self._can_edit_review():
            return
        key=self._photo_key(self.current.path)
        if key in self.favourites:self.favourites.remove(key)
        else:self.favourites.add(key)
        self._review_changed()

    def _toggle_lock(self):
        if self.current is None:return
        key=self._photo_key(self.current.path)
        if key in self.locked_photos:self.locked_photos.remove(key)
        else:self.locked_photos.add(key)
        self._review_changed()

    def _list_name(self,title,initial=""):
        name=simpledialog.askstring(title,"List name:",initialvalue=initial,parent=self.root)
        if name is None:return None
        name=name.strip()
        if not name or len(name)>60 or any(ord(c)<32 for c in name):
            messagebox.showinfo("Choose a list name","Use a name with 1–60 readable characters.",parent=self.root);return None
        if any(n.casefold()==name.casefold() and n!=initial for n in self.custom_lists):
            messagebox.showinfo("List already exists","Choose a different list name.",parent=self.root);return None
        return name

    def _create_list(self):
        name=self._list_name("Create photo list")
        if name is None:return
        self.custom_lists[name]=set()
        self.collection.set("List: "+name)
        self._review_changed()

    def _add_to_list(self,name):
        if name not in self.custom_lists or not self._can_edit_review():return
        self.custom_lists[name].add(self._photo_key(self.current.path))
        self._review_changed()

    def _active_list(self):
        value=self.collection.get()
        return value[6:] if value.startswith("List: ") and value[6:] in self.custom_lists else None

    def _remove_from_list(self):
        name=self._active_list()
        if name is None:
            messagebox.showinfo("Choose a list","Choose a custom list in Show first.",parent=self.root);return
        if self._can_edit_review():
            self.custom_lists[name].discard(self._photo_key(self.current.path));self._review_changed()

    def _rename_list(self):
        old=self._active_list()
        if old is None:
            messagebox.showinfo("Choose a list","Choose a custom list in Show first.",parent=self.root);return
        new=self._list_name("Rename photo list",old)
        if new and new!=old:
            self.custom_lists[new]=self.custom_lists.pop(old);self.collection.set("List: "+new);self._review_changed()

    def _delete_list(self):
        name=self._active_list()
        if name is None:
            messagebox.showinfo("Choose a list","Choose a custom list in Show first.",parent=self.root);return
        if self.custom_lists[name]&self.locked_photos:
            messagebox.showinfo("List contains locked photos","Unlock the photos in this list before deleting their memberships.",parent=self.root);return
        if messagebox.askyesno("Delete list?","Delete the list '"+name+"'? The original photos stay untouched.",parent=self.root):
            del self.custom_lists[name];self.collection.set("All photos");self._review_changed()

    def _delete_photo(self):
        if self.busy or self.current is None:return
        path=self.current.path
        if self._photo_key(path) in self.locked_photos:
            messagebox.showinfo("Photo locked","Unlock this photo before deleting it, so its protected list memberships are not changed.",parent=self.root)
            return
        if not messagebox.askyesno("Delete selected photo?",f"Move this original to the Recycle Bin?\n\n{path}\n\nYou can restore it from the Recycle Bin.",parent=self.root,default="no"):
            return
        self.busy=True
        self.operation="delete"
        self._status("Moving photo to Recycle Bin…")
        def worker():
            try:
                send2trash(str(path.resolve()))
                self.events.put(("photo_deleted",path))
            except Exception as error:
                self.events.put(("delete_error",str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_photo_delete(self,path):
        self._end_busy()
        key=self._photo_key(path)
        self.favourites.discard(key)
        for members in self.custom_lists.values():members.discard(key)
        self._save_review_state()
        self.results=[r for r in self.results if r.path!=path]
        self.ranking_sessions.clear()
        self.compare_image=None
        self.compare_name=""
        self._deselect()
        self._refresh_grid()
        items=self._browse_results()
        if items:self._select(items[0])
        self._status(f"Moved {path.name} to Recycle Bin")


