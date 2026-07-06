from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
from pyproj import CRS, Transformer

from .water_core import DIR_OFFSETS, RasterData

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
DEM_CACHE_VERSION = "v1"
DemCacheProgressCallback = Callable[[int, int, int, int], None]
DemCacheCancelChecker = Callable[[], bool]


class DemCacheCancelled(RuntimeError):
    pass


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
    transform: Tuple[float, float, float, float, float, float]
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


@dataclass(frozen=True)
class DemDirectionScore:
    row: int
    col: int
    code: int
    status: str
    severity: str
    current_elevation: Optional[float]
    next_elevation: Optional[float]
    drop: Optional[float]
    reason: str


@dataclass(frozen=True)
class DemCacheBuildResult:
    arrays: Dict[str, np.ndarray]
    metadata: Dict[str, object]
    row_range: Tuple[int, int]
    col_range: Tuple[int, int]
    processed_cells: int
    readable_cells: int
    warning_cells: int
    blocked_cells: int


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
            transform=tuple(float(value) for value in ds.transform[:6]),
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


def build_dem_cache(
    dem_path: Path,
    raster: RasterData,
    row_range: Optional[Tuple[int, int]] = None,
    col_range: Optional[Tuple[int, int]] = None,
    source_crs_text: str = "",
    max_pixels_per_cell: int = DEFAULT_DEM_MAX_PIXELS,
    warning_pixels_per_cell: int = DEFAULT_DEM_WARNING_PIXELS,
    hard_max_pixels_per_cell: int = DEFAULT_DEM_HARD_MAX_PIXELS,
    progress_callback: Optional[DemCacheProgressCallback] = None,
    cancel_checker: Optional[DemCacheCancelChecker] = None,
    progress_interval_cells: int = 100,
) -> DemCacheBuildResult:
    require_rasterio()
    row0, row1 = _normalize_range(row_range, raster.nrows)
    col0, col1 = _normalize_range(col_range, raster.ncols)
    height = row1 - row0
    width = col1 - col0
    arrays = _empty_cache_arrays(height, width)
    raster_crs = source_crs_text or raster.crs_text or "EPSG:4326"
    processed = 0
    readable = 0
    warnings = 0
    blocked = 0
    total_cells = height * width
    progress_interval = max(1, int(progress_interval_cells))
    if progress_callback is not None:
        progress_callback(0, total_cells, 0, 0)
    with rasterio.open(dem_path) as ds:
        if ds.crs is None:
            metadata = build_dem_cache_metadata(dem_path, raster, row0, row1, col0, col1, raster_crs)
            metadata["error"] = "DEM 缺少 CRS"
            return DemCacheBuildResult(arrays, metadata, (row0, row1), (col0, col1), 0, 0, 0, height * width)
        dem_crs_text = ds.crs.to_string()
        for row in range(row0, row1):
            for col in range(col0, col1):
                if cancel_checker is not None and cancel_checker():
                    raise DemCacheCancelled("DEM 缓存生成已取消")
                processed += 1
                local_row = row - row0
                local_col = col - col0
                plan = _plan_dem_window_for_dataset(
                    ds,
                    raster_cell_bounds(raster, row, col),
                    raster_crs,
                    dem_crs_text,
                    max_pixels_per_cell,
                    warning_pixels_per_cell,
                    hard_max_pixels_per_cell,
                )
                arrays["pixel_count"][local_row, local_col] = plan.pixel_count
                arrays["warning"][local_row, local_col] = 1 if plan.warning else 0
                if not plan.readable or plan.window is None:
                    blocked += 1
                    continue
                summary = _summarize_dem_window_from_dataset(ds, plan.window)
                arrays["valid_count"][local_row, local_col] = summary.valid_count
                arrays["nodata_count"][local_row, local_col] = summary.nodata_count
                if summary.valid_count > 0:
                    readable += 1
                    arrays["readable"][local_row, local_col] = 1
                    arrays["min"][local_row, local_col] = float(summary.min_elevation)
                    arrays["max"][local_row, local_col] = float(summary.max_elevation)
                    arrays["mean"][local_row, local_col] = float(summary.mean_elevation)
                    arrays["median"][local_row, local_col] = float(summary.median_elevation)
                if plan.warning:
                    warnings += 1
                if progress_callback is not None and (processed % progress_interval == 0 or processed == total_cells):
                    progress_callback(processed, total_cells, readable, blocked)
    metadata = build_dem_cache_metadata(dem_path, raster, row0, row1, col0, col1, raster_crs)
    metadata["stats"] = {
        "processed_cells": processed,
        "readable_cells": readable,
        "warning_cells": warnings,
        "blocked_cells": blocked,
    }
    return DemCacheBuildResult(arrays, metadata, (row0, row1), (col0, col1), processed, readable, warnings, blocked)


