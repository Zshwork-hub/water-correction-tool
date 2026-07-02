from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw
from tkinter import messagebox

from water_core import NODATA, STREAM_VALUE, ChangeBatch, RasterData, clamp, direction_text
from water_flow_assist import direction_from_delta
from water_geometry import brush_cells, line_cells


class RasterEditingMixin:
    def current_edit_value(self) -> int:
        if self.tool_var.get() == "eraser":
            return NODATA
        if self.mode_var.get() == "stream":
            return STREAM_VALUE
        try:
            return int(self.direction_var.get().split()[0])
        except Exception:
            return 1

    def brush_radius(self) -> int:
        try:
            size = int(self.brush_size_var.get())
        except Exception:
            size = 1
        size = clamp(size, 1, 15)
        self.brush_size_var.set(size)
        return size // 2

    def apply_selected_direction(self) -> None:
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
            messagebox.showinfo("提示", "请先右键选中像元，或把鼠标停在需要修改的像元上。")
            return
        row, col, _, _ = selection
        new_value = self.current_edit_value()
        old_value = raster.value_at(row, col)
        if old_value == new_value:
            return
        batch = ChangeBatch(mode="flow", tool="direction", note="apply selected direction")
        raster.set_value(row, col, new_value)
        batch.add(row, col, old_value, new_value)
        self.histories["flow"].append(batch)
        if len(self.histories["flow"]) > 50:
            self.histories["flow"] = self.histories["flow"][-50:]
        self.redo_stacks["flow"].clear()
        self.log_batch(batch)
        self.take_snapshot(silent=True)
        self.selected_flow_cell = (row, col)
        self.mark_dirty_cell(row, col)
        self.schedule_view_refresh(full=True)
        self.info_var.set(f"已修改流向为 {direction_text(new_value)}")

    def paint_stroke_to(self, row: int, col: int) -> None:
        if self.current_batch is None:
            return
        if self.last_painted is None:
            cells = [(row, col)]
        else:
            cells = line_cells(self.last_painted, (row, col))
        raster = self.get_active_raster()
        if raster is None:
            return
        radius = self.brush_radius()
        for rr, cc in cells:
            for br, bc in brush_cells(rr, cc, raster.nrows, raster.ncols, radius):
                if (br, bc) in self._stroke_seen:
                    continue
                self._stroke_seen.add((br, bc))
                self.paint_single_cell(br, bc)
        self.last_painted = (row, col)

    def paint_direction_line_to(self, start_row: int, start_col: int, end_row: int, end_col: int) -> None:
        if self.current_batch is None or self.mode_var.get() != "flow":
            return
        if self._flow_preview_last_cell is None:
            cells = line_cells((start_row, start_col), (end_row, end_col))
        else:
            cells = line_cells(self._flow_preview_last_cell, (end_row, end_col))
        if not cells:
            return
        direction = self._direction_from_delta(start_row, start_col, end_row, end_col)
        if direction is None:
            direction = self.current_edit_value()
        for row, col in cells:
            self.paint_flow_cell(row, col, direction)
        self._flow_preview_last_cell = (end_row, end_col)

    def paint_flow_cell(self, row: int, col: int, direction: Optional[int] = None) -> None:
        raster = self.get_active_raster()
        if raster is None or self.current_batch is None or self.mode_var.get() != "flow":
            return
        new_value = direction if direction is not None else self.current_edit_value()
        old_value = raster.value_at(row, col)
        if old_value == new_value:
            return
        raster.set_value(row, col, new_value)
        self.current_batch.add(row, col, old_value, new_value)
        self.mark_dirty_cell(row, col)

    def paint_single_cell(self, row: int, col: int) -> None:
        raster = self.get_active_raster()
        if raster is None or self.current_batch is None:
            return
        if self.tool_var.get() not in {"brush", "eraser"}:
            return
        new_value = self.current_edit_value()
        old_value = raster.value_at(row, col)
        if old_value == new_value:
            return
        raster.set_value(row, col, new_value)
        self.current_batch.add(row, col, old_value, new_value)
        self.mark_dirty_cell(row, col)
        if self.active_mode() == "stream":
            self._clear_flow_skeleton_state()

    def _direction_from_delta(self, start_row: int, start_col: int, end_row: int, end_col: int) -> Optional[int]:
        return direction_from_delta(start_row, start_col, end_row, end_col)

    def mark_dirty_cell(self, row: int, col: int) -> None:
        zoom = float(self.zoom_var.get())
        x0 = int(math.floor(col * zoom - self._view_x))
        y0 = int(math.floor(row * zoom - self._view_y))
        x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - self._view_x)))
        y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - self._view_y)))
        self._dirty_cells.add((row, col))
        if self._dirty_bbox is None:
            self._dirty_bbox = (x0, y0, x1, y1)
        else:
            bx0, by0, bx1, by1 = self._dirty_bbox
            self._dirty_bbox = (min(bx0, x0), min(by0, y0), max(bx1, x1), max(by1, y1))
        self.schedule_refresh()

    def apply_vector_batch(self) -> None:
        if self.mode_var.get() != "stream":
            messagebox.showinfo("提示", "矢量批量修正仅在订正河道模式中使用。")
            return
        raster = self.get_active_raster()
        if raster is None:
            messagebox.showwarning("提示", "请先加载河道ASC。")
            return
        if self.vector_layer is None:
            messagebox.showwarning("提示", "请先加载SHP参考文件。")
            return
        tol = float(self.vector_tol_var.get())
        mask = self.build_vector_mask(raster, tol)
        ys, xs = np.where(mask & (raster.data != STREAM_VALUE))
        if len(xs) == 0:
            self.info_var.set("没有发现需要修正的像元")
            return
        batch = ChangeBatch(mode="stream", tool="vector", note=f"vector batch tol={tol}")
        for row, col in zip(ys.tolist(), xs.tolist()):
            old = raster.value_at(row, col)
            if old == STREAM_VALUE:
                continue
            raster.set_value(row, col, STREAM_VALUE)
            batch.add(row, col, old, STREAM_VALUE)
            self.mark_dirty_cell(row, col)
        if batch.ops:
            self.histories["stream"].append(batch)
            if len(self.histories["stream"]) > 50:
                self.histories["stream"] = self.histories["stream"][-50:]
            self.redo_stacks["stream"].clear()
            self.log_batch(batch)
            self.take_snapshot(silent=True)
            self._clear_flow_skeleton_state()
            self.flush_pending_render(force=True)
            self.info_var.set(f"矢量批量修正完成，修改 {len(batch.ops)} 个像元")

    def build_vector_mask(self, raster: RasterData, tolerance_cells: float) -> np.ndarray:
        mask = np.zeros((raster.nrows, raster.ncols), dtype=bool)
        if not self.vector_layer:
            return mask
        width = max(1, int(round(tolerance_cells * 2.0 + 1.0)))
        for line in self.vector_layer.polylines:
            pts = []
            for x, y in line:
                if self.transformer is not None:
                    x, y = self.transformer.transform(x, y)
                row, col = raster.world_to_rc(x, y)
                pts.append((col, row))
            if len(pts) < 2:
                continue
            tmp = Image.new("1", (raster.ncols, raster.nrows), 0)
            ImageDraw.Draw(tmp).line(pts, fill=1, width=width)
            mask |= np.array(tmp, dtype=bool)
        return mask
