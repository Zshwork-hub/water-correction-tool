from __future__ import annotations

from typing import List, Sequence, Tuple


def line_cells(start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Return raster cells along a line using linear interpolation."""
    r0, c0 = start
    r1, c1 = end
    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    steps = max(dr, dc)
    if steps == 0:
        return [(r0, c0)]
    cells: List[Tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        row = int(round(r0 + (r1 - r0) * t))
        col = int(round(c0 + (c1 - c0) * t))
        if not cells or cells[-1] != (row, col):
            cells.append((row, col))
    return cells


def brush_cells(
    row: int,
    col: int,
    nrows: int,
    ncols: int,
    radius: int,
) -> List[Tuple[int, int]]:
    cells: List[Tuple[int, int]] = []
    for rr in range(row - radius, row + radius + 1):
        if rr < 0 or rr >= nrows:
            continue
        for cc in range(col - radius, col + radius + 1):
            if cc < 0 or cc >= ncols:
                continue
            if radius <= 0 or (rr - row) ** 2 + (cc - col) ** 2 <= radius ** 2:
                cells.append((rr, cc))
    return cells

