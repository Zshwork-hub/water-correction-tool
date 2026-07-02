from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np

from water_core import RasterData, parse_asc_header_lines


PathFormatter = Callable[[Path], str]
PathResolver = Callable[[str], Path]


@dataclass
class ProjectReadResult:
    payload: Dict[str, object]
    arrays: Optional[Dict[str, np.ndarray]]
    data_error: Optional[Exception] = None


def empty_raster_array() -> np.ndarray:
    return np.empty((0, 0), dtype=np.int32)


def raster_array(raster: Optional[RasterData]) -> np.ndarray:
    if raster is None:
        return empty_raster_array()
    return np.array(raster.data, dtype=np.int32)


def raster_payload(raster: Optional[RasterData], store_path: PathFormatter) -> Dict[str, object]:
    if raster is None:
        return {}
    return {
        "path": store_path(raster.path),
        "header": raster.header.raw_lines,
        "crs_text": raster.crs_text,
        "shape": [raster.nrows, raster.ncols],
    }


def rebuild_raster(payload: Dict[str, object], data: np.ndarray, resolve_path: PathResolver) -> Optional[RasterData]:
    path_value = payload.get("path")
    header_value = payload.get("header")
    if not isinstance(path_value, str) or not isinstance(header_value, list):
        return None
    header = parse_asc_header_lines([str(line) for line in header_value])
    crs_text = str(payload.get("crs_text", ""))
    return RasterData(resolve_path(path_value), header, data.astype(np.int32), crs_text)


def project_data_path(project_path: Path) -> Path:
    return project_path.with_suffix(project_path.suffix + ".npz")


def write_project_files(
    project_path: Path,
    data_path: Path,
    payload: Dict[str, object],
    stream_raster: Optional[RasterData],
    flow_raster: Optional[RasterData],
    original_stream_raster: Optional[RasterData],
    original_flow_raster: Optional[RasterData],
) -> None:
    np.savez_compressed(
        data_path,
        stream=raster_array(stream_raster),
        flow=raster_array(flow_raster),
        original_stream=raster_array(original_stream_raster),
        original_flow=raster_array(original_flow_raster),
    )
    project_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_project_payload(project_path: Path) -> Dict[str, object]:
    return json.loads(project_path.read_text(encoding="utf-8"))


def read_project_arrays(payload: Dict[str, object], resolve_path: PathResolver) -> ProjectReadResult:
    arrays = None
    data_error = None
    data_path_value = payload.get("data_path")
    if isinstance(data_path_value, str) and data_path_value:
        data_path = resolve_path(data_path_value)
        if data_path.exists():
            try:
                arrays = read_array_file(data_path)
            except Exception as exc:
                data_error = exc
    return ProjectReadResult(payload=payload, arrays=arrays, data_error=data_error)


def read_project_files(project_path: Path, resolve_path: PathResolver) -> ProjectReadResult:
    return read_project_arrays(read_project_payload(project_path), resolve_path)


def read_array_file(path: Path) -> Dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as loaded:
        return {name: np.array(loaded[name], dtype=np.int32) for name in loaded.files}


def write_session_files(
    meta_path: Path,
    data_path: Path,
    meta: Dict[str, object],
    stream_raster: Optional[RasterData],
    flow_raster: Optional[RasterData],
    original_stream_raster: Optional[RasterData],
    original_flow_raster: Optional[RasterData],
) -> None:
    np.savez_compressed(
        data_path,
        stream=raster_array(stream_raster),
        flow=raster_array(flow_raster),
        original_stream=raster_array(original_stream_raster),
        original_flow=raster_array(original_flow_raster),
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def read_session_files(meta_path: Path, data_path: Path) -> Optional[ProjectReadResult]:
    if not (data_path.exists() and meta_path.exists()):
        return None
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    arrays = read_array_file(data_path)
    return ProjectReadResult(payload=payload, arrays=arrays)
