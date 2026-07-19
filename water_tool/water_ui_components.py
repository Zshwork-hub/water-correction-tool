from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from .water_shell_model import NAV_ITEMS, NavigationId
from .water_ui_theme import UI_COLORS


def _safe_event_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_wheel_steps(delta: int = 0, button: int = 0) -> int:
    button_value = _safe_event_int(button)
    delta_value = _safe_event_int(delta)
    if button_value == 4:
        return -1
    if button_value == 5:
        return 1
    if delta_value == 0:
        return 0
    magnitude = max(1, abs(delta_value) // 120)
    return -magnitude if delta_value > 0 else magnitude


class ScrollableTaskPanel(ttk.Frame):
    def __init__(self, master, *, title_var=None, summary_var=None, padding=8):
        super().__init__(master, style="Panel.TFrame", padding=padding)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._wheel_bindings: Dict[str, str] = {}
        self._release_job: Optional[str] = None

        self.header = ttk.Frame(self, style="Panel.TFrame")
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, padding))
        self.header.columnconfigure(0, weight=1)
        header_row = 0
        if title_var is not None:
            ttk.Label(self.header, textvariable=title_var, style="Status.TLabel").grid(
                row=header_row, column=0, sticky="ew"
            )
            header_row += 1
        if summary_var is not None:
            ttk.Label(
                self.header,
                textvariable=summary_var,
                style="Muted.TLabel",
                justify="left",
                wraplength=320,
            ).grid(row=header_row, column=0, sticky="ew", pady=(4, 0))
            header_row += 1
        if header_row == 0:
            self.header.grid_remove()

        viewport = ttk.Frame(self, style="Panel.TFrame")
        viewport.grid(row=1, column=0, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            viewport,
            background=UI_COLORS["panel"],
            borderwidth=0,
            highlightthickness=0,
        )
        self._scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")

        self._body = ttk.Frame(self._canvas, style="Panel.TFrame")
        self._body.columnconfigure(0, weight=1)
        self._body_window = self._canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self._footer = ttk.Frame(self, style="Panel.TFrame")
        self._footer.grid(row=2, column=0, sticky="ew", pady=(padding, 0))
        self._footer.columnconfigure(0, weight=1)

        self.bind("<Enter>", self._acquire_wheel_bindings)
        self.bind("<Leave>", self._schedule_wheel_release)

    @property
    def body(self) -> ttk.Frame:
        return self._body

    @property
    def footer(self) -> ttk.Frame:
        return self._footer

    def scroll_to_top(self) -> None:
        self._canvas.yview_moveto(0.0)

    def _on_body_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._body_window, width=max(1, int(event.width)))

    def _acquire_wheel_bindings(self, _event=None) -> None:
        if self._release_job is not None:
            self.after_cancel(self._release_job)
            self._release_job = None
        if self._wheel_bindings:
            return
        top = self.winfo_toplevel()
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            binding_id = top.bind(sequence, self._on_mousewheel, add="+")
            if binding_id:
                self._wheel_bindings[sequence] = binding_id

    def _schedule_wheel_release(self, _event=None) -> None:
        if self._release_job is not None:
            self.after_cancel(self._release_job)
        self._release_job = self.after_idle(self._release_wheel_if_outside)

    def _release_wheel_if_outside(self) -> None:
        self._release_job = None
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        if self._is_descendant(widget):
            return
        top = self.winfo_toplevel()
        for sequence, binding_id in self._wheel_bindings.items():
            top.unbind(sequence, binding_id)
        self._wheel_bindings.clear()

    def _is_descendant(self, widget) -> bool:
        while widget is not None:
            if widget == self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_mousewheel(self, event):
        if not self._is_descendant(self.winfo_containing(event.x_root, event.y_root)):
            return None
        steps = normalize_wheel_steps(
            delta=getattr(event, "delta", 0),
            button=getattr(event, "num", 0),
        )
        if steps:
            self._canvas.yview_scroll(steps, "units")
            return "break"
        return None

    def destroy(self) -> None:
        if self._release_job is not None:
            self.after_cancel(self._release_job)
            self._release_job = None
        if self._wheel_bindings:
            top = self.winfo_toplevel()
            for sequence, binding_id in self._wheel_bindings.items():
                top.unbind(sequence, binding_id)
            self._wheel_bindings.clear()
        super().destroy()


class CollapsibleSection(ttk.Frame):
    def __init__(self, master, text: str, *, expanded: bool = False):
        super().__init__(master, style="Panel.TFrame")
        self.columnconfigure(0, weight=1)
        self._text = text
        self._expanded = False
        self._header_text = tk.StringVar()
        self._header = ttk.Button(self, textvariable=self._header_text, command=self._toggle)
        self._header.grid(row=0, column=0, sticky="ew")
        self._content = ttk.Frame(self, style="Panel.TFrame", padding=(8, 6, 0, 4))
        self._content.grid(row=1, column=0, sticky="ew")
        self._content.columnconfigure(0, weight=1)
        self.set_expanded(expanded)

    @property
    def content(self) -> ttk.Frame:
        return self._content

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._header_text.set(("▼ " if self._expanded else "▶ ") + self._text)
        if self._expanded:
            self._content.grid()
        else:
            self._content.grid_remove()

    def _toggle(self) -> None:
        self.set_expanded(not self._expanded)


class NavigationRail(ttk.Frame):
    def __init__(self, master, variable, command):
        super().__init__(master, style="Panel.TFrame", padding=(8, 10))
        self.variable = variable
        self.command = command
        self.buttons: Dict[NavigationId, ttk.Button] = {}
        self.indicators: Dict[NavigationId, tk.Frame] = {}
        self.columnconfigure(0, weight=1)
        for row, item in enumerate(NAV_ITEMS):
            row_frame = tk.Frame(self, background=UI_COLORS["panel"])
            row_frame.grid(row=row, column=0, sticky="ew", pady=(0, 4))
            row_frame.columnconfigure(1, weight=1)
            indicator = tk.Frame(row_frame, width=3, background=UI_COLORS["panel"])
            indicator.grid(row=0, column=0, sticky="ns")
            indicator.grid_propagate(False)
            button = ttk.Button(
                row_frame,
                text=item.label,
                style="Nav.TButton",
                command=lambda value=item.navigation_id: self._select(value),
            )
            button.grid(row=0, column=1, sticky="ew")
            self.buttons[item.navigation_id] = button
            self.indicators[item.navigation_id] = indicator
        self.set_selected(NavigationId(self.variable.get()))

    def set_selected(self, navigation_id: NavigationId) -> None:
        navigation_id = NavigationId(navigation_id)
        self.variable.set(navigation_id.value)
        for item_id, button in self.buttons.items():
            selected = item_id == navigation_id
            button.configure(style="NavSelected.TButton" if selected else "Nav.TButton")
            self.indicators[item_id].configure(
                background=UI_COLORS["primary"] if selected else UI_COLORS["panel"]
            )

    def _select(self, navigation_id: NavigationId) -> None:
        self.set_selected(navigation_id)
        self.command()