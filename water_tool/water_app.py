from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageTk

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .water_core import (
    CRS,
    DIR_ORDER,
    NODATA,
    STREAM_VALUE,
    ChangeBatch,
    PolygonLayer,
    RasterData,
    Transformer,
    app_base_dir,
    clamp,
    direction_text,
    fmt_value,
    parse_asc,
    parse_shapefile_polygon,
    parse_shapefile_lines,
    write_asc,
)
from .water_dem_workflow import DemWorkflowMixin
from .water_editing import RasterEditingMixin
from .water_flow_render import FlowRenderMixin
from .water_flow_status import FlowStatusMixin
from .water_flow_workflow import FlowWorkflowMixin
from .water_geometry import line_cells
from .water_history import EditingHistoryMixin
from .water_palette import PaletteMixin
from .water_project_workflow import ProjectWorkflowMixin
from .water_render import build_base_image, overlay_flow_arrows, overlay_grid, overlay_scale_bar, overlay_vector_layer, render_viewport_image, render_viewport_layers
from .water_shortcuts import DEFAULT_SHORTCUTS, load_shortcuts, normalize_shortcut, save_shortcuts, shortcut_label
from .water_state import FlowStateMixin
from .water_ui import FitTargetDialog, ShortcutSettingsDialog, ToolTip
from .water_ui_model import FlowAssistViewState
from .water_ui_state import UIStateMixin
from .water_workspace import WorkspaceMixin


RGBA = Tuple[int, int, int, int]


