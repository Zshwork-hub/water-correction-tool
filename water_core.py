from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from pyproj import CRS, Transformer
except Exception:  # pragma: no cover - optional dependency
    CRS = None
    Transformer = None


NODATA = -9999
STREAM_VALUE = 1

DIR_CODES = {
    1: "东",
    2: "东南",
    4: "南",
    8: "西南",
    16: "西",
    32: "西北",
    64: "北",
    128: "东北",
}

DIR_ORDER = [1, 2, 4, 8, 16, 32, 64, 128]

DIR_OFFSETS = {
    1: (0, 1),
    2: (1, 1),
    4: (1, 0),
    8: (1, -1),
    16: (0, -1),
    32: (-1, -1),
    64: (-1, 0),
    128: (-1, 1),
}

OPPOSITE_DIR = {
    1: 16,
    2: 32,
    4: 64,
    8: 128,
    16: 1,
    32: 2,
    64: 4,
    128: 8,
}

DIR_COLORS = {
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


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def resolve_relative_or_absolute(stored: str, root: Path) -> Path:
    path = Path(stored)
    if path.is_absolute():
        return path
    return (root / path).resolve()


@dataclass
class AscHeader:
    raw_lines: List[str]
    values: Dict[str, float]

    @property
    def ncols(self) -> int:
        return int(self.values["ncols"])

    @property
    def nrows(self) -> int:
        return int(self.values["nrows"])

    @property
    def xllcorner(self) -> float:
        return float(self.values["xllcorner"])

    @property
    def yllcorner(self) -> float:
        return float(self.values["yllcorner"])

    @property
    def cellsize(self) -> float:
        return float(self.values["cellsize"])

    @property
    def nodata(self) -> int:
        return int(self.values["nodata_value"])

    @property
    def ymax(self) -> float:
        return self.yllcorner + self.nrows * self.cellsize


@dataclass
class RasterData:
    path: Path
    header: AscHeader
    data: np.ndarray
    crs_text: str = ""

    def copy(self) -> "RasterData":
        return RasterData(self.path, self.header, self.data.copy(), self.crs_text)

    @property
    def nrows(self) -> int:
        return self.header.nrows

    @property
    def ncols(self) -> int:
        return self.header.ncols

    def world_to_rc(self, x: float, y: float) -> Tuple[float, float]:
        col = (x - self.header.xllcorner) / self.header.cellsize
        row = (self.header.ymax - y) / self.header.cellsize
        return row, col

    def rc_to_world(self, row: float, col: float) -> Tuple[float, float]:
        x = self.header.xllcorner + (col + 0.5) * self.header.cellsize
        y = self.header.ymax - (row + 0.5) * self.header.cellsize
        return x, y

    def value_at(self, row: int, col: int) -> int:
        return int(self.data[row, col])

    def set_value(self, row: int, col: int, value: int) -> int:
        old = int(self.data[row, col])
        self.data[row, col] = value
        return old


@dataclass
class VectorLayer:
    path: Path
    polylines: List[List[Tuple[float, float]]]
    bounds: Tuple[float, float, float, float]
    crs_text: str = ""


@dataclass
class PolygonLayer:
    path: Path
    boundaries: List[List[Tuple[float, float]]]
    bounds: Tuple[float, float, float, float]
    crs_text: str = ""


@dataclass
class ChangeOp:
    row: int
    col: int
    old: int
    new: int


@dataclass
class ChangeBatch:
    mode: str
    tool: str
    note: str
    ops: List[ChangeOp] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def add(self, row: int, col: int, old: int, new: int) -> None:
        self.ops.append(ChangeOp(row, col, old, new))

    def apply(self, raster: RasterData) -> None:
        for op in self.ops:
            raster.data[op.row, op.col] = op.new

    def undo(self, raster: RasterData) -> None:
        for op in reversed(self.ops):
            raster.data[op.row, op.col] = op.old


def parse_asc(path: Path) -> RasterData:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        raw_lines = [f.readline() for _ in range(6)]
        if any(not line for line in raw_lines):
            raise ValueError(f"ASC header incomplete: {path}")

    header = parse_asc_header_lines(raw_lines, source=path)

    data = np.loadtxt(path, skiprows=6, dtype=np.int32)
    data = np.atleast_2d(data)
    if data.shape != (header.nrows, header.ncols):
        raise ValueError(
            f"ASC shape mismatch in {path}: got {data.shape}, expected "
            f"({header.nrows}, {header.ncols})"
        )
    return RasterData(path=path, header=header, data=data, crs_text=read_prj_text(path))


def parse_asc_header_lines(raw_lines: List[str], source: Optional[Path] = None) -> AscHeader:
    values: Dict[str, float] = {}
    for line in raw_lines:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        value = parts[-1]
        if key == "nodata_value":
            key = "nodata_value"
        try:
            values[key] = float(value)
        except ValueError as exc:
            if source is not None:
                raise ValueError(f"Invalid ASC header value in {source}: {line.strip()}") from exc
            raise ValueError(f"Invalid ASC header value: {line.strip()}") from exc

    required = ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "nodata_value"]
    missing = [k for k in required if k not in values]
    if missing:
        if source is not None:
            raise ValueError(f"Missing ASC header keys in {source}: {missing}")
        raise ValueError(f"Missing ASC header keys: {missing}")
    return AscHeader(raw_lines=list(raw_lines), values=values)


