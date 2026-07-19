from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
from tkinter import filedialog, messagebox

from .water_core import (
    RasterData,
    parse_asc,
    parse_shapefile_lines,
    parse_shapefile_polygon,
    resolve_relative_or_absolute,
)
def resolve_display_mode(
    payload: Dict[str, object],
    edit_mode: str,
    has_stream: bool,
    has_flow: bool,
) -> str:
    requested = str(payload.get("display_mode", payload.get("mode", edit_mode)))
    loaded = {"stream": has_stream, "flow": has_flow}
    if requested in loaded and loaded[requested]:
        return requested
    if edit_mode in loaded and loaded[edit_mode]:
        return edit_mode
    if has_stream:
        return "stream"
    if has_flow:
        return "flow"
    return edit_mode if edit_mode in loaded else "stream"


from .water_project import (
    project_data_path,
    raster_payload,
    read_project_arrays,
    read_project_payload,
    read_session_files,
    rebuild_raster,
    write_project_files,
    write_session_files,
)


class ProjectWorkflowMixin:
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
        dem_params = self._dem_score_params()
        payload = {
            "version": "2.0",
            "workspace_dir": str(self.workspace_dir),
            "mode": self.mode_var.get(),
            "display_mode": self.display_mode_var.get(),
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
            "dem_path": self._store_path(self.dem_path) if self.dem_path is not None else "",
            "dem_flat_tolerance": dem_params["flat_tolerance"],
            "dem_mild_uphill": dem_params["mild_uphill_threshold"],
            "dem_severe_uphill": dem_params["severe_uphill_threshold"],
            "dem_score_display": self.dem_score_display_var.get(),
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
        dem_path = payload.get("dem_path")
        if isinstance(dem_path, str) and dem_path:
            resolved = self._resolve_stored_path(dem_path)
            if resolved.exists():
                self.load_dem(resolved, update_autosave=False)
        mode = str(payload.get("mode", self.mode_var.get()))
        if mode in {"stream", "flow"}:
            self.mode_var.set(mode)
            self._show_edit_navigation(mode)
        display_mode = resolve_display_mode(
            payload,
            self.mode_var.get(),
            self.stream_raster is not None,
            self.flow_raster is not None,
        )
        self.display_mode_var.set(display_mode)
        self._sync_display_mode_label()
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
        self.dem_flat_tolerance_var.set(float(payload.get("dem_flat_tolerance", self.dem_flat_tolerance_var.get())))
        self.dem_mild_uphill_var.set(float(payload.get("dem_mild_uphill", self.dem_mild_uphill_var.get())))
        self.dem_severe_uphill_var.set(float(payload.get("dem_severe_uphill", self.dem_severe_uphill_var.get())))
        self.dem_score_display_var.set(payload.get("dem_score_display", self.dem_score_display_var.get()))
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

    def _clear_loaded_session(self) -> None:
        self.stream_raster = None
        self.flow_raster = None
        self.original_stream_raster = None
        self.original_flow_raster = None
        self.vector_layer = None
        self.confluence_polygon_layer = None
        self.transformer = None
        self.confluence_transformer = None
        self._clear_dem_state()
        self.stream_file_var.set("未加载")
        self.flow_file_var.set("未加载")
        self.shp_var.set("未加载")
        self.confluence_shp_var.set("未加载")
        self.histories = {"stream": [], "flow": []}
        self.redo_stacks = {"stream": [], "flow": []}
        self.snapshots = {"stream": [], "flow": []}
        self.current_batch = None
        self._clear_flow_skeleton_state()
        self.flow_suggestions = []
        self._reset_flow_selection_state()
        self._invalidate_flow_network_cache()
        self._invalidate_viewport_cache()

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
            dem_params = self._dem_score_params()
            meta = {
                "mode": self.mode_var.get(),
            "display_mode": self.display_mode_var.get(),
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
                "dem_path": self._store_path(self.dem_path) if self.dem_path is not None else "",
                "dem_flat_tolerance": dem_params["flat_tolerance"],
                "dem_mild_uphill": dem_params["mild_uphill_threshold"],
                "dem_severe_uphill": dem_params["severe_uphill_threshold"],
                "dem_score_display": self.dem_score_display_var.get(),
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
            restored_mode = str(meta.get("mode", self.mode_var.get()))
            if restored_mode in {"stream", "flow"}:
                self.mode_var.set(restored_mode)
                self._show_edit_navigation(restored_mode)
            display_mode = resolve_display_mode(
                meta,
                self.mode_var.get(),
                self.stream_raster is not None,
                self.flow_raster is not None,
            )
            self.display_mode_var.set(display_mode)
            self._sync_display_mode_label()
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
            self.dem_flat_tolerance_var.set(float(meta.get("dem_flat_tolerance", self.dem_flat_tolerance_var.get())))
            self.dem_mild_uphill_var.set(float(meta.get("dem_mild_uphill", self.dem_mild_uphill_var.get())))
            self.dem_severe_uphill_var.set(float(meta.get("dem_severe_uphill", self.dem_severe_uphill_var.get())))
            self.dem_score_display_var.set(meta.get("dem_score_display", self.dem_score_display_var.get()))
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
            dem_path = meta.get("dem_path")
            if isinstance(dem_path, str) and dem_path:
                dem = self._resolve_stored_path(dem_path)
                if dem.exists():
                    self.load_dem(dem, update_autosave=False)
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
