from __future__ import annotations

import heapq
import json
import math
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageTk

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from water_core import (
    CRS,
    DIR_ORDER,
    DIR_OFFSETS,
    NODATA,
    OPPOSITE_DIR,
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
    resolve_relative_or_absolute,
    write_asc,
)
from water_editing import RasterEditingMixin
from water_geometry import line_cells
from water_flow_assist import FlowNetworkAssistant, FlowSegment, direction_from_delta
from water_history import EditingHistoryMixin
from water_palette import PaletteMixin
from water_project import project_data_path, raster_payload, read_project_arrays, read_project_payload, read_session_files, rebuild_raster, write_project_files, write_session_files
from water_polygon import point_in_any_ring, rings_bounds
from water_render import build_base_image, overlay_flow_arrows, overlay_grid, overlay_scale_bar, overlay_selection, overlay_vector_layer, render_viewport_image, render_viewport_layers
from water_shortcuts import DEFAULT_SHORTCUTS, load_shortcuts, normalize_shortcut, save_shortcuts, shortcut_label
from water_ui import FitTargetDialog, ShortcutSettingsDialog, ToolTip
from water_workspace import WorkspaceMixin


RGBA = Tuple[int, int, int, int]


class WaterCorrectionApp(WorkspaceMixin, PaletteMixin, RasterEditingMixin, EditingHistoryMixin, tk.Tk):
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
        self.coord_var = tk.StringVar(value="")
        self.confluence_inner_radius_var = tk.IntVar(value=3)
        self.confluence_outer_radius_var = tk.IntVar(value=4)
        self.confluence_mode_var = tk.StringVar(value="近远带")
        self.confluence_max_distance_var = tk.IntVar(value=30)
        self.confluence_hint_var = tk.StringVar(value="")
        self.river_flow_mode_var = tk.StringVar(value="平滑")

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
        self.selected_flow_cell: Optional[Tuple[int, int]] = None
        self.selected_flow_region: Optional[Tuple[int, int, int, int]] = None
        self.selected_flow_segment: Optional[FlowSegment] = None
        self.flow_segment_downstream: Optional[Tuple[int, int]] = None
        self.confirmed_flow_segments: Dict[Tuple[Tuple[int, int], Tuple[int, int]], Tuple[int, int]] = {}
        self.confirmed_flow_segment_cells: Dict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[int, int]]] = {}
        self.flow_skeleton_outlet: Optional[Tuple[int, int]] = None
        self.flow_assist_sources: List[Tuple[int, int]] = []
        self.flow_assist_outlets: List[Tuple[int, int]] = []
        self.flow_assist_nodes: List[Tuple[int, int]] = []
        self.flow_preview_ops: List[Tuple[int, int, int]] = []
        self.flow_preview_unchanged_ops: List[Tuple[int, int, int]] = []
        self.flow_preview_kind: str = ""
        self.flow_preview_segment_key: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None

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
        self.flow_suggestions: List[Tuple[int, int, int]] = []

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
        self.btn_remove_locked_region = ttk.Button(lock_box, text="清除选区锁定", command=self.remove_selected_locked_region)
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
        self.btn_preview_segment = ttk.Button(action_box, text="清除预览", command=self.clear_flow_preview)
        self.btn_preview_segment.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.btn_confirm_segment = ttk.Button(action_box, text="取消锁定", command=self.clear_flow_segment_state)
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
            self.btn_reverse_segment: "将当前橙色预览结果写入流向栅格；河道像元不会被周边汇流覆盖。",
            self.btn_preview_segment: "清除当前预览，不修改数据。",
            self.btn_confirm_segment: "取消当前锁定的河道、出口和预览，选错时使用。",
            self.btn_load_confluence_polygon: "加载面状 SHP 作为后续面范围汇流的边界图层，当前阶段只显示边界。",
            self.chk_show_confluence_polygon: "显示或隐藏汇流范围面 SHP 边界。",
            self.btn_lock_polygon_stream: "将汇流范围面内的 Stream=1 河道像元加入当前锁定骨架，不修改栅格值。",
            self.btn_preview_confluence: "基于已锁定河道，预览周边非河道像元向河道汇流的方向。",
            self.btn_clear_flow_marks: "取消当前锁定的河道、出口和预览，选错时使用。",
            self.btn_apply_flow_preview: "将当前橙色预览结果写入流向栅格。",
            self.btn_clear_flow_preview: "清除当前流向辅助预览，不修改数据。",
            self.btn_stream_palette: "修改河道栅格的 NoData、河道和背景颜色。",
            self.btn_flow_palette: "修改 8 个 D8 流向和 NoData 的栅格颜色。",
            self.btn_vector_color: "修改河流参考线 SHP 的叠加颜色。",
            self.btn_confluence_polygon_color: "修改汇流范围面 SHP 的边界颜色。",
            self.btn_assist_palette: "修改流向预览、框选、锁定河道、源头/节点/出口等辅助标记颜色。",
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

    def _update_shortcut_hint(self) -> None:
        if hasattr(self, "vector_hint"):
            flow_note = "；流向模式禁用橡皮擦" if self.mode_var.get() == "flow" else ""
            self.vector_hint.configure(
                text=(
                    f"快捷键：{self._shortcut_label('brush')}=画笔，{self._shortcut_label('eraser')}=橡皮擦；"
                    f"河道模式可用矢量批量修正，流向模式左键改方向{flow_note}"
                )
            )
        self.update_mode_status()

    def update_mode_status(self) -> None:
        if not hasattr(self, "mode_status_var"):
            return
        mode_text = "订正河道" if self.mode_var.get() == "stream" else "订正流向"
        tool_text = "画笔" if self.tool_var.get() == "brush" else "橡皮擦" if self.tool_var.get() == "eraser" else self.tool_var.get()
        locked_count = len(self._locked_flow_cells_set()) if hasattr(self, "confirmed_flow_segment_cells") else 0
        if self.flow_preview_kind == "river_skeleton":
            preview_text = f"河道流向预览 需修改 {len(self.flow_preview_ops)} / 已一致 {len(self.flow_preview_unchanged_ops)}"
        elif self.flow_preview_kind == "confluence":
            preview_text = f"周边汇流预览 需修改 {len(self.flow_preview_ops)} / 已一致 {len(self.flow_preview_unchanged_ops)}"
        elif self.flow_preview_ops:
            preview_text = f"流向预览 {len(self.flow_preview_ops)} 个像元"
        else:
            preview_text = "无预览"
        outlet_text = f"出口 {self.flow_skeleton_outlet}" if self.flow_skeleton_outlet is not None else "未设出口"
        autosave_text = "开启" if self.autosave_var.get() else "关闭"
        stream_loaded = "已加载" if self.stream_raster is not None else "未加载"
        flow_loaded = "已加载" if self.flow_raster is not None else "未加载"
        range_loaded = "，范围SHP已加载" if self.confluence_polygon_layer is not None else ""
        self.mode_status_var.set(f"当前模式：{mode_text}")
        self.tool_status_var.set(f"当前工具：{tool_text}  快捷键 {self._shortcut_label('brush')}=画笔 / {self._shortcut_label('eraser')}=橡皮擦")
        self.flow_status_var.set(f"流向辅助：锁定 {locked_count} 个河道像元，{outlet_text}，{preview_text}{range_loaded}")
        self.session_status_var.set(f"数据：河道{stream_loaded}，流向{flow_loaded}；自动保存{autosave_text}")

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

    def save_project_dialog(self) -> None:
        path = filedialog.asksaveasfilename(
            title="保存项目",
            defaultextension=".waterproj",
            initialdir=str(self.workspace_dir),
            filetypes=[("Water project", "*.waterproj"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.save_project(Path(path))

    def open_project_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="打开项目",
            initialdir=str(self.workspace_dir),
            filetypes=[("Water project", "*.waterproj"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.open_project(Path(path))

    def save_project(self, path: Path) -> None:
        data_path = project_data_path(path)
        payload = {
            "version": "2.0",
            "workspace_dir": str(self.workspace_dir),
            "mode": self.mode_var.get(),
            "tool": self.tool_var.get(),
            "direction": self.direction_var.get(),
            "brush_size": int(self.brush_size_var.get()),
            "vector_tol": float(self.vector_tol_var.get()),
            "river_flow_mode": self.river_flow_mode_var.get(),
            "confluence_mode": self.confluence_mode_var.get(),
            "confluence_max_distance": int(self.confluence_max_distance_var.get()),
            "zoom": float(self.zoom_var.get()),
            "confluence_inner_radius": int(self.confluence_inner_radius_var.get()),
            "confluence_outer_radius": int(self.confluence_outer_radius_var.get()),
            "view": {"x": self._view_x, "y": self._view_y},
            "stream_path": self._store_path(self.stream_raster.path) if self.stream_raster is not None else "",
            "flow_path": self._store_path(self.flow_raster.path) if self.flow_raster is not None else "",
            "shp_path": self._store_path(self.vector_layer.path) if self.vector_layer is not None else "",
            "confluence_polygon_path": self._store_path(self.confluence_polygon_layer.path) if self.confluence_polygon_layer is not None else "",
            "show_confluence_polygon": self.show_confluence_polygon_var.get(),
            "confluence_polygon_width": int(self.confluence_polygon_width_var.get()),
            "data_path": self._store_path(data_path),
            "palette_state": self._palette_state(),
        }
        write_project_files(
            path,
            data_path,
            payload,
            self.stream_raster,
            self.flow_raster,
            self.original_stream_raster,
            self.original_flow_raster,
        )
        self.info_var.set(f"已保存项目 {path.name}")

    def open_project(self, path: Path) -> None:
        try:
            payload = read_project_payload(path)
        except Exception as exc:
            messagebox.showerror("打开项目失败", str(exc))
            return
        self._clear_loaded_session()
        workspace = payload.get("workspace_dir")
        if isinstance(workspace, str) and workspace and Path(workspace).exists():
            self.workspace_dir = Path(workspace).resolve()
            self._save_workspace_dir(self.workspace_dir)
        project = read_project_arrays(payload, self._resolve_stored_path)
        project_data = project.arrays
        if project.data_error is not None:
            messagebox.showwarning("项目数据提示", f"项目数据文件读取失败，将尝试按原始路径加载。\n{project.data_error}")
        stream_path = payload.get("stream_path")
        if isinstance(stream_path, str) and stream_path:
            resolved = self._resolve_stored_path(stream_path)
            if resolved.exists():
                if project_data is not None and "stream" in project_data and isinstance(project_data["stream"], np.ndarray) and project_data["stream"].size:
                    source = parse_asc(resolved)
                    stream_payload = {"path": stream_path, "header": source.header.raw_lines, "crs_text": source.crs_text}
                    self.stream_raster = self._rebuild_raster_from_payload(stream_payload, project_data["stream"])
                    if "original_stream" in project_data and isinstance(project_data["original_stream"], np.ndarray) and project_data["original_stream"].size:
                        self.original_stream_raster = self._rebuild_raster_from_payload(stream_payload, project_data["original_stream"])
                    else:
                        self.original_stream_raster = source
                    self.stream_file_var.set(self._store_path(resolved))
                else:
                    self.load_stream(resolved, switch_mode=False, update_autosave=False, validate_kind=False)
        flow_path = payload.get("flow_path")
        if isinstance(flow_path, str) and flow_path:
            resolved = self._resolve_stored_path(flow_path)
            if resolved.exists():
                if project_data is not None and "flow" in project_data and isinstance(project_data["flow"], np.ndarray) and project_data["flow"].size:
                    source = parse_asc(resolved)
                    flow_payload = {"path": flow_path, "header": source.header.raw_lines, "crs_text": source.crs_text}
                    self.flow_raster = self._rebuild_raster_from_payload(flow_payload, project_data["flow"])
                    if "original_flow" in project_data and isinstance(project_data["original_flow"], np.ndarray) and project_data["original_flow"].size:
                        self.original_flow_raster = self._rebuild_raster_from_payload(flow_payload, project_data["original_flow"])
                    else:
                        self.original_flow_raster = source
                    self.flow_file_var.set(self._store_path(resolved))
                else:
                    self.load_flow(resolved, switch_mode=False, update_autosave=False, validate_kind=False)
        shp_path = payload.get("shp_path")
        if isinstance(shp_path, str) and shp_path:
            resolved = self._resolve_stored_path(shp_path)
            if resolved.exists():
                self.load_shp(resolved, update_autosave=False)
        confluence_polygon_path = payload.get("confluence_polygon_path")
        if isinstance(confluence_polygon_path, str) and confluence_polygon_path:
            resolved = self._resolve_stored_path(confluence_polygon_path)
            if resolved.exists():
                self.load_confluence_polygon(resolved, update_autosave=False)
        mode = str(payload.get("mode", self.mode_var.get()))
        if mode in {"stream", "flow"}:
            self.mode_var.set(mode)
        self.tool_var.set(str(payload.get("tool", self.tool_var.get())))
        self.direction_var.set(str(payload.get("direction", self.direction_var.get())))
        self.brush_size_var.set(int(payload.get("brush_size", self.brush_size_var.get())))
        self.vector_tol_var.set(float(payload.get("vector_tol", self.vector_tol_var.get())))
        river_flow_mode = str(payload.get("river_flow_mode", self.river_flow_mode_var.get()))
        if river_flow_mode in {"平滑", "稳健"}:
            self.river_flow_mode_var.set(river_flow_mode)
        confluence_mode = str(payload.get("confluence_mode", self.confluence_mode_var.get()))
        if confluence_mode in {"近远带", "范围SHP"}:
            self.confluence_mode_var.set(confluence_mode)
        self._update_confluence_hint()
        self.confluence_max_distance_var.set(int(payload.get("confluence_max_distance", self.confluence_max_distance_var.get())))
        self.zoom_var.set(float(payload.get("zoom", self.zoom_var.get())))
        self.confluence_inner_radius_var.set(int(payload.get("confluence_inner_radius", self.confluence_inner_radius_var.get())))
        self.confluence_outer_radius_var.set(int(payload.get("confluence_outer_radius", self.confluence_outer_radius_var.get())))
        self.show_confluence_polygon_var.set(bool(payload.get("show_confluence_polygon", self.show_confluence_polygon_var.get())))
        self.confluence_polygon_width_var.set(int(payload.get("confluence_polygon_width", self.confluence_polygon_width_var.get())))
        palette_state = payload.get("palette_state")
        if isinstance(palette_state, dict):
            self._apply_palette_state(palette_state)
        view = payload.get("view", {})
        if isinstance(view, dict):
            self._view_x = float(view.get("x", self._view_x))
            self._view_y = float(view.get("y", self._view_y))
        self.on_tool_changed()
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.refresh_snapshot_list()
        if self.autosave_var.get():
            self.save_autosave()
        self.info_var.set(f"已打开项目 {path.name}")
        self.update_mode_status()

    def load_stream(self, path: Path, switch_mode: bool = True, update_autosave: bool = True, validate_kind: bool = True) -> None:
        raster = parse_asc(path)
        if validate_kind and not self._confirm_raster_kind(raster, "stream"):
            return
        self.stream_raster = raster
        self.original_stream_raster = self.stream_raster.copy()
        self.stream_file_var.set(self._store_path(path))
        if switch_mode:
            self.mode_var.set("stream")
        self.selected_flow_cell = None
        self.selected_flow_region = None
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
        self.flow_raster = raster
        self.original_flow_raster = self.flow_raster.copy()
        self.flow_file_var.set(self._store_path(path))
        if switch_mode:
            self.mode_var.set("flow")
        self.selected_flow_cell = None
        self.selected_flow_region = None
        self.selected_flow_segment = None
        self.flow_segment_downstream = None
        self.confirmed_flow_segments.clear()
        self.confirmed_flow_segment_cells.clear()
        self.flow_assist_sources = []
        self.flow_assist_outlets = []
        self.flow_assist_nodes = []
        self.flow_preview_ops = []
        self.flow_preview_unchanged_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
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

    def _clear_loaded_session(self) -> None:
        self.stream_raster = None
        self.flow_raster = None
        self.original_stream_raster = None
        self.original_flow_raster = None
        self.vector_layer = None
        self.confluence_polygon_layer = None
        self.transformer = None
        self.confluence_transformer = None
        self.stream_file_var.set("未加载")
        self.flow_file_var.set("未加载")
        self.shp_var.set("未加载")
        self.confluence_shp_var.set("未加载")
        self.histories = {"stream": [], "flow": []}
        self.redo_stacks = {"stream": [], "flow": []}
        self.snapshots = {"stream": [], "flow": []}
        self.flow_suggestions = []
        self.current_batch = None
        self._clear_flow_skeleton_state()
        self.selected_flow_cell = None
        self.selected_flow_region = None
        self._flow_network_cache_key = None
        self._flow_network_cache = None
        self._invalidate_viewport_cache()

    def on_mode_changed(self) -> None:
        self.tool_var.set("brush")
        self.on_tool_changed()
        if self.active_mode() != "flow":
            self.selected_flow_cell = None
            self.selected_flow_region = None
            self.selected_flow_segment = None
            self.flow_segment_downstream = None
            self.flow_preview_ops = []
            self.flow_preview_kind = ""
            self.flow_preview_segment_key = None
            self.flow_assist_sources = []
            self.flow_assist_outlets = []
            self.flow_assist_nodes = []
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.refresh_snapshot_list()

    def on_tool_changed(self) -> None:
        is_stream = self.mode_var.get() == "stream"
        if not is_stream and self.tool_var.get() == "eraser":
            self.tool_var.set("brush")
            self.info_var.set("订正流向模式禁用橡皮擦，已切换到画笔。")
        self.direction_box.configure(state="disabled" if is_stream else "readonly")
        self.btn_apply_direction.configure(state="disabled" if is_stream else "normal")
        self.btn_flow_suggest.configure(state="disabled" if is_stream else "normal")
        self.btn_vector_batch.configure(state="normal" if is_stream else "disabled")
        self.radio_eraser_tool.configure(state="normal" if is_stream else "disabled")
        self._refresh_flow_controls()
        self._update_shortcut_hint()

    def _refresh_flow_controls(self) -> None:
        has_flow_data = self.stream_raster is not None and self.flow_raster is not None
        locked_ready = bool(self.confirmed_flow_segments)
        apply_ready = bool(self.flow_preview_kind and self.flow_preview_ops)
        preview_ready = bool(self.flow_preview_kind and (self.flow_preview_ops or self.flow_preview_unchanged_ops))
        apply_text = self._flow_apply_button_text()

        def state(enabled: bool) -> str:
            return "normal" if enabled else "disabled"

        self.btn_flow_preview.configure(state=state(locked_ready))
        self.btn_flow_apply.configure(state=state(apply_ready), text=apply_text)
        self.btn_pick_flow_segment.configure(state=state(has_flow_data))
        self.btn_set_flow_outlet.configure(state=state(locked_ready and self.selected_flow_cell is not None))
        self.btn_preview_river_flow.configure(state=state(locked_ready and self.flow_skeleton_outlet is not None))
        self.btn_set_downstream.configure(state=state(locked_ready))
        self.btn_add_locked_cell.configure(state=state(has_flow_data and self.selected_flow_cell is not None))
        self.btn_remove_locked_region.configure(state=state(locked_ready and (self.selected_flow_cell is not None or self.selected_flow_region is not None)))
        self.btn_reverse_segment.configure(state=state(apply_ready), text=apply_text)
        self.btn_preview_segment.configure(state=state(preview_ready))
        self.btn_confirm_segment.configure(state=state(locked_ready))
        self.btn_preview_confluence.configure(state=state(locked_ready))
        self.btn_clear_flow_marks.configure(state=state(locked_ready))
        self.btn_apply_flow_preview.configure(state=state(apply_ready), text=apply_text)
        self.btn_clear_flow_preview.configure(state=state(preview_ready))
        self.update_mode_status()

    def _flow_apply_button_text(self) -> str:
        if self.flow_preview_kind == "river_skeleton":
            return "应用河道流向"
        if self.flow_preview_kind == "confluence":
            return "应用周边汇流"
        if self.flow_preview_kind == "segment":
            return "应用河道流向"
        return "应用预览"

    def on_river_flow_mode_changed(self, _event: Optional[tk.Event] = None) -> None:
        if self.flow_preview_kind == "river_skeleton":
            self.flow_preview_ops = []
            self.flow_preview_kind = ""
            self.flow_preview_segment_key = None
            self._update_flow_assist_text()
            self._refresh_flow_controls()
            self.render(full=True)
            self.info_var.set("河道流向计算模式已切换，请重新点击“预览河道流向”。")

    def on_confluence_mode_changed(self, _event: Optional[tk.Event] = None) -> None:
        if self.flow_preview_kind == "confluence":
            self.flow_preview_ops = []
            self.flow_preview_unchanged_ops = []
            self.flow_preview_kind = ""
            self.flow_preview_segment_key = None
            self.render(full=True)
        self._update_confluence_hint()
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        if self.confluence_mode_var.get() == "范围SHP":
            self.info_var.set("范围SHP模式：先加载范围SHP并锁定范围内河道；最大距为0表示不限距离。")
        else:
            self.info_var.set("近远带模式：按已锁定河道周边的近带/远带缓冲范围生成汇流预览。")

    def _update_confluence_hint(self) -> None:
        if not hasattr(self, "confluence_hint_var"):
            return
        if self.confluence_mode_var.get() == "范围SHP":
            self.confluence_hint_var.set("范围SHP：只处理面内非河道有效像元；最大距=0 不限，数值越小预览范围越贴近锁定河道。")
        else:
            self.confluence_hint_var.set("近远带：只处理锁定河道周边缓冲带；近带直接吸附，远带逐步流向河道。")

    def suggest_flow_direction(self) -> None:
        if self.mode_var.get() != "flow":
            messagebox.showinfo("提示", "这个功能仅用于订正流向模式。")
            return
        raster = self.get_active_raster()
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        selection = self.selected_flow_cell
        if selection is None:
            selection = self.canvas_to_rc(self.winfo_pointerx() - self.canvas.winfo_rootx(), self.winfo_pointery() - self.canvas.winfo_rooty())
        if selection is None:
            messagebox.showinfo("提示", "请先右键选中像元，或把鼠标停在需要建议的像元上。")
            return
        row, col, _, _ = selection
        suggestions = self._suggest_flow_candidates(raster, row, col)
        if not suggestions:
            messagebox.showinfo("提示", "当前像元附近没有可用的方向建议。")
            return
        text = "，".join(f"{code} {direction_text(code)}" for code in suggestions[:3])
        self.info_var.set(f"方向建议: {text}")
        if suggestions:
            self.direction_var.set(f"{suggestions[0]} {direction_text(suggestions[0])}")

    def _require_selected_flow_cell(self) -> Optional[Tuple[int, int]]:
        if self.selected_flow_cell is None:
            messagebox.showinfo("提示", "请先在地图上右键选中一个像元。")
            return None
        return self.selected_flow_cell

    def _flow_assistant(self) -> Optional[FlowNetworkAssistant]:
        raster = self.flow_raster
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return None
        if self.stream_raster is None:
            messagebox.showwarning("提示", "请先加载并订正河道ASC，当前 Stream=1 将作为流向骨架。")
            return None
        if self.stream_raster.nrows != raster.nrows or self.stream_raster.ncols != raster.ncols:
            messagebox.showwarning("提示", "河道ASC与流向ASC行列数不一致，不能作为同一骨架修正。")
            return None
        self._maybe_setup_transformer()
        return FlowNetworkAssistant(raster, self.vector_layer, self.transformer, self.stream_raster)

    def _flow_network(self) -> Optional[Dict[str, object]]:
        assistant = self._flow_assistant()
        if assistant is None:
            return None
        raster = self.flow_raster
        vector = self.vector_layer
        stream = self.stream_raster
        if raster is None or vector is None or stream is None:
            return None
        transformer_key = None if self.transformer is None else str(self.transformer)
        cache_key = (raster.path.resolve(), vector.path.resolve(), stream.path.resolve(), transformer_key)
        if self._flow_network_cache_key == cache_key and self._flow_network_cache is not None:
            return self._flow_network_cache
        network = assistant.build_network()
        self._flow_network_cache_key = cache_key
        self._flow_network_cache = network
        return network

    def lock_visible_stream_skeleton(self) -> None:
        if self.stream_raster is None:
            messagebox.showwarning("提示", "请先加载并订正河道ASC。")
            return
        if self.flow_raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        if self.stream_raster.nrows != self.flow_raster.nrows or self.stream_raster.ncols != self.flow_raster.ncols:
            messagebox.showwarning("提示", "河道ASC与流向ASC行列数不一致，不能锁定为同一骨架。")
            return
        if self.selected_flow_region is not None:
            row0, row1, col0, col1 = self.selected_flow_region
            row1 += 1
            col1 += 1
            row0 = max(0, row0)
            col0 = max(0, col0)
            row1 = min(self.stream_raster.nrows, row1)
            col1 = min(self.stream_raster.ncols, col1)
            cells = self._collect_stream_cells_in_bounds(row0, row1, col0, col1)
        else:
            cell = self.selected_flow_cell
            if cell is None:
                messagebox.showinfo("提示", "请先在目标河段上右键选中一个像元，或右键拖框后再点击锁定。")
                return
            row, col = cell
            if self.stream_raster.value_at(row, col) != STREAM_VALUE:
                messagebox.showinfo("提示", "当前选中的像元不是河道像元，请先在目标河段上右键选中河道。")
                return
            bounds = self._visible_raster_bounds(self.stream_raster)
            if bounds is None:
                return
            row0, row1, col0, col1 = bounds
            cells = self._collect_visible_stream_component((row, col), row0, row1, col0, col1)
        if not cells:
            messagebox.showinfo("提示", "当前选区内没有可锁定的 Stream=1 河道。")
            return
        self._add_locked_flow_cells(cells, reset_outlet=True)
        self.info_var.set(f"已锁定当前选区河道 {len(set(cells))} 个像元，后续只修周边非河道流向。")

    def lock_confluence_polygon_stream_skeleton(self) -> None:
        if self.stream_raster is None:
            messagebox.showwarning("提示", "请先加载并订正河道ASC。")
            return
        if self.flow_raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        if self.confluence_polygon_layer is None:
            messagebox.showwarning("提示", "请先加载汇流范围面SHP。")
            return
        if self.stream_raster.nrows != self.flow_raster.nrows or self.stream_raster.ncols != self.flow_raster.ncols:
            messagebox.showwarning("提示", "河道ASC与流向ASC行列数不一致，不能锁定为同一骨架。")
            return
        rings = self._confluence_polygon_rings_for_raster(self.stream_raster)
        cells = self._collect_stream_cells_in_polygon(rings)
        if not cells:
            messagebox.showinfo("提示", "汇流范围内没有找到 Stream=1 河道像元。")
            return
        unique_count = len(set(cells))
        if unique_count > 50000:
            ok = messagebox.askyesno("确认锁定", f"汇流范围内找到 {unique_count} 个河道像元，锁定后可能影响预览性能。是否继续？")
            if not ok:
                return
        self._add_locked_flow_cells(cells, reset_outlet=True)
        self.info_var.set(f"已锁定汇流范围内河道 {unique_count} 个像元。请右键选择出口后预览河道流向。")

    def add_selected_stream_cell_to_lock(self) -> None:
        if self.stream_raster is None:
            messagebox.showwarning("提示", "请先加载并订正河道ASC。")
            return
        if self.flow_raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        cell = self.selected_flow_cell
        if cell is None:
            messagebox.showinfo("提示", "请先右键单点选中一个要补充锁定的河道像元。")
            return
        row, col = cell
        if self.stream_raster.value_at(row, col) != STREAM_VALUE:
            messagebox.showinfo("提示", "当前选中的像元不是 Stream=1 河道像元。")
            return
        before = len(self._locked_flow_cells_set())
        self._add_locked_flow_cells([cell], reset_outlet=False)
        after = len(self._locked_flow_cells_set())
        self.info_var.set("已补充锁定 1 个河道像元。" if after > before else "该像元已经在锁定河道内。")

    def remove_selected_locked_region(self) -> None:
        if not self.confirmed_flow_segment_cells:
            messagebox.showinfo("提示", "当前没有已锁定河道。")
            return
        remove_cells: Set[Tuple[int, int]] = set()
        if self.selected_flow_region is not None:
            row0, row1, col0, col1 = self.selected_flow_region
            for row in range(row0, row1 + 1):
                for col in range(col0, col1 + 1):
                    remove_cells.add((row, col))
        elif self.selected_flow_cell is not None:
            remove_cells.add(self.selected_flow_cell)
        else:
            messagebox.showinfo("提示", "请先右键单点或拖框选择要清除锁定的区域。")
            return
        target = self._locked_flow_cells_set() & remove_cells
        if not target:
            messagebox.showinfo("提示", "当前选区内没有已锁定的河道像元。")
            return
        self._remove_locked_flow_cells(target)
        self.info_var.set(f"已清除选区内 {len(target)} 个锁定河道像元，其他锁定保留。")

    def _add_locked_flow_cells(self, cells: List[Tuple[int, int]], reset_outlet: bool) -> None:
        unique_cells = sorted(set(cells))
        if not unique_cells:
            return
        key = self._locked_group_key(unique_cells)
        existing = self.confirmed_flow_segment_cells.get(key, [])
        merged = sorted(set(existing) | set(unique_cells))
        key = self._locked_group_key(merged)
        self.confirmed_flow_segments[key] = merged[-1]
        self.confirmed_flow_segment_cells[key] = merged
        if reset_outlet:
            self.flow_skeleton_outlet = None
        self.selected_flow_segment = None
        self.flow_segment_downstream = None
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)

    def _remove_locked_flow_cells(self, cells_to_remove: Set[Tuple[int, int]]) -> None:
        new_groups: Dict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[int, int]]] = {}
        for cells in self.confirmed_flow_segment_cells.values():
            remaining = sorted(set(cells) - cells_to_remove)
            if not remaining:
                continue
            key = self._locked_group_key(remaining)
            new_groups[key] = sorted(set(new_groups.get(key, [])) | set(remaining))
        self.confirmed_flow_segment_cells = new_groups
        self.confirmed_flow_segments = {key: cells[-1] for key, cells in new_groups.items() if cells}
        if self.flow_skeleton_outlet in cells_to_remove:
            self.flow_skeleton_outlet = None
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self.selected_flow_region = None
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)

    def _locked_group_key(self, cells: List[Tuple[int, int]]) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        ordered = sorted(cells)
        return ordered[0], ordered[-1]

    def _collect_stream_cells_in_bounds(
        self,
        row0: int,
        row1: int,
        col0: int,
        col1: int,
    ) -> List[Tuple[int, int]]:
        stream = self.stream_raster
        if stream is None or row0 >= row1 or col0 >= col1:
            return []
        view = stream.data[row0:row1, col0:col1]
        ys, xs = np.where(view == STREAM_VALUE)
        return [(row0 + int(row_offset), col0 + int(col_offset)) for row_offset, col_offset in zip(ys.tolist(), xs.tolist())]

    def _confluence_polygon_rings_for_raster(self, raster: RasterData) -> List[List[Tuple[float, float]]]:
        layer = self.confluence_polygon_layer
        if layer is None:
            return []
        transformer = self._build_layer_transformer_for_raster(layer, raster)
        rings: List[List[Tuple[float, float]]] = []
        for ring in layer.boundaries:
            transformed: List[Tuple[float, float]] = []
            for x, y in ring:
                if transformer is not None:
                    x, y = transformer.transform(x, y)
                transformed.append((x, y))
            if len(transformed) >= 3:
                rings.append(transformed)
        return rings

    def _collect_stream_cells_in_polygon(self, rings: List[List[Tuple[float, float]]]) -> List[Tuple[int, int]]:
        stream = self.stream_raster
        if stream is None or not rings:
            return []
        bounds = rings_bounds(rings)
        if bounds is None:
            return []
        min_x, min_y, max_x, max_y = bounds
        rows: List[float] = []
        cols: List[float] = []
        for x, y in ((min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)):
            row, col = stream.world_to_rc(x, y)
            rows.append(row)
            cols.append(col)
        row0 = max(0, int(math.floor(min(rows))) - 1)
        row1 = min(stream.nrows, int(math.ceil(max(rows))) + 1)
        col0 = max(0, int(math.floor(min(cols))) - 1)
        col1 = min(stream.ncols, int(math.ceil(max(cols))) + 1)
        candidates = self._collect_stream_cells_in_bounds(row0, row1, col0, col1)
        inside: List[Tuple[int, int]] = []
        for row, col in candidates:
            x, y = stream.rc_to_world(row, col)
            if point_in_any_ring(x, y, rings):
                inside.append((row, col))
        return inside

    def _confluence_polygon_candidate_mask(self) -> np.ndarray:
        flow = self.flow_raster
        if flow is None:
            return np.zeros((0, 0), dtype=bool)
        rings = self._confluence_polygon_rings_for_raster(flow)
        mask = np.zeros((flow.nrows, flow.ncols), dtype=bool)
        bounds = rings_bounds(rings)
        if bounds is None:
            return mask
        min_x, min_y, max_x, max_y = bounds
        rows: List[float] = []
        cols: List[float] = []
        for x, y in ((min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)):
            row, col = flow.world_to_rc(x, y)
            rows.append(row)
            cols.append(col)
        row0 = max(0, int(math.floor(min(rows))) - 1)
        row1 = min(flow.nrows, int(math.ceil(max(rows))) + 1)
        col0 = max(0, int(math.floor(min(cols))) - 1)
        col1 = min(flow.ncols, int(math.ceil(max(cols))) + 1)
        stream = self.stream_raster
        has_stream = stream is not None and stream.nrows == flow.nrows and stream.ncols == flow.ncols
        for row in range(row0, row1):
            for col in range(col0, col1):
                if int(flow.data[row, col]) == NODATA:
                    continue
                if has_stream and int(stream.data[row, col]) == STREAM_VALUE:
                    continue
                x, y = flow.rc_to_world(row, col)
                if point_in_any_ring(x, y, rings):
                    mask[row, col] = True
        return mask

    def _collect_visible_stream_component(
        self,
        anchor: Tuple[int, int],
        row0: int,
        row1: int,
        col0: int,
        col1: int,
    ) -> List[Tuple[int, int]]:
        stream = self.stream_raster
        if stream is None:
            return []
        ar, ac = anchor
        if not (row0 <= ar < row1 and col0 <= ac < col1):
            return []
        if stream.value_at(ar, ac) != STREAM_VALUE:
            return []
        visited = {(ar, ac)}
        queue = deque([(ar, ac)])
        while queue:
            row, col = queue.popleft()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr = row + dr
                    nc = col + dc
                    if nr < row0 or nr >= row1 or nc < col0 or nc >= col1:
                        continue
                    if (nr, nc) in visited:
                        continue
                    if stream.value_at(nr, nc) != STREAM_VALUE:
                        continue
                    visited.add((nr, nc))
                    queue.append((nr, nc))
        return list(visited)

    def _visible_raster_bounds(self, raster: RasterData) -> Optional[Tuple[int, int, int, int]]:
        try:
            zoom = max(0.1, float(self.zoom_var.get()))
        except Exception:
            return None
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        row0 = max(0, int(math.floor(self._view_y / zoom)))
        col0 = max(0, int(math.floor(self._view_x / zoom)))
        row1 = min(raster.nrows, int(math.ceil((self._view_y + height) / zoom)))
        col1 = min(raster.ncols, int(math.ceil((self._view_x + width) / zoom)))
        if row0 >= row1 or col0 >= col1:
            return None
        return row0, row1, col0, col1

    def pick_nearest_flow_segment(self) -> None:
        cell = self._require_selected_flow_cell()
        if cell is None:
            return
        assistant = self._flow_assistant()
        if assistant is None:
            return
        segment = assistant.find_nearest_segment(cell, max_distance_cells=12)
        if segment is None:
            messagebox.showinfo("提示", "当前选中像元附近没有找到 Stream=1 的已订正河道骨架。")
            return
        self.selected_flow_segment = segment
        self.flow_segment_downstream = segment.end if (cell[0] - segment.end[0]) ** 2 + (cell[1] - segment.end[1]) ** 2 <= (cell[0] - segment.start[0]) ** 2 + (cell[1] - segment.start[1]) ** 2 else segment.start
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self.render(full=False)

    def set_flow_segment_downstream(self) -> None:
        cell = self._require_selected_flow_cell()
        if cell is None:
            return
        if self.selected_flow_segment is None:
            self.pick_nearest_flow_segment()
            if self.selected_flow_segment is None:
                return
        segment = self.selected_flow_segment
        self.flow_segment_downstream = segment.end if (cell[0] - segment.end[0]) ** 2 + (cell[1] - segment.end[1]) ** 2 <= (cell[0] - segment.start[0]) ** 2 + (cell[1] - segment.start[1]) ** 2 else segment.start
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self.render(full=False)

    def reverse_selected_flow_segment(self) -> None:
        if self.mode_var.get() != "flow":
            messagebox.showinfo("提示", "请先切换到订正流向模式。")
            return
        if self.selected_flow_segment is None:
            messagebox.showinfo("提示", "请先选中一条河段。")
            return
        if self.flow_segment_downstream == self.selected_flow_segment.start:
            self.flow_segment_downstream = self.selected_flow_segment.end
        else:
            self.flow_segment_downstream = self.selected_flow_segment.start
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self.render(full=False)

    def clear_flow_segment_state(self) -> None:
        self._clear_flow_skeleton_state()
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)
        self.info_var.set("已取消当前锁定河道、出口和预览。")

    def _clear_flow_skeleton_state(self) -> None:
        self.selected_flow_segment = None
        self.flow_segment_downstream = None
        self.confirmed_flow_segments.clear()
        self.confirmed_flow_segment_cells.clear()
        self.flow_skeleton_outlet = None
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self.selected_flow_region = None
        self.selected_flow_cell = None
        self._refresh_flow_controls()

    def _update_flow_assist_text(self) -> None:
        preview = len(self.flow_preview_ops)
        unchanged = len(self.flow_preview_unchanged_ops)
        locked_cells = sum(len(cells) for cells in self.confirmed_flow_segment_cells.values())
        if locked_cells:
            selected = f"已锁定河道 {len(self.confirmed_flow_segments)} 组 / {locked_cells} 像元"
        else:
            selected = "未锁定河道"
        outlet = f"出口 {self.flow_skeleton_outlet}" if self.flow_skeleton_outlet is not None else "未设出口"
        preview_label = "河道预览" if self.flow_preview_kind == "river_skeleton" else "周边预览"
        max_distance = int(self.confluence_max_distance_var.get())
        distance_text = "不限距" if max_distance <= 0 else f"最大距 {max_distance}"
        if self.flow_preview_kind in {"confluence", "river_skeleton"}:
            preview_detail = f"{preview_label} 需修改 {preview} / 已一致 {unchanged}"
        else:
            preview_detail = f"{preview_label} {preview} 个像元"
        self.flow_assist_var.set(f"{selected}  {outlet}  汇流模式 {self.confluence_mode_var.get()}  {distance_text}  {preview_detail}")

    def set_flow_skeleton_outlet(self) -> None:
        if not self.confirmed_flow_segment_cells:
            messagebox.showinfo("提示", "请先锁定选区河道。")
            return
        cell = self.selected_flow_cell
        if cell is None:
            messagebox.showinfo("提示", "请先右键单点选中锁定河道上的出口像元。")
            return
        locked = self._locked_flow_cells_set()
        if cell not in locked:
            messagebox.showinfo("提示", "出口必须位于已锁定的河道像元内。")
            return
        self.flow_skeleton_outlet = cell
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)
        self.info_var.set(f"已设置下游出口像元 {cell}，可点击“预览河道流向”。")

    def preview_locked_river_flow(self) -> None:
        if self.flow_raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        if not self.confirmed_flow_segment_cells:
            messagebox.showinfo("提示", "请先锁定选区河道。")
            return
        if self.flow_skeleton_outlet is None:
            messagebox.showinfo("提示", "请先右键选中出口像元并点击“设为出口”。")
            return
        self.flow_preview_ops = []
        ops = self._build_locked_river_flow_ops(self.flow_skeleton_outlet)
        self._set_flow_preview(ops, "河道本体流向", "river_skeleton", None)

    def _locked_flow_cells_set(self) -> Set[Tuple[int, int]]:
        cells: Set[Tuple[int, int]] = set()
        for group in self.confirmed_flow_segment_cells.values():
            cells.update(group)
        return cells

    def _build_locked_river_flow_ops(self, outlet: Tuple[int, int]) -> List[Tuple[int, int, int]]:
        raster = self.flow_raster
        if raster is None:
            return []
        locked = self._locked_flow_cells_set()
        if outlet not in locked:
            return []
        distances: Dict[Tuple[int, int], int] = {outlet: 0}
        queue: List[Tuple[int, int, int]] = [(0, outlet[0], outlet[1])]
        while queue:
            base, row, col = heapq.heappop(queue)
            if base != distances.get((row, col)):
                continue
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    neighbor = (row + dr, col + dc)
                    if neighbor not in locked:
                        continue
                    step_cost = self._river_graph_step_cost(row, col, dr, dc, locked)
                    new_distance = base + step_cost
                    if new_distance >= distances.get(neighbor, 10**12):
                        continue
                    distances[neighbor] = new_distance
                    heapq.heappush(queue, (new_distance, neighbor[0], neighbor[1]))
        ops: List[Tuple[int, int, int]] = []
        for row, col in locked:
            if (row, col) == outlet:
                continue
            current_distance = distances.get((row, col))
            if current_distance is None:
                continue
            best_neighbor: Optional[Tuple[int, int]] = None
            best_distance = current_distance
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    neighbor = (row + dr, col + dc)
                    neighbor_distance = distances.get(neighbor)
                    if neighbor_distance is None:
                        continue
                    step_cost = self._river_graph_step_cost(row, col, dr, dc, locked)
                    if neighbor_distance + step_cost != current_distance:
                        continue
                    if neighbor_distance >= best_distance:
                        continue
                    best_neighbor = neighbor
                    best_distance = neighbor_distance
            if best_neighbor is None:
                continue
            code = direction_from_delta(row, col, best_neighbor[0], best_neighbor[1])
            if code is None:
                continue
            ops.append((row, col, code))
        return ops

    def _river_graph_step_cost(self, row: int, col: int, dr: int, dc: int, locked: Set[Tuple[int, int]]) -> int:
        if dr == 0 or dc == 0:
            return 10
        if self.river_flow_mode_var.get() == "平滑":
            if self._has_diagonal_trend(row, col, dr, dc, locked):
                return 14
            cost = 16
            if (row + dr, col) in locked or (row, col + dc) in locked:
                cost += 8
            return cost
        cost = 14
        if (row + dr, col) in locked or (row, col + dc) in locked:
            cost += 20
        return cost

    def _has_diagonal_trend(self, row: int, col: int, dr: int, dc: int, locked: Set[Tuple[int, int]]) -> bool:
        trend_hits = 0
        if (row - dr, col - dc) in locked:
            trend_hits += 1
        if (row + 2 * dr, col + 2 * dc) in locked:
            trend_hits += 1
        if (row - 2 * dr, col - 2 * dc) in locked:
            trend_hits += 1
        return trend_hits >= 1

    def preview_selected_flow_segment(self) -> None:
        assistant = self._flow_assistant()
        if assistant is None:
            return
        if self.selected_flow_segment is None:
            self.pick_nearest_flow_segment()
            if self.selected_flow_segment is None:
                return
        downstream = assistant.normalize_segment_downstream(self.selected_flow_segment, self.flow_segment_downstream)
        self.flow_segment_downstream = downstream
        ops = assistant.preview_segment_flow(self.selected_flow_segment, downstream)
        self._set_flow_preview(ops, "河段预览", "segment", self.selected_flow_segment.edge_key)
        self.info_var.set(f"河道流向预览完成，方向建议 {len(self.flow_preview_ops)} 个。可点击“{self._flow_apply_button_text()}”写入。")
        self._refresh_flow_controls()

    def confirm_selected_flow_segment(self) -> None:
        raster = self.flow_raster
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        if self.selected_flow_segment is None:
            self.pick_nearest_flow_segment()
            if self.selected_flow_segment is None:
                messagebox.showinfo("提示", "请先右键单点或拖框选择目标河道，再点击“锁定选区河道”。")
                return
        assistant = self._flow_assistant()
        if assistant is None:
            return
        downstream = assistant.normalize_segment_downstream(self.selected_flow_segment, self.flow_segment_downstream)
        self.flow_segment_downstream = downstream
        ops = assistant.preview_segment_flow(self.selected_flow_segment, downstream)
        batch = self._apply_flow_ops(ops, "skeleton_lock", "apply and lock skeleton flow")
        self.confirmed_flow_segments[self.selected_flow_segment.edge_key] = downstream
        self.confirmed_flow_segment_cells[self.selected_flow_segment.edge_key] = list(self.selected_flow_segment.cells)
        self.flow_preview_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        if batch.ops:
            self._record_flow_batch(batch)
            self.flush_pending_render(force=True)
            self.info_var.set(f"已应用并锁定河道流向，修改 {len(batch.ops)} 个像元。")
        else:
            self.render(full=False)
            self.info_var.set("河道流向已与当前栅格一致，已锁定为缓冲汇流依据。")
        self._refresh_flow_controls()

    def preview_confirmed_confluence(self) -> None:
        assistant = self._flow_assistant()
        if assistant is None:
            return
        if not self.confirmed_flow_segments:
            messagebox.showinfo("提示", "请先右键单点或拖框选择目标河道，再点击“锁定选区河道”。")
            return
        locked_segments = [
            (self.confirmed_flow_segment_cells[edge_key], downstream)
            for edge_key, downstream in self.confirmed_flow_segments.items()
            if edge_key in self.confirmed_flow_segment_cells
        ]
        if self.confluence_mode_var.get() == "范围SHP":
            if self.confluence_polygon_layer is None:
                messagebox.showwarning("提示", "请先加载汇流范围面SHP，或将汇流模式切换为近远带。")
                return
            candidate_mask = self._confluence_polygon_candidate_mask()
            candidate_count = int(candidate_mask.sum())
            if candidate_count == 0:
                messagebox.showinfo("提示", "汇流范围内没有可预览的非河道有效流向像元。")
                return
            if candidate_count > 200000:
                ok = messagebox.askyesno("确认预览", f"汇流范围内初筛有 {candidate_count} 个候选像元，预览可能需要一些时间。是否继续？")
                if not ok:
                    return
            max_distance = max(0, int(self.confluence_max_distance_var.get()))
            ops, unchanged_ops, seed_edge_count, candidate_count = assistant.preview_polygon_confluence(locked_segments, candidate_mask, max_distance)
            if seed_edge_count == 0:
                messagebox.showinfo("提示", "没有找到已锁定河道。")
                return
            if candidate_count == 0:
                messagebox.showinfo("提示", "最大汇流距离过滤后没有候选像元。请调大“最大距”，或设为 0 表示不限距离。")
                self.info_var.set("范围SHP汇流未生成预览：最大距过滤后候选像元为 0")
                self._refresh_flow_controls()
                return
            self._set_flow_preview(ops, "范围SHP汇流", "confluence", None, unchanged_ops)
            distance_text = "不限距离" if max_distance <= 0 else f"最大距离 {max_distance} 像元"
            if not self.flow_preview_ops:
                self.info_var.set(
                    f"范围SHP汇流没有生成可应用预览：{distance_text}，候选像元 {candidate_count} 个，已一致 {len(self.flow_preview_unchanged_ops)} 个。"
                )
                self._refresh_flow_controls()
                return
            self.info_var.set(
                f"范围SHP汇流预览完成，锁定河道 {seed_edge_count} 组，{distance_text}，候选像元 {candidate_count} 个，需修改 {len(self.flow_preview_ops)} 个，已一致 {len(self.flow_preview_unchanged_ops)} 个"
            )
            self._refresh_flow_controls()
            return
        ops, unchanged_ops, radius, seed_edge_count = assistant.preview_locked_skeleton_confluence(
            locked_segments,
            int(self.confluence_inner_radius_var.get()),
            int(self.confluence_outer_radius_var.get()),
        )
        if seed_edge_count == 0:
            messagebox.showinfo("提示", "没有找到已锁定河道。")
            return
        self._set_flow_preview(ops, "周边汇流", "confluence", None, unchanged_ops)
        self.info_var.set(
            f"周边汇流预览完成，锁定河道 {seed_edge_count} 组，远带 {radius} 像元，需修改 {len(self.flow_preview_ops)} 个，已一致 {len(self.flow_preview_unchanged_ops)} 个"
        )
        self._refresh_flow_controls()

    def _set_flow_preview(
        self,
        ops: List[Tuple[int, int, int]],
        label: str,
        kind: str = "",
        segment_key: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        unchanged_ops: Optional[List[Tuple[int, int, int]]] = None,
    ) -> None:
        unique: Dict[Tuple[int, int], int] = {}
        unchanged_unique: Dict[Tuple[int, int], int] = {}
        raster = self.flow_raster
        for row, col, code in ops:
            if kind == "confluence" and self._is_current_stream_cell(row, col):
                continue
            if raster is not None and 0 <= row < raster.nrows and 0 <= col < raster.ncols and raster.value_at(row, col) == code:
                unchanged_unique[(row, col)] = code
            else:
                unique[(row, col)] = code
        for row, col, code in unchanged_ops or []:
            if (row, col) in unique:
                continue
            if kind == "confluence" and self._is_current_stream_cell(row, col):
                continue
            unchanged_unique[(row, col)] = code
        self.flow_preview_ops = [(row, col, code) for (row, col), code in unique.items()]
        self.flow_preview_unchanged_ops = [(row, col, code) for (row, col), code in unchanged_unique.items()]
        self.flow_preview_kind = kind
        self.flow_preview_segment_key = segment_key
        self._update_flow_assist_text()
        if not self.flow_preview_ops and not self.flow_preview_unchanged_ops:
            self.info_var.set(f"{label}: 没有可预览的像元")
        elif not self.flow_preview_ops:
            self._refresh_flow_controls()
            self.info_var.set(f"{label}: 没有需要修改的像元，已一致 {len(self.flow_preview_unchanged_ops)} 个")
            self.render(full=True)
            return
        else:
            self._refresh_flow_controls()
            unchanged_text = f"，已一致 {len(self.flow_preview_unchanged_ops)} 个" if self.flow_preview_unchanged_ops else ""
            self.info_var.set(f"{label}: 需修改 {len(self.flow_preview_ops)} 个{unchanged_text}，点击“{self._flow_apply_button_text()}”写入橙色像元")
            self.render(full=True)
            return
        self._refresh_flow_controls()
        self.render(full=True)

    def apply_flow_preview(self) -> None:
        raster = self.flow_raster
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        if not self.flow_preview_ops:
            messagebox.showinfo("提示", "当前没有可应用的流向预览。")
            return
        tool = "river_skeleton" if self.flow_preview_kind == "river_skeleton" else "manual_assist"
        note = "locked river skeleton flow" if self.flow_preview_kind == "river_skeleton" else "manual flow assist preview"
        batch = self._apply_flow_ops(self.flow_preview_ops, tool, note)
        if not batch.ops:
            self.clear_flow_preview()
            self.info_var.set("预览结果与当前流向一致，无需修改")
            return
        self._record_flow_batch(batch)
        count = len(batch.ops)
        if self.flow_preview_kind == "segment" and self.selected_flow_segment is not None:
            downstream = self.flow_segment_downstream or self.selected_flow_segment.end
            self.confirmed_flow_segments[self.selected_flow_segment.edge_key] = downstream
            self.confirmed_flow_segment_cells[self.selected_flow_segment.edge_key] = list(self.selected_flow_segment.cells)
        self.flow_preview_ops = []
        self.flow_preview_unchanged_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        if self.active_mode() != "flow":
            self.mode_var.set("flow")
            self.on_tool_changed()
            self._invalidate_viewport_cache()
            self.refresh_snapshot_list()
        self._refresh_flow_controls()
        self.flush_pending_render(force=True)
        if tool == "river_skeleton":
            self.info_var.set(f"已应用河道本体流向预览，修改 {count} 个河道像元；已切换到订正流向模式")
        else:
            self.info_var.set(f"已应用周边汇流预览，修改 {count} 个像元；已切换到订正流向模式")

    def _apply_flow_ops(self, ops: List[Tuple[int, int, int]], tool: str, note: str) -> ChangeBatch:
        batch = ChangeBatch(mode="flow", tool=tool, note=note)
        raster = self.flow_raster
        if raster is None:
            return batch
        for row, col, code in ops:
            if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
                continue
            if tool == "manual_assist" and self._is_current_stream_cell(row, col):
                continue
            old = raster.value_at(row, col)
            if old == code:
                continue
            raster.set_value(row, col, code)
            batch.add(row, col, old, code)
            self.mark_dirty_cell(row, col)
        return batch

    def _is_current_stream_cell(self, row: int, col: int) -> bool:
        stream = self.stream_raster
        raster = self.flow_raster
        if stream is None or raster is None:
            return False
        if stream.nrows != raster.nrows or stream.ncols != raster.ncols:
            return False
        if not (0 <= row < stream.nrows and 0 <= col < stream.ncols):
            return False
        return stream.value_at(row, col) == STREAM_VALUE

    def _record_flow_batch(self, batch: ChangeBatch) -> None:
        if not batch.ops:
            return
        self.histories["flow"].append(batch)
        if len(self.histories["flow"]) > 50:
            self.histories["flow"] = self.histories["flow"][-50:]
        self.redo_stacks["flow"].clear()
        self.log_batch(batch)
        self._take_flow_snapshot(silent=True)

    def _take_flow_snapshot(self, silent: bool = False) -> None:
        raster = self.flow_raster
        if raster is None:
            return
        tag = f"flow_{Path(raster.path).stem}_{len(self.snapshots['flow']) + 1}"
        self.snapshots["flow"].append((tag, raster.copy()))
        if len(self.snapshots["flow"]) > 50:
            self.snapshots["flow"] = self.snapshots["flow"][-50:]
        if self.active_mode() == "flow":
            self.refresh_snapshot_list()
        if not silent:
            self.info_var.set(f"已创建快照 {tag}")

    def clear_flow_preview(self) -> None:
        self.flow_preview_ops = []
        self.flow_preview_unchanged_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)

    def _suggest_flow_candidates(self, raster: RasterData, row: int, col: int) -> List[int]:
        votes: Dict[int, int] = {}
        current = raster.value_at(row, col)
        if current in DIR_ORDER:
            votes[current] = votes.get(current, 0) + 3
        for code, (dr, dc) in DIR_OFFSETS.items():
            nr = row + dr
            nc = col + dc
            if not (0 <= nr < raster.nrows and 0 <= nc < raster.ncols):
                continue
            neighbor = raster.value_at(nr, nc)
            if neighbor in DIR_ORDER:
                votes[OPPOSITE_DIR[code]] = votes.get(OPPOSITE_DIR[code], 0) + 2
            elif neighbor == STREAM_VALUE:
                votes[code] = votes.get(code, 0) + 1
        ranked = sorted(votes.items(), key=lambda item: (-item[1], DIR_ORDER.index(item[0]) if item[0] in DIR_ORDER else 999))
        return [code for code, _ in ranked]

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
            self.selected_flow_segment = None
            self.flow_segment_downstream = None
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
        self._flow_network_cache_key = None
        self._flow_network_cache = None

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

    def _apply_selection_overlay(self, image: Image.Image, raster: RasterData, zoom: float) -> Image.Image:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        if self.selected_flow_region is not None:
            row0, row1, col0, col1 = self.selected_flow_region
            x0 = int(math.floor(col0 * zoom - self._view_x))
            y0 = int(math.floor(row0 * zoom - self._view_y))
            x1 = max(x0 + 1, int(math.ceil((col1 + 1) * zoom - self._view_x)))
            y1 = max(y0 + 1, int(math.ceil((row1 + 1) * zoom - self._view_y)))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle(
                (x0, y0, x1 - 1, y1 - 1),
                outline=self.assist_palette["region_outline"],
                width=max(2, int(round(max(1.0, zoom / 8.0)))),
                fill=self.assist_palette["region_fill"],
            )
        if self.selected_flow_cell is not None:
            overlay_selection(overlay, raster, self.selected_flow_cell, zoom, view_x=self._view_x, view_y=self._view_y)
        self._draw_flow_assist_markers(overlay, raster, zoom)
        self._draw_flow_preview_overlay(overlay, raster, zoom)
        return Image.alpha_composite(image, overlay)

    def _draw_flow_preview_overlay(self, overlay: Image.Image, raster: RasterData, zoom: float) -> None:
        if not self.flow_preview_kind or (not self.flow_preview_ops and not self.flow_preview_unchanged_ops):
            return
        draw = ImageDraw.Draw(overlay)
        for row, col, code in self.flow_preview_unchanged_ops:
            self._draw_flow_preview_cell(
                draw,
                overlay,
                raster,
                zoom,
                row,
                col,
                code,
                fill=self.assist_palette["preview_same_fill"],
                outline=self.assist_palette["preview_same_outline"],
                arrow=self.assist_palette["preview_same_arrow"],
                width_scale=9.0,
            )
        for row, col, code in self.flow_preview_ops:
            self._draw_flow_preview_cell(
                draw,
                overlay,
                raster,
                zoom,
                row,
                col,
                code,
                fill=self.assist_palette["preview_change_fill"],
                outline=self.assist_palette["preview_change_outline"],
                arrow=self.assist_palette["preview_change_arrow"],
                width_scale=7.0,
            )

    def _draw_flow_preview_cell(
        self,
        draw: ImageDraw.ImageDraw,
        overlay: Image.Image,
        raster: RasterData,
        zoom: float,
        row: int,
        col: int,
        code: int,
        fill: RGBA,
        outline: RGBA,
        arrow: RGBA,
        width_scale: float,
    ) -> None:
        if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
            return
        x0 = int(math.floor(col * zoom - self._view_x))
        y0 = int(math.floor(row * zoom - self._view_y))
        x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - self._view_x)))
        y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - self._view_y)))
        if x1 < 0 or y1 < 0 or x0 >= overlay.size[0] or y0 >= overlay.size[1]:
            return
        draw.rectangle(
            (x0, y0, x1 - 1, y1 - 1),
            fill=fill,
            outline=outline,
            width=max(1, int(round(max(1.0, zoom / width_scale)))),
        )
        self._draw_preview_direction_arrow(draw, row, col, code, zoom, arrow)

    def _draw_preview_direction_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        row: int,
        col: int,
        code: int,
        zoom: float,
        color: RGBA = (165, 35, 0, 255),
    ) -> None:
        offset = DIR_OFFSETS.get(int(code))
        if offset is None:
            return
        dr, dc = offset
        cx = (col + 0.5) * zoom - self._view_x
        cy = (row + 0.5) * zoom - self._view_y
        length = max(5.0, 0.62 * zoom)
        ex = cx + dc * length
        ey = cy + dr * length
        width = max(3, int(round(max(1.0, zoom / 6.0))))
        head = max(3.0, 0.24 * zoom)
        draw.line((cx, cy, ex, ey), fill=color, width=width)
        angle = math.atan2(ey - cy, ex - cx)
        left = (ex - head * math.cos(angle - math.pi / 6), ey - head * math.sin(angle - math.pi / 6))
        right = (ex - head * math.cos(angle + math.pi / 6), ey - head * math.sin(angle + math.pi / 6))
        draw.line((ex, ey, left[0], left[1]), fill=color, width=width)
        draw.line((ex, ey, right[0], right[1]), fill=color, width=width)

    def _draw_flow_assist_markers(self, overlay: Image.Image, raster: RasterData, zoom: float) -> None:
        draw = ImageDraw.Draw(overlay)
        size = max(5, int(round(min(18.0, max(7.0, zoom * 1.8)))))
        if self.selected_flow_segment is not None:
            self._draw_selected_flow_segment(draw, overlay.size, raster, zoom, size)
        for edge_key, downstream in self.confirmed_flow_segments.items():
            self._draw_confirmed_flow_segment(draw, overlay.size, raster, zoom, edge_key, downstream, size)
        if self.flow_skeleton_outlet is not None:
            self._draw_flow_outlet_marker(draw, overlay.size, raster, zoom, self.flow_skeleton_outlet, size)

    def _draw_flow_outlet_marker(
        self,
        draw: ImageDraw.ImageDraw,
        image_size: Tuple[int, int],
        raster: RasterData,
        zoom: float,
        cell: Tuple[int, int],
        size: int,
    ) -> None:
        row, col = cell
        if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
            return
        cx = (col + 0.5) * zoom - self._view_x
        cy = (row + 0.5) * zoom - self._view_y
        if cx < -size or cy < -size or cx > image_size[0] + size or cy > image_size[1] + size:
            return
        fill = self.assist_palette["outlet_fill"]
        outline = self.assist_palette["outlet_outline"]
        draw.ellipse((cx - size, cy - size, cx + size, cy + size), fill=fill, outline=outline, width=2)
        draw.text((cx + size + 2, cy - size), "出口", fill=outline)

    def _draw_marker_group(
        self,
        draw: ImageDraw.ImageDraw,
        image_size: Tuple[int, int],
        raster: RasterData,
        zoom: float,
        cells: List[Tuple[int, int]],
        kind: str,
        size: int,
    ) -> None:
        for idx, (row, col) in enumerate(cells, start=1):
            if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
                continue
            cx = (col + 0.5) * zoom - self._view_x
            cy = (row + 0.5) * zoom - self._view_y
            if cx < -size or cy < -size or cx > image_size[0] + size or cy > image_size[1] + size:
                continue
            label = str(idx)
            if kind == "source":
                color = self.assist_palette["source_fill"]
                outline = self.assist_palette["source_outline"]
                points = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
                draw.polygon(points, fill=color, outline=outline)
                draw.text((cx + size + 2, cy - size), f"S{label}", fill=outline)
            elif kind == "outlet":
                color = self.assist_palette["outlet_fill"]
                outline = self.assist_palette["outlet_outline"]
                draw.ellipse((cx - size, cy - size, cx + size, cy + size), fill=color, outline=outline, width=2)
                draw.text((cx + size + 2, cy - size), f"O{label}", fill=outline)
            else:
                color = self.assist_palette["node_fill"]
                outline = self.assist_palette["node_outline"]
                draw.rectangle((cx - size, cy - size, cx + size, cy + size), fill=color, outline=outline, width=2)
                draw.text((cx + size + 2, cy - size), f"N{label}", fill=outline)

    def _draw_selected_flow_segment(self, draw: ImageDraw.ImageDraw, image_size: Tuple[int, int], raster: RasterData, zoom: float, size: int) -> None:
        self._draw_flow_segment(
            draw,
            image_size,
            raster,
            zoom,
            self.selected_flow_segment,
            self.flow_segment_downstream,
            self.assist_palette["selected_line"],
            self.assist_palette["selected_fill"],
            size,
        )

    def _draw_confirmed_flow_segment(
        self,
        draw: ImageDraw.ImageDraw,
        image_size: Tuple[int, int],
        raster: RasterData,
        zoom: float,
        edge_key: Tuple[Tuple[int, int], Tuple[int, int]],
        downstream: Tuple[int, int],
        size: int,
    ) -> None:
        if self.selected_flow_segment is not None and self.selected_flow_segment.edge_key == edge_key:
            return
        cells = self.confirmed_flow_segment_cells.get(edge_key)
        if not cells or len(cells) < 2:
            return
        self._draw_locked_skeleton_cells(
            draw,
            image_size,
            raster,
            zoom,
            cells,
            self.assist_palette["locked_line"],
            self.assist_palette["locked_fill"],
        )

    def _draw_locked_skeleton_cells(
        self,
        draw: ImageDraw.ImageDraw,
        image_size: Tuple[int, int],
        raster: RasterData,
        zoom: float,
        cells: List[Tuple[int, int]],
        line_color: Tuple[int, int, int, int],
        fill_color: Tuple[int, int, int, int],
    ) -> None:
        width = max(1, int(round(max(1.0, zoom / 10.0))))
        for row, col in cells:
            if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
                continue
            x0 = int(math.floor(col * zoom - self._view_x))
            y0 = int(math.floor(row * zoom - self._view_y))
            x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - self._view_x)))
            y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - self._view_y)))
            if x1 < 0 or y1 < 0 or x0 >= image_size[0] or y0 >= image_size[1]:
                continue
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill_color, outline=line_color, width=width)

    def _draw_flow_segment(
        self,
        draw: ImageDraw.ImageDraw,
        image_size: Tuple[int, int],
        raster: RasterData,
        zoom: float,
        segment: Optional[FlowSegment],
        downstream_end: Optional[Tuple[int, int]],
        line_color: Tuple[int, int, int, int],
        fill_color: Tuple[int, int, int, int],
        size: int,
    ) -> None:
        if segment is None:
            return
        assistant = self._flow_assistant()
        if assistant is None:
            return
        cells = assistant.oriented_segment_cells(segment, downstream_end)
        if len(cells) < 1:
            return
        for row, col in cells:
            if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
                continue
            x0 = int(math.floor(col * zoom - self._view_x))
            y0 = int(math.floor(row * zoom - self._view_y))
            x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - self._view_x)))
            y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - self._view_y)))
            if x1 < 0 or y1 < 0 or x0 >= image_size[0] or y0 >= image_size[1]:
                continue
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill_color, outline=line_color, width=max(1, int(round(max(1.0, zoom / 10.0)))))
        start = cells[0]
        end = cells[-1]
        sx = (start[1] + 0.5) * zoom - self._view_x
        sy = (start[0] + 0.5) * zoom - self._view_y
        ex = (end[1] + 0.5) * zoom - self._view_x
        ey = (end[0] + 0.5) * zoom - self._view_y
        draw.ellipse((sx - size, sy - size, sx + size, sy + size), outline=line_color, width=2)
        draw.ellipse((ex - size, ey - size, ex + size, ey + size), outline=line_color, width=2)
        # 仅保留端点和线段高亮，避免把旧的上下游骨架叙事继续放大到界面上。

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

    def _snapshot_raster_payload(self, raster: Optional[RasterData]) -> Dict[str, object]:
        return raster_payload(raster, self._store_path)

    def _rebuild_raster_from_payload(self, payload: Dict[str, object], data: np.ndarray) -> Optional[RasterData]:
        return rebuild_raster(payload, data, self._resolve_stored_path)

    def _store_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace_dir.resolve()))
        except Exception:
            return str(path)

    def _resolve_stored_path(self, stored: str) -> Path:
        return resolve_relative_or_absolute(stored, self.workspace_dir)

    def save_autosave(self) -> None:
        if self.stream_raster is None and self.flow_raster is None:
            return
        try:
            meta = {
                "mode": self.mode_var.get(),
                "tool": self.tool_var.get(),
                "direction": self.direction_var.get(),
                "brush_size": int(self.brush_size_var.get()),
                "vector_tol": float(self.vector_tol_var.get()),
                "river_flow_mode": self.river_flow_mode_var.get(),
                "confluence_mode": self.confluence_mode_var.get(),
                "confluence_max_distance": int(self.confluence_max_distance_var.get()),
                "zoom": float(self.zoom_var.get()),
                "confluence_inner_radius": int(self.confluence_inner_radius_var.get()),
                "confluence_outer_radius": int(self.confluence_outer_radius_var.get()),
                "show_grid": self.show_grid_var.get(),
                "show_scale": self.show_scale_var.get(),
                "show_flow_arrows": self.show_flow_arrows_var.get(),
                "compare_original": self.compare_original_var.get(),
                "show_confluence_polygon": self.show_confluence_polygon_var.get(),
                "confluence_polygon_width": int(self.confluence_polygon_width_var.get()),
                "autosave": self.autosave_var.get(),
                "stream": self._snapshot_raster_payload(self.stream_raster),
                "flow": self._snapshot_raster_payload(self.flow_raster),
                "original_stream": self._snapshot_raster_payload(self.original_stream_raster),
                "original_flow": self._snapshot_raster_payload(self.original_flow_raster),
                "shp_path": self._store_path(self.vector_layer.path) if self.vector_layer is not None else "",
                "confluence_polygon_path": self._store_path(self.confluence_polygon_layer.path) if self.confluence_polygon_layer is not None else "",
                "palette_state": self._palette_state(),
            }
            write_session_files(
                self._autosave_meta_path,
                self._autosave_data_path,
                meta,
                self.stream_raster,
                self.flow_raster,
                self.original_stream_raster,
                self.original_flow_raster,
            )
        except Exception as exc:
            self.info_var.set(f"自动保存失败: {exc}")

    def _restore_autosave(self) -> bool:
        try:
            session = read_session_files(self._autosave_meta_path, self._autosave_data_path)
            if session is None:
                return False
            meta = session.payload
            data = session.arrays or {}
            stream_meta = meta.get("stream", {})
            if isinstance(stream_meta, dict) and "stream" in data and isinstance(data["stream"], np.ndarray) and data["stream"].size:
                candidate = self._rebuild_raster_from_payload(stream_meta, data["stream"])
                if candidate is not None and self._looks_like_raster_kind(candidate, "stream"):
                    self.stream_raster = candidate
            flow_meta = meta.get("flow", {})
            if isinstance(flow_meta, dict) and "flow" in data and isinstance(data["flow"], np.ndarray) and data["flow"].size:
                candidate = self._rebuild_raster_from_payload(flow_meta, data["flow"])
                if candidate is not None and self._looks_like_raster_kind(candidate, "flow"):
                    self.flow_raster = candidate
            original_stream_meta = meta.get("original_stream", stream_meta)
            if self.stream_raster is not None and isinstance(original_stream_meta, dict) and "original_stream" in data and isinstance(data["original_stream"], np.ndarray) and data["original_stream"].size:
                self.original_stream_raster = self._rebuild_raster_from_payload(original_stream_meta, data["original_stream"])
            elif self.stream_raster is not None and self.stream_raster.path.exists():
                self.original_stream_raster = parse_asc(self.stream_raster.path)
            original_flow_meta = meta.get("original_flow", flow_meta)
            if self.flow_raster is not None and isinstance(original_flow_meta, dict) and "original_flow" in data and isinstance(data["original_flow"], np.ndarray) and data["original_flow"].size:
                self.original_flow_raster = self._rebuild_raster_from_payload(original_flow_meta, data["original_flow"])
            elif self.flow_raster is not None and self.flow_raster.path.exists():
                self.original_flow_raster = parse_asc(self.flow_raster.path)
            if self.stream_raster is None and self.flow_raster is None:
                return False
            self.mode_var.set(str(meta.get("mode", self.mode_var.get())))
            self.tool_var.set(str(meta.get("tool", self.tool_var.get())))
            self.direction_var.set(str(meta.get("direction", self.direction_var.get())))
            self.brush_size_var.set(int(meta.get("brush_size", self.brush_size_var.get())))
            self.vector_tol_var.set(float(meta.get("vector_tol", self.vector_tol_var.get())))
            river_flow_mode = str(meta.get("river_flow_mode", self.river_flow_mode_var.get()))
            if river_flow_mode in {"平滑", "稳健"}:
                self.river_flow_mode_var.set(river_flow_mode)
            confluence_mode = str(meta.get("confluence_mode", self.confluence_mode_var.get()))
            if confluence_mode in {"近远带", "范围SHP"}:
                self.confluence_mode_var.set(confluence_mode)
            self._update_confluence_hint()
            self.confluence_max_distance_var.set(int(meta.get("confluence_max_distance", self.confluence_max_distance_var.get())))
            self.zoom_var.set(float(meta.get("zoom", self.zoom_var.get())))
            self.confluence_inner_radius_var.set(int(meta.get("confluence_inner_radius", self.confluence_inner_radius_var.get())))
            self.confluence_outer_radius_var.set(int(meta.get("confluence_outer_radius", self.confluence_outer_radius_var.get())))
            self.show_grid_var.set(bool(meta.get("show_grid", self.show_grid_var.get())))
            self.show_scale_var.set(bool(meta.get("show_scale", self.show_scale_var.get())))
            self.show_flow_arrows_var.set(bool(meta.get("show_flow_arrows", self.show_flow_arrows_var.get())))
            self.compare_original_var.set(bool(meta.get("compare_original", self.compare_original_var.get())))
            self.show_confluence_polygon_var.set(bool(meta.get("show_confluence_polygon", self.show_confluence_polygon_var.get())))
            self.confluence_polygon_width_var.set(int(meta.get("confluence_polygon_width", self.confluence_polygon_width_var.get())))
            self.autosave_var.set(bool(meta.get("autosave", self.autosave_var.get())))
            palette_state = meta.get("palette_state")
            if isinstance(palette_state, dict):
                self._apply_palette_state(palette_state)
            self.on_tool_changed()
            shp_path = meta.get("shp_path")
            if isinstance(shp_path, str) and shp_path:
                shp = self._resolve_stored_path(shp_path)
                if shp.exists():
                    self.vector_layer = parse_shapefile_lines(shp)
                    self.shp_var.set(self._store_path(shp))
            confluence_polygon_path = meta.get("confluence_polygon_path")
            if isinstance(confluence_polygon_path, str) and confluence_polygon_path:
                polygon = self._resolve_stored_path(confluence_polygon_path)
                if polygon.exists():
                    self.confluence_polygon_layer = parse_shapefile_polygon(polygon)
                    self.confluence_shp_var.set(self._store_path(polygon))
            if self.stream_raster is not None:
                self.stream_file_var.set(self._store_path(self.stream_raster.path))
            if self.flow_raster is not None:
                self.flow_file_var.set(self._store_path(self.flow_raster.path))
            self._maybe_setup_transformer()
            self.render(full=True)
            self.refresh_snapshot_list()
            missing = []
            if self.stream_raster is None:
                missing.append("河道ASC")
            if self.flow_raster is None:
                missing.append("流向ASC")
            if missing:
                self.info_var.set("已恢复部分自动保存，请重新加载" + "、".join(missing))
            else:
                self.info_var.set("已从自动保存恢复")
            return True
        except Exception:
            return False

    def _schedule_autosave(self) -> None:
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except Exception:
                pass
        self._autosave_job = self.after(30000, self._autosave_tick)

    def _autosave_tick(self) -> None:
        self._autosave_job = None
        if self.autosave_var.get():
            self.save_autosave()
        self._schedule_autosave()

    def restore_autosave_dialog(self) -> None:
        if not self._restore_autosave():
            messagebox.showinfo("提示", "没有可恢复的自动保存。")

    def on_close(self) -> None:
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
