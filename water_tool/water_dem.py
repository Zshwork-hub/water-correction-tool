from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
from pyproj import CRS, Transformer

from .water_core import RasterData

try:
    import rasterio
    from rasterio.windows import Window, from_bounds
except Exception:  # pragma: no cover - rasterio is optional until V2.3 UI integration
    rasterio = None
    Window = object  # type: ignore
    from_bounds = None


Bounds = Tuple[float, float, float, float]

DEFAULT_DEM_WARNING_PIXELS = 5_000_000
DEFAULT_DEM_MAX_PIXELS = 30_000_000
DEFAULT_DEM_HARD_MAX_PIXELS = 100_000_000


@dataclass(frozen=True)
class DemMetadata:
    path: Path
    driver: str
    width: int
    height: int
    count: int
    dtypes: Tuple[str, ...]
    crs_text: str
    bounds: Bounds
    resolution: Tuple[float, float]
    nodata: Optional[float]
    overviews: Tuple[int, ...]


@dataclass(frozen=True)
class DemWindowPlan:
    source_bounds: Bounds
    dem_bounds: Bounds
    window: Optional[Window]
    pixel_count: int
    max_pixels: int
    warning_pixels: int
    hard_max_pixels: int
    too_large: bool
    hard_blocked: bool
    warning: bool
    reason: str = ""

    @property
    def readable(self) -> bool:
        return self.window is not None and not self.too_large and not self.hard_blocked and self.pixel_count > 0


@dataclass(frozen=True)
class DemWindowSummary:
    pixel_count: int
    valid_count: int
    nodata_count: int
    min_elevation: Optional[float]
    max_elevation: Optional[float]
    mean_elevation: Optional[float]
    median_elevation: Optional[float]


@dataclass(frozen=True)
class DemCellSummary:
    row: int
    col: int
    source_bounds: Bounds
    readable: bool
    warning: bool
    reason: str
    pixel_count: int
    valid_count: int
    nodata_count: int
    min_elevation: Optional[float]
    max_elevation: Optional[float]
    mean_elevation: Optional[float]
    median_elevation: Optional[float]


def require_rasterio() -> None:
    if rasterio is None or from_bounds is None:
        raise RuntimeError("V2.3 DEM 辅助需要安装 rasterio。")


def read_dem_metadata(path: Path) -> DemMetadata:
    require_rasterio()
    with rasterio.open(path) as ds:
        return DemMetadata(
            path=Path(path),
            driver=ds.driver,
            width=ds.width,
            height=ds.height,
            count=ds.count,
            dtypes=tuple(str(dtype) for dtype in ds.dtypes),
            crs_text=ds.crs.to_string() if ds.crs is not None else "",
            bounds=(ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top),
            resolution=(abs(float(ds.res[0])), abs(float(ds.res[1]))),
            nodata=None if ds.nodata is None else float(ds.nodata),
            overviews=tuple(int(value) for value in ds.overviews(1)) if ds.count else (),
        )


def transform_bounds_to_dem(
    source_bounds: Bounds,
    source_crs_text: str,
    dem_crs_text: str,
    samples_per_edge: int = 8,
) -> Bounds:
    source_crs = CRS.from_user_input(source_crs_text or "EPSG:4326")
    dem_crs = CRS.from_user_input(dem_crs_text)
    transformer = Transformer.from_crs(source_crs, dem_crs, always_xy=True)
    min_x, min_y, max_x, max_y = source_bounds
    samples = max(2, int(samples_per_edge))
    xs: List[float] = []
    ys: List[float] = []
    for idx in range(samples):
        ratio = idx / (samples - 1)
        x = min_x + (max_x - min_x) * ratio
        y = min_y + (max_y - min_y) * ratio
        xs.extend([x, x, min_x, max_x])
        ys.extend([min_y, max_y, y, y])
    tx, ty = transformer.transform(xs, ys)
    return min(tx), min(ty), max(tx), max(ty)


def plan_dem_window(
    dem_path: Path,
    source_bounds: Bounds,
    source_crs_text: str = "EPSG:4326",
    max_pixels: int = DEFAULT_DEM_MAX_PIXELS,
    warning_pixels: int = DEFAULT_DEM_WARNING_PIXELS,
    hard_max_pixels: int = DEFAULT_DEM_HARD_MAX_PIXELS,
    buffer_dem_pixels: int = 0,
) -> DemWindowPlan:
    require_rasterio()
    max_pixels = int(max_pixels)
    warning_pixels = int(warning_pixels)
    hard_max_pixels = int(hard_max_pixels)
    effective_max_pixels = min(max_pixels, hard_max_pixels)
    with rasterio.open(dem_path) as ds:
        if ds.crs is None:
            return DemWindowPlan(
                source_bounds,
                source_bounds,
                None,
                0,
                max_pixels,
                warning_pixels,
                hard_max_pixels,
                True,
                False,
                False,
                "DEM 缺少 CRS",
            )
        dem_bounds = transform_bounds_to_dem(source_bounds, source_crs_text, ds.crs.to_string())
        raw_window = from_bounds(*dem_bounds, transform=ds.transform)
        window = _round_and_buffer_window(raw_window, int(buffer_dem_pixels))
        clipped = _clip_window(window, ds.width, ds.height)
        if clipped is None:
            return DemWindowPlan(
                source_bounds,
                dem_bounds,
                None,
                0,
                max_pixels,
                warning_pixels,
                hard_max_pixels,
                False,
                False,
                False,
                "范围与 DEM 无交集",
            )
        pixel_count = int(math.ceil(clipped.width) * math.ceil(clipped.height))
        hard_blocked = pixel_count > hard_max_pixels
        too_large = pixel_count > effective_max_pixels
        warning = warning_pixels > 0 and pixel_count > warning_pixels and not too_large and not hard_blocked
        if hard_blocked:
            reason = f"DEM window 像元 {pixel_count} 超过硬上限 {hard_max_pixels}"
        elif too_large:
            reason = f"DEM window 像元 {pixel_count} 超过当前上限 {effective_max_pixels}"
        elif warning:
            reason = f"DEM window 像元 {pixel_count} 超过提示阈值 {warning_pixels}，建议确认后读取"
        else:
            reason = ""
        return DemWindowPlan(
            source_bounds,
            dem_bounds,
            clipped,
            pixel_count,
            max_pixels,
            warning_pixels,
            hard_max_pixels,
            too_large,
            hard_blocked,
            warning,
            reason,
        )


