from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from water_core import DIR_COLORS, NODATA, STREAM_VALUE, PolygonLayer, RasterData, VectorLayer

RGBA = Tuple[int, int, int, int]

FLOW_VECTORS = {
    1: (1, 0),
    2: (1, 1),
    4: (0, 1),
    8: (-1, 1),
    16: (-1, 0),
    32: (-1, -1),
    64: (0, -1),
    128: (1, -1),
}


def build_base_image(
    raster: RasterData,
    mode: str,
    stream_palette: Optional[Dict[str, RGBA]] = None,
    flow_palette: Optional[Dict[int, RGBA]] = None,
) -> Image.Image:
    stream_palette = stream_palette or {
        "nodata": (245, 245, 245, 255),
        "river": (31, 119, 180, 255),
        "background": (220, 220, 220, 255),
    }
    flow_palette = flow_palette or DIR_COLORS
    arr = raster.data
    if mode == "stream":
        img = Image.new("RGBA", (raster.ncols, raster.nrows), (255, 255, 255, 255))
        pix = np.array(img)
        nodata = arr == raster.header.nodata
        river = arr == STREAM_VALUE
        pix[nodata] = np.array(stream_palette["nodata"], dtype=np.uint8)
        pix[river] = np.array(stream_palette["river"], dtype=np.uint8)
        pix[(~nodata) & (~river)] = np.array(stream_palette["background"], dtype=np.uint8)
        return Image.fromarray(pix, "RGBA")

    rgba = np.zeros((raster.nrows, raster.ncols, 4), dtype=np.uint8)
    rgba[:, :] = np.array([255, 255, 255, 255], dtype=np.uint8)
    rgba[arr == raster.header.nodata] = np.array([240, 240, 240, 255], dtype=np.uint8)
    for code, color in flow_palette.items():
        if code == NODATA:
            continue
        rgba[arr == code] = np.array(color, dtype=np.uint8)
    unknown = (~np.isin(arr, list(flow_palette.keys()) + [raster.header.nodata]))
    rgba[unknown] = np.array([200, 200, 200, 255], dtype=np.uint8)
    return Image.fromarray(rgba, "RGBA")


def overlay_vector_layer(
    img: Image.Image,
    raster: RasterData,
    vector_layer: Optional[VectorLayer],
    transformer,
    zoom: float,
    vector_color: RGBA = (220, 30, 30, 190),
    view_x: float = 0.0,
    view_y: float = 0.0,
) -> None:
    if not vector_layer:
        return
    draw = ImageDraw.Draw(img)
    width = max(1, int(round(zoom)))
    for line in vector_layer.polylines:
        pts = []
        for x, y in line:
            if transformer is not None:
                x, y = transformer.transform(x, y)
            row, col = raster.world_to_rc(x, y)
            pts.append((col * zoom - view_x, row * zoom - view_y))
        if len(pts) >= 2:
            draw.line(pts, fill=vector_color, width=width)


def overlay_polygon_boundary(
    img: Image.Image,
    raster: RasterData,
    polygon_layer: Optional[PolygonLayer],
    transformer,
    zoom: float,
    color: RGBA = (30, 110, 220, 180),
    line_width: int = 1,
    view_x: float = 0.0,
    view_y: float = 0.0,
) -> None:
    if not polygon_layer:
        return
    draw = ImageDraw.Draw(img)
    width = max(1, int(line_width))
    for boundary in polygon_layer.boundaries:
        pts = []
        for x, y in boundary:
            if transformer is not None:
                x, y = transformer.transform(x, y)
            row, col = raster.world_to_rc(x, y)
            pts.append((col * zoom - view_x, row * zoom - view_y))
        if len(pts) < 2:
            continue
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        draw.line(pts, fill=color, width=width)


