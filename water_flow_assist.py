from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import ndimage

from water_core import NODATA, STREAM_VALUE, RasterData, VectorLayer, clamp
from water_geometry import line_cells


Cell = Tuple[int, int]
EdgeKey = Tuple[Cell, Cell]


def direction_from_delta(start_row: int, start_col: int, end_row: int, end_col: int) -> Optional[int]:
    dr = end_row - start_row
    dc = end_col - start_col
    if dr == 0 and dc == 0:
        return None
    adx = abs(dc)
    ady = abs(dr)
    if adx >= ady * 2:
        return 1 if dc > 0 else 16
    if ady >= adx * 2:
        return 4 if dr > 0 else 64
    if dr > 0 and dc > 0:
        return 2
    if dr > 0 and dc < 0:
        return 8
    if dr < 0 and dc < 0:
        return 32
    if dr < 0 and dc > 0:
        return 128
    return None


def cell_distance2(a: Cell, b: Cell) -> float:
    return float((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


@dataclass
class FlowSegment:
    edge_key: EdgeKey
    start: Cell
    end: Cell
    cells: List[Cell]
    nearest_cell: Cell
    nearest_index: int
    nearest_distance2: float


class FlowNetworkAssistant:
    def __init__(
        self,
        raster: RasterData,
        vector_layer: Optional[VectorLayer],
        transformer=None,
        stream_raster: Optional[RasterData] = None,
    ) -> None:
        self.raster = raster
        self.vector_layer = vector_layer
        self.transformer = transformer
        self.stream_raster = stream_raster

    def build_network(self) -> Dict[str, object]:
        nodes: Set[Cell] = set()
        adjacency: Dict[Cell, List[Cell]] = {}
        edge_map: Dict[EdgeKey, Dict[str, object]] = {}
        junctions: Set[Cell] = set()
        node_to_edges: Dict[Cell, Set[EdgeKey]] = {}
        if self.vector_layer is None:
            return {"nodes": nodes, "adjacency": adjacency, "edge_map": edge_map, "junctions": junctions, "node_to_edges": node_to_edges}

        poly_cells: List[List[Cell]] = []
        cell_degree: Dict[Cell, int] = {}
        for line in self.vector_layer.polylines:
            cells = self._rasterize_vector_line(line)
            if len(cells) < 2:
                continue
            poly_cells.append(cells)
            for cell in cells:
                cell_degree[cell] = cell_degree.get(cell, 0) + 1

        for cell, degree in cell_degree.items():
            if degree > 1:
                junctions.add(cell)

        for cells in poly_cells:
            split_points = set(junctions)
            split_points.add(cells[0])
            split_points.add(cells[-1])
            segment: List[Cell] = [cells[0]]
            for cell in cells[1:]:
                segment.append(cell)
                if len(segment) < 2:
                    continue
                if cell in split_points and segment[0] != segment[-1]:
                    self._register_network_edge(segment, nodes, adjacency, edge_map, node_to_edges)
                    segment = [cell]
            if len(segment) >= 2:
                self._register_network_edge(segment, nodes, adjacency, edge_map, node_to_edges)

        return {"nodes": nodes, "adjacency": adjacency, "edge_map": edge_map, "junctions": junctions, "node_to_edges": node_to_edges}

    def find_nearest_segment(
        self,
        target: Cell,
        network: Optional[Dict[str, object]] = None,
        max_distance_cells: Optional[int] = None,
    ) -> Optional[FlowSegment]:
        if self._has_stream_skeleton():
            return self.find_nearest_stream_segment(target, max_distance_cells=max_distance_cells)
        if network is None:
            network = self.build_network()
        edge_map = network.get("edge_map", {})
        if not edge_map:
            return None
        max_dist2 = None if max_distance_cells is None else float(max_distance_cells * max_distance_cells)
        best: Optional[FlowSegment] = None
        best_dist2 = float("inf")
        for edge_key, edge in edge_map.items():
            cells = edge.get("cells", [])
            start = edge.get("start")
            end = edge.get("end")
            if not isinstance(start, tuple) or not isinstance(end, tuple) or len(cells) < 2:
                continue
            nearest_index = 0
            nearest_cell = cells[0]
            nearest_distance2 = cell_distance2(nearest_cell, target)
            for idx, cell in enumerate(cells[1:], start=1):
                dist2 = cell_distance2(cell, target)
                if dist2 < nearest_distance2:
                    nearest_index = idx
                    nearest_cell = cell
                    nearest_distance2 = dist2
            if max_dist2 is not None and nearest_distance2 > max_dist2:
                continue
            if nearest_distance2 < best_dist2:
                best_dist2 = nearest_distance2
                best = FlowSegment(
                    edge_key=edge_key,
                    start=start,
                    end=end,
                    cells=list(cells),
                    nearest_cell=nearest_cell,
                    nearest_index=nearest_index,
                    nearest_distance2=nearest_distance2,
                )
        return best

    def find_nearest_stream_segment(self, target: Cell, max_distance_cells: Optional[int] = None) -> Optional[FlowSegment]:
        anchor = self._nearest_stream_cell(target, max_distance_cells or 12)
        if anchor is None:
            return None
        local_cells = self._collect_local_stream_component(anchor, target, radius=96, max_cells=12000)
        if len(local_cells) < 2:
            return None
        cells = self._trace_stream_segment(anchor, local_cells)
        if len(cells) < 2:
            return None
        start = cells[0]
        end = cells[-1]
        if start == end:
            return None
        nearest_index = 0
        nearest_cell = cells[0]
        nearest_distance2 = cell_distance2(nearest_cell, target)
        for idx, cell in enumerate(cells[1:], start=1):
            dist2 = cell_distance2(cell, target)
            if dist2 < nearest_distance2:
                nearest_index = idx
                nearest_cell = cell
                nearest_distance2 = dist2
        return FlowSegment(
            edge_key=tuple(sorted((start, end))),
            start=start,
            end=end,
            cells=cells,
            nearest_cell=nearest_cell,
            nearest_index=nearest_index,
            nearest_distance2=nearest_distance2,
        )

    def _has_stream_skeleton(self) -> bool:
        return (
            self.stream_raster is not None
            and self.stream_raster.nrows == self.raster.nrows
            and self.stream_raster.ncols == self.raster.ncols
        )

    def _is_stream_cell(self, row: int, col: int) -> bool:
        if not self._has_stream_skeleton() or self.stream_raster is None:
            return False
        if not (0 <= row < self.stream_raster.nrows and 0 <= col < self.stream_raster.ncols):
            return False
        return self.stream_raster.value_at(row, col) == STREAM_VALUE

    def _nearest_stream_cell(self, target: Cell, max_distance_cells: int) -> Optional[Cell]:
        tr, tc = target
        radius = max(1, int(max_distance_cells))
        best_cell: Optional[Cell] = None
        best_dist2 = float("inf")
        for row in range(max(0, tr - radius), min(self.raster.nrows, tr + radius + 1)):
            for col in range(max(0, tc - radius), min(self.raster.ncols, tc + radius + 1)):
                if not self._is_stream_cell(row, col):
                    continue
                dist2 = cell_distance2((row, col), target)
                if dist2 < best_dist2:
                    best_cell = (row, col)
                    best_dist2 = dist2
        return best_cell

    def _collect_local_stream_component(self, anchor: Cell, target: Cell, radius: int, max_cells: int) -> Set[Cell]:
        tr, tc = target
        row_min = max(0, tr - radius)
        row_max = min(self.raster.nrows - 1, tr + radius)
        col_min = max(0, tc - radius)
        col_max = min(self.raster.ncols - 1, tc + radius)
        cells: Set[Cell] = {anchor}
        queue = deque([anchor])
        while queue and len(cells) < max_cells:
            row, col = queue.popleft()
            for nr, nc in self._stream_neighbors((row, col), None):
                if nr < row_min or nr > row_max or nc < col_min or nc > col_max:
                    continue
                if (nr, nc) in cells:
                    continue
                cells.add((nr, nc))
                queue.append((nr, nc))
        return cells

    def _stream_neighbors(self, cell: Cell, allowed_cells: Optional[Set[Cell]]) -> List[Cell]:
        row, col = cell
        neighbors: List[Cell] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if allowed_cells is not None:
                    if (nr, nc) not in allowed_cells:
                        continue
                elif not self._is_stream_cell(nr, nc):
                    continue
                neighbors.append((nr, nc))
        neighbors.sort(key=lambda item: (item[0], item[1]))
        return neighbors

    def _trace_stream_segment(self, anchor: Cell, local_cells: Set[Cell]) -> List[Cell]:
        neighbors = self._stream_neighbors(anchor, local_cells)
        if not neighbors:
            return [anchor]
        branches: List[List[Cell]] = []
        for neighbor in neighbors:
            branches.append([anchor] + self._trace_branch(neighbor, anchor, local_cells))
        if len(neighbors) == 2:
            left = branches[0]
            right = branches[1]
            return list(reversed(left[1:])) + [anchor] + right[1:]
        best_left = branches[0]
        best_right = branches[0]
        best_score = -1
        for i in range(len(branches)):
            for j in range(i + 1, len(branches)):
                score = len(branches[i]) + len(branches[j])
                if score > best_score:
                    best_score = score
                    best_left = branches[i]
                    best_right = branches[j]
        if best_score < 0:
            branches.sort(key=len, reverse=True)
            return branches[0]
        return list(reversed(best_left[1:])) + [anchor] + best_right[1:]

    def _trace_branch(self, current: Cell, previous: Cell, local_cells: Set[Cell]) -> List[Cell]:
        queue = deque([current])
        parent: Dict[Cell, Cell] = {current: previous}
        distance: Dict[Cell, int] = {current: 0}
        best = current
        while queue:
            cell = queue.popleft()
            if distance[cell] > distance[best]:
                best = cell
            for neighbor in self._stream_neighbors(cell, local_cells):
                if neighbor == previous or neighbor in distance:
                    continue
                parent[neighbor] = cell
                distance[neighbor] = distance[cell] + 1
                queue.append(neighbor)
        path: List[Cell] = [best]
        while path[-1] != current:
            path.append(parent[path[-1]])
        path.reverse()
        return path[1:] if path and path[0] == previous else path

    def normalize_segment_downstream(self, segment: FlowSegment, downstream_end: Optional[Cell]) -> Cell:
        if downstream_end == segment.start or downstream_end == segment.end:
            return downstream_end
        if downstream_end is None:
            return segment.end
        return segment.end if cell_distance2(downstream_end, segment.end) <= cell_distance2(downstream_end, segment.start) else segment.start

    def oriented_segment_cells(self, segment: FlowSegment, downstream_end: Optional[Cell]) -> List[Cell]:
        downstream = self.normalize_segment_downstream(segment, downstream_end)
        if downstream == segment.start:
            return list(reversed(segment.cells))
        return list(segment.cells)

    def preview_segment_flow(
        self,
        segment: FlowSegment,
        downstream_end: Optional[Cell] = None,
    ) -> List[Tuple[int, int, int]]:
        oriented = self.oriented_segment_cells(segment, downstream_end)
        ops: List[Tuple[int, int, int]] = []
        if len(oriented) < 2:
            return ops
        for (r0, c0), (r1, c1) in zip(oriented[:-1], oriented[1:]):
            code = direction_from_delta(r0, c0, r1, c1)
            if code is None:
                continue
            if self.raster.value_at(r0, c0) != code:
                ops.append((r0, c0, code))
        return ops

    def preview_confirmed_confluence(
        self,
        confirmed_segments: Dict[EdgeKey, Cell],
        inner_radius: int,
        outer_radius: int,
        network: Optional[Dict[str, object]] = None,
    ) -> Tuple[List[Tuple[int, int, int]], Dict[str, object], int, int]:
        if network is None:
            network = self.build_network()
        inner_radius = max(1, clamp(int(inner_radius), 1, 30))
        outer_radius = max(inner_radius, clamp(int(outer_radius), inner_radius, 30))
        edge_map = network.get("edge_map", {})
        if not edge_map:
            return [], network, outer_radius, 0

        seed_mask = np.zeros((self.raster.nrows, self.raster.ncols), dtype=bool)
        seed_count = 0
        for edge_key, downstream_end in confirmed_segments.items():
            edge = edge_map.get(edge_key)
            if not edge:
                continue
            cells = edge.get("cells", [])
            start = edge.get("start")
            end = edge.get("end")
            if not isinstance(start, tuple) or not isinstance(end, tuple) or len(cells) < 2:
                continue
            segment = FlowSegment(edge_key=edge_key, start=start, end=end, cells=list(cells), nearest_cell=downstream_end, nearest_index=0, nearest_distance2=0.0)
            seed_count += 1
            oriented = self.oriented_segment_cells(segment, downstream_end)
            for row, col in oriented:
                if 0 <= row < self.raster.nrows and 0 <= col < self.raster.ncols:
                    seed_mask[row, col] = True

        if not seed_mask.any():
            return [], network, outer_radius, seed_count

        ops = self._preview_confluence_from_seed_mask(seed_mask, inner_radius, outer_radius)
        return ops, network, outer_radius, seed_count

    def preview_locked_skeleton_confluence(
        self,
        locked_segments: List[Tuple[List[Cell], Cell]],
        inner_radius: int,
        outer_radius: int,
    ) -> Tuple[List[Tuple[int, int, int]], int, int]:
        inner_radius = max(1, clamp(int(inner_radius), 1, 30))
        outer_radius = max(inner_radius, clamp(int(outer_radius), inner_radius, 30))
        seed_mask = np.zeros((self.raster.nrows, self.raster.ncols), dtype=bool)
        seed_count = 0
        for cells, downstream_end in locked_segments:
            if len(cells) < 2:
                continue
            segment = FlowSegment(
                edge_key=tuple(sorted((cells[0], cells[-1]))),
                start=cells[0],
                end=cells[-1],
                cells=list(cells),
                nearest_cell=downstream_end,
                nearest_index=0,
                nearest_distance2=0.0,
            )
            oriented = self.oriented_segment_cells(segment, downstream_end)
            added = False
            for row, col in oriented:
                if 0 <= row < self.raster.nrows and 0 <= col < self.raster.ncols:
                    seed_mask[row, col] = True
                    added = True
            if added:
                seed_count += 1
        if not seed_mask.any():
            return [], outer_radius, seed_count
        ops = self._preview_confluence_from_seed_mask(seed_mask, inner_radius, outer_radius)
        return ops, outer_radius, seed_count

    def _preview_confluence_from_seed_mask(
        self,
        seed_mask: np.ndarray,
        inner_radius: int,
        outer_radius: int,
    ) -> List[Tuple[int, int, int]]:
        seed_rows, seed_cols = np.where(seed_mask)
        row0 = max(0, int(seed_rows.min()) - outer_radius - 1)
        row1 = min(self.raster.nrows, int(seed_rows.max()) + outer_radius + 2)
        col0 = max(0, int(seed_cols.min()) - outer_radius - 1)
        col1 = min(self.raster.ncols, int(seed_cols.max()) + outer_radius + 2)
        local_seed_mask = seed_mask[row0:row1, col0:col1]
        dist, indices = ndimage.distance_transform_edt(~local_seed_mask, return_indices=True)
        ops: List[Tuple[int, int, int]] = []
        for row in range(row0, row1):
            local_row = row - row0
            for col in range(col0, col1):
                local_col = col - col0
                if self.raster.value_at(row, col) == NODATA:
                    continue
                if self._is_stream_cell(row, col):
                    continue
                if local_seed_mask[local_row, local_col]:
                    continue
                if dist[local_row, local_col] > outer_radius:
                    continue
                target_local_row, target_local_col = self._buffer_target_cell(
                    local_row,
                    local_col,
                    dist,
                    indices,
                    local_seed_mask,
                    inner_radius,
                    row0,
                    col0,
                )
                if target_local_row is None or target_local_col is None:
                    continue
                target_row = target_local_row + row0
                target_col = target_local_col + col0
                if (target_row, target_col) == (row, col):
                    continue
                code = direction_from_delta(row, col, target_row, target_col)
                if code is None or self.raster.value_at(row, col) == code:
                    continue
                ops.append((row, col, code))
        return ops

    def _buffer_target_cell(
        self,
        row: int,
        col: int,
        dist: np.ndarray,
        indices: np.ndarray,
        seed_mask: np.ndarray,
        inner_radius: int,
        row_offset: int = 0,
        col_offset: int = 0,
    ) -> Tuple[Optional[int], Optional[int]]:
        current_dist = float(dist[row, col])
        if current_dist <= 0.0:
            return None, None
        if current_dist <= float(inner_radius):
            seed_row = int(indices[0, row, col])
            seed_col = int(indices[1, row, col])
            if seed_mask[seed_row, seed_col]:
                return seed_row, seed_col
        best_cell: Optional[Cell] = None
        best_score = current_dist
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if not (0 <= nr < seed_mask.shape[0] and 0 <= nc < seed_mask.shape[1]):
                    continue
                if self.raster.value_at(nr + row_offset, nc + col_offset) == NODATA:
                    continue
                neighbor_dist = float(dist[nr, nc])
                if neighbor_dist < best_score - 1e-6:
                    best_score = neighbor_dist
                    best_cell = (nr, nc)
        if best_cell is not None:
            return best_cell
        seed_row = int(indices[0, row, col])
        seed_col = int(indices[1, row, col])
        if seed_mask[seed_row, seed_col]:
            return seed_row, seed_col
        return None, None

    def preview_network(
        self,
        sources: List[Cell],
        outlets: List[Cell],
        fixed_nodes: List[Cell],
    ) -> Tuple[List[Tuple[int, int, int]], Dict[str, object]]:
        network = self.build_network()
        if not network["edge_map"]:
            return [], network
        outlet_nodes = self.resolve_anchor_nodes(network["nodes"], outlets)
        source_nodes = self.resolve_anchor_nodes(network["nodes"], sources)
        fixed = self.resolve_anchor_nodes(network["nodes"], fixed_nodes)
        if not outlet_nodes:
            return [], network

        downstream_rank = self.multi_source_distances(network["adjacency"], outlet_nodes)
        upstream_rank = self.multi_source_distances(network["adjacency"], source_nodes) if source_nodes else {}
        node_rank: Dict[Cell, int] = {}
        for node in network["nodes"]:
            down = downstream_rank.get(node)
            up = upstream_rank.get(node)
            if down is None and up is None:
                continue
            if down is None:
                node_rank[node] = -int(up or 0)
            elif up is None:
                node_rank[node] = int(down)
            else:
                node_rank[node] = int(down - up)
        for node in fixed:
            node_rank.setdefault(node, 0)

        ops: List[Tuple[int, int, int]] = []
        for edge in network["edge_map"].values():
            start = edge["start"]
            end = edge["end"]
            cells = edge["cells"]
            if len(cells) < 2:
                continue
            sr = node_rank.get(start)
            er = node_rank.get(end)
            if sr is None and er is None:
                continue
            downstream = start
            if sr is None:
                downstream = end
            elif er is None:
                downstream = start
            elif er < sr:
                downstream = end
            elif sr < er:
                downstream = start
            oriented = list(reversed(cells)) if downstream == end else cells
            for (r0, c0), (r1, c1) in zip(oriented[:-1], oriented[1:]):
                code = direction_from_delta(r0, c0, r1, c1)
                if code is None:
                    continue
                if self.raster.value_at(r0, c0) != code:
                    ops.append((r0, c0, code))
        return ops, network

    def preview_confluence(
        self,
        sources: List[Cell],
        outlets: List[Cell],
        fixed_nodes: List[Cell],
        radius: int,
    ) -> Tuple[List[Tuple[int, int, int]], Dict[str, object], int, int]:
        network = self.build_network()
        radius = max(1, clamp(int(radius), 1, 30))
        if not network["edge_map"] or not network["node_to_edges"]:
            return [], network, radius, 0

        seed_edge_keys = self.seed_edges_for_confluence(network, sources, outlets, fixed_nodes)
        if not seed_edge_keys:
            return [], network, radius, 0

        mask = np.zeros((self.raster.nrows, self.raster.ncols), dtype=bool)
        for edge_key in seed_edge_keys:
            for row, col in network["edge_map"][edge_key]["cells"]:
                if 0 <= row < self.raster.nrows and 0 <= col < self.raster.ncols:
                    mask[row, col] = True
        if not mask.any():
            return [], network, radius, len(seed_edge_keys)

        dist, indices = ndimage.distance_transform_edt(~mask, return_indices=True)
        ops: List[Tuple[int, int, int]] = []
        for row in range(self.raster.nrows):
            for col in range(self.raster.ncols):
                if self.raster.value_at(row, col) == NODATA:
                    continue
                if not mask[row, col] and dist[row, col] > radius:
                    continue
                target_row = int(indices[0, row, col])
                target_col = int(indices[1, row, col])
                if (target_row, target_col) == (row, col):
                    continue
                code = direction_from_delta(row, col, target_row, target_col)
                if code is None or self.raster.value_at(row, col) == code:
                    continue
                ops.append((row, col, code))
        return ops, network, radius, len(seed_edge_keys)

    def resolve_anchor_nodes(self, nodes: Set[Cell], anchors: List[Cell]) -> List[Cell]:
        resolved: List[Cell] = []
        for anchor in anchors:
            node = self.find_nearest_network_node(nodes, anchor)
            if node is not None and node not in resolved:
                resolved.append(node)
        return resolved

    def seed_edges_for_confluence(
        self,
        network: Dict[str, object],
        sources: List[Cell],
        outlets: List[Cell],
        fixed_nodes: List[Cell],
    ) -> List[EdgeKey]:
        edge_map = network["edge_map"]
        if not edge_map:
            return []
        anchors = outlets + sources + fixed_nodes
        seed_nodes = self.resolve_anchor_nodes(network["nodes"], anchors)
        if not seed_nodes:
            seed_nodes = [node for node in network["nodes"] if len(network["adjacency"].get(node, [])) <= 1]
        seeds: List[EdgeKey] = []
        seen: Set[EdgeKey] = set()
        for node in seed_nodes:
            for edge_key in network["node_to_edges"].get(node, set()):
                if edge_key in seen or edge_key not in edge_map:
                    continue
                seen.add(edge_key)
                seeds.append(edge_key)
        if not seeds:
            best = sorted(edge_map.items(), key=lambda item: len(item[1]["cells"]), reverse=True)
            seeds = [key for key, _ in best[:1]]
        return seeds

    def multi_source_distances(self, adjacency: Dict[Cell, List[Cell]], sources: List[Cell]) -> Dict[Cell, int]:
        if not sources:
            return {}
        distances: Dict[Cell, int] = {source: 0 for source in sources}
        queue = deque(sources)
        while queue:
            node = queue.popleft()
            base = distances[node]
            for neighbor in adjacency.get(node, []):
                if neighbor in distances:
                    continue
                distances[neighbor] = base + 1
                queue.append(neighbor)
        return distances

    def find_nearest_network_node(self, nodes: Set[Cell], target: Cell) -> Optional[Cell]:
        if not nodes:
            return None
        tr, tc = target
        best_node: Optional[Cell] = None
        best_dist = float("inf")
        for node in nodes:
            dist = float((node[0] - tr) ** 2 + (node[1] - tc) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_node = node
        return best_node

    def _rasterize_vector_line(self, line: List[Tuple[float, float]]) -> List[Cell]:
        cells: List[Cell] = []
        for x, y in line:
            if self.transformer is not None:
                x, y = self.transformer.transform(x, y)
            row, col = self.raster.world_to_rc(x, y)
            cell = (int(round(row)), int(round(col)))
            if not (0 <= cell[0] < self.raster.nrows and 0 <= cell[1] < self.raster.ncols):
                continue
            if not cells or cells[-1] != cell:
                cells.append(cell)
        if len(cells) < 2:
            return []

        dense: List[Cell] = [cells[0]]
        for start, end in zip(cells[:-1], cells[1:]):
            segment = line_cells(start, end)
            if dense and segment and segment[0] == dense[-1]:
                dense.extend(segment[1:])
            else:
                dense.extend(segment)

        compact: List[Cell] = []
        for cell in dense:
            if not compact or compact[-1] != cell:
                compact.append(cell)
        return compact

    def _register_network_edge(
        self,
        cells: List[Cell],
        nodes: Set[Cell],
        adjacency: Dict[Cell, List[Cell]],
        edge_map: Dict[EdgeKey, Dict[str, object]],
        node_to_edges: Dict[Cell, Set[EdgeKey]],
    ) -> None:
        if len(cells) < 2:
            return
        start = cells[0]
        end = cells[-1]
        if start == end:
            return
        edge_key = tuple(sorted((start, end)))
        nodes.add(start)
        nodes.add(end)
        adjacency.setdefault(start, []).append(end)
        adjacency.setdefault(end, []).append(start)
        edge_map[edge_key] = {"start": start, "end": end, "cells": cells}
        node_to_edges.setdefault(start, set()).add(edge_key)
        node_to_edges.setdefault(end, set()).add(edge_key)
