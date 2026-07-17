from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Dict, Mapping, Optional

from .water_ui_commands import CommandId


class FlowAssistStage(str, Enum):
    DATA = "data"
    OBJECTS = "objects"
    DIRECTION = "direction"
    REVIEW = "review"


@dataclass(frozen=True)
class FlowAssistFacts:
    has_stream: bool = False
    has_flow: bool = False
    has_selected_cell: bool = False
    has_selected_region: bool = False
    selection_in_locked: bool = False
    locked_count: int = 0
    outlet_set: bool = False
    preview_target: str = "river"
    preview_exists: bool = False
    preview_changes: int = 0
    dem_cache_ready: bool = False
    dem_running: bool = False
    dem_scores_ready: bool = False
    dem_conflicts: int = 0


@dataclass(frozen=True)
class FlowAssistViewState:
    stage: FlowAssistStage
    primary_command: Optional[CommandId]
    enabled: Mapping[CommandId, bool]
    summary: str


def derive_flow_assist_state(facts: FlowAssistFacts) -> FlowAssistViewState:
    has_data = facts.has_stream and facts.has_flow
    locked_ready = facts.locked_count > 0
    has_selection = facts.has_selected_cell or facts.has_selected_region
    can_generate = locked_ready and (
        facts.preview_target == "confluence" or facts.outlet_set
    )

    enabled_values: Dict[CommandId, bool] = {
        CommandId.ADD_SELECTED_RIVERS: has_data and has_selection,
        CommandId.ADD_SELECTED_CELL: has_data and facts.has_selected_cell,
        CommandId.REMOVE_SELECTED_RIVERS: locked_ready and has_selection,
        CommandId.RESET_FLOW_ASSIST: locked_ready or facts.preview_exists,
        CommandId.SET_DOWNSTREAM_OUTLET: locked_ready and facts.selection_in_locked,
        CommandId.GENERATE_FLOW_PREVIEW: can_generate,
        CommandId.APPLY_FLOW_PREVIEW: facts.preview_exists and facts.preview_changes > 0,
        CommandId.CLEAR_FLOW_PREVIEW: facts.preview_exists,
        CommandId.BUILD_DEM_CACHE: locked_ready and not facts.dem_running,
        CommandId.CANCEL_DEM_CACHE: facts.dem_running,
        CommandId.EVALUATE_DEM_PREVIEW: (
            facts.preview_exists and facts.dem_cache_ready and not facts.dem_running
        ),
        CommandId.LOCATE_NEXT_UPHILL: facts.dem_conflicts > 0,
        CommandId.EXPORT_DEM_REPORT: facts.dem_scores_ready,
        CommandId.EXPORT_UPHILL_CONFLICTS: facts.dem_conflicts > 0,
    }
    enabled = MappingProxyType(enabled_values)

    if not has_data:
        stage = FlowAssistStage.DATA
        primary_command = None
        summary = "需要加载河道 ASC 和流向 ASC"
    elif not locked_ready:
        stage = FlowAssistStage.OBJECTS
        primary_command = CommandId.ADD_SELECTED_RIVERS if has_selection else None
        summary = "尚未确定订正对象"
    elif facts.preview_exists:
        stage = FlowAssistStage.REVIEW
        primary_command = (
            CommandId.APPLY_FLOW_PREVIEW
            if facts.preview_changes > 0
            else CommandId.CLEAR_FLOW_PREVIEW
        )
        summary = f"预览待修改 {facts.preview_changes}"
        if facts.dem_conflicts > 0:
            summary += f"，逆坡冲突 {facts.dem_conflicts}"
    elif facts.preview_target == "river" and not facts.outlet_set:
        stage = FlowAssistStage.DIRECTION
        primary_command = CommandId.SET_DOWNSTREAM_OUTLET
        summary = "需要设置下游出口"
    else:
        stage = FlowAssistStage.DIRECTION
        primary_command = CommandId.GENERATE_FLOW_PREVIEW
        summary = "可以生成方向预览"

    return FlowAssistViewState(stage, primary_command, enabled, summary)