def overlay_flow_arrows(
    img: Image.Image,
    raster: RasterData,
    zoom: float,
    arrow_color: RGBA = (40, 40, 40, 220),
    sample_step_cells: Optional[int] = None,
    view_x: float = 0.0,
    view_y: float = 0.0,
) -> None:
    draw = ImageDraw.Draw(img)
    if sample_step_cells is not None:
        step = sample_step_cells
    elif zoom >= 14.0:
        step = 1
    else:
        step = max(2, int(round(26 / max(zoom, 0.15))))
    length = max(4, int(round(0.55 * zoom)))
    head = max(2, int(round(0.22 * zoom)))
    col0 = max(0, int(math.floor(view_x / max(zoom, 0.15))) - 1)
    row0 = max(0, int(math.floor(view_y / max(zoom, 0.15))) - 1)
    col1 = min(raster.ncols, int(math.ceil((view_x + img.size[0]) / max(zoom, 0.15))) + 1)
    row1 = min(raster.nrows, int(math.ceil((view_y + img.size[1]) / max(zoom, 0.15))) + 1)
    start_row = (row0 // step) * step
    start_col = (col0 // step) * step
    for row in range(start_row, row1, step):
        for col in range(start_col, col1, step):
            value = int(raster.data[row, col])
            if value not in FLOW_VECTORS:
                continue
            dx, dy = FLOW_VECTORS[value]
            cx = (col + 0.5) * zoom - view_x
            cy = (row + 0.5) * zoom - view_y
            ex = cx + dx * length
            ey = cy + dy * length
            draw.line((cx, cy, ex, ey), fill=arrow_color, width=max(1, int(round(0.08 * zoom)) or 1))
            _draw_arrow_head(draw, cx, cy, ex, ey, head, arrow_color)


def _draw_arrow_head(draw: ImageDraw.ImageDraw, sx: float, sy: float, ex: float, ey: float, head: int, color: RGBA) -> None:
    ang = math.atan2(ey - sy, ex - sx)
    left = (ex - head * math.cos(ang - math.pi / 6), ey - head * math.sin(ang - math.pi / 6))
    right = (ex - head * math.cos(ang + math.pi / 6), ey - head * math.sin(ang + math.pi / 6))
    draw.line((ex, ey, left[0], left[1]), fill=color, width=1)
    draw.line((ex, ey, right[0], right[1]), fill=color, width=1)


def overlay_grid(
    img: Image.Image,
    raster: RasterData,
    zoom: float,
    grid_step_cells: Optional[int] = None,
    color: RGBA = (180, 180, 180, 70),
    major_color: RGBA = (120, 120, 120, 110),
    view_x: float = 0.0,
    view_y: float = 0.0,
) -> None:
    draw = ImageDraw.Draw(img)
    step = grid_step_cells or max(1, int(round(40 / max(zoom, 0.15))))
    width = 1 if zoom < 4 else 2
    col0 = max(0, int(math.floor(view_x / max(zoom, 0.15))) - 1)
    row0 = max(0, int(math.floor(view_y / max(zoom, 0.15))) - 1)
    col1 = min(raster.ncols + 1, int(math.ceil((view_x + img.size[0]) / max(zoom, 0.15))) + 1)
    row1 = min(raster.nrows + 1, int(math.ceil((view_y + img.size[1]) / max(zoom, 0.15))) + 1)
    start_col = (col0 // step) * step
    start_row = (row0 // step) * step
    for c in range(start_col, col1, step):
        x = c * zoom - view_x
        draw.line((x, 0, x, img.size[1]), fill=major_color if c % (step * 5 or 1) == 0 else color, width=width)
    for r in range(start_row, row1, step):
        y = r * zoom - view_y
        draw.line((0, y, img.size[0], y), fill=major_color if r % (step * 5 or 1) == 0 else color, width=width)


def overlay_scale_bar(
    img: Image.Image,
    raster: RasterData,
    zoom: float,
    color: RGBA = (40, 40, 40, 220),
) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    margin = max(8, int(round(10 * zoom)))
    bar_px = max(60, int(round(min(w, h) * 0.18)))
    bar_px = min(bar_px, max(80, w // 4))
    x0 = margin
    y0 = h - margin - 18
    x1 = x0 + bar_px
    y1 = y0 + 8
    draw.rectangle((x0, y0, x1, y1), outline=color, fill=(255, 255, 255, 130))
    draw.rectangle((x0, y0, x1, y1), outline=color, width=1)
    draw.text((x0, y0 - 14), f"{int(round(bar_px / max(zoom, 0.15)))} cells", fill=color)


def render_viewport_image(
    raster: RasterData,
    mode: str,
    zoom: float,
    view_x: float,
    view_y: float,
    width: int,
    height: int,
    stream_palette: Optional[Dict[str, RGBA]] = None,
    flow_palette: Optional[Dict[int, RGBA]] = None,
    vector_layer: Optional[VectorLayer] = None,
    transformer=None,
    vector_color: RGBA = (220, 30, 30, 190),
    polygon_layer: Optional[PolygonLayer] = None,
    polygon_transformer=None,
    polygon_color: RGBA = (30, 110, 220, 180),
    polygon_line_width: int = 1,
    show_polygon_boundary: bool = True,
    show_grid: bool = False,
    show_scale: bool = True,
    show_flow_arrows: bool = False,
    compare_raster: Optional[RasterData] = None,
) -> Image.Image:
    base, overlay = render_viewport_layers(
        raster,
        mode,
        zoom,
        view_x,
        view_y,
        width,
        height,
        stream_palette=stream_palette,
        flow_palette=flow_palette,
        vector_layer=vector_layer,
        transformer=transformer,
        vector_color=vector_color,
        polygon_layer=polygon_layer,
        polygon_transformer=polygon_transformer,
        polygon_color=polygon_color,
        polygon_line_width=polygon_line_width,
        show_polygon_boundary=show_polygon_boundary,
        show_grid=show_grid,
        show_scale=show_scale,
        show_flow_arrows=show_flow_arrows,
        compare_raster=compare_raster,
    )
    return Image.alpha_composite(base, overlay)


def render_viewport_layers(
    raster: RasterData,
    mode: str,
    zoom: float,
    view_x: float,
    view_y: float,
    width: int,
    height: int,
    stream_palette: Optional[Dict[str, RGBA]] = None,
    flow_palette: Optional[Dict[int, RGBA]] = None,
    vector_layer: Optional[VectorLayer] = None,
    transformer=None,
    vector_color: RGBA = (220, 30, 30, 190),
    polygon_layer: Optional[PolygonLayer] = None,
    polygon_transformer=None,
    polygon_color: RGBA = (30, 110, 220, 180),
    polygon_line_width: int = 1,
    show_polygon_boundary: bool = True,
    show_grid: bool = False,
    show_scale: bool = True,
    show_flow_arrows: bool = False,
    compare_raster: Optional[RasterData] = None,
) -> Tuple[Image.Image, Image.Image]:
    base = _render_viewport_base(raster, mode, zoom, view_x, view_y, width, height, stream_palette, flow_palette)
    if compare_raster is not None:
        compare_base = _render_viewport_base(compare_raster, mode, zoom, view_x, view_y, width, height, stream_palette, flow_palette)
        if compare_base.size == base.size:
            base = Image.blend(base, compare_base, 0.45)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    if show_grid:
        overlay_grid(overlay, raster, zoom, view_x=view_x, view_y=view_y)
    overlay_vector_layer(overlay, raster, vector_layer, transformer, zoom, vector_color, view_x=view_x, view_y=view_y)
    if show_polygon_boundary:
        overlay_polygon_boundary(
            overlay,
            raster,
            polygon_layer,
            polygon_transformer,
            zoom,
            color=polygon_color,
            line_width=polygon_line_width,
            view_x=view_x,
            view_y=view_y,
        )
    if show_flow_arrows and mode == "flow":
        overlay_flow_arrows(overlay, raster, zoom, view_x=view_x, view_y=view_y)
    if show_scale:
        overlay_scale_bar(overlay, raster, zoom)
    return base, overlay


def overlay_selection(
    img: Image.Image,
    raster: RasterData,
    selection: Optional[Tuple[int, int]],
    zoom: float,
    color: RGBA = (30, 160, 60, 220),
    view_x: float = 0.0,
    view_y: float = 0.0,
) -> None:
    if selection is None:
        return
    row, col = selection
    if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
        return
    draw = ImageDraw.Draw(img)
    x0 = col * zoom - view_x
    y0 = row * zoom - view_y
    x1 = (col + 1) * zoom - view_x
    y1 = (row + 1) * zoom - view_y
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=color, width=max(1, int(round(max(1.0, zoom / 6.0)))))


def _render_viewport_base(
    raster: RasterData,
    mode: str,
    zoom: float,
    view_x: float,
    view_y: float,
    width: int,
    height: int,
    stream_palette: Optional[Dict[str, RGBA]],
    flow_palette: Optional[Dict[int, RGBA]],
) -> Image.Image:
    stream_palette = stream_palette or {
        "nodata": (245, 245, 245, 255),
        "river": (31, 119, 180, 255),
        "background": (220, 220, 220, 255),
    }
    flow_palette = flow_palette or DIR_COLORS
    if mode == "stream":
        img = Image.new("RGBA", (width, height), stream_palette["background"])
    else:
        img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    col0 = max(0, int(math.floor(view_x / max(zoom, 0.15))))
    row0 = max(0, int(math.floor(view_y / max(zoom, 0.15))))
    col1 = min(raster.ncols, int(math.ceil((view_x + width) / max(zoom, 0.15))) + 1)
    row1 = min(raster.nrows, int(math.ceil((view_y + height) / max(zoom, 0.15))) + 1)
    for row in range(row0, row1):
        y0 = int(math.floor(row * zoom - view_y))
        y1 = max(y0 + 1, int(math.ceil((row + 1) * zoom - view_y)))
        if y1 < 0 or y0 > height:
            continue
        for col in range(col0, col1):
            x0 = int(math.floor(col * zoom - view_x))
            x1 = max(x0 + 1, int(math.ceil((col + 1) * zoom - view_x)))
            if x1 < 0 or x0 > width:
                continue
            value = raster.value_at(row, col)
            if mode == "stream":
                if value == raster.header.nodata:
                    color = stream_palette["nodata"]
                elif value == STREAM_VALUE:
                    color = stream_palette["river"]
                else:
                    color = stream_palette["background"]
            else:
                if value == raster.header.nodata:
                    color = (240, 240, 240, 255)
                else:
                    color = flow_palette.get(value, (200, 200, 200, 255))
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=color)
    return img
