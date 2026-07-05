from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


FlowCell = Tuple[int, int]
FlowOp = Tuple[int, int, int]
FlowSegmentKey = Tuple[FlowCell, FlowCell]


@dataclass
class FlowPreviewState:
    ops: List[FlowOp] = field(default_factory=list)
    unchanged_ops: List[FlowOp] = field(default_factory=list)
    kind: str = ""
    segment_key: Optional[FlowSegmentKey] = None


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