def build_dem_cache_metadata(
    dem_path: Path,
    raster: RasterData,
    row0: int,
    row1: int,
    col0: int,
    col1: int,
    raster_crs_text: str,
) -> Dict[str, object]:
    dem_meta = read_dem_metadata(dem_path)
    stat = Path(dem_path).stat()
    return {
        "version": DEM_CACHE_VERSION,
        "method": "median_min_max_mean_valid_count",
        "dem": {
            "path": str(Path(dem_path).resolve()),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "driver": dem_meta.driver,
            "width": dem_meta.width,
            "height": dem_meta.height,
            "count": dem_meta.count,
            "dtypes": list(dem_meta.dtypes),
            "crs": dem_meta.crs_text,
            "bounds": list(dem_meta.bounds),
            "resolution": list(dem_meta.resolution),
            "transform": list(dem_meta.transform),
            "nodata": dem_meta.nodata,
        },
        "raster": {
            "path": str(raster.path),
            "nrows": raster.nrows,
            "ncols": raster.ncols,
            "xllcorner": raster.header.xllcorner,
            "yllcorner": raster.header.yllcorner,
            "cellsize": raster.header.cellsize,
            "nodata": raster.header.nodata,
            "crs": raster_crs_text,
            "header": list(raster.header.raw_lines),
        },
        "window": {
            "row0": int(row0),
            "row1": int(row1),
            "col0": int(col0),
            "col1": int(col1),
        },
    }


