from __future__ import annotations

from typing import Optional

import tkinter as tk

from .water_state import FlowPreviewState
from .water_ui_commands import CommandId
from .water_ui_model import (
    FlowAssistFacts,
    FlowAssistViewState,
    derive_flow_assist_state,
)


def build_flow_assist_facts(
    *,
    has_stream: bool,
    has_flow: bool,
    has_dem: bool,
    has_selected_cell: bool,
    has_selected_region: bool,
    selection_in_locked: bool,
    locked_count: int,
    outlet_set: bool,
    preview_target: str,
    preview: FlowPreviewState,
    dem_cache_ready: bool,
    dem_running: bool,
    dem_conflicts: int,
) -> FlowAssistFacts:
    return FlowAssistFacts(
        has_stream=has_stream,
        has_flow=has_flow,
        has_dem=has_dem,
        has_selected_cell=has_selected_cell,
        has_selected_region=has_selected_region,
        selection_in_locked=selection_in_locked,
        locked_count=locked_count,
        outlet_set=outlet_set,
        preview_target=preview_target,
        preview_exists=preview.has_preview(),
        preview_changes=preview.change_count,
        dem_cache_ready=dem_cache_ready,
        dem_running=dem_running,
        dem_scores_ready=bool(getattr(preview, "dem_score_details", [])),
        dem_conflicts=dem_conflicts,
    )


class UIStateMixin:
    def _flow_assist_view_state(self) -> FlowAssistViewState:
        locked_cells = self._locked_flow_cells_set()
        preview = self.flow_preview_state
        has_selected_cell = self.selected_flow_cell is not None
        has_selected_region = self.selected_flow_region is not None
        selection_in_locked = (
            self.selected_flow_cell in locked_cells if has_selected_cell else False
        )
        dem_cache_ready = (
            getattr(self, "dem_cache_arrays", None) is not None
            and getattr(self, "dem_cache_metadata", None) is not None
        )
        dem_running = (
            self._dem_cache_is_running()
            if hasattr(self, "_dem_cache_is_running")
            else False
        )
        dem_conflicts = int(preview.dem_score_summary.get("uphill", 0))
        facts = build_flow_assist_facts(
            has_stream=self.stream_raster is not None,
            has_flow=self.flow_raster is not None,
            has_dem=getattr(self, "dem_path", None) is not None,
            has_selected_cell=has_selected_cell,
            has_selected_region=has_selected_region,
            selection_in_locked=selection_in_locked,
            locked_count=len(locked_cells),
            outlet_set=self.flow_skeleton_outlet is not None,
            preview_target=self.flow_preview_target_var.get(),
            preview=preview,
            dem_cache_ready=dem_cache_ready,
            dem_running=dem_running,
            dem_conflicts=dem_conflicts,
        )
        return derive_flow_assist_state(facts)

    def on_mode_changed(self) -> None:
        self.tool_var.set("brush")
        self.on_tool_changed()
        if self.active_mode() != "flow":
            self._reset_flow_selection_state()
            self._reset_flow_preview_state()
            self._reset_flow_marker_state()
        self._maybe_setup_transformer()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.refresh_snapshot_list()

    def on_tool_changed(self) -> None:
        is_stream = self.mode_var.get() == "stream"
        if not is_stream and self.tool_var.get() == "eraser":
            self.tool_var.set("brush")
            self.info_var.set("订正流向模式禁用橡皮擦，已切换到画笔。")
        self.direction_box.configure(state="disabled" if is_stream else "readonly")
        self.btn_apply_direction.configure(state="disabled" if is_stream else "normal")
        self.btn_flow_suggest.configure(state="disabled" if is_stream else "normal")
        self.btn_vector_batch.configure(state="normal" if is_stream else "disabled")
        self.radio_eraser_tool.configure(state="normal" if is_stream else "disabled")
        self._refresh_flow_controls()
        self._update_shortcut_hint()

    def _refresh_flow_controls(self) -> None:
        view_state = self._flow_assist_view_state()
        enabled = view_state.enabled
        has_flow_data = self.stream_raster is not None and self.flow_raster is not None
        locked_ready = bool(self.confirmed_flow_segments)
        apply_ready = enabled[CommandId.APPLY_FLOW_PREVIEW]
        preview_ready = enabled[CommandId.CLEAR_FLOW_PREVIEW]
        apply_text = self._flow_apply_button_text()

        def state(enabled: bool) -> str:
            return "normal" if enabled else "disabled"

        self.btn_flow_preview.configure(state=state(locked_ready))
        self.btn_flow_apply.configure(state=state(apply_ready), text=apply_text)
        self.btn_pick_flow_segment.configure(state=state(has_flow_data))
        self.btn_set_flow_outlet.configure(state=state(locked_ready and self.selected_flow_cell is not None))
        self.btn_preview_river_flow.configure(state=state(locked_ready and self.flow_skeleton_outlet is not None))
        self.btn_set_downstream.configure(state=state(locked_ready))
        self.btn_add_locked_cell.configure(state=state(enabled[CommandId.ADD_SELECTED_CELL]))
        self.btn_remove_locked_region.configure(state=state(enabled[CommandId.REMOVE_SELECTED_RIVERS]))
        self.btn_reverse_segment.configure(state=state(enabled[CommandId.APPLY_FLOW_PREVIEW]), text=apply_text)
        self.btn_preview_segment.configure(state=state(enabled[CommandId.CLEAR_FLOW_PREVIEW]))
        self.btn_confirm_segment.configure(state=state(enabled[CommandId.RESET_FLOW_ASSIST]))
        self.btn_preview_confluence.configure(state=state(locked_ready))
        self.btn_clear_flow_marks.configure(state=state(enabled[CommandId.RESET_FLOW_ASSIST]))
        self.btn_apply_flow_preview.configure(state=state(enabled[CommandId.APPLY_FLOW_PREVIEW]), text=apply_text)
        self.btn_clear_flow_preview.configure(state=state(enabled[CommandId.CLEAR_FLOW_PREVIEW]))
        self.update_mode_status(view_state)
        if hasattr(self, "_refresh_dem_controls"):
            self._refresh_dem_controls()

    def on_river_flow_mode_changed(self, _event: Optional[tk.Event] = None) -> None:
        if self.flow_preview_state.kind == "river_skeleton":
            self._reset_flow_preview_state()
            self._update_flow_assist_text()
            self._refresh_flow_controls()
            self.render(full=True)
            self.info_var.set("河道流向计算模式已切换，请重新点击“预览河道流向”。")

    def on_confluence_mode_changed(self, _event: Optional[tk.Event] = None) -> None:
        if self.flow_preview_state.kind == "confluence":
            self._reset_flow_preview_state()
            self.render(full=True)
        self._update_confluence_hint()
        self._update_flow_assist_text()
        self._refresh_flow_controls()
        if self.confluence_mode_var.get() == "范围SHP":
            self.info_var.set("范围SHP模式：先加载范围SHP并锁定范围内河道；最大距为0表示不限距离。")
        else:
            self.info_var.set("近远带模式：按已锁定河道周边的近带/远带缓冲范围生成汇流预览。")

    def _update_confluence_hint(self) -> None:
        if not hasattr(self, "confluence_hint_var"):
            return
        if self.confluence_mode_var.get() == "范围SHP":
            self.confluence_hint_var.set("范围SHP：只处理面内非河道有效像元；最大距=0 不限，数值越小预览范围越贴近锁定河道。")
        else:
            self.confluence_hint_var.set("近远带：只处理锁定河道周边缓冲带；近带直接吸附，远带逐步流向河道。")
