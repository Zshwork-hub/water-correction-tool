from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


FlowCell = Tuple[int, int]
FlowOp = Tuple[int, int, int]
FlowSegmentKey = Tuple[FlowCell, FlowCell]


@dataclass
class FlowPreviewState:
    ops: List[FlowOp] = field(default_factory=list)
    unchanged_ops: List[FlowOp] = field(default_factory=list)
    label: str = ""
    kind: str = ""
    segment_key: Optional[FlowSegmentKey] = None
    apply_tool: str = ""
    apply_note: str = ""
    dem_score_status: Dict[FlowCell, str] = field(default_factory=dict)
    dem_score_summary: Dict[str, int] = field(default_factory=dict)
    dem_score_label: str = ""
    dem_score_details: List[Any] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        ops: List[FlowOp],
        unchanged_ops: Optional[List[FlowOp]] = None,
        label: str = "",
        kind: str = "",
        segment_key: Optional[FlowSegmentKey] = None,
    ) -> "FlowPreviewState":
        state = cls(
            ops=list(ops),
            unchanged_ops=list(unchanged_ops or []),
            label=label,
            kind=kind,
            segment_key=segment_key,
        )
        state.apply_tool = state.default_apply_tool()
        state.apply_note = state.default_apply_note()
        return state

    @property
    def change_count(self) -> int:
        return len(self.ops)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged_ops)

    def has_apply_ops(self) -> bool:
        return bool(self.kind and self.ops)

    def has_preview(self) -> bool:
        return bool(self.kind and (self.ops or self.unchanged_ops))

    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.kind == "river_skeleton":
            return "河道本体流向"
        if self.kind == "confluence":
            return "周边汇流"
        if self.kind == "segment":
            return "河段预览"
        return "流向预览"

    def status_label(self) -> str:
        if self.kind == "river_skeleton":
            return "河道流向预览"
        if self.kind == "confluence":
            return "周边汇流预览"
        if self.kind == "segment":
            return "河段预览"
        return self.display_label()

    def assist_label(self) -> str:
        if self.kind in {"river_skeleton", "segment"}:
            return "河道预览"
        if self.kind == "confluence":
            return "周边预览"
        return "流向预览"

    def apply_button_text(self) -> str:
        if self.kind in {"river_skeleton", "segment"}:
            return "应用河道流向"
        if self.kind == "confluence":
            return "应用周边汇流"
        return "应用预览"

    def default_apply_tool(self) -> str:
        if self.kind in {"river_skeleton", "segment"}:
            return "river_skeleton"
        return "manual_assist"

    def default_apply_note(self) -> str:
        if self.kind == "river_skeleton":
            return "locked river skeleton flow"
        if self.kind == "confluence":
            return "manual confluence flow preview"
        if self.kind == "segment":
            return "manual segment flow preview"
        return "manual flow assist preview"

    def applied_message(self, count: int) -> str:
        if self.kind == "river_skeleton":
            return f"已应用河道本体流向预览，修改 {count} 个河道像元；已切换到订正流向模式"
        if self.kind == "segment":
            return f"已应用河段流向预览，修改 {count} 个像元；已切换到订正流向模式"
        return f"已应用周边汇流预览，修改 {count} 个像元；已切换到订正流向模式"


class FlowStateMixin:
    @property
    def flow_preview_ops(self) -> List[FlowOp]:
        return self.flow_preview_state.ops

    @flow_preview_ops.setter
    def flow_preview_ops(self, value: List[FlowOp]) -> None:
        self.flow_preview_state.ops = value

    @property
    def flow_preview_unchanged_ops(self) -> List[FlowOp]:
        return self.flow_preview_state.unchanged_ops

    @flow_preview_unchanged_ops.setter
    def flow_preview_unchanged_ops(self, value: List[FlowOp]) -> None:
        self.flow_preview_state.unchanged_ops = value

    @property
    def flow_preview_kind(self) -> str:
        return self.flow_preview_state.kind

    @flow_preview_kind.setter
    def flow_preview_kind(self, value: str) -> None:
        self.flow_preview_state.kind = value
        self.flow_preview_state.apply_tool = self.flow_preview_state.default_apply_tool()
        self.flow_preview_state.apply_note = self.flow_preview_state.default_apply_note()

    @property
    def flow_preview_segment_key(self) -> Optional[FlowSegmentKey]:
        return self.flow_preview_state.segment_key

    @flow_preview_segment_key.setter
    def flow_preview_segment_key(self, value: Optional[FlowSegmentKey]) -> None:
        self.flow_preview_state.segment_key = value

    def _init_flow_state(self) -> None:
        self.selected_flow_cell = None
        self.selected_flow_region = None
        self.selected_flow_segment = None
        self.flow_segment_downstream = None
        self.confirmed_flow_segments = {}
        self.confirmed_flow_segment_cells = {}
        self.flow_skeleton_outlet = None
        self.flow_assist_sources = []
        self.flow_assist_outlets = []
        self.flow_assist_nodes = []
        self.flow_preview_state = FlowPreviewState()
        self.flow_suggestions = []
        self._flow_network_cache_key = None
        self._flow_network_cache = None

    def _reset_flow_preview_state(self) -> None:
        self.flow_preview_state = FlowPreviewState()

    def _reset_flow_selection_state(self, *, clear_cell: bool = True, clear_region: bool = True, clear_segment: bool = True) -> None:
        if clear_cell:
            self.selected_flow_cell = None
        if clear_region:
            self.selected_flow_region = None
        if clear_segment:
            self.selected_flow_segment = None
            self.flow_segment_downstream = None

    def _reset_flow_marker_state(self) -> None:
        self.flow_assist_sources = []
        self.flow_assist_outlets = []
        self.flow_assist_nodes = []

    def _reset_flow_lock_state(self) -> None:
        self.confirmed_flow_segments.clear()
        self.confirmed_flow_segment_cells.clear()
        self.flow_skeleton_outlet = None

    def _invalidate_flow_network_cache(self) -> None:
        self._flow_network_cache_key = None
        self._flow_network_cache = None
