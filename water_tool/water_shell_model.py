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

STREAM_PAGE_COMMANDS: Tuple[CommandId, ...] = (
    CommandId.APPLY_VECTOR_CORRECTION,
)

STREAM_CONTROL_KEYS: Tuple[str, ...] = (
    "radio_brush_tool",
    "radio_eraser_tool",
    "brush_size_spin",
    "btn_shortcuts",
    "btn_vector_batch",
    "vector_hint",
)

FLOW_CONTROL_KEYS: Tuple[str, ...] = (
    "direction_box",
    "btn_apply_direction",
    "btn_flow_suggest",
    "chk_show_confluence_polygon",
    "btn_lock_polygon_stream",
    "btn_pick_flow_segment",
    "btn_add_locked_cell",
    "btn_remove_locked_region",
    "btn_set_flow_outlet",
    "river_flow_mode_box",
    "btn_preview_river_flow",
    "confluence_mode_box",
    "btn_set_downstream",
    "btn_reverse_segment",
    "btn_preview_segment",
    "btn_confirm_segment",
    "btn_flow_preview",
    "btn_flow_apply",
    "btn_preview_confluence",
    "btn_apply_flow_preview",
    "btn_clear_flow_preview",
    "btn_clear_flow_marks",
    "flow_assist_var",
    "btn_load_dem",
    "btn_build_dem_cache",
    "btn_cancel_dem_cache",
    "btn_evaluate_dem_preview",
    "dem_score_display_box",
    "btn_locate_dem_conflict",
    "btn_export_dem_report",
    "btn_export_dem_conflicts",
)

DISPLAY_CONTROL_KEYS: Tuple[str, ...] = (
    "chk_grid",
    "chk_scale",
    "chk_arrows",
    "chk_compare",
    "btn_stream_palette",
    "btn_flow_palette",
    "btn_vector_color",
    "btn_confluence_polygon_color",
    "btn_assist_palette",
    "btn_reset_palette",
    "preset_combo",
    "btn_load_preset",
    "btn_save_preset",
    "btn_delete_preset",
)

HISTORY_CONTROL_KEYS: Tuple[str, ...] = (
    "snapshot_list",
    "btn_restore_snapshot",
    "btn_snapshot",
    "btn_restore_autosave",
)


@dataclass(frozen=True)
class ShellMetrics:
    navigation_width: int
    context_width: int
    map_width: int
    status_height: int


def navigation_mode(navigation_id: NavigationId, current_mode: str) -> str:
    navigation_id = NavigationId(navigation_id)
    if navigation_id == NavigationId.STREAM:
        return "stream"
    if navigation_id == NavigationId.FLOW:
        return "flow"
    return current_mode


def shell_metrics(width: int, height: int) -> ShellMetrics:
    safe_width = max(1024, int(width))
    navigation_width = 136 if safe_width <= 1366 else 156
    context_width = max(340, min(380, int(safe_width * 0.22)))
    map_width = max(640, safe_width - navigation_width - context_width - 96)
    return ShellMetrics(navigation_width, context_width, map_width, 28)