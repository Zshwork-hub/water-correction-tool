from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .water_shell_model import STREAM_CONTROL_KEYS
from .water_ui import ToolTip
from .water_ui_commands import CommandId, get_command
from .water_ui_components import CollapsibleSection, ScrollableTaskPanel


def build_stream_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]:
    title_var = tk.StringVar(master=parent, value="河道订正")
    summary_var = tk.StringVar(master=parent)
    panel = ScrollableTaskPanel(parent, title_var=title_var, summary_var=summary_var)
    panel.body.columnconfigure(0, weight=1)

    def refresh_summary(*_args) -> None:
        tool = "画笔" if app.tool_var.get() == "brush" else "橡皮擦"
        stream_state = "已加载" if app.stream_file_var.get() != "未加载" else "未加载"
        river_state = "已加载" if app.shp_var.get() != "未加载" else "未加载"
        summary_var.set(
            f"{tool} · {int(app.brush_size_var.get())} 像元 | 河道 ASC {stream_state} | 河流线 {river_state}"
        )

    for variable in (app.tool_var, app.brush_size_var, app.stream_file_var, app.shp_var):
        variable.trace_add("write", refresh_summary)
    refresh_summary()

    manual = ttk.LabelFrame(panel.body, text="手动工具", padding=8)
    manual.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    manual.columnconfigure(1, weight=1)

    radio_brush_tool = ttk.Radiobutton(
        manual,
        text="画笔",
        variable=app.tool_var,
        value="brush",
        command=app.on_tool_changed,
    )
    radio_brush_tool.grid(row=0, column=0, sticky="w")
    radio_eraser_tool = ttk.Radiobutton(
        manual,
        text="橡皮擦",
        variable=app.tool_var,
        value="eraser",
        command=app.on_tool_changed,
    )
    radio_eraser_tool.grid(row=0, column=1, sticky="w", padx=(8, 0))

    ttk.Label(manual, text="画笔大小").grid(row=1, column=0, sticky="w", pady=(8, 0))
    brush_size_spin = ttk.Spinbox(
        manual,
        from_=1,
        to=15,
        increment=2,
        width=7,
        textvariable=app.brush_size_var,
    )
    brush_size_spin.grid(row=1, column=1, sticky="w", pady=(8, 0))
    btn_shortcuts = ttk.Button(manual, text="快捷键设置", command=app.edit_shortcuts)
    btn_shortcuts.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    ToolTip(btn_shortcuts, "设置画笔和橡皮擦的键盘快捷键。")

    vector_section = CollapsibleSection(panel.body, "按河流线修正", expanded=False)
    vector_section.grid(row=1, column=0, sticky="ew")
    vector_section.content.columnconfigure(1, weight=1)
    ttk.Label(vector_section.content, text="矢量容差（像元）").grid(row=0, column=0, sticky="w")
    ttk.Spinbox(
        vector_section.content,
        from_=0.0,
        to=5.0,
        increment=0.1,
        width=7,
        textvariable=app.vector_tol_var,
    ).grid(row=0, column=1, sticky="w", padx=(8, 0))
    vector_hint = ttk.Label(
        vector_section.content,
        text="依据河流参考线批量补充河道像元；执行前确认容差和当前河道图层。",
        style="Muted.TLabel",
        justify="left",
        wraplength=300,
    )
    vector_hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    command = get_command(CommandId.APPLY_VECTOR_CORRECTION)
    btn_vector_batch = ttk.Button(
        panel.footer,
        text=command.label,
        style="Primary.TButton",
        command=app.apply_vector_batch,
    )
    btn_vector_batch.grid(row=0, column=0, sticky="ew")
    ToolTip(btn_vector_batch, command.tooltip)

    controls = {
        "radio_brush_tool": radio_brush_tool,
        "radio_eraser_tool": radio_eraser_tool,
        "brush_size_spin": brush_size_spin,
        "btn_shortcuts": btn_shortcuts,
        "btn_vector_batch": btn_vector_batch,
        "vector_hint": vector_hint,
    }
    if tuple(controls) != STREAM_CONTROL_KEYS:
        raise RuntimeError("河道订正页控件注册表与契约不一致")
    return panel, controls