def write_asc(path: Path, raster: RasterData) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for line in raster.header.raw_lines:
            if line.endswith("\n"):
                f.write(line)
            else:
                f.write(line + "\n")
        np.savetxt(f, raster.data, fmt="%d", delimiter=" ")


def read_prj_text(path: Path) -> str:
    prj = path.with_suffix(".prj")
    if prj.exists():
        return prj.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def parse_shapefile_lines(path: Path) -> VectorLayer:
    with path.open("rb") as f:
        header = f.read(100)
        if len(header) != 100:
            raise ValueError(f"Invalid SHP header: {path}")

        file_code = struct.unpack(">i", header[0:4])[0]
        shp_type = struct.unpack("<i", header[32:36])[0]
        if file_code != 9994:
            raise ValueError(f"Invalid SHP file code: {path}")

        if shp_type not in {3, 5, 13, 23, 25, 31}:
            raise ValueError(f"Unsupported shapefile type {shp_type} in {path}")

        polylines: List[List[Tuple[float, float]]] = []
        all_x: List[float] = []
        all_y: List[float] = []

        while True:
            rec_hdr = f.read(8)
            if len(rec_hdr) < 8:
                break
            _, rec_len = struct.unpack(">2i", rec_hdr)
            rec = f.read(rec_len * 2)
            if len(rec) < 4:
                break
            rec_type = struct.unpack("<i", rec[:4])[0]
            if rec_type == 0 or rec_type not in {3, 5, 13, 23, 25, 31}:
                continue

            offset = 4 + 32
            num_parts, num_points = struct.unpack("<2i", rec[offset:offset + 8])
            offset += 8
            parts = list(struct.unpack(f"<{num_parts}i", rec[offset:offset + 4 * num_parts])) if num_parts else [0]
            offset += 4 * num_parts
            points = struct.unpack(f"<{num_points * 2}d", rec[offset:offset + 16 * num_points])
            coords = [(points[i], points[i + 1]) for i in range(0, len(points), 2)]
            parts.append(num_points)
            for i in range(num_parts if num_parts else 1):
                start = parts[i]
                end = parts[i + 1]
                line = coords[start:end]
                if len(line) >= 2:
                    polylines.append(line)
                    for x, y in line:
                        all_x.append(x)
                        all_y.append(y)

        if not polylines:
            raise ValueError(f"No line features found in {path}")

        bounds = (min(all_x), min(all_y), max(all_x), max(all_y))
        return VectorLayer(path=path, polylines=polylines, bounds=bounds, crs_text=read_prj_text(path))


def parse_shapefile_polygon(path: Path) -> PolygonLayer:
    with path.open("rb") as f:
        header = f.read(100)
        if len(header) != 100:
            raise ValueError(f"Invalid SHP header: {path}")

        file_code = struct.unpack(">i", header[0:4])[0]
        shp_type = struct.unpack("<i", header[32:36])[0]
        if file_code != 9994:
            raise ValueError(f"Invalid SHP file code: {path}")
        if shp_type not in {5, 15, 25}:
            raise ValueError(f"Unsupported polygon shapefile type {shp_type} in {path}")

        boundaries: List[List[Tuple[float, float]]] = []
        all_x: List[float] = []
        all_y: List[float] = []
        while True:
            rec_hdr = f.read(8)
            if len(rec_hdr) < 8:
                break
            _, rec_len = struct.unpack(">2i", rec_hdr)
            rec = f.read(rec_len * 2)
            if len(rec) < 4:
                break
            rec_type = struct.unpack("<i", rec[:4])[0]
            if rec_type == 0:
                continue
            if rec_type not in {5, 15, 25}:
                raise ValueError(f"Unsupported polygon record type {rec_type} in {path}")

            offset = 4 + 32
            num_parts, num_points = struct.unpack("<2i", rec[offset:offset + 8])
            offset += 8
            parts = list(struct.unpack(f"<{num_parts}i", rec[offset:offset + 4 * num_parts])) if num_parts else [0]
            offset += 4 * num_parts
            points = struct.unpack(f"<{num_points * 2}d", rec[offset:offset + 16 * num_points])
            coords = [(points[i], points[i + 1]) for i in range(0, len(points), 2)]
            parts.append(num_points)
            for i in range(num_parts if num_parts else 1):
                start = parts[i]
                end = parts[i + 1]
                ring = coords[start:end]
                if len(ring) < 3:
                    continue
                boundaries.append(ring)
                for x, y in ring:
                    all_x.append(x)
                    all_y.append(y)

        if not boundaries:
            raise ValueError(f"No polygon features found in {path}")
        bounds = (min(all_x), min(all_y), max(all_x), max(all_y))
        return PolygonLayer(path=path, boundaries=boundaries, bounds=bounds, crs_text=read_prj_text(path))


def fmt_value(value: int) -> str:
    if value == NODATA:
        return "NODATA(-9999)"
    if value in DIR_CODES:
        return f"{value}({DIR_CODES[value]})"
    return str(value)


def direction_text(value: int) -> str:
    return DIR_CODES.get(value, "未知") if value != NODATA else "NODATA"


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))
