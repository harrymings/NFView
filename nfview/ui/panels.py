"""Ui Panels functionality for NFView."""
from __future__ import annotations



class PanelsMixin:
    def _layout_viewer_toolbar(self):
        if not hasattr(self,"viewer_tool_groups"):return
        views,navigation,tools=self.viewer_tool_groups
        width=self.content.winfo_width()
        if self.details_visible and self.view_var.get()!="grid":
            width-=round(self.details_width*self.display_scale)
        needed=2*max(views.winfo_reqwidth(),tools.winfo_reqwidth())+navigation.winfo_reqwidth()+20
        self.preview_tools.columnconfigure(0,weight=1 if width>=needed else 0,uniform="viewer-sides" if width>=needed else "")
        self.preview_tools.columnconfigure(2,weight=1 if width>=needed else 0,uniform="viewer-sides" if width>=needed else "")
        if width<needed:
            navigation.grid_configure(row=1,column=0,columnspan=3,pady=(3,0))
        else:
            navigation.grid_configure(row=0,column=1,columnspan=1,pady=0)

    def _draw_details_grip(self,event=None):
        canvas=self.details_divider
        canvas.delete("all")
        center=canvas.winfo_width()/2
        mid=canvas.winfo_height()/2
        canvas.create_line(center,mid-22*self.display_scale,center,mid+22*self.display_scale,
                           fill="#a8b5c7",width=max(2,round(2*self.display_scale)))

    def _start_details_resize(self,event):
        # Preserve the pointer's grab offset so the divider never jumps on press.
        self.details_drag_origin=(event.x_root,self.details.winfo_width())

    def _resize_details(self,event):
        origin=getattr(self,"details_drag_origin",None)
        if origin is None:
            self._start_details_resize(event)
            origin=self.details_drag_origin
        width=origin[1]-(event.x_root-origin[0])
        available=self.content.winfo_width()
        width=max(round(220*self.display_scale),min(width,round(available*.6)))
        self.details_width=round(width/self.display_scale)
        self.details.configure(width=width)
        self.content.columnconfigure(1,weight=0,minsize=width)
        self._layout_viewer_toolbar()

    def _toggle_details(self):
        if self.view_var.get()=="grid":
            return
        self.details_visible=not self.details_visible
        if self.details_visible:
            self.content.columnconfigure(1,weight=0,minsize=round(self.details_width*self.display_scale))
            self.details.grid()
            self.details_button.configure(text="Hide details")
        else:
            self.details.grid_remove()
            self.content.columnconfigure(1,weight=0,minsize=0)
            self.details_button.configure(text="Show details")
        self._layout_viewer_toolbar()


