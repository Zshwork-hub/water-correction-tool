from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk


RGBA = Tuple[int, int, int, int]


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: Optional[tk.Toplevel] = None
        self._job: Optional[str] = None
        widget.bind("<Enter>", self._schedule, add=True)
        widget.bind("<Leave>", self._hide, add=True)
        widget.bind("<ButtonPress>", self._hide, add=True)

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.widget.after(450, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self) -> None:
        if self.tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            ttk.Label(tip, text=self.text, justify="left", padding=(8, 4)).pack()
            self.tip = tip
        except Exception:
            self.tip = None

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class PaletteEditorDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, entries: List[Tuple[str, RGBA]]) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[Dict[str, RGBA]] = None
        self._colors: Dict[str, RGBA] = {name: color for name, color in entries}
        self._swatches: Dict[str, tk.Button] = {}
        self._alpha_vars: Dict[str, tk.IntVar] = {}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="项目").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="颜色").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(body, text="透明度").grid(row=0, column=2, sticky="w", padx=(8, 0))
        for row, (name, color) in enumerate(entries):
            grid_row = row + 1
            ttk.Label(body, text=name, width=18).grid(row=grid_row, column=0, sticky="w", pady=4)
            swatch = tk.Button(body, width=16, relief="flat", command=lambda n=name: self._pick_color(n))
            swatch.grid(row=grid_row, column=1, sticky="w", padx=(8, 0), pady=4)
            self._swatches[name] = swatch
            alpha_var = tk.IntVar(value=color[3])
            self._alpha_vars[name] = alpha_var
            ttk.Spinbox(
                body,
                from_=0,
                to=255,
                increment=5,
                width=6,
                textvariable=alpha_var,
            ).grid(row=grid_row, column=2, sticky="w", padx=(8, 0), pady=4)
            self._set_swatch(name, color)

        actions = ttk.Frame(body)
        actions.grid(row=len(entries) + 1, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="取消", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="应用", command=self._apply).pack(side="right")
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _set_swatch(self, name: str, color: RGBA) -> None:
        self._colors[name] = color
        btn = self._swatches[name]
        hex_color = "#%02x%02x%02x" % color[:3]
        btn.configure(background=hex_color, activebackground=hex_color)

    def _pick_color(self, name: str) -> None:
        current = self._colors[name]
        picked = colorchooser.askcolor(color="#%02x%02x%02x" % current[:3], parent=self, title=f"选择{name}颜色")
        if not picked or not picked[0]:
            return
        r, g, b = [int(v) for v in picked[0]]
        self._set_swatch(name, (r, g, b, current[3]))

    def _apply(self) -> None:
        for name, color in list(self._colors.items()):
            try:
                alpha = int(self._alpha_vars[name].get())
            except Exception:
                alpha = color[3]
            alpha = max(0, min(255, alpha))
            self._colors[name] = (color[0], color[1], color[2], alpha)
        self.result = dict(self._colors)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class FitTargetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, has_stream: bool, has_flow: bool, has_vector: bool) -> None:
        super().__init__(parent)
        self.title("适配窗口")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[str] = None
        self.choice = tk.StringVar(value="current")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Radiobutton(body, text="当前模式", variable=self.choice, value="current").pack(anchor="w", pady=2)
        if has_stream:
            ttk.Radiobutton(body, text="河道文件", variable=self.choice, value="stream").pack(anchor="w", pady=2)
        if has_flow:
            ttk.Radiobutton(body, text="流向文件", variable=self.choice, value="flow").pack(anchor="w", pady=2)
        if has_vector:
            ttk.Radiobutton(body, text="河流SHP", variable=self.choice, value="vector").pack(anchor="w", pady=2)

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="取消", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="确定", command=self._apply).pack(side="right")
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _apply(self) -> None:
        self.result = self.choice.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class ShortcutSettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, shortcuts: Dict[str, str]) -> None:
        super().__init__(parent)
        self.title("快捷键设置")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[Dict[str, str]] = None
        self.brush_var = tk.StringVar(value=shortcuts.get("brush", "b").upper())
        self.eraser_var = tk.StringVar(value=shortcuts.get("eraser", "e").upper())

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="画笔").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(body, width=10, textvariable=self.brush_var).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(body, text="橡皮擦").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, width=10, textvariable=self.eraser_var).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(body, text="请输入单个字母或数字，例如 B、E、1。", foreground="#555").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="恢复默认", command=self._defaults).pack(side="left", padx=(0, 12))
        ttk.Button(actions, text="取消", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="保存", command=self._apply).pack(side="right")
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _defaults(self) -> None:
        self.brush_var.set("B")
        self.eraser_var.set("E")

    def _normalize(self, value: str) -> str:
        key = value.strip()
        if len(key) != 1 or key.isspace():
            return ""
        return key.lower()

    def _apply(self) -> None:
        brush = self._normalize(self.brush_var.get())
        eraser = self._normalize(self.eraser_var.get())
        if not brush or not eraser:
            messagebox.showwarning("提示", "快捷键请输入单个字母或数字。", parent=self)
            return
        if brush == eraser:
            messagebox.showwarning("提示", "画笔和橡皮擦不能使用同一个快捷键。", parent=self)
            return
        self.result = {"brush": brush, "eraser": eraser}
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
