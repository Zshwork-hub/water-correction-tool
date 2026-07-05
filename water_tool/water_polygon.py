from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple


Point = Tuple[float, float]
Ring = Sequence[Point]


def point_in_ring(x: float, y: float, ring: Ring) -> bool:
    """Return True when a point is inside or on a polygon ring."""
    if len(ring) < 3:
        return False
    inside = False
    prev_x, prev_y = ring[-1]
    eps = 1e-12
    for curr_x, curr_y in ring:
        dx = curr_x - prev_x
        dy = curr_y - prev_y
        cross = (x - prev_x) * dy - (y - prev_y) * dx
        on_segment = (
            abs(cross) <= eps
            and min(prev_x, curr_x) - eps <= x <= max(prev_x, curr_x) + eps
            and min(prev_y, curr_y) - eps <= y <= max(prev_y, curr_y) + eps
        )
        if on_segment:
            return True
        if (curr_y > y) != (prev_y > y):
            x_at_y = (prev_x - curr_x) * (y - curr_y) / (prev_y - curr_y) + curr_x
            if x <= x_at_y:
                inside = not inside
        prev_x, prev_y = curr_x, curr_y
    return inside


def point_in_any_ring(x: float, y: float, rings: Iterable[Ring]) -> bool:
    return any(point_in_ring(x, y, ring) for ring in rings)


def rings_bounds(rings: Iterable[Ring]) -> Optional[Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    for ring in rings:
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)
