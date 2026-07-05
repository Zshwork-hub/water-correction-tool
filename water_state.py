from __future__ import annotations


class FlowStateMixin:
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
        self.flow_preview_ops = []
        self.flow_preview_unchanged_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None
        self.flow_suggestions = []
        self._flow_network_cache_key = None
        self._flow_network_cache = None

    def _reset_flow_preview_state(self) -> None:
        self.flow_preview_ops = []
        self.flow_preview_unchanged_ops = []
        self.flow_preview_kind = ""
        self.flow_preview_segment_key = None

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
