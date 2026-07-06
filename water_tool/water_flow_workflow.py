from __future__ import annotations

import heapq
import math
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from tkinter import messagebox

from .water_core import (
    DIR_OFFSETS,
    DIR_ORDER,
    NODATA,
    OPPOSITE_DIR,
    STREAM_VALUE,
    ChangeBatch,
    RasterData,
    direction_text,
)
from .water_flow_assist import FlowNetworkAssistant, direction_from_delta
from .water_polygon import point_in_any_ring, rings_bounds
from .water_state import FlowPreviewState


class FlowWorkflowMixin:
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
        self._reset_flow_selection_state(clear_cell=False, clear_region=False, clear_segment=True)
        self._reset_flow_preview_state()
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
        self._reset_flow_preview_state()
        self._reset_flow_selection_state(clear_cell=False, clear_region=True, clear_segment=False)
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
        self._reset_flow_preview_state()
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
        self._reset_flow_preview_state()
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
        self._reset_flow_preview_state()
        self._update_flow_assist_text()
        self.render(full=False)

    def clear_flow_segment_state(self) -> None:
        self._clear_flow_skeleton_state()
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        self.render(full=False)
        self.info_var.set("已取消当前锁定河道、出口和预览。")

    def _clear_flow_skeleton_state(self) -> None:
        self._reset_flow_selection_state()
        self._reset_flow_lock_state()
        self._reset_flow_preview_state()
        self._refresh_flow_controls()

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
        self._reset_flow_preview_state()
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
        self._reset_flow_preview_state()
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
        preview = self.flow_preview_state
        self.info_var.set(f"河道流向预览完成，方向建议 {preview.change_count} 个。可点击“{preview.apply_button_text()}”写入。")
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
        self._reset_flow_preview_state()
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
            preview = self.flow_preview_state
            if not preview.has_apply_ops():
                self.info_var.set(
                    f"范围SHP汇流没有生成可应用预览：{distance_text}，候选像元 {candidate_count} 个，已一致 {preview.unchanged_count} 个。"
                )
                self._refresh_flow_controls()
                return
            self.info_var.set(
                f"范围SHP汇流预览完成，锁定河道 {seed_edge_count} 组，{distance_text}，候选像元 {candidate_count} 个，需修改 {preview.change_count} 个，已一致 {preview.unchanged_count} 个"
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
        preview = self.flow_preview_state
        self.info_var.set(
            f"周边汇流预览完成，锁定河道 {seed_edge_count} 组，远带 {radius} 像元，需修改 {preview.change_count} 个，已一致 {preview.unchanged_count} 个"
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
        self.flow_preview_state = FlowPreviewState.create(
            [(row, col, code) for (row, col), code in unique.items()],
            [(row, col, code) for (row, col), code in unchanged_unique.items()],
            label=label,
            kind=kind,
            segment_key=segment_key,
        )
        if hasattr(self, "update_dem_preview_coverage_hint"):
            self.update_dem_preview_coverage_hint()
        self._update_flow_assist_text()
        if not self.flow_preview_state.has_preview():
            self.info_var.set(f"{label}: 没有可预览的像元")
        elif not self.flow_preview_state.has_apply_ops():
            self._refresh_flow_controls()
            self.info_var.set(f"{label}: 没有需要修改的像元，已一致 {self.flow_preview_state.unchanged_count} 个")
            self.render(full=True)
            return
        else:
            self._refresh_flow_controls()
            unchanged_text = f"，已一致 {self.flow_preview_state.unchanged_count} 个" if self.flow_preview_state.unchanged_ops else ""
            self.info_var.set(f"{label}: 需修改 {self.flow_preview_state.change_count} 个{unchanged_text}，点击“{self._flow_apply_button_text()}”写入橙色像元")
            self.render(full=True)
            return
        self._refresh_flow_controls()
        self.render(full=True)

    def apply_flow_preview(self) -> None:
        raster = self.flow_raster
        if raster is None:
            messagebox.showwarning("提示", "请先加载流向ASC。")
            return
        preview = self.flow_preview_state
        if not preview.has_apply_ops():
            messagebox.showinfo("提示", "当前没有可应用的流向预览。")
            return
        tool = preview.apply_tool or preview.default_apply_tool()
        note = preview.apply_note or preview.default_apply_note()
        batch = self._apply_flow_ops(preview.ops, tool, note)
        if not batch.ops:
            self.clear_flow_preview()
            self.info_var.set("预览结果与当前流向一致，无需修改")
            return
        self._record_flow_batch(batch)
        count = len(batch.ops)
        preview_kind = preview.kind
        applied_message = preview.applied_message(count)
        if preview_kind == "segment" and self.selected_flow_segment is not None:
            downstream = self.flow_segment_downstream or self.selected_flow_segment.end
            self.confirmed_flow_segments[self.selected_flow_segment.edge_key] = downstream
            self.confirmed_flow_segment_cells[self.selected_flow_segment.edge_key] = list(self.selected_flow_segment.cells)
        self._reset_flow_preview_state()
        self._update_flow_assist_text()
        if self.active_mode() != "flow":
            self.mode_var.set("flow")
            self.on_tool_changed()
            self._invalidate_viewport_cache()
            self.refresh_snapshot_list()
        self._refresh_flow_controls()
        self.flush_pending_render(force=True)
        self.info_var.set(applied_message)

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
        self._reset_flow_preview_state()
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
