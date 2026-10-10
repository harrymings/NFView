"""Ui Layout_Extra functionality for NFView."""
from __future__ import annotations
import tkinter as tk



class LayoutExtraMixin:
    def _ranking_key(self):
        return (str(self.source.resolve()),self.mode,str(self.reference_path.resolve()) if self.reference_path else "")

    def _change_view(self):
        gallery=self.view_var.get()=="grid"
        self.preview_tools.grid_configure(columnspan=2 if gallery else 1)
        if gallery:
            self.main_view.grid_remove();self.details.grid_remove()
            self.film_header.grid(row=1,column=0,columnspan=2,sticky="ew")
            self.content.rowconfigure(1,weight=0)
            self.content.rowconfigure(2,weight=1)
            self.content.columnconfigure(1,weight=0,minsize=0)
            self.film_panel.grid(row=2,column=0,columnspan=2,sticky="nsew",pady=(8,0))
            self.film_panel.pack_propagate(False)
            self.film_scroll.pack_forget();self.film_canvas.pack_forget()
            self.film_scroll.configure(orient="vertical",command=self.film_canvas.yview)
            self.film_scroll.pack(side="right",fill="y")
            self.film_canvas.pack(side="left",fill="both",expand=True)
            self.film_canvas.configure(xscrollcommand="",yscrollcommand=self.film_scroll.set)
        else:
            self.main_view.grid()
            self.film_header.grid(row=2,column=0,columnspan=2,sticky="ew")
            self.content.rowconfigure(1,weight=1)
            self.content.rowconfigure(2,weight=0)
            if self.details_visible:
                self.details.grid();self.content.columnconfigure(1,weight=0,minsize=round(self.details_width*self.display_scale))
            self.film_panel.grid(row=3,column=0,columnspan=2,sticky="ew",pady=(8,0))
            self.film_panel.pack_propagate(True)
            self.film_scroll.pack_forget();self.film_canvas.pack_forget()
            self.film_canvas.pack(fill="x",expand=False)
            self.film_scroll.configure(orient="horizontal",command=self.film_canvas.xview)
            self.film_scroll.pack(fill="x")
            self.film_canvas.configure(xscrollcommand=self._film_xscroll,yscrollcommand="",height=round(216*self.display_scale))
        if not gallery and not self.filmstrip_visible:
            self.film_panel.grid_remove()
        self.film_canvas.xview_moveto(0);self.film_canvas.yview_moveto(0)
        self._refresh_grid()
        self._save_settings()

    def _arrange_thumbnails(self):
        self.arrange_job=None
        if self.closed:
            return
        gallery=self.view_var.get()=="grid"
        if not gallery:
            for index,path in enumerate(self.card_widgets):
                x=index*(round(204*self.display_scale)+8)+4
                self.photo_positions[path]=x
                window=self.card_windows.get(path)
                if window:self.film_canvas.coords(window,x,4)
            width=len(self.card_widgets)*(round(204*self.display_scale)+8)
            self.film_canvas.configure(scrollregion=(0,0,width,round(204*self.display_scale)))
            self._schedule_film_visibility()
            return
        columns=max(1,self.film_canvas.winfo_width()//round(212*self.display_scale)) if gallery else self.page_size
        for index,(card,widgets) in enumerate(self.card_widgets.values()):
            row,column=(index//columns,index%columns) if gallery else (0,index)
            placement=card.grid_info()
            if int(placement.get("row",-1))!=row or int(placement.get("column",-1))!=column:
                card.grid_configure(row=row,column=column)
        # Never nest update_idletasks here: geometry callbacks can re-enter layout
        # and starve the main-thread queue which delivers decoded thumbnails.
        self.root.after_idle(lambda:self.film_canvas.configure(scrollregion=self.film_canvas.bbox("all")) if not self.closed else None)

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
            tk.Label(window[0],text=text() if callable(text) else text,bg="#34445a",fg="#ffffff",padx=10,pady=7,wraplength=400).pack()
        widget.bind("<Enter>",lambda e: pending.__setitem__(0,self.root.after(650,show)),add="+")
        widget.bind("<Leave>",hide,add="+")
        widget.bind("<ButtonPress>",hide,add="+")


