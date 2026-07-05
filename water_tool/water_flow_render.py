from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from .water_core import DIR_OFFSETS, RasterData
from .water_flow_assist import FlowSegment
from .water_render import overlay_selection


RGBA = Tuple[int, int, int, int]


class FlowRenderMixin:
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
        preview = self.flow_preview_state
        if not preview.has_preview():
            return
        draw = ImageDraw.Draw(overlay)
        for row, col, code in preview.unchanged_ops:
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
        for row, col, code in preview.ops:
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
