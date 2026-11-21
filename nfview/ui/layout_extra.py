"""Ui Layout_Extra functionality for NFView."""
from __future__ import annotations
import tkinter as tk



class LayoutExtraMixin:
    def _ranking_key(self):
        return (str(self.source.resolve()),self.mode,str(self.reference_path.resolve()) if self.reference_path else "")

    def _change_view(self):
        gallery=self.view_var.get()=="grid"
        self.preview_tools.grid_configure(column=0 if gallery else 1,columnspan=3 if gallery else 1)
        self.content.rowconfigure(1,weight=0)
        self.content.rowconfigure(2,weight=1)
        self.content.rowconfigure(3,weight=0)
        self.content.columnconfigure(0,minsize=0 if gallery or not self.filmstrip_visible else round(220*self.display_scale))
        self.content.columnconfigure(2,minsize=0 if gallery or not self.details_visible else round(self.details_width*self.display_scale))
        if gallery:
            self.main_view.grid_remove();self.details.grid_remove()
            self.film_panel.grid(row=2,column=0,columnspan=3,rowspan=1,sticky="nsew",padx=0)
        else:
            self.main_view.grid()
            if self.details_visible:self.details.grid()
            self.film_panel.grid(row=1,column=0,columnspan=1,rowspan=2,sticky="nsew",padx=(0,8))
            if not self.filmstrip_visible:self.film_panel.grid_remove()
        self.film_canvas.yview_moveto(0)
        self._refresh_grid()
        self._layout_viewer_toolbar()
        self._save_settings()

    def _arrange_thumbnails(self):
        self.arrange_job=None
        if self.closed:
            return
        self.card_row_height = round(196 * self.display_scale) + 8
        self.card_column_width = round(204 * self.display_scale) + 8
        self.browser_columns = 1
        if self.view_var.get() == "grid":
            self.browser_columns = max(1, self.film_canvas.winfo_width() // self.card_column_width)
        rows = (len(self.browser_items) + self.browser_columns - 1) // self.browser_columns
        self.film_canvas.configure(scrollregion=(0, 0, self.browser_columns * self.card_column_width,
                                                  rows * self.card_row_height))
        self._schedule_film_visibility()

    def _schedule_arrange(self):
        if not self.closed and self.arrange_job is None:
            self.arrange_job=self.root.after(40,self._arrange_thumbnails)

    def _wrap_controls(self, frame, children=None):
        """Wrap controls as the window narrows so every action stays reachable."""
        children = children if children is not None else frame.winfo_children()
        for child in children:
            child.pack_forget()
        pending = [None]
        def layout():
            pending[0] = None
            available = max(300, frame.winfo_width()-20)
            row = column = used = 0
            for child in children:
                needed = child.winfo_reqwidth()+8
                if used and used+needed > available:
                    row += 1
                    column = used = 0
                child.grid(row=row, column=column, sticky="nsew", padx=3, pady=2)
                used += needed
                column += 1
        def resized(event):
            if pending[0]:
                self.root.after_cancel(pending[0])
            pending[0] = self.root.after(50,layout)
        frame.bind("<Configure>",resized)
        self.root.after_idle(layout)

    def _tooltip(self, widget, text):
        pending = [None]
        window = [None]
        def hide(event=None):
            if pending[0]:
                self.root.after_cancel(pending[0])
                pending[0] = None
            if window[0]:
                window[0].destroy()
                window[0] = None
        def show():
            pending[0] = None
            if not widget.winfo_exists():
                return
            window[0] = tk.Toplevel(self.root)
            window[0].overrideredirect(True)
            window[0].geometry(f"+{min(widget.winfo_rootx(),self.root.winfo_screenwidth()-420)}+{widget.winfo_rooty()+widget.winfo_height()+5}")
            tk.Label(window[0],text=text() if callable(text) else text,bg="#343a3d",fg="#ffffff",padx=10,pady=7,wraplength=400).pack()
        widget.bind("<Enter>",lambda e: pending.__setitem__(0,self.root.after(650,show)),add="+")
        widget.bind("<Leave>",hide,add="+")
        widget.bind("<Destroy>",hide,add="+")
        widget.bind("<ButtonPress>",hide,add="+")