def summarize_dem_window(dem_path: Path, window: Window) -> DemWindowSummary:
    require_rasterio()
    with rasterio.open(dem_path) as ds:
        data = ds.read(1, window=window, masked=True)
        compressed = data.compressed()
        valid_count = int(compressed.size)
        pixel_count = int(data.size)
        nodata_count = pixel_count - valid_count
        if valid_count == 0:
            return DemWindowSummary(pixel_count, 0, nodata_count, None, None, None, None)
        values = compressed.astype(np.float64, copy=False)
        return DemWindowSummary(
            pixel_count=pixel_count,
            valid_count=valid_count,
            nodata_count=nodata_count,
            min_elevation=float(values.min()),
            max_elevation=float(values.max()),
            mean_elevation=float(values.mean()),
            median_elevation=float(np.median(values)),
        )


def raster_cell_bounds(raster: RasterData, row: int, col: int) -> Bounds:
    cellsize = raster.header.cellsize
    min_x = raster.header.xllcorner + col * cellsize
    max_x = raster.header.xllcorner + (col + 1) * cellsize
    max_y = raster.header.ymax - row * cellsize
    min_y = raster.header.ymax - (row + 1) * cellsize
    return min_x, min_y, max_x, max_y


def summarize_dem_for_raster_cells(
    dem_path: Path,
    raster: RasterData,
    cells: Iterable[Tuple[int, int]],
    source_crs_text: str = "",
    max_pixels_per_cell: int = DEFAULT_DEM_MAX_PIXELS,
    warning_pixels_per_cell: int = DEFAULT_DEM_WARNING_PIXELS,
    hard_max_pixels_per_cell: int = DEFAULT_DEM_HARD_MAX_PIXELS,
) -> List[DemCellSummary]:
    summaries: List[DemCellSummary] = []
    raster_crs = source_crs_text or raster.crs_text or "EPSG:4326"
    for row, col in cells:
        bounds = raster_cell_bounds(raster, row, col)
        if not (0 <= row < raster.nrows and 0 <= col < raster.ncols):
            summaries.append(_empty_cell_summary(row, col, bounds, "像元超出栅格范围"))
            continue
        plan = plan_dem_window(
            dem_path,
            bounds,
            raster_crs,
            max_pixels=max_pixels_per_cell,
            warning_pixels=warning_pixels_per_cell,
            hard_max_pixels=hard_max_pixels_per_cell,
        )
        if not plan.readable or plan.window is None:
            summaries.append(_empty_cell_summary(row, col, bounds, plan.reason, warning=plan.warning, pixel_count=plan.pixel_count))
            continue
        window_summary = summarize_dem_window(dem_path, plan.window)
        summaries.append(
            DemCellSummary(
                row=row,
                col=col,
                source_bounds=bounds,
                readable=True,
                warning=plan.warning,
                reason=plan.reason,
                pixel_count=window_summary.pixel_count,
                valid_count=window_summary.valid_count,
                nodata_count=window_summary.nodata_count,
                min_elevation=window_summary.min_elevation,
                max_elevation=window_summary.max_elevation,
                mean_elevation=window_summary.mean_elevation,
                median_elevation=window_summary.median_elevation,
            )
        )
    return summaries


def _empty_cell_summary(
    row: int,
    col: int,
    bounds: Bounds,
    reason: str,
    warning: bool = False,
    pixel_count: int = 0,
) -> DemCellSummary:
    return DemCellSummary(
        row=row,
        col=col,
        source_bounds=bounds,
        readable=False,
        warning=warning,
        reason=reason,
        pixel_count=pixel_count,
        valid_count=0,
        nodata_count=0,
        min_elevation=None,
        max_elevation=None,
        mean_elevation=None,
        median_elevation=None,
    )


def _round_and_buffer_window(window: Window, buffer_pixels: int) -> Window:
    rounded = window.round_offsets().round_lengths()
    if buffer_pixels <= 0:
        return rounded
    return Window(
        rounded.col_off - buffer_pixels,
        rounded.row_off - buffer_pixels,
        rounded.width + buffer_pixels * 2,
        rounded.height + buffer_pixels * 2,
    )


def _clip_window(window: Window, width: int, height: int) -> Optional[Window]:
    col0 = max(0, int(math.floor(window.col_off)))
    row0 = max(0, int(math.floor(window.row_off)))
    col1 = min(width, int(math.ceil(window.col_off + window.width)))
    row1 = min(height, int(math.ceil(window.row_off + window.height)))
    if col0 >= col1 or row0 >= row1:
        return None
    return Window(col0, row0, col1 - col0, row1 - row0)
