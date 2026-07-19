from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .water_core import DIR_ORDER, direction_text
from .water_shell_model import DISPLAY_CONTROL_KEYS, FLOW_CONTROL_KEYS, HISTORY_CONTROL_KEYS
from .water_ui import ToolTip
from .water_ui_commands import CommandId, get_command
from .water_ui_components import CollapsibleSection, ScrollableTaskPanel


def _command_tip(widget, command_id: CommandId) -> None:
    ToolTip(widget, get_command(command_id).tooltip)


def _validate_controls(page_name: str, controls: dict[str, object], expected: tuple[str, ...]) -> None:
    if tuple(controls) != expected:
        missing = sorted(set(expected).difference(controls))
        extra = sorted(set(controls).difference(expected))
        raise RuntimeError(f"{page_name}控件注册表不一致，缺少={missing}，多余={extra}")


def build_flow_compatibility_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]:
    title_var = tk.StringVar(master=parent, value="流向订正")
    panel = ScrollableTaskPanel(parent, title_var=title_var, summary_var=app.flow_status_var)
    panel.body.columnconfigure(0, weight=1)
    panel.body.rowconfigure(0, weight=1)
    notebook = ttk.Notebook(panel.body)
    notebook.grid(row=0, column=0, sticky="nsew")
    manual_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=8)
    assist_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=8)
    dem_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=8)
    for tab in (manual_tab, assist_tab, dem_tab):
        tab.columnconfigure(0, weight=1)
    notebook.add(manual_tab, text="手动改向")
    notebook.add(assist_tab, text="河网辅助")
    notebook.add(dem_tab, text="DEM 审核")

    manual = ttk.LabelFrame(manual_tab, text="手动改向", padding=8)
    manual.grid(row=0, column=0, sticky="ew")
    manual.columnconfigure(1, weight=1)
    ttk.Label(manual, text="D8 方向").grid(row=0, column=0, sticky="w")
    direction_box = ttk.Combobox(
        manual,
        state="readonly",
        values=[f"{code} {direction_text(code)}" for code in DIR_ORDER],
        textvariable=app.direction_var,
        width=12,
    )
    direction_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
    write_command = get_command(CommandId.WRITE_FLOW_DIRECTION)
    btn_apply_direction = ttk.Button(manual, text=write_command.label, command=app.apply_selected_direction)
    btn_apply_direction.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    _command_tip(btn_apply_direction, CommandId.WRITE_FLOW_DIRECTION)

    row = 0

    range_section = CollapsibleSection(assist_tab, "汇流范围", expanded=False)
    range_section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
    range_section.content.columnconfigure(2, weight=1)
    row += 1
    chk_show_confluence_polygon = ttk.Checkbutton(
        range_section.content,
        text="显示边界",
        variable=app.show_confluence_polygon_var,
        command=lambda: app.render(full=True),
    )
    chk_show_confluence_polygon.grid(row=0, column=0, sticky="w", padx=(0, 10))
    ttk.Label(range_section.content, text="线宽").grid(row=0, column=1, sticky="e", padx=(0, 4))
    ttk.Spinbox(
        range_section.content,
        from_=1,
        to=8,
        increment=1,
        width=5,
        textvariable=app.confluence_polygon_width_var,
        command=lambda: app.render(full=True),
    ).grid(row=0, column=2, sticky="w")
    lock_polygon_command = get_command(CommandId.ADD_POLYGON_RIVERS)
    btn_lock_polygon_stream = ttk.Button(
        range_section.content,
        text=lock_polygon_command.label,
        command=app.lock_confluence_polygon_stream_skeleton,
    )
    btn_lock_polygon_stream.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
    _command_tip(btn_lock_polygon_stream, CommandId.ADD_POLYGON_RIVERS)

    lock_section = CollapsibleSection(assist_tab, "订正对象", expanded=True)
    lock_section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
    row += 1
    for column in range(2):
        lock_section.content.columnconfigure(column, weight=1)
    add_command = get_command(CommandId.ADD_SELECTED_RIVERS)
    btn_pick_flow_segment = ttk.Button(
        lock_section.content,
        text=add_command.label,
        command=app.lock_visible_stream_skeleton,
    )
    btn_pick_flow_segment.grid(row=0, column=0, columnspan=2, sticky="ew")
    _command_tip(btn_pick_flow_segment, CommandId.ADD_SELECTED_RIVERS)
    cell_command = get_command(CommandId.ADD_SELECTED_CELL)
    btn_add_locked_cell = ttk.Button(
        lock_section.content,
        text=cell_command.label,
        command=app.add_selected_stream_cell_to_lock,
    )
    btn_add_locked_cell.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
    _command_tip(btn_add_locked_cell, CommandId.ADD_SELECTED_CELL)
    remove_command = get_command(CommandId.REMOVE_SELECTED_RIVERS)
    btn_remove_locked_region = ttk.Button(
        lock_section.content,
        text=remove_command.label,
        command=app.remove_selected_locked_region,
    )
    btn_remove_locked_region.grid(row=1, column=1, sticky="ew", pady=(6, 0))
    _command_tip(btn_remove_locked_region, CommandId.REMOVE_SELECTED_RIVERS)

    river_section = CollapsibleSection(assist_tab, "河道本体流向", expanded=True)
    river_section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
    row += 1
    river_section.content.columnconfigure(1, weight=1)
    outlet_command = get_command(CommandId.SET_DOWNSTREAM_OUTLET)
    btn_set_flow_outlet = ttk.Button(
        river_section.content,
        text=outlet_command.label,
        command=app.set_flow_skeleton_outlet,
    )
    btn_set_flow_outlet.grid(row=0, column=0, columnspan=2, sticky="ew")
    _command_tip(btn_set_flow_outlet, CommandId.SET_DOWNSTREAM_OUTLET)
    ttk.Label(river_section.content, text="计算模式").grid(row=1, column=0, sticky="w", pady=(6, 0))
    river_flow_mode_box = ttk.Combobox(
        river_section.content,
        state="readonly",
        values=["平滑", "稳健"],
        textvariable=app.river_flow_mode_var,
        width=10,
    )
    river_flow_mode_box.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
    river_flow_mode_box.bind("<<ComboboxSelected>>", app.on_river_flow_mode_changed)
    btn_preview_river_flow = ttk.Button(
        river_section.content,
        text="预览河道流向",
        command=app.preview_locked_river_flow,
    )
    btn_preview_river_flow.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    confluence_section = CollapsibleSection(assist_tab, "周边汇流", expanded=True)
    confluence_section.grid(row=row, column=0, sticky="ew", pady=(0, 8))
    row += 1
    confluence_section.content.columnconfigure(1, weight=1)
    ttk.Label(confluence_section.content, text="范围模式").grid(row=0, column=0, sticky="w")
    confluence_mode_box = ttk.Combobox(
        confluence_section.content,
        state="readonly",
        values=["近远带", "范围SHP"],
        textvariable=app.confluence_mode_var,
        width=10,
    )
    confluence_mode_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
    confluence_mode_box.bind("<<ComboboxSelected>>", app.on_confluence_mode_changed)
    ttk.Label(confluence_section.content, text="近带").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Spinbox(
        confluence_section.content,
        from_=1,
        to=30,
        width=7,
        textvariable=app.confluence_inner_radius_var,
    ).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
    ttk.Label(confluence_section.content, text="远带").grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Spinbox(
        confluence_section.content,
        from_=1,
        to=30,
        width=7,
        textvariable=app.confluence_outer_radius_var,
    ).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
    ttk.Label(confluence_section.content, text="最大距离").grid(row=3, column=0, sticky="w", pady=(6, 0))
    ttk.Spinbox(
        confluence_section.content,
        from_=0,
        to=300,
        width=7,
        textvariable=app.confluence_max_distance_var,
    ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
    btn_set_downstream = ttk.Button(
        confluence_section.content,
        text="预览周边汇流",
        command=app.preview_confirmed_confluence,
    )
    btn_set_downstream.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    ttk.Label(
        confluence_section.content,
        textvariable=app.confluence_hint_var,
        style="Muted.TLabel",
        justify="left",
        wraplength=300,
    ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    app._update_confluence_hint()

    flow_assist_var = tk.StringVar(
        master=parent,
        value="右键选择目标河道并加入订正对象；设出口后先预览河道本体，再预览周边汇流。",
    )
    ttk.Label(
        assist_tab,
        textvariable=flow_assist_var,
        style="Muted.TLabel",
        justify="left",
        wraplength=310,
    ).grid(row=row, column=0, sticky="ew", pady=(0, 8))
    row += 1

    dem_section = CollapsibleSection(dem_tab, "DEM 工具与审核", expanded=True)
    dem_section.grid(row=0, column=0, sticky="ew")
    for column in range(2):
        dem_section.content.columnconfigure(column, weight=1)
    btn_load_dem = ttk.Button(dem_section.content, text="加载 DEM", command=app.load_dem_dialog)
    btn_load_dem.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    _command_tip(btn_load_dem, CommandId.LOAD_DEM)
    btn_build_dem_cache = ttk.Button(
        dem_section.content,
        text="生成 DEM 缓存",
        command=app.start_locked_dem_cache_task,
    )
    btn_build_dem_cache.grid(row=0, column=1, sticky="ew")
    _command_tip(btn_build_dem_cache, CommandId.BUILD_DEM_CACHE)
    btn_cancel_dem_cache = ttk.Button(
        dem_section.content,
        text="取消缓存任务",
        command=app.cancel_dem_cache_task,
    )
    btn_cancel_dem_cache.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    _command_tip(btn_cancel_dem_cache, CommandId.CANCEL_DEM_CACHE)
    btn_evaluate_dem_preview = ttk.Button(
        dem_section.content,
        text="使用 DEM 评估预览",
        command=app.evaluate_current_flow_preview_with_dem,
    )
    btn_evaluate_dem_preview.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    _command_tip(btn_evaluate_dem_preview, CommandId.EVALUATE_DEM_PREVIEW)
    ttk.Label(dem_section.content, text="标记显示").grid(row=3, column=0, sticky="w", pady=(6, 0))
    dem_score_display_box = ttk.Combobox(
        dem_section.content,
        textvariable=app.dem_score_display_var,
        values=("全部", "仅冲突", "隐藏"),
        state="readonly",
        width=10,
    )
    dem_score_display_box.grid(row=3, column=1, sticky="ew", pady=(6, 0))
    dem_score_display_box.bind("<<ComboboxSelected>>", lambda _event: app.render(full=False))
    for setting_row, (label, variable, maximum, increment) in enumerate(
        (
            ("平坦容差", app.dem_flat_tolerance_var, 50.0, 0.5),
            ("轻微逆坡", app.dem_mild_uphill_var, 100.0, 0.5),
            ("严重逆坡", app.dem_severe_uphill_var, 500.0, 1.0),
        ),
        start=4,
    ):
        ttk.Label(dem_section.content, text=label).grid(row=setting_row, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(
            dem_section.content,
            from_=0.0,
            to=maximum,
            increment=increment,
            width=8,
            textvariable=variable,
        ).grid(row=setting_row, column=1, sticky="ew", pady=(6, 0))
    btn_locate_dem_conflict = ttk.Button(
        dem_section.content,
        text="定位下一处逆坡",
        command=app.locate_next_dem_conflict,
    )
    btn_locate_dem_conflict.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    _command_tip(btn_locate_dem_conflict, CommandId.LOCATE_NEXT_UPHILL)
    btn_export_dem_report = ttk.Button(
        dem_section.content,
        text="导出 DEM 评估报告",
        command=app.export_dem_score_report,
    )
    btn_export_dem_report.grid(row=8, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
    _command_tip(btn_export_dem_report, CommandId.EXPORT_DEM_REPORT)
    btn_export_dem_conflicts = ttk.Button(
        dem_section.content,
        text="导出逆坡冲突",
        command=app.export_dem_conflict_report,
    )
    btn_export_dem_conflicts.grid(row=8, column=1, sticky="ew", pady=(6, 0))
    _command_tip(btn_export_dem_conflicts, CommandId.EXPORT_UPHILL_CONFLICTS)
    ttk.Label(
        dem_section.content,
        text="绿=顺坡  黄=近似平坦  红=逆坡冲突  灰=无 DEM",
        style="Muted.TLabel",
        justify="left",
        wraplength=300,
    ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    ttk.Label(
        dem_section.content,
        textvariable=app.dem_cache_status_var,
        style="Muted.TLabel",
        justify="left",
        wraplength=300,
    ).grid(row=10, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    ttk.Label(
        dem_section.content,
        textvariable=app.dem_score_status_var,
        style="Muted.TLabel",
        justify="left",
        wraplength=300,
    ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    for column in range(3):
        panel.footer.columnconfigure(column, weight=1)
    apply_command = get_command(CommandId.APPLY_FLOW_PREVIEW)
    btn_reverse_segment = ttk.Button(
        panel.footer,
        text=apply_command.label,
        style="Primary.TButton",
        command=app.apply_flow_preview,
    )
    btn_reverse_segment.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    _command_tip(btn_reverse_segment, CommandId.APPLY_FLOW_PREVIEW)
    clear_command = get_command(CommandId.CLEAR_FLOW_PREVIEW)
    btn_preview_segment = ttk.Button(
        panel.footer,
        text=clear_command.label,
        command=app.clear_flow_preview,
    )
    btn_preview_segment.grid(row=0, column=1, sticky="ew", padx=(0, 4))
    _command_tip(btn_preview_segment, CommandId.CLEAR_FLOW_PREVIEW)
    reset_command = get_command(CommandId.RESET_FLOW_ASSIST)
    btn_confirm_segment = ttk.Button(
        panel.footer,
        text=reset_command.label,
        command=app.clear_flow_segment_state,
    )
    btn_confirm_segment.grid(row=0, column=2, sticky="ew")
    _command_tip(btn_confirm_segment, CommandId.RESET_FLOW_ASSIST)

    controls = {
        "direction_box": direction_box,
        "btn_apply_direction": btn_apply_direction,
        "chk_show_confluence_polygon": chk_show_confluence_polygon,
        "btn_lock_polygon_stream": btn_lock_polygon_stream,
        "btn_pick_flow_segment": btn_pick_flow_segment,
        "btn_add_locked_cell": btn_add_locked_cell,
        "btn_remove_locked_region": btn_remove_locked_region,
        "btn_set_flow_outlet": btn_set_flow_outlet,
        "river_flow_mode_box": river_flow_mode_box,
        "btn_preview_river_flow": btn_preview_river_flow,
        "confluence_mode_box": confluence_mode_box,
        "btn_set_downstream": btn_set_downstream,
        "btn_reverse_segment": btn_reverse_segment,
        "btn_preview_segment": btn_preview_segment,
        "btn_confirm_segment": btn_confirm_segment,
        "btn_flow_preview": btn_set_downstream,
        "btn_flow_apply": btn_reverse_segment,
        "btn_preview_confluence": btn_set_downstream,
        "btn_apply_flow_preview": btn_reverse_segment,
        "btn_clear_flow_preview": btn_preview_segment,
        "btn_clear_flow_marks": btn_confirm_segment,
        "flow_assist_var": flow_assist_var,
        "btn_load_dem": btn_load_dem,
        "btn_build_dem_cache": btn_build_dem_cache,
        "btn_cancel_dem_cache": btn_cancel_dem_cache,
        "btn_evaluate_dem_preview": btn_evaluate_dem_preview,
        "dem_score_display_box": dem_score_display_box,
        "btn_locate_dem_conflict": btn_locate_dem_conflict,
        "btn_export_dem_report": btn_export_dem_report,
        "btn_export_dem_conflicts": btn_export_dem_conflicts,
    }
    _validate_controls("流向页", controls, FLOW_CONTROL_KEYS)
    return panel, controls


def build_display_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]:
    title_var = tk.StringVar(master=parent, value="显示与配色")
    panel = ScrollableTaskPanel(parent, title_var=title_var, summary_var=app.session_status_var)
    panel.body.columnconfigure(0, weight=1)

    display_box = ttk.LabelFrame(panel.body, text="显示开关", padding=8)
    display_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    for column in range(2):
        display_box.columnconfigure(column, weight=1)
    chk_grid = ttk.Checkbutton(display_box, text="坐标网格", variable=app.show_grid_var, command=app.render)
    chk_grid.grid(row=0, column=0, sticky="w")
    chk_scale = ttk.Checkbutton(display_box, text="比例尺", variable=app.show_scale_var, command=app.render)
    chk_scale.grid(row=0, column=1, sticky="w")
    chk_arrows = ttk.Checkbutton(display_box, text="流向箭头", variable=app.show_flow_arrows_var, command=app.render)
    chk_arrows.grid(row=1, column=0, sticky="w", pady=(6, 0))
    chk_compare = ttk.Checkbutton(display_box, text="原始图层对比", variable=app.compare_original_var, command=app.render)
    chk_compare.grid(row=1, column=1, sticky="w", pady=(6, 0))

    color_box = ttk.LabelFrame(panel.body, text="颜色", padding=8)
    color_box.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    for column in range(2):
        color_box.columnconfigure(column, weight=1)
    color_specs = (
        ("河道栅格", app.pick_stream_palette),
        ("流向栅格", app.pick_flow_palette),
        ("河流参考线", app.pick_vector_color),
        ("汇流范围", app.pick_confluence_polygon_color),
        ("辅助标记", app.pick_assist_palette),
        ("恢复默认颜色", app.reset_palette_defaults),
    )
    color_buttons = []
    for index, (label, callback) in enumerate(color_specs):
        button = ttk.Button(color_box, text=label, command=callback)
        button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 4) if index % 2 == 0 else 0, pady=(0, 6))
        color_buttons.append(button)
    (
        btn_stream_palette,
        btn_flow_palette,
        btn_vector_color,
        btn_confluence_polygon_color,
        btn_assist_palette,
        btn_reset_palette,
    ) = color_buttons

    preset_box = ttk.LabelFrame(panel.body, text="配色预设", padding=8)
    preset_box.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    preset_box.columnconfigure(0, weight=1)
    preset_combo = ttk.Combobox(
        preset_box,
        state="readonly",
        textvariable=app.preset_var,
        values=[],
    )
    preset_combo.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    btn_load_preset = ttk.Button(preset_box, text="加载", command=app.load_palette_preset_dialog)
    btn_load_preset.grid(row=1, column=0, sticky="ew", padx=(0, 4))
    btn_save_preset = ttk.Button(preset_box, text="保存当前", command=app.save_palette_preset_dialog)
    btn_save_preset.grid(row=1, column=1, sticky="ew", padx=(0, 4))
    btn_delete_preset = ttk.Button(preset_box, text="删除", command=app.delete_palette_preset_dialog)
    btn_delete_preset.grid(row=1, column=2, sticky="ew")

    info_box = ttk.LabelFrame(panel.body, text="像元信息", padding=8)
    info_box.grid(row=3, column=0, sticky="ew")
    ttk.Label(info_box, textvariable=app.coord_var, justify="left", wraplength=300).grid(row=0, column=0, sticky="ew")
    ttk.Label(info_box, textvariable=app.info_var, style="Muted.TLabel", justify="left", wraplength=300).grid(
        row=1, column=0, sticky="ew", pady=(4, 0)
    )
    panel.footer.grid_remove()

    controls = {
        "chk_grid": chk_grid,
        "chk_scale": chk_scale,
        "chk_arrows": chk_arrows,
        "chk_compare": chk_compare,
        "btn_stream_palette": btn_stream_palette,
        "btn_flow_palette": btn_flow_palette,
        "btn_vector_color": btn_vector_color,
        "btn_confluence_polygon_color": btn_confluence_polygon_color,
        "btn_assist_palette": btn_assist_palette,
        "btn_reset_palette": btn_reset_palette,
        "preset_combo": preset_combo,
        "btn_load_preset": btn_load_preset,
        "btn_save_preset": btn_save_preset,
        "btn_delete_preset": btn_delete_preset,
    }
    _validate_controls("显示页", controls, DISPLAY_CONTROL_KEYS)
    return panel, controls


def build_history_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]:
    title_var = tk.StringVar(master=parent, value="历史与恢复")
    panel = ScrollableTaskPanel(parent, title_var=title_var, summary_var=app.session_status_var)
    panel.body.columnconfigure(0, weight=1)

    actions = ttk.LabelFrame(panel.body, text="会话", padding=8)
    actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)
    snapshot_command = get_command(CommandId.CREATE_SNAPSHOT)
    btn_snapshot = ttk.Button(actions, text=snapshot_command.label, command=app.take_snapshot)
    btn_snapshot.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    _command_tip(btn_snapshot, CommandId.CREATE_SNAPSHOT)
    autosave_command = get_command(CommandId.RESTORE_AUTOSAVE)
    btn_restore_autosave = ttk.Button(actions, text=autosave_command.label, command=app.restore_autosave_dialog)
    btn_restore_autosave.grid(row=0, column=1, sticky="ew")
    _command_tip(btn_restore_autosave, CommandId.RESTORE_AUTOSAVE)

    snapshot_box = ttk.LabelFrame(panel.body, text="版本快照", padding=8)
    snapshot_box.grid(row=1, column=0, sticky="nsew")
    snapshot_box.columnconfigure(0, weight=1)
    snapshot_box.rowconfigure(0, weight=1)
    snapshot_list = tk.Listbox(snapshot_box, height=14)
    snapshot_list.grid(row=0, column=0, sticky="nsew")
    snapshot_list.bind("<Double-Button-1>", lambda _event: app.restore_selected_snapshot())
    scrollbar = ttk.Scrollbar(snapshot_box, orient="vertical", command=snapshot_list.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    snapshot_list.configure(yscrollcommand=scrollbar.set)

    btn_restore_snapshot = ttk.Button(
        panel.footer,
        text="恢复所选快照",
        style="Primary.TButton",
        command=app.restore_selected_snapshot,
    )
    btn_restore_snapshot.grid(row=0, column=0, sticky="ew")
    controls = {
        "snapshot_list": snapshot_list,
        "btn_restore_snapshot": btn_restore_snapshot,
        "btn_snapshot": btn_snapshot,
        "btn_restore_autosave": btn_restore_autosave,
    }
    _validate_controls("历史页", controls, HISTORY_CONTROL_KEYS)
    return panel, controls