class WaterCorrectionApp(WorkspaceMixin, ProjectWorkflowMixin, DemWorkflowMixin, PaletteMixin, FlowStateMixin, FlowStatusMixin, UIStateMixin, FlowWorkflowMixin, FlowRenderMixin, RasterEditingMixin, EditingHistoryMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("水系栅格数据可视化订正工具")
        self.geometry("1600x980")
        self.minsize(1280, 840)

        self.base_dir = app_base_dir()
        self.user_data_dir = self.base_dir / "user_data"
        self.user_data_dir.mkdir(exist_ok=True)
        self.config_path = self.user_data_dir / "water_workspace.json"
        self.workspace_dir = self._load_workspace_dir()
        self.default_stream = self._prefer_path("Stream_origin.asc")
        self.default_flow = self._prefer_path("FDR.asc")
        self.default_shp = self._prefer_path("重庆/重庆主要河流.shp")
        self.log_path = self.user_data_dir / "water_correction_log.csv"

        self.mode_var = tk.StringVar(value="stream")
        self.tool_var = tk.StringVar(value="brush")
        self.direction_var = tk.StringVar(value="1 东")
        self.brush_size_var = tk.IntVar(value=1)
        self.vector_tol_var = tk.DoubleVar(value=0.2)
        self.zoom_var = tk.DoubleVar(value=1.0)
        self.show_grid_var = tk.BooleanVar(value=False)
        self.show_scale_var = tk.BooleanVar(value=True)
        self.show_flow_arrows_var = tk.BooleanVar(value=False)
        self.compare_original_var = tk.BooleanVar(value=False)
        self.show_confluence_polygon_var = tk.BooleanVar(value=True)
        self.confluence_polygon_width_var = tk.IntVar(value=1)
        self.autosave_var = tk.BooleanVar(value=True)
        self.preset_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="就绪")
        self.mode_status_var = tk.StringVar(value="")
        self.tool_status_var = tk.StringVar(value="")
        self.flow_status_var = tk.StringVar(value="")
        self.session_status_var = tk.StringVar(value="")
        self.stream_file_var = tk.StringVar(value="未加载")
        self.flow_file_var = tk.StringVar(value="未加载")
        self.shp_var = tk.StringVar(value="未加载")
        self.confluence_shp_var = tk.StringVar(value="未加载")
        self.dem_file_var = tk.StringVar(value="未加载")
        self.dem_cache_status_var = tk.StringVar(value="未生成")
        self.dem_score_status_var = tk.StringVar(value="未评估")
        self.dem_flat_tolerance_var = tk.DoubleVar(value=1.0)
        self.dem_mild_uphill_var = tk.DoubleVar(value=2.0)
        self.dem_severe_uphill_var = tk.DoubleVar(value=10.0)
        self.dem_score_display_var = tk.StringVar(value="全部")
        self.coord_var = tk.StringVar(value="")
        self.confluence_inner_radius_var = tk.IntVar(value=3)
        self.confluence_outer_radius_var = tk.IntVar(value=4)
        self.confluence_mode_var = tk.StringVar(value="近远带")
        self.confluence_max_distance_var = tk.IntVar(value=30)
        self.confluence_hint_var = tk.StringVar(value="")
        self.river_flow_mode_var = tk.StringVar(value="平滑")
        self.flow_preview_target_var = tk.StringVar(value="river")

        self.stream_palette: Dict[str, RGBA] = {
            "nodata": (245, 245, 245, 255),
            "river": (31, 119, 180, 255),
            "background": (220, 220, 220, 255),
        }
        self.flow_palette: Dict[int, RGBA] = {
            NODATA: (245, 245, 245, 255),
            1: (217, 48, 37, 255),
            2: (244, 109, 67, 255),
            4: (253, 174, 97, 255),
            8: (254, 224, 144, 255),
            16: (171, 217, 233, 255),
            32: (116, 173, 209, 255),
            64: (69, 117, 180, 255),
            128: (49, 54, 149, 255),
        }
        self.vector_color: RGBA = (220, 30, 30, 190)
        self.confluence_polygon_color: RGBA = (30, 110, 220, 180)
        self.assist_palette: Dict[str, RGBA] = {
            "preview_change_fill": (255, 205, 45, 115),
            "preview_change_outline": (230, 95, 0, 255),
            "preview_change_arrow": (165, 35, 0, 255),
            "preview_same_fill": (40, 150, 220, 70),
            "preview_same_outline": (35, 120, 180, 190),
            "preview_same_arrow": (25, 95, 150, 210),
            "locked_line": (70, 140, 255, 255),
            "locked_fill": (70, 140, 255, 115),
            "selected_line": (255, 153, 0, 255),
            "selected_fill": (255, 192, 80, 130),
            "region_outline": (0, 110, 220, 240),
            "region_fill": (0, 110, 220, 30),
            "source_fill": (30, 170, 80, 235),
            "source_outline": (10, 90, 40, 255),
            "outlet_fill": (220, 45, 40, 240),
            "outlet_outline": (120, 20, 20, 255),
            "node_fill": (35, 110, 230, 235),
            "node_outline": (15, 55, 140, 255),
        }
        self.default_palette_state = self._palette_color_state()
        self._init_flow_state()
        self._init_dem_state()

        self.stream_raster: Optional[RasterData] = None
        self.flow_raster: Optional[RasterData] = None
        self.original_stream_raster: Optional[RasterData] = None
        self.original_flow_raster: Optional[RasterData] = None
        self.vector_layer = None
        self.confluence_polygon_layer: Optional[PolygonLayer] = None
        self.transformer = None
        self.confluence_transformer = None

        self.histories: Dict[str, List[ChangeBatch]] = {"stream": [], "flow": []}
        self.redo_stacks: Dict[str, List[ChangeBatch]] = {"stream": [], "flow": []}
        self.snapshots: Dict[str, List[Tuple[str, RasterData]]] = {"stream": [], "flow": []}

        self.current_batch: Optional[ChangeBatch] = None
        self.dragging = False
        self.last_painted: Optional[Tuple[int, int]] = None
        self._stroke_seen: Set[Tuple[int, int]] = set()
        self._pending_edit = False
        self._press_xy: Optional[Tuple[float, float]] = None
        self._press_hit: Optional[Tuple[int, int, float, float]] = None
        self._secondary_press_xy: Optional[Tuple[float, float]] = None
        self._secondary_press_hit: Optional[Tuple[int, int, float, float]] = None
        self._drag_threshold = 3
        self._drag_is_flow_line = False
        self._secondary_dragging = False
        self._painted_preview: Set[Tuple[int, int]] = set()
        self._flow_preview_raster: Optional[RasterData] = None
        self._flow_preview_batch: Optional[ChangeBatch] = None
        self._flow_preview_last_cell: Optional[Tuple[int, int]] = None
        self._flow_network_cache_key: Optional[Tuple[object, ...]] = None
        self._flow_network_cache: Optional[Dict[str, object]] = None
        self._pan_dragging = False
        self._pan_origin_view: Optional[Tuple[float, float]] = None
        self._last_motion_update = 0.0
        self._last_motion_text = ""
        self._refresh_job: Optional[str] = None
        self._view_refresh_job: Optional[str] = None
        self._view_refresh_full_requested = False
        self._autosave_job: Optional[str] = None
        self._full_render_requested = True
        self._render_signature: Optional[Tuple] = None
        self._dirty_cells: Set[Tuple[int, int]] = set()
        self._dirty_bbox: Optional[Tuple[int, int, int, int]] = None
        self._view_x = 0.0
        self._view_y = 0.0
        self._pan_pointer: Optional[Tuple[float, float]] = None
        self._canvas_size: Optional[Tuple[int, int]] = None
        self._viewport_cache_key: Optional[Tuple] = None
        self._viewport_cache_image: Optional[Image.Image] = None

        self.canvas_image_id: Optional[int] = None
        self.tk_image = None
        self.rendered_image: Optional[Image.Image] = None
        self.base_scaled_image: Optional[Image.Image] = None
        self.overlay_image: Optional[Image.Image] = None

        self._presets_path = self.user_data_dir / "water_palette_presets.json"
        self._shortcuts_path = self.user_data_dir / "water_shortcuts.json"
        self._autosave_data_path = self.user_data_dir / "water_session_autosave.npz"
        self._autosave_meta_path = self.user_data_dir / "water_session_autosave.json"
        self.palette_presets: Dict[str, Dict[str, object]] = {}
        self.shortcuts: Dict[str, str] = dict(DEFAULT_SHORTCUTS)

        self._build_ui()
        self.on_tool_changed()
        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-y>", lambda e: self.redo())
        self.bind_all("<KeyPress>", self.on_global_keypress, add=True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._setup_log_file()
        self._load_palette_presets()
        self._load_shortcuts()
        self._update_shortcut_hint()
        if not self._restore_autosave():
            self._load_defaults()
        self._schedule_autosave()
        self._install_tooltips()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=6)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        top_row = ttk.Frame(toolbar)
        top_row.grid(row=0, column=0, sticky="ew")
        view_row = ttk.Frame(toolbar)
        view_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        file_bar = ttk.LabelFrame(top_row, text="文件与项目", padding=(6, 4))
        file_bar.pack(side="left", padx=(0, 8))
        self.btn_load_stream = ttk.Button(file_bar, text="加载河道ASC", command=self.load_stream_dialog)
        self.btn_load_stream.grid(row=0, column=0, padx=(0, 4))
        self.btn_load_flow = ttk.Button(file_bar, text="加载流向ASC", command=self.load_flow_dialog)
        self.btn_load_flow.grid(row=0, column=1, padx=(0, 4))
        self.btn_load_shp = ttk.Button(file_bar, text="加载河流SHP", command=self.load_shp_dialog)
        self.btn_load_shp.grid(row=0, column=2, padx=(0, 8))
        self.btn_load_confluence_polygon = ttk.Button(file_bar, text="加载范围SHP", command=self.load_confluence_polygon_dialog)
        self.btn_load_confluence_polygon.grid(row=0, column=3, padx=(0, 8))
        self.btn_open_project = ttk.Button(file_bar, text="打开项目", command=self.open_project_dialog)
        self.btn_open_project.grid(row=0, column=4, padx=(0, 4))
        self.btn_save_project = ttk.Button(file_bar, text="保存项目", command=self.save_project_dialog)
        self.btn_save_project.grid(row=0, column=5, padx=(0, 4))
        self.btn_export = ttk.Button(file_bar, text="导出ASC", command=self.export_active)
        self.btn_export.grid(row=0, column=6)

        mode_bar = ttk.LabelFrame(top_row, text="工作模式", padding=(6, 4))
        mode_bar.pack(side="left", padx=(0, 8))
        self.radio_stream = ttk.Radiobutton(mode_bar, text="订正河道", variable=self.mode_var, value="stream", command=self.on_mode_changed)
        self.radio_stream.grid(row=0, column=0, padx=(0, 6))
        self.radio_flow = ttk.Radiobutton(mode_bar, text="订正流向", variable=self.mode_var, value="flow", command=self.on_mode_changed)
        self.radio_flow.grid(row=0, column=1)

        edit_bar = ttk.LabelFrame(top_row, text="编辑记录", padding=(6, 4))
        edit_bar.pack(side="left")
        self.btn_undo = ttk.Button(edit_bar, text="撤销", command=self.undo)
        self.btn_undo.grid(row=0, column=0, padx=(0, 4))
        self.btn_redo = ttk.Button(edit_bar, text="重做", command=self.redo)
        self.btn_redo.grid(row=0, column=1, padx=(0, 4))
        self.btn_snapshot = ttk.Button(edit_bar, text="快照", command=self.take_snapshot)
        self.btn_snapshot.grid(row=0, column=2)

        view_bar = ttk.LabelFrame(view_row, text="视图", padding=(6, 4))
        view_bar.pack(side="left", padx=(0, 8))
        self.btn_fit = ttk.Button(view_bar, text="适配窗口", command=self.fit_content_to_view)
        self.btn_fit.grid(row=0, column=0, padx=(0, 4))
        self.btn_center_shp = ttk.Button(view_bar, text="居中SHP", command=self.center_shp_at_current_zoom)
        self.btn_center_shp.grid(row=0, column=1, padx=(0, 8))
        self.btn_zoom_in = ttk.Button(view_bar, text="放大", command=lambda: self.change_zoom(1.25))
        self.btn_zoom_in.grid(row=0, column=2, padx=(0, 4))
        self.btn_zoom_out = ttk.Button(view_bar, text="缩小", command=lambda: self.change_zoom(0.8))
        self.btn_zoom_out.grid(row=0, column=3, padx=(0, 8))
        ttk.Label(view_bar, text="缩放").grid(row=0, column=4, padx=(0, 4))
        ttk.Entry(view_bar, width=8, textvariable=self.zoom_var).grid(row=0, column=5, padx=(0, 4))
        self.btn_zoom_apply = ttk.Button(view_bar, text="应用", command=self.apply_zoom_entry)
        self.btn_zoom_apply.grid(row=0, column=6)

        session_bar = ttk.LabelFrame(view_row, text="会话", padding=(6, 4))
        session_bar.pack(side="left")
        self.chk_autosave = ttk.Checkbutton(session_bar, text="自动保存", variable=self.autosave_var, command=self.update_mode_status)
        self.chk_autosave.grid(row=0, column=0, padx=(0, 6))
        self.btn_restore_autosave = ttk.Button(session_bar, text="恢复自动保存", command=self.restore_autosave_dialog)
        self.btn_restore_autosave.grid(row=0, column=1)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew")
        left = ttk.Frame(main)
        right = ttk.Frame(main, padding=8)
        main.add(left, weight=5)
        main.add(right, weight=2)

        canvas_frame = ttk.Frame(left)
        canvas_frame.pack(fill="both", expand=True)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_frame, background="#f7f7f7", highlightthickness=0)
        self.hbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.on_hscroll)
        self.vbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.on_vscroll)
        self.canvas.configure(xscrollcommand=self._on_canvas_xscroll, yscrollcommand=self._on_canvas_yscroll)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda e: self.info_var.set("就绪"))
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_button_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<ButtonPress-3>", self.on_secondary_press)
        self.canvas.bind("<B3-Motion>", self.on_secondary_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_secondary_release)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)
        self.canvas.bind("<Button-5>", self.on_mousewheel)

        file_box = ttk.LabelFrame(right, text="文件状态", padding=8)
        file_box.pack(fill="x", pady=(0, 8))
        ttk.Label(file_box, text="河道:").grid(row=0, column=0, sticky="w")
        ttk.Label(file_box, textvariable=self.stream_file_var, wraplength=320).grid(row=0, column=1, sticky="w")
        ttk.Label(file_box, text="流向:").grid(row=1, column=0, sticky="w")
        ttk.Label(file_box, textvariable=self.flow_file_var, wraplength=320).grid(row=1, column=1, sticky="w")
        ttk.Label(file_box, text="SHP:").grid(row=2, column=0, sticky="w")
        ttk.Label(file_box, textvariable=self.shp_var, wraplength=320).grid(row=2, column=1, sticky="w")
        ttk.Label(file_box, text="汇流范围:").grid(row=3, column=0, sticky="w")
        ttk.Label(file_box, textvariable=self.confluence_shp_var, wraplength=320).grid(row=3, column=1, sticky="w")
        ttk.Label(file_box, text="DEM:").grid(row=4, column=0, sticky="w")
        ttk.Label(file_box, textvariable=self.dem_file_var, wraplength=320).grid(row=4, column=1, sticky="w")

        status_box = ttk.LabelFrame(right, text="操作模式提示", padding=8)
        status_box.pack(fill="x", pady=(0, 8))
        ttk.Label(status_box, textvariable=self.mode_status_var, wraplength=320, justify="left").pack(anchor="w")
        ttk.Label(status_box, textvariable=self.tool_status_var, wraplength=320, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Label(status_box, textvariable=self.flow_status_var, wraplength=320, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Label(status_box, textvariable=self.session_status_var, wraplength=320, justify="left").pack(anchor="w", pady=(3, 0))

        tool_tabs = ttk.Notebook(right)
        tool_tabs.pack(fill="both", expand=True)
        edit_tab = ttk.Frame(tool_tabs, padding=6)
        display_tab = ttk.Frame(tool_tabs, padding=6)
        flow_tab = ttk.Frame(tool_tabs, padding=6)
        history_tab = ttk.Frame(tool_tabs, padding=6)
        tool_tabs.add(edit_tab, text="编辑")
        tool_tabs.add(display_tab, text="显示")
        tool_tabs.add(flow_tab, text="流向")
        tool_tabs.add(history_tab, text="版本")

        tool_box = ttk.LabelFrame(edit_tab, text="编辑工具", padding=8)
        tool_box.pack(fill="x", pady=(0, 8))
        self.radio_brush_tool = ttk.Radiobutton(tool_box, text="画笔", variable=self.tool_var, value="brush", command=self.on_tool_changed)
        self.radio_brush_tool.grid(row=0, column=0, sticky="w")
        self.radio_eraser_tool = ttk.Radiobutton(tool_box, text="橡皮擦", variable=self.tool_var, value="eraser", command=self.on_tool_changed)
        self.radio_eraser_tool.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(tool_box, text="方向").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.direction_box = ttk.Combobox(tool_box, state="readonly", values=[f"{code} {direction_text(code)}" for code in DIR_ORDER], textvariable=self.direction_var, width=12)
        self.direction_box.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.direction_box.set("1 东")
        self.btn_apply_direction = ttk.Button(tool_box, text="应用方向", command=self.apply_selected_direction)
        self.btn_apply_direction.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        self.btn_flow_suggest = ttk.Button(tool_box, text="断点建议", command=self.suggest_flow_direction)
        self.btn_flow_suggest.grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(8, 0))
        ttk.Label(tool_box, text="画笔大小").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(tool_box, from_=1, to=15, increment=2, width=6, textvariable=self.brush_size_var).grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.btn_shortcuts = ttk.Button(tool_box, text="快捷键设置", command=self.edit_shortcuts)
        self.btn_shortcuts.grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(tool_box, text="矢量容差").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(tool_box, from_=0.0, to=5.0, increment=0.1, width=6, textvariable=self.vector_tol_var).grid(row=3, column=1, sticky="w", pady=(8, 0))
        self.btn_vector_batch = ttk.Button(tool_box, text="矢量批量修正", command=self.apply_vector_batch)
        self.btn_vector_batch.grid(row=3, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        self.vector_hint = ttk.Label(tool_box, text="河道模式可用矢量批量修正；流向模式左键改方向、右键选中像元")
        self.vector_hint.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        display_box = ttk.LabelFrame(display_tab, text="显示开关", padding=8)
        display_box.pack(fill="x", pady=(0, 8))
        self.chk_grid = ttk.Checkbutton(display_box, text="网格", variable=self.show_grid_var, command=self.render)
        self.chk_grid.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.chk_scale = ttk.Checkbutton(display_box, text="比例尺", variable=self.show_scale_var, command=self.render)
        self.chk_scale.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.chk_arrows = ttk.Checkbutton(display_box, text="流向箭头", variable=self.show_flow_arrows_var, command=self.render)
        self.chk_arrows.grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.chk_compare = ttk.Checkbutton(display_box, text="原始对比", variable=self.compare_original_var, command=self.render)
        self.chk_compare.grid(row=0, column=3, sticky="w")

        color_box = ttk.LabelFrame(display_tab, text="颜色编辑", padding=8)
        color_box.pack(fill="x", pady=(0, 8))
        self.btn_stream_palette = ttk.Button(color_box, text="河道栅格", command=self.pick_stream_palette)
        self.btn_stream_palette.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_flow_palette = ttk.Button(color_box, text="流向栅格", command=self.pick_flow_palette)
        self.btn_flow_palette.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_vector_color = ttk.Button(color_box, text="河流线SHP", command=self.pick_vector_color)
        self.btn_vector_color.grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.btn_confluence_polygon_color = ttk.Button(color_box, text="范围面SHP", command=self.pick_confluence_polygon_color)
        self.btn_confluence_polygon_color.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(8, 0))
        self.btn_assist_palette = ttk.Button(color_box, text="辅助标记", command=self.pick_assist_palette)
        self.btn_assist_palette.grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=(8, 0))
        self.btn_reset_palette = ttk.Button(color_box, text="恢复默认颜色", command=self.reset_palette_defaults)
        self.btn_reset_palette.grid(row=1, column=2, sticky="ew", padx=(0, 4), pady=(8, 0))
        for col in range(4):
            display_box.columnconfigure(col, weight=1)
        for col in range(3):
            color_box.columnconfigure(col, weight=1)

        preset_box = ttk.LabelFrame(display_tab, text="配色预设", padding=8)
        preset_box.pack(fill="x", pady=(0, 8))
        self.preset_combo = ttk.Combobox(preset_box, state="readonly", textvariable=self.preset_var, values=[], width=18)
        self.preset_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_load_preset = ttk.Button(preset_box, text="加载", command=self.load_palette_preset_dialog)
        self.btn_load_preset.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_save_preset = ttk.Button(preset_box, text="保存当前", command=self.save_palette_preset_dialog)
        self.btn_save_preset.grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.btn_delete_preset = ttk.Button(preset_box, text="删除", command=self.delete_palette_preset_dialog)
        self.btn_delete_preset.grid(row=0, column=3, sticky="ew")
        preset_box.columnconfigure(0, weight=1)

        info_box = ttk.LabelFrame(display_tab, text="像元信息", padding=8)
        info_box.pack(fill="x", pady=(0, 8))
        ttk.Label(info_box, textvariable=self.coord_var, wraplength=320, justify="left").pack(anchor="w")
        ttk.Label(info_box, textvariable=self.info_var, wraplength=320, justify="left").pack(anchor="w", pady=(4, 0))

        flow_assist_box = ttk.LabelFrame(flow_tab, text="流向辅助", padding=8)
        flow_assist_box.pack(fill="x", pady=(0, 8))
        range_box = ttk.LabelFrame(flow_assist_box, text="0 汇流范围", padding=6)
        range_box.pack(fill="x", pady=(0, 6))
        self.chk_show_confluence_polygon = ttk.Checkbutton(range_box, text="显示边界", variable=self.show_confluence_polygon_var, command=lambda: self.render(full=True))
        self.chk_show_confluence_polygon.grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(range_box, text="线宽").grid(row=0, column=1, sticky="e", padx=(0, 4))
        ttk.Spinbox(range_box, from_=1, to=8, increment=1, width=4, textvariable=self.confluence_polygon_width_var, command=lambda: self.render(full=True)).grid(row=0, column=2, sticky="w")
        self.btn_lock_polygon_stream = ttk.Button(range_box, text="锁定范围内河道", command=self.lock_confluence_polygon_stream_skeleton)
        self.btn_lock_polygon_stream.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        range_box.columnconfigure(2, weight=1)
        lock_box = ttk.LabelFrame(flow_assist_box, text="1 选择与锁定", padding=6)
        lock_box.pack(fill="x", pady=(0, 6))
        self.btn_pick_flow_segment = ttk.Button(lock_box, text="锁定选区河道", command=self.lock_visible_stream_skeleton)
        self.btn_pick_flow_segment.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_add_locked_cell = ttk.Button(lock_box, text="补锁单像元", command=self.add_selected_stream_cell_to_lock)
        self.btn_add_locked_cell.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_remove_locked_region = ttk.Button(lock_box, text="清除选区", command=self.remove_selected_locked_region)
        self.btn_remove_locked_region.grid(row=0, column=2, sticky="ew")
        for col in range(3):
            lock_box.columnconfigure(col, weight=1)

        river_box = ttk.LabelFrame(flow_assist_box, text="2 河道本体流向", padding=6)
        river_box.pack(fill="x", pady=(0, 6))
        self.btn_set_flow_outlet = ttk.Button(river_box, text="设为出口", command=self.set_flow_skeleton_outlet)
        self.btn_set_flow_outlet.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Label(river_box, text="模式").grid(row=0, column=1, sticky="e", padx=(0, 4))
        self.river_flow_mode_box = ttk.Combobox(river_box, state="readonly", values=["平滑", "稳健"], textvariable=self.river_flow_mode_var, width=8)
        self.river_flow_mode_box.grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.river_flow_mode_box.bind("<<ComboboxSelected>>", self.on_river_flow_mode_changed)
        self.btn_preview_river_flow = ttk.Button(river_box, text="预览河道流向", command=self.preview_locked_river_flow)
        self.btn_preview_river_flow.grid(row=0, column=3, sticky="ew")
        river_box.columnconfigure(0, weight=1)
        river_box.columnconfigure(2, weight=1)
        river_box.columnconfigure(3, weight=1)

        confluence_box = ttk.LabelFrame(flow_assist_box, text="3 周边汇流", padding=6)
        confluence_box.pack(fill="x", pady=(0, 6))
        ttk.Label(confluence_box, text="模式").grid(row=0, column=0, sticky="w")
        self.confluence_mode_box = ttk.Combobox(confluence_box, state="readonly", values=["近远带", "范围SHP"], textvariable=self.confluence_mode_var, width=8)
        self.confluence_mode_box.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.confluence_mode_box.bind("<<ComboboxSelected>>", self.on_confluence_mode_changed)
        ttk.Label(confluence_box, text="近带").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(confluence_box, from_=1, to=30, increment=1, width=5, textvariable=self.confluence_inner_radius_var).grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(confluence_box, text="远带").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(confluence_box, from_=1, to=30, increment=1, width=5, textvariable=self.confluence_outer_radius_var).grid(row=0, column=5, sticky="w", padx=(0, 8))
        ttk.Label(confluence_box, text="最大距").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(confluence_box, from_=0, to=300, increment=1, width=6, textvariable=self.confluence_max_distance_var).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(6, 0))
        self.btn_set_downstream = ttk.Button(confluence_box, text="预览周边汇流", command=self.preview_confirmed_confluence)
        self.btn_set_downstream.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        ttk.Label(confluence_box, textvariable=self.confluence_hint_var, wraplength=300, justify="left").grid(row=3, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self._update_confluence_hint()
        confluence_box.columnconfigure(5, weight=1)

        action_box = ttk.LabelFrame(flow_assist_box, text="4 应用与清理", padding=6)
        action_box.pack(fill="x", pady=(0, 6))
        self.btn_reverse_segment = ttk.Button(action_box, text="应用预览", command=self.apply_flow_preview)
        self.btn_reverse_segment.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_preview_segment = ttk.Button(action_box, text="清除当前预览", command=self.clear_flow_preview)
        self.btn_preview_segment.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_confirm_segment = ttk.Button(action_box, text="清空锁定", command=self.clear_flow_segment_state)
        self.btn_confirm_segment.grid(row=0, column=2, sticky="ew")
        for col in range(3):
            action_box.columnconfigure(col, weight=1)
        self.btn_flow_preview = self.btn_set_downstream
        self.btn_flow_apply = self.btn_reverse_segment
        self.btn_preview_confluence = self.btn_set_downstream
        self.btn_apply_flow_preview = self.btn_reverse_segment
        self.btn_clear_flow_preview = self.btn_preview_segment
        self.btn_clear_flow_marks = self.btn_confirm_segment
        self.flow_assist_var = tk.StringVar(value="先修好河道；右键单点或拖框选择目标河道，锁定后设出口，再预览河道流向和周边汇流。")
        ttk.Label(flow_assist_box, textvariable=self.flow_assist_var, wraplength=320, justify="left").pack(fill="x")

        dem_box = ttk.LabelFrame(flow_tab, text="DEM辅助", padding=8)
        dem_box.pack(fill="x", pady=(0, 8))
        self.btn_load_dem = ttk.Button(dem_box, text="加载DEM", command=self.load_dem_dialog)
        self.btn_load_dem.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_build_dem_cache = ttk.Button(dem_box, text="生成锁定范围缓存", command=self.start_locked_dem_cache_task)
        self.btn_build_dem_cache.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_cancel_dem_cache = ttk.Button(dem_box, text="取消缓存", command=self.cancel_dem_cache_task)
        self.btn_cancel_dem_cache.grid(row=0, column=2, sticky="ew")
        self.btn_evaluate_dem_preview = ttk.Button(dem_box, text="评估当前预览", command=self.evaluate_current_flow_preview_with_dem)
        self.btn_evaluate_dem_preview.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(dem_box, text="显示").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.dem_score_display_box = ttk.Combobox(
            dem_box,
            textvariable=self.dem_score_display_var,
            values=("全部", "仅冲突", "隐藏"),
            state="readonly",
            width=8,
        )
        self.dem_score_display_box.grid(row=2, column=0, sticky="e", pady=(6, 0))
        self.dem_score_display_box.bind("<<ComboboxSelected>>", lambda _event: self.render(full=False))
        ttk.Label(dem_box, text="平坦").grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Spinbox(dem_box, from_=0.0, to=50.0, increment=0.5, width=6, textvariable=self.dem_flat_tolerance_var).grid(row=2, column=1, sticky="e", pady=(6, 0))
        ttk.Label(dem_box, text="轻微").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Spinbox(dem_box, from_=0.0, to=100.0, increment=0.5, width=6, textvariable=self.dem_mild_uphill_var).grid(row=2, column=2, sticky="e", pady=(6, 0))
        ttk.Label(dem_box, text="严重").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(dem_box, from_=0.0, to=500.0, increment=1.0, width=6, textvariable=self.dem_severe_uphill_var).grid(row=3, column=0, sticky="e", pady=(6, 0))
        self.btn_locate_dem_conflict = ttk.Button(dem_box, text="定位逆坡冲突", command=self.locate_next_dem_conflict)
        self.btn_locate_dem_conflict.grid(row=3, column=1, sticky="ew", padx=(0, 4), pady=(6, 0))
        self.btn_export_dem_report = ttk.Button(dem_box, text="导出评估报告", command=self.export_dem_score_report)
        self.btn_export_dem_report.grid(row=3, column=2, sticky="ew", pady=(6, 0))
        self.btn_export_dem_conflicts = ttk.Button(dem_box, text="导出冲突报告", command=self.export_dem_conflict_report)
        self.btn_export_dem_conflicts.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(dem_box, text="图例：绿=顺坡，黄=近似平坦，红=逆坡冲突，灰=无DEM", wraplength=320, justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        ttk.Label(dem_box, textvariable=self.dem_cache_status_var, wraplength=320, justify="left").grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(dem_box, textvariable=self.dem_score_status_var, wraplength=320, justify="left").grid(row=7, column=0, columnspan=3, sticky="w", pady=(3, 0))
        for col in range(3):
            dem_box.columnconfigure(col, weight=1)

        snapshot_box = ttk.LabelFrame(history_tab, text="版本快照", padding=8)
        snapshot_box.pack(fill="both", expand=True)
        self.snapshot_list = tk.Listbox(snapshot_box, height=12)
        self.snapshot_list.pack(fill="both", expand=True, side="left")
        self.snapshot_list.bind("<Double-Button-1>", lambda e: self.restore_selected_snapshot())
        snap_scroll = ttk.Scrollbar(snapshot_box, orient="vertical", command=self.snapshot_list.yview)
        snap_scroll.pack(side="right", fill="y")
        self.snapshot_list.configure(yscrollcommand=snap_scroll.set)
        self.btn_restore_snapshot = ttk.Button(history_tab, text="恢复所选快照", command=self.restore_selected_snapshot)
        self.btn_restore_snapshot.pack(fill="x", pady=(8, 8))

        status = ttk.Label(self, textvariable=self.info_var, relief="sunken", anchor="w", padding=(8, 4))
        status.grid(row=2, column=0, sticky="ew")

    def _install_tooltips(self) -> None:
        tips = {
            self.btn_load_stream: "加载河道 ASC 栅格文件。",
            self.btn_load_flow: "加载流向 ASC 栅格文件。",
            self.btn_load_shp: "加载水系矢量参考线。",
            self.btn_open_project: "打开 .waterproj 项目文件，恢复路径和显示设置。",
            self.btn_save_project: "保存当前路径、视图和显示设置到 .waterproj。",
            self.radio_stream: "切换到河道订正模式。",
            self.radio_flow: "切换到流向订正模式。",
            self.btn_undo: "撤销最近一次编辑。",
            self.btn_redo: "重做最近一次撤销。",
            self.btn_fit: "选择一个文件并自动适配到窗口。",
            self.btn_center_shp: "保持当前缩放倍率，将河流SHP移到窗口中央。",
            self.btn_zoom_in: "放大当前视图。",
            self.btn_zoom_out: "缩小当前视图。",
            self.btn_zoom_apply: "按输入框中的缩放值刷新。",
            self.btn_shortcuts: "设置画笔和橡皮擦的键盘快捷键。",
            self.radio_eraser_tool: "橡皮擦仅用于订正河道；订正流向模式会自动禁用。",
            self.btn_vector_batch: "沿参考矢量线批量修正河道像元。",
            self.btn_flow_preview: "预览已锁定河道周边非河道像元的汇流建议。",
            self.btn_flow_apply: "将当前橙色流向预览结果写入流向栅格。",
            self.btn_pick_flow_segment: "右键单点会锁定该像元所在连通河段；右键拖框会锁定框内 Stream=1 河道，不修改河道本体流向。",
            self.btn_set_flow_outlet: "把当前右键选中的锁定河道像元设为本段下游出口。",
            self.btn_preview_river_flow: "按已设出口预览锁定河道本体的 D8 流向，出口像元保留原方向。",
            self.btn_set_downstream: "基于已锁定河道，预览周边非河道像元向河道汇流的方向。",
            self.confluence_mode_box: "选择按近远带缓冲汇流，或按汇流范围 SHP 面内汇流。",
            self.btn_add_locked_cell: "把当前右键单点选中的 Stream=1 河道像元补充加入锁定。",
            self.btn_remove_locked_region: "只清除当前右键单点或拖框范围内的已锁定河道，其他锁定保留。",
            self.btn_reverse_segment: "只将当前橙色预览结果写入流向栅格；蓝色已一致像元不会写入。",
            self.btn_preview_segment: "清除当前河道流向或周边汇流预览，不修改数据，也不清除锁定河道。",
            self.btn_confirm_segment: "清空所有已锁定河道、出口和当前预览，选错范围较大时使用。",
            self.btn_load_confluence_polygon: "加载面状 SHP 作为后续面范围汇流的边界图层，当前阶段只显示边界。",
            self.chk_show_confluence_polygon: "显示或隐藏汇流范围面 SHP 边界。",
            self.btn_lock_polygon_stream: "将汇流范围面内的 Stream=1 河道像元加入当前锁定骨架，不修改栅格值。",
            self.btn_preview_confluence: "基于已锁定河道，预览周边非河道像元向河道汇流的方向。",
            self.btn_clear_flow_marks: "清空所有已锁定河道、出口和当前预览，选错范围较大时使用。",
            self.btn_apply_flow_preview: "只将当前橙色预览结果写入流向栅格。",
            self.btn_clear_flow_preview: "清除当前流向辅助预览，不修改数据，也不清除锁定河道。",
            self.btn_stream_palette: "修改河道栅格的 NoData、河道和背景颜色。",
            self.btn_flow_palette: "修改 8 个 D8 流向和 NoData 的栅格颜色。",
            self.btn_vector_color: "修改河流参考线 SHP 的叠加颜色。",
            self.btn_confluence_polygon_color: "修改汇流范围面 SHP 的边界颜色。",
            self.btn_assist_palette: "修改流向预览、框选、锁定河道、源头/节点/出口等辅助标记颜色。",
            self.btn_load_dem: "加载 GeoTIFF DEM。DEM 不作为底图显示，只作为后续流向判断的地形证据。",
            self.btn_build_dem_cache: "为当前已锁定河道的局部外包范围生成 DEM 粗像元缓存，不扫描全国范围。",
            self.btn_evaluate_dem_preview: "用已生成的 DEM 缓存评估当前流向预览：顺坡、近似平坦、逆坡冲突或无DEM，并显示缓存覆盖率。",
            self.dem_score_display_box: "控制地图上的 DEM 评分标记显示：全部、仅逆坡冲突或隐藏；不影响评估结果和导出报告。",
            self.btn_locate_dem_conflict: "循环跳转到 DEM 评估中的红色逆坡冲突像元，方便人工检查。",
            self.btn_export_dem_report: "导出当前 DEM 评估明细 CSV，包括像元位置、方向、冲突等级、高程差和原因。",
            self.btn_export_dem_conflicts: "只导出当前 DEM 评估中的逆坡冲突像元。",
            self.btn_cancel_dem_cache: "取消正在运行的 DEM 缓存任务，取消后不会保存半成品缓存。",
            self.btn_reset_palette: "恢复内置默认颜色，不改变数据和显示开关。",
            self.preset_combo: "选择一个已保存的配色预设。",
            self.btn_save_preset: "把当前颜色和显示开关保存为预设。",
            self.btn_load_preset: "加载下拉框中选中的预设。",
            self.btn_delete_preset: "删除下拉框中选中的配色预设，不改变当前显示。",
            self.chk_grid: "显示或隐藏网格。",
            self.chk_scale: "显示或隐藏比例尺。",
            self.chk_arrows: "在流向图层上叠加箭头。",
            self.chk_compare: "对比原始图层。",
            self.chk_autosave: "启用或关闭自动保存。",
            self.btn_restore_autosave: "恢复最近一次自动保存。",
            self.btn_restore_snapshot: "恢复选中的版本快照。",
        }
        for widget, text in tips.items():
            ToolTip(widget, text)

    def _load_shortcuts(self) -> None:
        self.shortcuts = load_shortcuts(self._shortcuts_path, self.shortcuts)

    def _save_shortcuts(self) -> None:
        save_shortcuts(self._shortcuts_path, self.shortcuts)

    def _normalize_shortcut(self, value: str) -> str:
        return normalize_shortcut(value)

    def _shortcut_label(self, tool: str) -> str:
        return shortcut_label(self.shortcuts, tool)

    def _update_shortcut_hint(self, view_state: Optional[FlowAssistViewState] = None) -> None:
        if hasattr(self, "vector_hint"):
            flow_note = "；流向模式禁用橡皮擦" if self.mode_var.get() == "flow" else ""
            self.vector_hint.configure(
                text=(
                    f"快捷键：{self._shortcut_label('brush')}=画笔，{self._shortcut_label('eraser')}=橡皮擦；"
                    f"河道模式可用矢量批量修正，流向模式左键改方向{flow_note}"
                )
            )
        self.update_mode_status(view_state)

    def edit_shortcuts(self) -> None:
        dialog = ShortcutSettingsDialog(self, self.shortcuts)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.shortcuts = dict(dialog.result)
        self._save_shortcuts()
        self._update_shortcut_hint()
        self.info_var.set(f"快捷键已保存：{self._shortcut_label('brush')}=画笔，{self._shortcut_label('eraser')}=橡皮擦")

    def on_global_keypress(self, event: tk.Event):
        widget = self.focus_get()
        if isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            return None
        if event.state & 0x0004:
            return None
        key = self._normalize_shortcut(getattr(event, "keysym", "")) or self._normalize_shortcut(getattr(event, "char", ""))
        if not key:
            return None
        if key == self.shortcuts.get("brush"):
            self.set_edit_tool("brush")
            return "break"
        if key == self.shortcuts.get("eraser"):
            self.set_edit_tool("eraser")
            return "break"
        return None

    def set_edit_tool(self, tool: str) -> None:
        if tool not in {"brush", "eraser"}:
            return
        if self.mode_var.get() == "flow" and tool == "eraser":
            if self.tool_var.get() != "brush":
                self.tool_var.set("brush")
                self.on_tool_changed()
            self.info_var.set("订正流向模式禁用橡皮擦，请选择方向后用画笔修改。")
            return
        if self.tool_var.get() == tool:
            return
        self.tool_var.set(tool)
        self.on_tool_changed()
        label = "画笔" if tool == "brush" else "橡皮擦"
        self.info_var.set(f"已切换到{label}")

    def _maybe_setup_transformer(self) -> None:
        self.transformer = self._build_layer_transformer(self.vector_layer)
        self.confluence_transformer = self._build_layer_transformer(self.confluence_polygon_layer)

    def _build_layer_transformer(self, layer) -> Optional[Transformer]:
        return self._build_layer_transformer_for_raster(layer, self.get_active_raster())

    def _build_layer_transformer_for_raster(self, layer, raster: Optional[RasterData]) -> Optional[Transformer]:
        if not CRS or not Transformer or not layer:
            return None
        if raster is None or not raster.crs_text.strip() or not layer.crs_text.strip():
            return None
        if raster.crs_text.strip() == layer.crs_text.strip():
            return None
        try:
            return Transformer.from_crs(CRS.from_wkt(layer.crs_text.strip()), CRS.from_wkt(raster.crs_text.strip()), always_xy=True)
        except Exception:
            return None

    def load_stream_dialog(self) -> None:
        path = filedialog.askopenfilename(title="选择河道ASC", filetypes=[("ASC files", "*.asc"), ("All files", "*.*")])
        if path:
            self.load_stream(Path(path))

    def load_flow_dialog(self) -> None:
        path = filedialog.askopenfilename(title="选择流向ASC", filetypes=[("ASC files", "*.asc"), ("All files", "*.*")])
        if path:
            self.load_flow(Path(path))

    def load_shp_dialog(self) -> None:
        path = filedialog.askopenfilename(title="选择SHP", filetypes=[("Shapefile", "*.shp"), ("All files", "*.*")])
        if path:
            self.load_shp(Path(path))

    def load_confluence_polygon_dialog(self) -> None:
        path = filedialog.askopenfilename(title="选择汇流范围面SHP", filetypes=[("Shapefile", "*.shp"), ("All files", "*.*")])
        if path:
            self.load_confluence_polygon(Path(path))

    def load_stream(self, path: Path, switch_mode: bool = True, update_autosave: bool = True, validate_kind: bool = True) -> None:
        raster = parse_asc(path)
        if validate_kind and not self._confirm_raster_kind(raster, "stream"):
            return
        self._invalidate_dem_cache_for_raster_change()
        self.stream_raster = raster
        self.original_stream_raster = self.stream_raster.copy()
        self.stream_file_var.set(self._store_path(path))
        if switch_mode:
            self.mode_var.set("stream")
        self._reset_flow_selection_state(clear_segment=False)
        self._clear_flow_skeleton_state()
        self.histories["stream"].clear()
        self.redo_stacks["stream"].clear()
        self.snapshots["stream"].clear()
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.on_tool_changed()
        self.render(full=True)
        self.refresh_snapshot_list()
        if update_autosave and self.autosave_var.get():
            self.save_autosave()
        self.info_var.set(f"已加载河道ASC {path.name}")

    def load_flow(self, path: Path, switch_mode: bool = True, update_autosave: bool = True, validate_kind: bool = True) -> None:
        raster = parse_asc(path)
        if validate_kind and not self._confirm_raster_kind(raster, "flow"):
            return
        self._invalidate_dem_cache_for_raster_change()
        self.flow_raster = raster
        self.original_flow_raster = self.flow_raster.copy()
        self.flow_file_var.set(self._store_path(path))
        if switch_mode:
            self.mode_var.set("flow")
        self._reset_flow_selection_state()
        self._reset_flow_lock_state()
        self._reset_flow_marker_state()
        self._reset_flow_preview_state()
        self.histories["flow"].clear()
        self.redo_stacks["flow"].clear()
        self.snapshots["flow"].clear()
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.on_tool_changed()
        self.render(full=True)
        self.refresh_snapshot_list()
        if update_autosave and self.autosave_var.get():
            self.save_autosave()
        self.info_var.set(f"已加载流向ASC {path.name}")

    def load_shp(self, path: Path, update_autosave: bool = True) -> None:
        self.vector_layer = parse_shapefile_lines(path)
        self.shp_var.set(self._store_path(path))
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.on_tool_changed()
        self.render(full=True)
        if update_autosave and self.autosave_var.get():
            self.save_autosave()
        self.info_var.set(f"已加载SHP {path.name}")

    def load_confluence_polygon(self, path: Path, update_autosave: bool = True) -> None:
        try:
            self.confluence_polygon_layer = parse_shapefile_polygon(path)
        except Exception as exc:
            messagebox.showerror("汇流范围SHP加载失败", str(exc))
            return
        self.confluence_shp_var.set(self._store_path(path))
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.update_mode_status()
        if update_autosave and self.autosave_var.get():
            self.save_autosave()
        self.info_var.set(f"已加载汇流范围SHP {path.name}")

    def _confirm_raster_kind(self, raster: RasterData, expected: str) -> bool:
        if self._looks_like_raster_kind(raster, expected):
            return True
        kind_text = "河道ASC" if expected == "stream" else "流向ASC"
        opposite = "流向ASC" if expected == "stream" else "河道ASC"
        return messagebox.askyesno(
            "文件类型确认",
            f"{raster.path.name} 看起来更像{opposite}，不像{kind_text}。\n仍要作为{kind_text}加载吗？",
        )

    def _looks_like_raster_kind(self, raster: RasterData, expected: str) -> bool:
        valid_flow = set(DIR_ORDER)
        values = set(int(v) for v in np.unique(raster.data[: min(raster.nrows, 200), : min(raster.ncols, 200)]).tolist())
        non_nodata = {v for v in values if v != NODATA}
        if not non_nodata:
            return True
        if expected == "stream":
            suspicious_flow_values = non_nodata - {STREAM_VALUE}
            return not (suspicious_flow_values and suspicious_flow_values.issubset(valid_flow))
        if expected == "flow":
            return not non_nodata.issubset({STREAM_VALUE})
        return True

    def get_active_raster(self) -> Optional[RasterData]:
        return self.stream_raster if self.mode_var.get() == "stream" else self.flow_raster

    def get_original_active_raster(self) -> Optional[RasterData]:
        return self.original_stream_raster if self.mode_var.get() == "stream" else self.original_flow_raster

    def active_mode(self) -> str:
        return self.mode_var.get()

    def mode_name(self) -> str:
        return "订正河道" if self.active_mode() == "stream" else "订正流向"

    def fit_content_to_view(self) -> None:
        dialog = FitTargetDialog(self, self.stream_raster is not None, self.flow_raster is not None, self.vector_layer is not None)
        self.wait_window(dialog)
        target = dialog.result
        if target is None:
            return
        if target == "stream":
            if self.stream_raster is None:
                messagebox.showwarning("提示", "当前没有加载河道文件。")
                return
            self.mode_var.set("stream")
            self.on_mode_changed()
        elif target == "flow":
            if self.flow_raster is None:
                messagebox.showwarning("提示", "当前没有加载流向文件。")
                return
            self.mode_var.set("flow")
            self.on_mode_changed()
        elif target == "vector":
            if self.vector_layer is None:
                messagebox.showwarning("提示", "当前没有加载河流SHP。")
                return
            self._maybe_setup_transformer()

        raster = self.get_active_raster()
        if raster is None:
            return
        self.update_idletasks()
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        if target == "vector":
            bounds = self._vector_bounds_in_raster(raster)
            if bounds is None:
                messagebox.showwarning("提示", "当前河流SHP没有可用于适配的有效范围。")
                return
            row0, col0, row1, col1 = bounds
            center_row = (row0 + row1 + 1) * 0.5
            center_col = (col0 + col1 + 1) * 0.5
            fit_w = max(1, (col1 - col0 + 1))
            fit_h = max(1, (row1 - row0 + 1))
        else:
            row0, col0, row1, col1 = 0, 0, raster.nrows - 1, raster.ncols - 1
            center_row = raster.nrows * 0.5
            center_col = raster.ncols * 0.5
            fit_w = max(1, raster.ncols)
            fit_h = max(1, raster.nrows)
        pad = 0.12
        zoom = min(w / (fit_w * (1.0 + pad)), h / (fit_h * (1.0 + pad)))
        zoom = max(0.15, min(zoom, 8.0))
        self.zoom_var.set(round(zoom, 3))
        self._set_viewport_center(center_row, center_col, zoom, w, h)
        self.render(full=True)

    def center_shp_at_current_zoom(self) -> None:
        if self.vector_layer is None:
            messagebox.showwarning("提示", "当前没有加载河流SHP。")
            return
        raster = self.get_active_raster()
        if raster is None:
            messagebox.showwarning("提示", "请先加载当前模式对应的ASC栅格。")
            return
        self._maybe_setup_transformer()
        bounds = self._vector_bounds_in_raster(raster)
        if bounds is None:
            messagebox.showwarning("提示", "当前河流SHP没有可用于居中的有效范围。")
            return
        row0, col0, row1, col1 = bounds
        center_row = (row0 + row1 + 1) * 0.5
        center_col = (col0 + col1 + 1) * 0.5
        self.update_idletasks()
        zoom = max(0.1, min(float(self.zoom_var.get()), 16.0))
        self.zoom_var.set(round(zoom, 3))
        self._set_viewport_center(center_row, center_col, zoom, max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        self.render(full=True)
        self.info_var.set("已按当前缩放倍率居中河流SHP")

    def _vector_bounds_in_raster(self, raster: RasterData) -> Optional[Tuple[int, int, int, int]]:
        if self.vector_layer is None:
            return None
        rows: List[int] = []
        cols: List[int] = []
        for line in self.vector_layer.polylines:
            for x, y in line:
                if self.transformer is not None:
                    x, y = self.transformer.transform(x, y)
                row, col = raster.world_to_rc(x, y)
                rows.append(int(math.floor(row)))
                cols.append(int(math.floor(col)))
        if not rows or not cols:
            return None
        row0 = clamp(min(rows), 0, raster.nrows - 1)
        row1 = clamp(max(rows), 0, raster.nrows - 1)
        col0 = clamp(min(cols), 0, raster.ncols - 1)
        col1 = clamp(max(cols), 0, raster.ncols - 1)
        if row1 < row0 or col1 < col0:
            return None
        return row0, col0, row1, col1

    def _set_viewport_center(self, row_center: float, col_center: float, zoom: float, width: int, height: int) -> None:
        raster = self.get_active_raster()
        if raster is None:
            return
        total_w = max(1, int(round(raster.ncols * zoom)))
        total_h = max(1, int(round(raster.nrows * zoom)))
        center_x = col_center * zoom
        center_y = row_center * zoom
        self._view_x = max(0.0, min(float(max(0, total_w - width)), center_x - width * 0.5))
        self._view_y = max(0.0, min(float(max(0, total_h - height)), center_y - height * 0.5))

    def apply_zoom_entry(self) -> None:
        try:
            zoom = float(self.zoom_var.get())
        except Exception:
            messagebox.showerror("缩放错误", "缩放值必须是大于 0 的数字。")
            return
        if zoom <= 0:
            messagebox.showerror("缩放错误", "缩放值必须是大于 0 的数字。")
            return
        self.zoom_var.set(round(zoom, 3))
        self.schedule_view_refresh(full=True)

    def change_zoom(self, factor: float) -> None:
        try:
            old_zoom = float(self.zoom_var.get())
        except Exception:
            old_zoom = 1.0
        old_zoom = max(0.1, min(old_zoom, 16.0))
        raster = self.get_active_raster()
        if raster is not None:
            center_row = (self._view_y + max(1, self.canvas.winfo_height()) * 0.5) / old_zoom
            center_col = (self._view_x + max(1, self.canvas.winfo_width()) * 0.5) / old_zoom
        zoom = max(0.1, min(old_zoom * factor, 16.0))
        self.zoom_var.set(round(zoom, 3))
        if raster is not None:
            self._set_viewport_center(center_row, center_col, float(self.zoom_var.get()), max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        self.schedule_view_refresh(full=True)

    def on_mousewheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.change_zoom(1.15)
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self.change_zoom(0.87)

    def on_canvas_configure(self, _event: tk.Event) -> None:
        self._canvas_size = (max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        if self.rendered_image is None and self.get_active_raster() is not None:
            self.render(full=True)
        else:
            self.schedule_view_refresh()

    def _on_canvas_xscroll(self, first: str, last: str) -> None:
        self.hbar.set(first, last)

    def _on_canvas_yscroll(self, first: str, last: str) -> None:
        self.vbar.set(first, last)

    def on_hscroll(self, *args) -> None:
        self._scroll_view("x", *args)
        self.schedule_view_refresh()

    def on_vscroll(self, *args) -> None:
        self._scroll_view("y", *args)
        self.schedule_view_refresh()

    def on_pan_start(self, event: tk.Event) -> None:
        self._pan_dragging = True
        self._pan_pointer = (float(event.x), float(event.y))
        self._pan_origin_view = (self._view_x, self._view_y)
        self.canvas.configure(cursor="fleur")

    def on_pan_move(self, event: tk.Event) -> None:
        if not self._pan_dragging or self._pan_pointer is None or self._pan_origin_view is None:
            return
        dx = float(event.x) - self._pan_pointer[0]
        dy = float(event.y) - self._pan_pointer[1]
        self._set_viewport_offset(self._pan_origin_view[0] - dx, self._pan_origin_view[1] - dy)
        self.schedule_view_refresh()

    def on_pan_end(self, _event: tk.Event) -> None:
        self._pan_dragging = False
        self._pan_origin_view = None
        self._pan_pointer = None
        self.canvas.configure(cursor="")

    def on_secondary_press(self, event: tk.Event) -> None:
        if self.mode_var.get() not in {"stream", "flow"}:
            return
        hit = self.canvas_to_rc(event.x, event.y)
        if not hit:
            return
        self._secondary_press_xy = (float(event.x), float(event.y))
        self._secondary_press_hit = hit
        self._secondary_dragging = False
        self.selected_flow_cell = (hit[0], hit[1])
        self.selected_flow_region = None

    def on_secondary_drag(self, event: tk.Event) -> None:
        if self.mode_var.get() not in {"stream", "flow"}:
            return
        if self._secondary_press_xy is None or self._secondary_press_hit is None:
            return
        hit = self.canvas_to_rc(event.x, event.y)
        if not hit:
            return
        dx = abs(float(event.x) - self._secondary_press_xy[0])
        dy = abs(float(event.y) - self._secondary_press_xy[1])
        if not self._secondary_dragging and max(dx, dy) < self._drag_threshold:
            return
        self._secondary_dragging = True
        start_row, start_col, _, _ = self._secondary_press_hit
        row, col, _, _ = hit
        self.selected_flow_cell = (start_row, start_col)
        self.selected_flow_region = (
            min(start_row, row),
            max(start_row, row),
            min(start_col, col),
            max(start_col, col),
        )
        self.coord_var.set(f"已框选像元: ({self.selected_flow_region[0]}, {self.selected_flow_region[2]}) - ({self.selected_flow_region[1]}, {self.selected_flow_region[3]})")
        self.info_var.set("右键拖框中，松开后将把该范围作为锁定目标")
        self.schedule_view_refresh()

    def on_secondary_release(self, event: tk.Event) -> None:
        if self.mode_var.get() not in {"stream", "flow"}:
            self._secondary_press_xy = None
            self._secondary_press_hit = None
            self._secondary_dragging = False
            return
        hit = self.canvas_to_rc(event.x, event.y)
        press_hit = self._secondary_press_hit
        if press_hit is None and hit is None:
            self._secondary_press_xy = None
            self._secondary_press_hit = None
            self._secondary_dragging = False
            return
        if hit is None:
            hit = press_hit
        if hit is None:
            self._secondary_press_xy = None
            self._secondary_press_hit = None
            self._secondary_dragging = False
            return
        row, col, _, _ = hit
        if not self._secondary_dragging and press_hit is not None:
            self.selected_flow_cell = (row, col)
            self.selected_flow_region = None
            raster = self.get_active_raster()
            if raster is not None:
                value = raster.value_at(row, col)
                if self.mode_var.get() == "flow" and value in DIR_ORDER:
                    self.direction_var.set(f"{value} {direction_text(value)}")
                self.coord_var.set(f"已选中像元: ({row}, {col})")
                if self.mode_var.get() == "flow":
                    self.info_var.set(f"右键已选中像元 ({row}, {col})，可在方向下拉框中手动应用方向")
                else:
                    self.info_var.set(f"右键已选中像元 ({row}, {col})，可点击“锁定选区河道”锁定目标河道")
        else:
            start_row, start_col, _, _ = press_hit if press_hit is not None else hit
            self.selected_flow_cell = (start_row, start_col)
            self.selected_flow_region = (
                min(start_row, row),
                max(start_row, row),
                min(start_col, col),
                max(start_col, col),
            )
            self.coord_var.set(
                f"已框选像元: ({self.selected_flow_region[0]}, {self.selected_flow_region[2]}) - ({self.selected_flow_region[1]}, {self.selected_flow_region[3]})"
            )
            self.info_var.set("右键框选完成，点击“锁定选区河道”即可锁定该范围内的目标河道")
        if self.selected_flow_segment is not None:
            self._reset_flow_selection_state(clear_cell=False, clear_region=False, clear_segment=True)
        self._secondary_press_xy = None
        self._secondary_press_hit = None
        self._secondary_dragging = False
        self._refresh_flow_controls()
        self.render(full=False)

    def canvas_to_rc(self, x: float, y: float) -> Optional[Tuple[int, int, float, float]]:
        raster = self.get_active_raster()
        if raster is None:
            return None
        zoom = float(self.zoom_var.get())
        px = (self._view_x + x) / zoom
        py = (self._view_y + y) / zoom
        col = int(math.floor(px))
        row = int(math.floor(py))
        if 0 <= row < raster.nrows and 0 <= col < raster.ncols:
            wx, wy = raster.rc_to_world(row, col)
            return row, col, wx, wy
        return None

    def _scroll_view(self, axis: str, *args) -> None:
        raster = self.get_active_raster()
        if raster is None:
            return
        zoom = float(self.zoom_var.get())
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        total_w = max(1, int(round(raster.ncols * zoom)))
        total_h = max(1, int(round(raster.nrows * zoom)))
        if axis == "x":
            max_offset = max(0.0, float(total_w - canvas_width))
            current = self._view_x
        else:
            max_offset = max(0.0, float(total_h - canvas_height))
            current = self._view_y
        if not args:
            return
        command = args[0]
        if command == "moveto" and len(args) >= 2:
            frac = float(args[1])
            value = max_offset * frac
        elif command == "scroll" and len(args) >= 3:
            amount = float(args[1])
            unit = args[2]
            step = 30.0 if unit == "units" else max(1.0, float(canvas_height if axis == "y" else canvas_width) * 0.9)
            value = current + amount * step
        else:
            value = current
        self._set_viewport_offset(value if axis == "x" else self._view_x, value if axis == "y" else self._view_y)
        self._update_scrollbars(total_w, total_h, canvas_width, canvas_height)

    def _set_viewport_offset(self, view_x: float, view_y: float) -> None:
        raster = self.get_active_raster()
        if raster is None:
            return
        zoom = float(self.zoom_var.get())
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        total_w = max(1, int(round(raster.ncols * zoom)))
        total_h = max(1, int(round(raster.nrows * zoom)))
        self._view_x = max(0.0, min(float(max(0, total_w - canvas_width)), float(view_x)))
        self._view_y = max(0.0, min(float(max(0, total_h - canvas_height)), float(view_y)))
        self._update_scrollbars(total_w, total_h, canvas_width, canvas_height)

    def _update_scrollbars(self, total_w: int, total_h: int, canvas_width: int, canvas_height: int) -> None:
        if total_w <= canvas_width:
            x_first, x_last = 0.0, 1.0
        else:
            x_first = self._view_x / float(total_w)
            x_last = min(1.0, (self._view_x + canvas_width) / float(total_w))
        if total_h <= canvas_height:
            y_first, y_last = 0.0, 1.0
        else:
            y_first = self._view_y / float(total_h)
            y_last = min(1.0, (self._view_y + canvas_height) / float(total_h))
        self.hbar.set(x_first, x_last)
        self.vbar.set(y_first, y_last)

    def _invalidate_viewport_cache(self) -> None:
        self._viewport_cache_key = None
        self._viewport_cache_image = None
        self.base_scaled_image = None
        self.overlay_image = None
        self._invalidate_flow_network_cache()

    def on_motion(self, event: tk.Event) -> None:
        now = time.monotonic()
        if now - self._last_motion_update < 0.03:
            return
        hit = self.canvas_to_rc(event.x, event.y)
        raster = self.get_active_raster()
        if hit and raster:
            row, col, wx, wy = hit
            value = raster.value_at(row, col)
            text = f"行列: ({row}, {col})  坐标: ({wx:.6f}, {wy:.6f})  值: {fmt_value(value)}"
            if self.mode_var.get() == "flow":
                text += f"  方向: {direction_text(value)}"
            self.coord_var.set(text)
            if text != self._last_motion_text:
                self.info_var.set(text)
                self._last_motion_text = text
            self._last_motion_update = now
        else:
            self.coord_var.set("")
            self.info_var.set("指针在栅格范围外")

    def on_button_press(self, event: tk.Event) -> None:
        hit = self.canvas_to_rc(event.x, event.y)
        if not hit:
            return
        row, col, _, _ = hit
        self._press_xy = (float(event.x), float(event.y))
        self._press_hit = hit
        self._pending_edit = True
        self.dragging = False
        self.last_painted = None
        self._stroke_seen = set()
        self.current_batch = None
        self._drag_is_flow_line = False
        self._flow_preview_raster = None
        self._flow_preview_batch = None
        self._flow_preview_last_cell = None
        if self.mode_var.get() == "flow":
            self.selected_flow_cell = (row, col)

    def on_button_drag(self, event: tk.Event) -> None:
        if not self._pending_edit or self._press_hit is None or self._press_xy is None:
            return
        hit = self.canvas_to_rc(event.x, event.y)
        if not hit:
            return
        row, col, _, _ = hit
        if not self.dragging:
            dx = abs(float(event.x) - self._press_xy[0])
            dy = abs(float(event.y) - self._press_xy[1])
            if max(dx, dy) < self._drag_threshold:
                return
            self.dragging = True
            if self.active_mode() == "flow" and self.tool_var.get() == "brush":
                self._drag_is_flow_line = True
                self._flow_preview_raster = None
                self._flow_preview_batch = ChangeBatch(mode="flow", tool="direction_line", note="direction line")
                self.current_batch = self._flow_preview_batch
                self._flow_preview_last_cell = None
            else:
                self.current_batch = ChangeBatch(mode=self.active_mode(), tool=self.tool_var.get(), note="mouse edit")
            press_row, press_col, _, _ = self._press_hit
            if self.active_mode() == "flow" and self._drag_is_flow_line:
                self.paint_direction_line_to(press_row, press_col, row, col)
            else:
                self.paint_stroke_to(press_row, press_col)
                self.paint_stroke_to(row, col)
            return
        if self.active_mode() == "flow" and self._drag_is_flow_line:
            press_row, press_col, _, _ = self._press_hit
            self.paint_direction_line_to(press_row, press_col, row, col)
        else:
            self.paint_stroke_to(row, col)

    def on_button_release(self, _event: tk.Event) -> None:
        if not self._pending_edit or self._press_hit is None:
            return
        if not self.dragging:
            row, col, _, _ = self._press_hit
            if self.active_mode() == "flow":
                self.current_batch = ChangeBatch(mode="flow", tool="direction", note="flow click")
                self.paint_flow_cell(row, col, self.current_edit_value())
                self.selected_flow_cell = (row, col)
            else:
                self.current_batch = ChangeBatch(mode=self.active_mode(), tool=self.tool_var.get(), note="mouse edit")
                self.paint_stroke_to(row, col)
        elif self._drag_is_flow_line and self._flow_preview_batch is not None:
            self.current_batch = self._flow_preview_batch
        self.dragging = False
        had_ops = bool(self.current_batch and self.current_batch.ops)
        if self.current_batch and self.current_batch.ops:
            self.histories[self.active_mode()].append(self.current_batch)
            if len(self.histories[self.active_mode()]) > 50:
                self.histories[self.active_mode()] = self.histories[self.active_mode()][-50:]
            self.redo_stacks[self.active_mode()].clear()
            self.log_batch(self.current_batch)
            self.take_snapshot(silent=True)
            self.info_var.set(f"已完成 {len(self.current_batch.ops)} 个像元修改")
        self.current_batch = None
        self.last_painted = None
        self._stroke_seen = set()
        self._press_xy = None
        self._press_hit = None
        self._pending_edit = False
        self._drag_is_flow_line = False
        self._flow_preview_raster = None
        self._flow_preview_batch = None
        self._flow_preview_last_cell = None
        if self.active_mode() == "flow":
            self._refresh_flow_controls()
        self.schedule_view_refresh(full=had_ops and not self._dirty_cells)

    def schedule_refresh(self) -> None:
        if self._refresh_job is None:
            self._refresh_job = self.after(12, self.flush_pending_render)

    def schedule_view_refresh(self, full: bool = False) -> None:
        self._view_refresh_full_requested = self._view_refresh_full_requested or full
        if self._view_refresh_job is None:
            self._view_refresh_job = self.after(20, self.flush_view_refresh)

    def flush_view_refresh(self) -> None:
        if self._view_refresh_job is not None:
            try:
                self.after_cancel(self._view_refresh_job)
            except Exception:
                pass
            self._view_refresh_job = None
        full = self._view_refresh_full_requested
        self._view_refresh_full_requested = False
        self.render(full=full)

    def flush_pending_render(self, force: bool = False) -> None:
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if force:
            self._full_render_requested = True
        if self._requires_full_refresh_for_dirty_overlay():
            self._full_render_requested = True
        self.render(full=False)

    def _requires_full_refresh_for_dirty_overlay(self) -> bool:
        return (
            self.show_grid_var.get()
            or self.show_scale_var.get()
            or self.compare_original_var.get()
            or self.vector_layer is not None
            or (self.confluence_polygon_layer is not None and self.show_confluence_polygon_var.get())
            or (self.mode_var.get() == "flow" and self.show_flow_arrows_var.get())
        )

    def preview_flow_from_shp(self) -> None:
        self.preview_confirmed_confluence()

    def apply_flow_from_shp(self) -> None:
        self.apply_flow_preview()

    def build_flow_suggestions_from_shp(self) -> List[Tuple[int, int, int]]:
        raster = self.flow_raster
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return []
        if self.vector_layer is None:
            messagebox.showwarning("提示", "请先加载SHP参考文件。")
            return []
        votes: Dict[Tuple[int, int], Dict[int, int]] = {}
        self._maybe_setup_transformer()
        for line in self.vector_layer.polylines:
            if len(line) < 2:
                continue
            for idx in range(len(line) - 1):
                x0, y0 = line[idx]
                x1, y1 = line[idx + 1]
                if self.transformer is not None:
                    x0, y0 = self.transformer.transform(x0, y0)
                    x1, y1 = self.transformer.transform(x1, y1)
                row0, col0 = raster.world_to_rc(x0, y0)
                row1, col1 = raster.world_to_rc(x1, y1)
                direction = self._direction_from_delta(int(round(row0)), int(round(col0)), int(round(row1)), int(round(col1)))
                if direction is None:
                    continue
                for row, col in line_cells((int(round(row0)), int(round(col0))), (int(round(row1)), int(round(col1)))):
                    if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
                        continue
                    cell_votes = votes.setdefault((row, col), {})
                    cell_votes[direction] = cell_votes.get(direction, 0) + 1
        suggestions: List[Tuple[int, int, int]] = []
        for (row, col), cell_votes in votes.items():
            code = max(cell_votes.items(), key=lambda item: (item[1], -DIR_ORDER.index(item[0]) if item[0] in DIR_ORDER else -999))[0]
            if raster.value_at(row, col) != code:
                suggestions.append((row, col, code))
        return suggestions

    def render(self, full: bool = False) -> None:
        raster = self.get_active_raster()
        if raster is None:
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", text="请先加载 ASC 栅格文件。", fill="#555")
            return

        zoom = float(self.zoom_var.get())
        zoom = max(0.1, min(zoom, 16.0))
        self.zoom_var.set(round(zoom, 3))
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        signature = (
            self.active_mode(),
            zoom,
            raster.path.resolve(),
            raster.ncols,
            raster.nrows,
            tuple(self.stream_palette.items()),
            tuple(self.flow_palette.items()),
            self.vector_color,
            self.vector_layer.path.resolve() if self.vector_layer else None,
            self.confluence_polygon_layer.path.resolve() if self.confluence_polygon_layer else None,
            self.show_confluence_polygon_var.get(),
            int(self.confluence_polygon_width_var.get()),
            self.confluence_polygon_color,
            self.show_grid_var.get(),
            self.show_scale_var.get(),
            self.show_flow_arrows_var.get(),
            self.compare_original_var.get(),
        )
        rebuild = full or self._full_render_requested or self._render_signature != signature or self._viewport_cache_key != (signature, round(self._view_x, 2), round(self._view_y, 2), width, height)
        if rebuild:
            self._sync_viewport_for_zoom(raster, zoom, width, height)
            compare_raster = self.get_original_active_raster() if self.compare_original_var.get() else None
            self.base_scaled_image, self.overlay_image = render_viewport_layers(
                raster,
                self.active_mode(),
                zoom,
                self._view_x,
                self._view_y,
                width,
                height,
                stream_palette=self.stream_palette,
                flow_palette=self.flow_palette,
                vector_layer=self.vector_layer,
                transformer=self.transformer,
                vector_color=self.vector_color,
                polygon_layer=self.confluence_polygon_layer,
                polygon_transformer=self.confluence_transformer,
                polygon_color=self.confluence_polygon_color,
                polygon_line_width=int(self.confluence_polygon_width_var.get()),
                show_polygon_boundary=self.show_confluence_polygon_var.get(),
                show_grid=self.show_grid_var.get(),
                show_scale=self.show_scale_var.get(),
                show_flow_arrows=self.show_flow_arrows_var.get(),
                compare_raster=compare_raster,
            )
            base_render = Image.alpha_composite(self.base_scaled_image, self.overlay_image)
            self._viewport_cache_image = base_render
            self.rendered_image = self._apply_selection_overlay(base_render.copy(), raster, zoom)
            self._viewport_cache_key = (signature, round(self._view_x, 2), round(self._view_y, 2), width, height)
            self._render_signature = signature
            self._dirty_cells.clear()
            self._dirty_bbox = None
            self._full_render_requested = False
        elif self._dirty_cells and self.base_scaled_image is not None:
            self._apply_dirty_cells_to_base(raster, zoom)
            base_render = Image.alpha_composite(self.base_scaled_image, self.overlay_image or Image.new("RGBA", self.base_scaled_image.size, (0, 0, 0, 0)))
            self._viewport_cache_image = base_render
            self.rendered_image = self._apply_selection_overlay(base_render.copy(), raster, zoom)
            self._dirty_cells.clear()
            self._dirty_bbox = None
        elif self._viewport_cache_image is not None:
            self.rendered_image = self._apply_selection_overlay(self._viewport_cache_image.copy(), raster, zoom)
        else:
            compare_raster = self.get_original_active_raster() if self.compare_original_var.get() else None
            self.base_scaled_image, self.overlay_image = render_viewport_layers(
                raster,
                self.active_mode(),
                zoom,
                self._view_x,
                self._view_y,
                width,
                height,
                stream_palette=self.stream_palette,
                flow_palette=self.flow_palette,
                vector_layer=self.vector_layer,
                transformer=self.transformer,
                vector_color=self.vector_color,
                polygon_layer=self.confluence_polygon_layer,
                polygon_transformer=self.confluence_transformer,
                polygon_color=self.confluence_polygon_color,
                polygon_line_width=int(self.confluence_polygon_width_var.get()),
                show_polygon_boundary=self.show_confluence_polygon_var.get(),
                show_grid=self.show_grid_var.get(),
                show_scale=self.show_scale_var.get(),
                show_flow_arrows=self.show_flow_arrows_var.get(),
                compare_raster=compare_raster,
            )
            base_render = Image.alpha_composite(self.base_scaled_image, self.overlay_image)
            self._viewport_cache_image = base_render
            self.rendered_image = self._apply_selection_overlay(base_render.copy(), raster, zoom)
            self._viewport_cache_key = (signature, round(self._view_x, 2), round(self._view_y, 2), width, height)
        self._present_render()
        self.info_var.set(self._render_status_text(raster, zoom))

    def _render_status_text(self, raster: RasterData, zoom: float) -> str:
        return f"{self.mode_name()} | {raster.path.name} | {raster.ncols}x{raster.nrows} | 缩放 {zoom:.3f}"

    def _build_compare_base(self, base: Image.Image, raster: RasterData, zoom: float) -> Image.Image:
        original = self.get_original_active_raster()
        if original is None:
            return base
        original_base = build_base_image(original, self.active_mode(), self.stream_palette, self.flow_palette)
        if original_base.size != base.size:
            original_base = original_base.resize(base.size, Image.NEAREST)
        return Image.blend(base, original_base, 0.45)

    def _sync_viewport_for_zoom(self, raster: RasterData, zoom: float, width: int, height: int) -> None:
        total_w = max(1, int(round(raster.ncols * zoom)))
        total_h = max(1, int(round(raster.nrows * zoom)))
        max_x = max(0, total_w - width)
        max_y = max(0, total_h - height)
        self._view_x = max(0.0, min(float(max_x), float(self._view_x)))
        self._view_y = max(0.0, min(float(max_y), float(self._view_y)))
        self.canvas.config(scrollregion=(0, 0, total_w, total_h))

    def _cell_color(self, raster: RasterData, row: int, col: int) -> RGBA:
        value = raster.value_at(row, col)
        if self.active_mode() == "stream":
            if value == raster.header.nodata:
                color = self.stream_palette["nodata"]
            elif value == STREAM_VALUE:
                color = self.stream_palette["river"]
            else:
                color = self.stream_palette["background"]
        else:
            if value == raster.header.nodata:
                color = (240, 240, 240, 255)
            else:
                color = self.flow_palette.get(value, (200, 200, 200, 255))
        if self.compare_original_var.get():
            original = self.get_original_active_raster()
            if original is not None:
                original_value = original.value_at(row, col)
                if self.active_mode() == "stream":
                    if original_value == original.header.nodata:
                        original_color = self.stream_palette["nodata"]
                    elif original_value == STREAM_VALUE:
                        original_color = self.stream_palette["river"]
                    else:
                        original_color = self.stream_palette["background"]
                else:
                    if original_value == original.header.nodata:
                        original_color = (240, 240, 240, 255)
                    else:
                        original_color = self.flow_palette.get(original_value, (200, 200, 200, 255))
                color = self._blend_rgba(color, original_color, 0.45)
        return color

    def _blend_rgba(self, left: RGBA, right: RGBA, alpha: float) -> RGBA:
        beta = 1.0 - alpha
        return (
            int(round(left[0] * beta + right[0] * alpha)),
            int(round(left[1] * beta + right[1] * alpha)),
            int(round(left[2] * beta + right[2] * alpha)),
            int(round(left[3] * beta + right[3] * alpha)),
        )

    def _apply_dirty_cells_to_base(self, raster: RasterData, zoom: float) -> None:
        if self.base_scaled_image is None:
            return
        draw = ImageDraw.Draw(self.base_scaled_image)
        for row, col in list(self._dirty_cells):
            x0 = int(math.floor(col * zoom - self._view_x))
            y0 = int(math.floor(row * zoom - self._view_y))
            x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - self._view_x)))
            y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - self._view_y)))
            if x1 < 0 or y1 < 0 or x0 >= self.base_scaled_image.size[0] or y0 >= self.base_scaled_image.size[1]:
                continue
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(self.base_scaled_image.size[0], x1)
            y1 = min(self.base_scaled_image.size[1], y1)
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=self._cell_color(raster, row, col))
        self._viewport_cache_image = None

    def _present_render(self) -> None:
        if self.rendered_image is None:
            return
        self.tk_image = ImageTk.PhotoImage(self.rendered_image)
        if self.canvas_image_id is None:
            self.canvas_image_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)
        else:
            self.canvas.itemconfig(self.canvas_image_id, image=self.tk_image)
        self.canvas.config(scrollregion=self.canvas["scrollregion"])

    def on_close(self) -> None:
        self.cancel_dem_cache_task(silent=True)
        if self.autosave_var.get():
            self.save_autosave()
        self.destroy()

    def export_active(self) -> None:
        raster = self.get_active_raster()
        if raster is None:
            messagebox.showwarning("提示", "当前没有可导出的栅格。")
            return
        default_name = raster.path.with_name(raster.path.stem + "_corrected.asc")
        path = filedialog.asksaveasfilename(
            title="导出ASC",
            defaultextension=".asc",
            initialfile=default_name.name,
            initialdir=str(default_name.parent),
            filetypes=[("ASC files", "*.asc"), ("All files", "*.*")],
        )
        if not path:
            return
        out_path = Path(path)
        backup_path = None
        if out_path.exists():
            backup_path = out_path.with_suffix(out_path.suffix + f".bak_{time.strftime('%Y%m%d_%H%M%S')}")
            shutil.copy2(out_path, backup_path)
        write_asc(out_path, raster)
        report_path = self.write_export_report(out_path, raster, backup_path)
        self.info_var.set(f"已导出 {out_path}，报告: {report_path.name}")

    def write_export_report(self, out_path: Path, raster: RasterData, backup_path: Optional[Path]) -> Path:
        original = self.get_original_active_raster()
        changed = 0
        if original is not None and original.data.shape == raster.data.shape:
            changed = int(np.count_nonzero(original.data != raster.data))
        report_path = out_path.with_name(out_path.stem + "_report.txt")
        lines = [
            "水系订正工具导出报告",
            f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"模式: {self.mode_name()}",
            f"输出文件: {out_path}",
            f"栅格尺寸: {raster.ncols} x {raster.nrows}",
            f"相对原始图层修改像元数: {changed}",
            f"操作日志: {self.log_path}",
        ]
        if backup_path is not None:
            lines.append(f"覆盖前备份: {backup_path}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path


def main() -> None:
    app = WaterCorrectionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
