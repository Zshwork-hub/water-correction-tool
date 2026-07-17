from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .water_shell_model import PROJECT_DATA_ITEMS
from .water_ui import ToolTip
from .water_ui_commands import get_command


class ProjectDataDialog(tk.Toplevel):
    def __init__(self, parent, *, file_variables, callbacks):
        super().__init__(parent)
        required = {item.key for item in PROJECT_DATA_ITEMS}
        missing_variables = required.difference(file_variables)
        missing_callbacks = required.difference(callbacks)
        if missing_variables or missing_callbacks:
            self.destroy()
            missing = sorted(missing_variables.union(missing_callbacks))
            raise ValueError(f"项目数据面板缺少绑定: {', '.join(missing)}")

        self.title("项目与数据")
        self.transient(parent)
        self.resizable(True, False)
        self.columnconfigure(0, weight=1)

        body = ttk.Frame(self, style="Panel.TFrame", padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        for row, item in enumerate(PROJECT_DATA_ITEMS):
            command = get_command(item.command_id)
            ttk.Label(body, text=item.label).grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=(0, 8)
            )
            ttk.Label(
                body,
                textvariable=file_variables[item.key],
                style="Muted.TLabel",
                justify="left",
                wraplength=420,
            ).grid(row=row, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
            button = ttk.Button(body, text=command.label, command=callbacks[item.key])
            button.grid(row=row, column=2, sticky="e", pady=(0, 8))
            ToolTip(button, command.tooltip)

        footer = ttk.Frame(body, style="Panel.TFrame")
        footer.grid(row=len(PROJECT_DATA_ITEMS), column=0, columnspan=3, sticky="ew", pady=(4, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="关闭", command=self.destroy).grid(row=0, column=1, sticky="e")
        self.protocol("WM_DELETE_WINDOW", self.destroy)