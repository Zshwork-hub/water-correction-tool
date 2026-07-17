from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from tkinter import ttk

from .water_shell_model import NavigationId
from .water_ui import ToolTip
from .water_ui_commands import CommandId, get_command
from .water_ui_components import NavigationRail


@dataclass
class UiShellHandles:
    navigation: NavigationRail
    map_frame: ttk.Frame
    page_host: ttk.Frame
    status_bar: ttk.Frame
    pages: Dict[NavigationId, ttk.Frame]

    def show_page(self, navigation_id: NavigationId) -> None:
        navigation_id = NavigationId(navigation_id)
        if navigation_id not in self.pages:
            raise KeyError(f"未注册页面: {navigation_id.value}")
        for page in self.pages.values():
            page.grid_remove()
        self.pages[navigation_id].grid(row=0, column=0, sticky="nsew")
        self.navigation.set_selected(navigation_id)


def _command_button(parent, command_id: CommandId, callback, *, style=None):
    command = get_command(command_id)
    options = {"text": command.label, "command": callback}
    if style is not None:
        options["style"] = style
    button = ttk.Button(parent, **options)
    button.pack(side="left", padx=(0, 4))
    ToolTip(button, command.tooltip)
    return button


def build_application_shell(app) -> UiShellHandles:
    app.columnconfigure(0, weight=1)
    app.rowconfigure(0, weight=1)

    shell = ttk.Frame(app, style="App.TFrame")
    shell.grid(row=0, column=0, sticky="nsew")
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(1, weight=1)

    toolbar = ttk.Frame(shell, style="Panel.TFrame", padding=(8, 6))
    toolbar.grid(row=0, column=0, sticky="ew")

    project_data = ttk.Button(toolbar, text="项目与数据", command=app.open_project_data_panel)
    project_data.pack(side="left", padx=(0, 4))
    ToolTip(project_data, "集中查看、加载或替换河道、流向、参考线、汇流范围和 DEM 数据。")
    app.btn_open_project = _command_button(toolbar, CommandId.OPEN_PROJECT, app.open_project_dialog)
    app.btn_save_project = _command_button(toolbar, CommandId.SAVE_PROJECT, app.save_project_dialog)
    app.btn_export = _command_button(toolbar, CommandId.EXPORT_ASC, app.export_active)

    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=(4, 8))
    app.btn_undo = _command_button(toolbar, CommandId.UNDO, app.undo)
    app.btn_redo = _command_button(toolbar, CommandId.REDO, app.redo)

    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=(4, 8))
    app.btn_fit = _command_button(toolbar, CommandId.FIT_CONTENT, app.fit_content_to_view)
    app.btn_center_shp = _command_button(toolbar, CommandId.CENTER_RIVER, app.center_shp_at_current_zoom)
    app.btn_zoom_out = ttk.Button(toolbar, text="−", width=3, command=lambda: app.change_zoom(0.8))
    app.btn_zoom_out.pack(side="left", padx=(0, 2))
    ToolTip(app.btn_zoom_out, "缩小当前视图。")
    app.btn_zoom_in = ttk.Button(toolbar, text="+", width=3, command=lambda: app.change_zoom(1.25))
    app.btn_zoom_in.pack(side="left", padx=(0, 4))
    ToolTip(app.btn_zoom_in, "放大当前视图。")
    ttk.Entry(toolbar, width=7, textvariable=app.zoom_var).pack(side="left", padx=(0, 2))
    app.btn_zoom_apply = ttk.Button(toolbar, text="应用", command=app.apply_zoom_entry)
    app.btn_zoom_apply.pack(side="left", padx=(0, 8))
    ToolTip(app.btn_zoom_apply, "按输入的缩放倍率刷新地图。")
    app.chk_autosave = ttk.Checkbutton(
        toolbar,
        text="自动保存",
        variable=app.autosave_var,
        command=app.update_mode_status,
    )
    app.chk_autosave.pack(side="right")

    content = ttk.Frame(shell, style="App.TFrame", padding=(8, 8, 8, 0))
    content.grid(row=1, column=0, sticky="nsew")
    content.columnconfigure(1, weight=1)
    content.rowconfigure(0, weight=1)

    navigation = NavigationRail(
        content,
        app.navigation_var,
        command=lambda: app.on_navigation_changed(),
    )
    navigation.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

    map_frame = ttk.Frame(content, style="Panel.TFrame")
    map_frame.grid(row=0, column=1, sticky="nsew")
    map_frame.columnconfigure(0, weight=1)
    map_frame.rowconfigure(0, weight=1)

    page_host = ttk.Frame(content, style="Panel.TFrame", width=360)
    page_host.grid(row=0, column=2, sticky="nse", padx=(8, 0))
    page_host.grid_propagate(False)
    page_host.columnconfigure(0, weight=1)
    page_host.rowconfigure(0, weight=1)

    status_bar = ttk.Frame(shell, style="App.TFrame")
    status_bar.grid(row=2, column=0, sticky="ew")
    status_bar.columnconfigure(0, weight=1)
    ttk.Label(status_bar, textvariable=app.info_var, style="Status.TLabel", anchor="w").grid(
        row=0, column=0, sticky="ew"
    )
    ttk.Label(status_bar, textvariable=app.coord_var, style="Status.TLabel", anchor="e").grid(
        row=0, column=1, sticky="e"
    )

    return UiShellHandles(navigation, map_frame, page_host, status_bar, {})