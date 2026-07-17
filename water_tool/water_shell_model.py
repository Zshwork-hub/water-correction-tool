from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from .water_ui_commands import CommandId


class NavigationId(str, Enum):
    STREAM = "stream"
    FLOW = "flow"
    DISPLAY = "display"
    HISTORY = "history"


@dataclass(frozen=True)
class NavigationItem:
    navigation_id: NavigationId
    label: str


NAV_ITEMS: Tuple[NavigationItem, ...] = (
    NavigationItem(NavigationId.STREAM, "河道订正"),
    NavigationItem(NavigationId.FLOW, "流向订正"),
    NavigationItem(NavigationId.DISPLAY, "显示与配色"),
    NavigationItem(NavigationId.HISTORY, "历史与恢复"),
)


@dataclass(frozen=True)
class ProjectDataItem:
    key: str
    label: str
    command_id: CommandId


PROJECT_DATA_ITEMS: Tuple[ProjectDataItem, ...] = (
    ProjectDataItem("stream", "河道 ASC", CommandId.LOAD_STREAM_ASC),
    ProjectDataItem("flow", "流向 ASC", CommandId.LOAD_FLOW_ASC),
    ProjectDataItem("river", "河流线 SHP", CommandId.LOAD_RIVER_SHP),
    ProjectDataItem("confluence", "汇流范围 SHP", CommandId.LOAD_CONFLUENCE_SHP),
    ProjectDataItem("dem", "DEM", CommandId.LOAD_DEM),
)


@dataclass(frozen=True)
class ShellMetrics:
    navigation_width: int
    context_width: int
    map_width: int
    status_height: int


def shell_metrics(width: int, height: int) -> ShellMetrics:
    safe_width = max(1024, int(width))
    navigation_width = 136 if safe_width <= 1366 else 156
    context_width = max(340, min(380, int(safe_width * 0.22)))
    map_width = max(640, safe_width - navigation_width - context_width - 96)
    return ShellMetrics(navigation_width, context_width, map_width, 28)