def save_dem_cache(cache_data_path: Path, cache_meta_path: Path, result: DemCacheBuildResult) -> None:
    cache_data_path.parent.mkdir(parents=True, exist_ok=True)
    cache_meta_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_data_path, **result.arrays)
    cache_meta_path.write_text(json.dumps(result.metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dem_cache(cache_data_path: Path, cache_meta_path: Path) -> Tuple[Dict[str, np.ndarray], Dict[str, object]]:
    metadata = json.loads(cache_meta_path.read_text(encoding="utf-8"))
    with np.load(cache_data_path, allow_pickle=False) as loaded:
        arrays = {name: np.array(loaded[name]) for name in loaded.files}
    return arrays, metadata


def dem_cache_matches(
    cache_meta: Dict[str, object],
    dem_path: Path,
    raster: RasterData,
    source_crs_text: str = "",
    row_range: Optional[Tuple[int, int]] = None,
    col_range: Optional[Tuple[int, int]] = None,
) -> bool:
    try:
        row0, row1 = _normalize_range(row_range, raster.nrows)
        col0, col1 = _normalize_range(col_range, raster.ncols)
        expected = build_dem_cache_metadata(
            dem_path,
            raster,
            row0,
            row1,
            col0,
            col1,
            source_crs_text or raster.crs_text or "EPSG:4326",
        )
    except Exception:
        return False
    if cache_meta.get("version") != expected["version"]:
        return False
    if cache_meta.get("method") != expected["method"]:
        return False
    if cache_meta.get("dem") != expected["dem"]:
        return False
    if cache_meta.get("raster") != expected["raster"]:
        return False
    if row_range is not None or col_range is not None:
        return cache_meta.get("window") == expected["window"]
    return True


def score_flow_directions_from_cache(
    arrays: Dict[str, np.ndarray],
    metadata: Dict[str, object],
    flow_ops: Iterable[Tuple[int, int, int]],
    flat_tolerance: float = 1.0,
    mild_uphill_threshold: float = 2.0,
    severe_uphill_threshold: float = 10.0,
) -> List[DemDirectionScore]:
    window = metadata.get("window", {})
    if not isinstance(window, dict):
        raise ValueError("DEM 缓存元数据缺少 window。")
    row0 = int(window.get("row0", 0))
    col0 = int(window.get("col0", 0))
    median = arrays.get("median")
    readable = arrays.get("readable")
    if median is None:
        raise ValueError("DEM 缓存缺少 median 数组。")
    scores: List[DemDirectionScore] = []
    for row, col, code in flow_ops:
        scores.append(
            _score_one_flow_direction(
                median,
                readable,
                row0,
                col0,
                int(row),
                int(col),
                int(code),
                float(flat_tolerance),
                float(mild_uphill_threshold),
                float(severe_uphill_threshold),
            )
        )
    return scores


def summarize_dem_direction_scores(scores: Iterable[DemDirectionScore]) -> Dict[str, int]:
    summary = {
        "downhill": 0,
        "flat": 0,
        "uphill": 0,
        "no_data": 0,
        "uphill_mild": 0,
        "uphill_moderate": 0,
        "uphill_severe": 0,
    }
    for score in scores:
        summary[score.status] = summary.get(score.status, 0) + 1
        if score.status == "uphill" and score.severity:
            key = f"uphill_{score.severity}"
            summary[key] = summary.get(key, 0) + 1
    return summary


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


def _empty_cache_arrays(height: int, width: int) -> Dict[str, np.ndarray]:
    shape = (height, width)
    return {
        "median": np.full(shape, np.nan, dtype=np.float32),
        "min": np.full(shape, np.nan, dtype=np.float32),
        "max": np.full(shape, np.nan, dtype=np.float32),
        "mean": np.full(shape, np.nan, dtype=np.float32),
        "valid_count": np.zeros(shape, dtype=np.int32),
        "nodata_count": np.zeros(shape, dtype=np.int32),
        "pixel_count": np.zeros(shape, dtype=np.int32),
        "readable": np.zeros(shape, dtype=np.uint8),
        "warning": np.zeros(shape, dtype=np.uint8),
    }


def _score_one_flow_direction(
    median: np.ndarray,
    readable: Optional[np.ndarray],
    row0: int,
    col0: int,
    row: int,
    col: int,
    code: int,
    flat_tolerance: float,
    mild_uphill_threshold: float,
    severe_uphill_threshold: float,
) -> DemDirectionScore:
    offset = DIR_OFFSETS.get(code)
    if offset is None:
        return DemDirectionScore(row, col, code, "no_data", "", None, None, None, "无效D8方向")
    current = _cache_elevation_at(median, readable, row0, col0, row, col)
    if current is None:
        return DemDirectionScore(row, col, code, "no_data", "", None, None, None, "当前像元无DEM缓存")
    dr, dc = offset
    next_row = row + dr
    next_col = col + dc
    nxt = _cache_elevation_at(median, readable, row0, col0, next_row, next_col)
    if nxt is None:
        return DemDirectionScore(row, col, code, "no_data", "", current, None, None, "目标像元无DEM缓存")
    drop = current - nxt
    if drop > flat_tolerance:
        return DemDirectionScore(row, col, code, "downhill", "", current, nxt, drop, "方向顺坡")
    if drop < -flat_tolerance:
        uphill_amount = abs(drop)
        severity = _classify_uphill_severity(uphill_amount, mild_uphill_threshold, severe_uphill_threshold)
        return DemDirectionScore(row, col, code, "uphill", severity, current, nxt, drop, "方向逆坡")
    return DemDirectionScore(row, col, code, "flat", "", current, nxt, drop, "高程差接近平坦")


def _classify_uphill_severity(uphill_amount: float, mild_threshold: float, severe_threshold: float) -> str:
    mild = max(0.0, float(mild_threshold))
    severe = max(mild, float(severe_threshold))
    if uphill_amount <= mild:
        return "mild"
    if uphill_amount <= severe:
        return "moderate"
    return "severe"


def _cache_elevation_at(
    median: np.ndarray,
    readable: Optional[np.ndarray],
    row0: int,
    col0: int,
    row: int,
    col: int,
) -> Optional[float]:
    local_row = row - row0
    local_col = col - col0
    if local_row < 0 or local_col < 0 or local_row >= median.shape[0] or local_col >= median.shape[1]:
        return None
    if readable is not None and readable.shape == median.shape and int(readable[local_row, local_col]) == 0:
        return None
    value = float(median[local_row, local_col])
    if not np.isfinite(value):
        return None
    return value


def _normalize_range(value: Optional[Tuple[int, int]], limit: int) -> Tuple[int, int]:
    if value is None:
        return 0, int(limit)
    start, end = value
    start = max(0, min(int(limit), int(start)))
    end = max(start, min(int(limit), int(end)))
    return start, end


def _plan_dem_window_for_dataset(
    ds,
    source_bounds: Bounds,
    source_crs_text: str,
    dem_crs_text: str,
    max_pixels: int,
    warning_pixels: int,
    hard_max_pixels: int,
) -> DemWindowPlan:
    max_pixels = int(max_pixels)
    warning_pixels = int(warning_pixels)
    hard_max_pixels = int(hard_max_pixels)
    effective_max_pixels = min(max_pixels, hard_max_pixels)
    dem_bounds = transform_bounds_to_dem(source_bounds, source_crs_text, dem_crs_text)
    raw_window = from_bounds(*dem_bounds, transform=ds.transform)
    clipped = _clip_window(raw_window.round_offsets().round_lengths(), ds.width, ds.height)
    if clipped is None:
        return DemWindowPlan(source_bounds, dem_bounds, None, 0, max_pixels, warning_pixels, hard_max_pixels, False, False, False, "范围与 DEM 无交集")
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
    return DemWindowPlan(source_bounds, dem_bounds, clipped, pixel_count, max_pixels, warning_pixels, hard_max_pixels, too_large, hard_blocked, warning, reason)


def _summarize_dem_window_from_dataset(ds, window: Window) -> DemWindowSummary:
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
