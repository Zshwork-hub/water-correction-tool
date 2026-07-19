from __future__ import annotations

import unittest
from unittest.mock import patch

from pathlib import Path

import numpy as np

from water_tool.water_app import WaterCorrectionApp
from water_tool.water_flow_status import FlowStatusMixin
from water_tool.water_core import AscHeader, RasterData
from water_tool.water_editing import RasterEditingMixin
from water_tool.water_flow_workflow import FlowWorkflowMixin
from water_tool.water_state import FlowPreviewState, FlowStateMixin
from water_tool.water_ui_commands import CommandId
from water_tool.water_ui_model import (
    FlowAssistFacts,
    FlowAssistStage,
    derive_flow_assist_state,
)
from water_tool.water_ui_state import UIStateMixin, build_flow_assist_facts


class FakePreview:
    change_count = 5
    dem_score_details = [object(), object()]

    def has_preview(self) -> bool:
        return True


class FakePreviewTarget:
    def get(self) -> str:
        return "confluence"


class FakeButton:
    def __init__(self) -> None:
        self.configure_calls = []

    def configure(self, **kwargs) -> None:
        self.configure_calls.append(kwargs)


class FakeVar:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


def tiny_header() -> AscHeader:
    return AscHeader(
        [
            "ncols 3\n",
            "nrows 3\n",
            "xllcorner 0\n",
            "yllcorner 0\n",
            "cellsize 1\n",
            "NODATA_value -9999\n",
        ],
        {
            "ncols": 3,
            "nrows": 3,
            "xllcorner": 0,
            "yllcorner": 0,
            "cellsize": 1,
            "nodata_value": -9999,
        },
    )


class RasterModeHarness:
    get_edit_raster = WaterCorrectionApp.get_edit_raster
    get_display_raster = WaterCorrectionApp.get_display_raster
    can_modify_active_raster = WaterCorrectionApp.can_modify_active_raster

    def __init__(self, edit_mode: str, display_mode: str) -> None:
        self.mode_var = FakeVar(edit_mode)
        self.display_mode_var = FakeVar(display_mode)
        self.stream_raster = object()
        self.flow_raster = object()


class SelectedDirectionHarness(RasterEditingMixin):
    def __init__(self) -> None:
        self.mode_var = FakeVar("flow")
        self.tool_var = FakeVar("brush")
        self.direction_var = FakeVar("1 东")
        self.flow_raster = RasterData(
            Path("flow.asc"),
            tiny_header(),
            np.full((3, 3), 4, dtype=np.int32),
        )
        self.selected_flow_cell = (1, 2)
        self.histories = {"flow": []}
        self.redo_stacks = {"flow": []}
        self.info_var = FakeVar()
        self.dirty = []
        self.snapshots = []
        self.logged = []
        self.refreshes = []

    def get_active_raster(self):
        return self.flow_raster

    def log_batch(self, batch) -> None:
        self.logged.append(batch)

    def take_snapshot(self, silent: bool) -> None:
        self.snapshots.append(silent)

    def mark_dirty_cell(self, row: int, col: int) -> None:
        self.dirty.append((row, col))

    def schedule_view_refresh(self, *, full: bool) -> None:
        self.refreshes.append(full)


class AddSelectedStreamHarness(FlowWorkflowMixin):
    def __init__(self) -> None:
        self.stream_raster = RasterData(
            Path("stream.asc"),
            tiny_header(),
            np.array(
                [
                    [-9999, 1, -9999],
                    [-9999, -9999, -9999],
                    [-9999, -9999, -9999],
                ],
                dtype=np.int32,
            ),
        )
        self.flow_raster = self.stream_raster
        self.selected_flow_cell = (0, 1)
        self.selected_flow_region = None
        self.confirmed_flow_segments = {}
        self.confirmed_flow_segment_cells = {}
        self.info_var = FakeVar()
        self.render_calls = []

    def _locked_flow_cells_set(self):
        cells = []
        for group in self.confirmed_flow_segment_cells.values():
            cells.extend(group)
        return set(cells)

    def _locked_group_key(self, cells):
        return (cells[0], cells[-1])

    def _reset_flow_selection_state(self, **_kwargs):
        pass

    def _reset_flow_preview_state(self):
        pass

    def _refresh_flow_assist_ui(self):
        pass

    def render(self, *, full: bool):
        self.render_calls.append(full)


class FakeControlPreview:
    def has_apply_ops(self) -> bool:
        return False

    def has_preview(self) -> bool:
        return True


class RasterModeRegressionTests(unittest.TestCase):
    def test_edit_and_display_rasters_are_independent(self) -> None:
        app = RasterModeHarness("flow", "stream")

        self.assertIs(app.get_edit_raster(), app.flow_raster)
        self.assertIs(app.get_display_raster(), app.stream_raster)
        self.assertFalse(app.can_modify_active_raster())

    def test_matching_edit_and_display_modes_allow_writes(self) -> None:
        app = RasterModeHarness("flow", "flow")

        self.assertTrue(app.can_modify_active_raster())

class SelectionRegressionTests(unittest.TestCase):
    def test_selected_direction_accepts_row_col_pair(self) -> None:
        app = SelectedDirectionHarness()

        app.apply_selected_direction()

        self.assertEqual(int(app.flow_raster.data[1, 2]), 1)
        self.assertEqual(app.dirty, [(1, 2)])
        self.assertEqual(len(app.histories["flow"]), 1)


class AddSelectedCellRegressionTests(unittest.TestCase):
    def test_add_selected_stream_cell_accepts_valid_selected_pair(self) -> None:
        app = AddSelectedStreamHarness()

        app.add_selected_stream_cell_to_lock()

        self.assertEqual(app._locked_flow_cells_set(), {(0, 1)})
        self.assertIn("补充锁定", app.info_var.get())

    def test_add_selected_stream_cell_rejects_out_of_bounds_pair(self) -> None:
        app = AddSelectedStreamHarness()
        app.selected_flow_cell = (99, 99)

        with patch("water_tool.water_flow_workflow.messagebox.showinfo") as showinfo:
            app.add_selected_stream_cell_to_lock()

        showinfo.assert_called_once()
        self.assertEqual(app._locked_flow_cells_set(), set())


class FlowStatusHarness(FlowStatusMixin):
    def __init__(self) -> None:
        self.mode_var = FakeVar("flow")
        self.tool_var = FakeVar("brush")
        self.autosave_var = FakeVar(True)
        self.mode_status_var = FakeVar()
        self.tool_status_var = FakeVar()
        self.flow_status_var = FakeVar()
        self.session_status_var = FakeVar()
        self.flow_assist_var = FakeVar()
        self.dem_cache_status_var = FakeVar("已生成")
        self.confluence_mode_var = FakeVar("范围SHP")
        self.confluence_max_distance_var = FakeVar(12)
        self.stream_raster = object()
        self.flow_raster = object()
        self.dem_path = object()
        self.confluence_polygon_layer = object()
        self.confirmed_flow_segment_cells = {
            "first": [(1, 1), (1, 2)],
            "second": [(2, 2)],
        }
        self.confirmed_flow_segments = ["first", "second"]
        self.flow_skeleton_outlet = (2, 2)
        self.flow_preview_state = FlowPreviewState.create(
            [(3, 3, 1), (3, 4, 2)],
            unchanged_ops=[(4, 4, 4)],
            label="周边汇流",
            kind="confluence",
        )
        self.flow_preview_state.dem_score_label = "逆坡 1"

    def _flow_assist_view_state(self):
        raise AssertionError("supplied view state must be reused")

    def _locked_flow_cells_set(self):
        return {(1, 1), (1, 2), (2, 2)}

    def _shortcut_label(self, action: str) -> str:
        return {"brush": "B", "eraser": "E"}[action]


class FlowAssistUiRefreshHarness(FlowStatusMixin):
    def __init__(self) -> None:
        self.view_state = object()
        self.view_state_calls = 0
        self.text_view_state = None
        self.controls_view_state = None

    def _flow_assist_view_state(self):
        self.view_state_calls += 1
        return self.view_state

    def _update_flow_assist_text(self, view_state=None) -> None:
        self.text_view_state = view_state

    def _refresh_flow_controls(self, view_state=None) -> None:
        self.controls_view_state = view_state


class FakeSegmentAssistant:
    def normalize_segment_downstream(self, segment, downstream):
        return downstream

    def preview_segment_flow(self, segment, downstream):
        return [(1, 1, 2)]


class FlowPreviewCallerHarness(FlowWorkflowMixin):
    def __init__(self) -> None:
        self.selected_flow_segment = type(
            "FakeSegment", (), {"edge_key": ((0, 0), (1, 1))}
        )()
        self.flow_segment_downstream = (1, 1)
        self.flow_raster = None
        self.flow_preview_state = FlowPreviewState()
        self.info_var = FakeVar()
        self.view_state = object()
        self.refresh_calls = 0

    def _flow_assistant(self):
        return FakeSegmentAssistant()

    def _flow_assist_view_state(self):
        return self.view_state

    def _update_flow_assist_text(self, view_state=None) -> None:
        self.text_view_state = view_state

    def _refresh_flow_controls(self, view_state=None) -> None:
        self.refresh_calls += 1
        self.controls_view_state = view_state

    def _flow_apply_button_text(self) -> str:
        return "应用河段预览"

    def render(self, *, full: bool) -> None:
        self.render_full = full


class FlowAssistViewStateHarness(UIStateMixin, FlowWorkflowMixin):
    def __init__(self) -> None:
        self.confirmed_flow_segment_cells = {
            "first": [(1, 1), (1, 2)],
            "second": [(1, 2), (2, 2)],
        }
        self.selected_flow_cell = (1, 2)
        self.selected_flow_region = (0, 2, 0, 2)
        self.flow_skeleton_outlet = (2, 2)
        self.flow_preview_target_var = FakePreviewTarget()
        self.stream_raster = object()
        self.flow_raster = object()
        self.dem_path = object()
        self.dem_cache_arrays = object()
        self.dem_cache_metadata = object()
        self.flow_preview_state = FlowPreviewState.create(
            [(3, 3, 1), (3, 4, 2)],
            label="周边汇流",
            kind="confluence",
        )
        self.flow_preview_state.dem_score_details = [object()]
        self.flow_preview_state.dem_score_summary = {"uphill": 2}

    def _dem_cache_is_running(self) -> bool:
        return False

    def _dem_conflict_scores(self) -> None:
        raise AssertionError("view-state adaptation must not scan DEM score details")


class FlowControlRefreshHarness(UIStateMixin):
    def __init__(self) -> None:
        self.stream_raster = None
        self.flow_raster = None
        self.confirmed_flow_segments = []
        self.selected_flow_cell = (1, 1)
        self.selected_flow_region = None
        self.flow_skeleton_outlet = None
        self.flow_preview_state = FakeControlPreview()
        self.view_state_calls = 0
        self.update_mode_status_calls = 0
        self.status_view_state = None
        self.enabled = {
            CommandId.ADD_SELECTED_CELL: True,
            CommandId.REMOVE_SELECTED_RIVERS: True,
            CommandId.APPLY_FLOW_PREVIEW: True,
            CommandId.CLEAR_FLOW_PREVIEW: False,
            CommandId.RESET_FLOW_ASSIST: True,
        }
        self.view_state = type("FakeViewState", (), {"enabled": self.enabled})()
        for name in (
            "btn_flow_preview",
            "btn_flow_apply",
            "btn_pick_flow_segment",
            "btn_set_flow_outlet",
            "btn_preview_river_flow",
            "btn_set_downstream",
            "btn_add_locked_cell",
            "btn_remove_locked_region",
            "btn_reverse_segment",
            "btn_preview_segment",
            "btn_confirm_segment",
            "btn_preview_confluence",
            "btn_clear_flow_marks",
            "btn_apply_flow_preview",
            "btn_clear_flow_preview",
        ):
            setattr(self, name, FakeButton())

    def _flow_assist_view_state(self):
        self.view_state_calls += 1
        return self.view_state

    def _flow_apply_button_text(self) -> str:
        return "apply"

    def update_mode_status(self, view_state=None) -> None:
        self.update_mode_status_calls += 1
        self.status_view_state = view_state


class ToolChangeRefreshHarness(FlowControlRefreshHarness):
    def __init__(self) -> None:
        super().__init__()
        self.mode_var = FakeVar("flow")
        self.tool_var = FakeVar("brush")
        self.info_var = FakeVar()
        for name in (
            "direction_box",
            "btn_apply_direction",
            "btn_vector_batch",
            "radio_eraser_tool",
        ):
            setattr(self, name, FakeButton())

    def update_mode_status(self, view_state=None) -> None:
        self.update_mode_status_calls += 1
        if view_state is None:
            view_state = self._flow_assist_view_state()
        self.status_view_state = view_state

    def _update_shortcut_hint(self, view_state=None) -> None:
        self.update_mode_status(view_state)


class ModeChangeRefreshHarness(FlowStatusMixin, UIStateMixin, FlowStateMixin):
    def __init__(self) -> None:
        self.mode_var = FakeVar("flow")
        self.tool_var = FakeVar("brush")
        self.autosave_var = FakeVar(True)
        self.mode_status_var = FakeVar()
        self.tool_status_var = FakeVar()
        self.flow_status_var = FakeVar()
        self.session_status_var = FakeVar()
        self.flow_assist_var = FakeVar()
        self.dem_cache_status_var = FakeVar("未生成")
        self.confluence_mode_var = FakeVar("范围SHP")
        self.confluence_max_distance_var = FakeVar(12)
        self.flow_preview_target_var = FakeVar("confluence")
        self.info_var = FakeVar()
        self.stream_raster = object()
        self.flow_raster = object()
        self.dem_path = None
        self.dem_cache_arrays = None
        self.dem_cache_metadata = None
        self.confluence_polygon_layer = None
        self.confirmed_flow_segments = {"edge": (1, 2)}
        self.confirmed_flow_segment_cells = {"edge": [(1, 1), (1, 2)]}
        self.selected_flow_cell = (1, 1)
        self.selected_flow_region = (0, 2, 0, 2)
        self.selected_flow_segment = object()
        self.flow_segment_downstream = (1, 2)
        self.flow_skeleton_outlet = (1, 2)
        self.flow_assist_sources = [(0, 0)]
        self.flow_assist_outlets = [(1, 2)]
        self.flow_assist_nodes = [(1, 1)]
        self.flow_preview_state = FlowPreviewState.create(
            [(3, 3, 2)],
            label="周边汇流",
            kind="confluence",
        )
        for name in (
            "direction_box",
            "btn_apply_direction",
            "btn_vector_batch",
            "radio_eraser_tool",
            "btn_flow_preview",
            "btn_flow_apply",
            "btn_pick_flow_segment",
            "btn_set_flow_outlet",
            "btn_preview_river_flow",
            "btn_set_downstream",
            "btn_add_locked_cell",
            "btn_remove_locked_region",
            "btn_reverse_segment",
            "btn_preview_segment",
            "btn_confirm_segment",
            "btn_preview_confluence",
            "btn_clear_flow_marks",
            "btn_apply_flow_preview",
            "btn_clear_flow_preview",
        ):
            setattr(self, name, FakeButton())
        initial_state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=2,
                outlet_set=True,
                preview_target="confluence",
                preview_exists=True,
                preview_changes=1,
            )
        )
        self.update_mode_status(initial_state)
        FlowStatusMixin._update_flow_assist_text(self, initial_state)
        self.view_state_calls = 0
        self.derived_snapshots = []
        self.assist_text_states = []
        self.last_view_state = None

    def _locked_flow_cells_set(self):
        return {(1, 1), (1, 2)}

    def _flow_assist_view_state(self):
        self.view_state_calls += 1
        self.derived_snapshots.append(
            (
                self.selected_flow_cell,
                self.flow_preview_state.has_preview(),
                tuple(self.flow_assist_sources),
                tuple(self.flow_assist_outlets),
                tuple(self.flow_assist_nodes),
            )
        )
        self.last_view_state = UIStateMixin._flow_assist_view_state(self)
        return self.last_view_state

    def _update_flow_assist_text(self, view_state=None) -> None:
        self.assist_text_states.append(view_state)
        FlowStatusMixin._update_flow_assist_text(self, view_state)

    def _shortcut_label(self, action: str) -> str:
        return {"brush": "B", "eraser": "E"}[action]

    def _update_shortcut_hint(self, view_state=None) -> None:
        self.update_mode_status(view_state)

    def active_mode(self) -> str:
        return self.mode_var.get()

    def _maybe_setup_transformer(self) -> None:
        pass

    def _invalidate_viewport_cache(self) -> None:
        pass

    def render(self, *, full: bool) -> None:
        pass

    def refresh_snapshot_list(self) -> None:
        pass


class ApplyPreviewModeSwitchHarness(FlowWorkflowMixin):
    def __init__(self) -> None:
        self.mode_var = FakeVar("stream")
        self.flow_raster = object()
        self.flow_preview_state = FlowPreviewState.create(
            [(1, 1, 2)],
            label="周边汇流",
            kind="confluence",
        )
        self.selected_flow_segment = None
        self.confirmed_flow_segments = {}
        self.confirmed_flow_segment_cells = {}
        self.info_var = FakeVar()
        self.view_state = object()
        self.view_state_calls = 0
        self.text_view_state = None

    def _apply_flow_ops(self, ops, tool, note):
        return type("FakeBatch", (), {"ops": list(ops)})()

    def _record_flow_batch(self, batch) -> None:
        pass

    def _reset_flow_preview_state(self) -> None:
        self.flow_preview_state = FlowPreviewState()

    def active_mode(self) -> str:
        return self.mode_var.get()

    def on_tool_changed(self):
        return self._flow_assist_view_state()

    def _flow_assist_view_state(self):
        self.view_state_calls += 1
        return self.view_state

    def _update_flow_assist_text(self, view_state=None) -> None:
        self.text_view_state = view_state

    def _refresh_flow_assist_ui(self) -> None:
        self._update_flow_assist_text(self._flow_assist_view_state())

    def _invalidate_viewport_cache(self) -> None:
        pass

    def refresh_snapshot_list(self) -> None:
        pass

    def flush_pending_render(self, *, force: bool) -> None:
        pass


class FlowAssistUiModelTests(unittest.TestCase):
    def test_missing_data_requires_stream_and_flow(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(has_stream=True, has_flow=False)
        )

        self.assertEqual(state.stage, FlowAssistStage.DATA)
        self.assertEqual(state.summary, "需要加载河道 ASC 和流向 ASC")
        self.assertFalse(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_review_summary_exactly_reports_changes_and_dem_conflicts(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=9,
                preview_exists=True,
                preview_changes=4,
                dem_conflicts=2,
            )
        )

        self.assertEqual(state.summary, "预览待修改 4，逆坡冲突 2")

    def test_selected_cell_is_primary_object_action_when_data_is_ready(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                has_selected_cell=True,
            )
        )

        self.assertEqual(state.stage, FlowAssistStage.OBJECTS)
        self.assertEqual(state.primary_command, CommandId.ADD_SELECTED_RIVERS)
        self.assertTrue(state.enabled[CommandId.ADD_SELECTED_RIVERS])

    def test_river_target_requires_an_outlet_before_preview_generation(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=12,
                preview_target="river",
            )
        )

        self.assertEqual(state.stage, FlowAssistStage.DIRECTION)
        self.assertEqual(state.primary_command, CommandId.SET_DOWNSTREAM_OUTLET)
        self.assertFalse(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_confluence_target_can_generate_without_an_outlet(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=12,
                preview_target="confluence",
            )
        )

        self.assertEqual(state.primary_command, CommandId.GENERATE_FLOW_PREVIEW)
        self.assertTrue(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_existing_preview_with_changes_is_ready_for_review(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=12,
                outlet_set=True,
                preview_target="river",
                preview_exists=True,
                preview_changes=4,
            )
        )

        self.assertEqual(state.stage, FlowAssistStage.REVIEW)
        self.assertEqual(state.primary_command, CommandId.APPLY_FLOW_PREVIEW)
        self.assertTrue(state.enabled[CommandId.CLEAR_FLOW_PREVIEW])

    def test_existing_preview_without_changes_can_be_cleared_or_reset(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=5,
                outlet_set=True,
                preview_exists=True,
                preview_changes=0,
            )
        )

        self.assertTrue(state.enabled[CommandId.CLEAR_FLOW_PREVIEW])
        self.assertFalse(state.enabled[CommandId.APPLY_FLOW_PREVIEW])
        self.assertTrue(state.enabled[CommandId.RESET_FLOW_ASSIST])

    def test_review_summary_and_navigation_report_dem_conflicts(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=12,
                outlet_set=True,
                preview_target="river",
                preview_exists=True,
                preview_changes=4,
                dem_conflicts=3,
            )
        )

        self.assertIn("逆坡冲突 3", state.summary)
        self.assertTrue(state.enabled[CommandId.LOCATE_NEXT_UPHILL])

    def test_build_dem_cache_requires_a_loaded_dem(self) -> None:
        without_dem = derive_flow_assist_state(FlowAssistFacts(locked_count=2))
        with_dem = derive_flow_assist_state(
            FlowAssistFacts(locked_count=2, has_dem=True)
        )

        self.assertFalse(without_dem.enabled[CommandId.BUILD_DEM_CACHE])
        self.assertTrue(with_dem.enabled[CommandId.BUILD_DEM_CACHE])

    def test_dem_result_actions_are_disabled_while_cache_is_running(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                dem_running=True,
                dem_scores_ready=True,
                dem_conflicts=2,
            )
        )

        self.assertFalse(state.enabled[CommandId.LOCATE_NEXT_UPHILL])
        self.assertFalse(state.enabled[CommandId.EXPORT_DEM_REPORT])
        self.assertFalse(state.enabled[CommandId.EXPORT_UPHILL_CONFLICTS])

    def test_command_enablement_is_derived_from_independent_facts(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                has_selected_cell=True,
                has_selected_region=True,
                selection_in_locked=True,
                locked_count=2,
                outlet_set=True,
                preview_exists=True,
                preview_changes=1,
                has_dem=True,
                dem_cache_ready=True,
                dem_running=False,
                dem_scores_ready=True,
                dem_conflicts=2,
            )
        )

        expected = {
            CommandId.ADD_SELECTED_RIVERS: True,
            CommandId.ADD_SELECTED_CELL: True,
            CommandId.REMOVE_SELECTED_RIVERS: True,
            CommandId.RESET_FLOW_ASSIST: True,
            CommandId.SET_DOWNSTREAM_OUTLET: True,
            CommandId.GENERATE_FLOW_PREVIEW: True,
            CommandId.APPLY_FLOW_PREVIEW: True,
            CommandId.CLEAR_FLOW_PREVIEW: True,
            CommandId.BUILD_DEM_CACHE: True,
            CommandId.CANCEL_DEM_CACHE: False,
            CommandId.EVALUATE_DEM_PREVIEW: True,
            CommandId.LOCATE_NEXT_UPHILL: True,
            CommandId.EXPORT_DEM_REPORT: True,
            CommandId.EXPORT_UPHILL_CONFLICTS: True,
        }

        self.assertEqual(state.enabled, expected)

    def test_build_flow_assist_facts_preserves_application_state(self) -> None:
        facts = build_flow_assist_facts(
            has_stream=True,
            has_flow=True,
            has_dem=True,
            has_selected_cell=True,
            has_selected_region=False,
            selection_in_locked=True,
            locked_count=8,
            outlet_set=True,
            preview_target="confluence",
            preview=FakePreview(),
            dem_cache_ready=True,
            dem_running=False,
            dem_conflicts=2,
        )

        self.assertEqual(facts.locked_count, 8)
        self.assertTrue(facts.has_dem)
        self.assertTrue(facts.preview_exists)
        self.assertEqual(facts.preview_changes, 5)
        self.assertTrue(facts.dem_scores_ready)
        self.assertEqual(facts.dem_conflicts, 2)
        self.assertEqual(facts.preview_target, "confluence")

    def test_flow_assist_view_state_adapts_harness_without_scanning_scores(self) -> None:
        app = FlowAssistViewStateHarness()
        captured_facts = []

        def derive_and_capture(facts: FlowAssistFacts):
            captured_facts.append(facts)
            return derive_flow_assist_state(facts)

        with patch(
            "water_tool.water_ui_state.derive_flow_assist_state",
            side_effect=derive_and_capture,
        ):
            state = app._flow_assist_view_state()
            ready_facts = captured_facts[-1]
            app.dem_cache_metadata = None
            without_cache_state = app._flow_assist_view_state()
            without_cache_facts = captured_facts[-1]

        self.assertTrue(ready_facts.has_stream)
        self.assertTrue(ready_facts.has_flow)
        self.assertEqual(ready_facts.locked_count, 3)
        self.assertTrue(ready_facts.has_selected_cell)
        self.assertTrue(ready_facts.has_selected_region)
        self.assertTrue(ready_facts.selection_in_locked)
        self.assertTrue(ready_facts.outlet_set)
        self.assertEqual(ready_facts.preview_target, "confluence")
        self.assertTrue(ready_facts.has_dem)
        self.assertTrue(ready_facts.dem_cache_ready)
        self.assertFalse(ready_facts.dem_running)
        self.assertTrue(ready_facts.preview_exists)
        self.assertEqual(ready_facts.preview_changes, 2)
        self.assertTrue(ready_facts.dem_scores_ready)
        self.assertEqual(ready_facts.dem_conflicts, 2)

        self.assertEqual(state.stage, FlowAssistStage.REVIEW)
        self.assertEqual(state.primary_command, CommandId.APPLY_FLOW_PREVIEW)
        self.assertTrue(state.enabled[CommandId.ADD_SELECTED_RIVERS])
        self.assertTrue(state.enabled[CommandId.SET_DOWNSTREAM_OUTLET])
        self.assertTrue(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])
        self.assertTrue(state.enabled[CommandId.EVALUATE_DEM_PREVIEW])
        self.assertTrue(state.enabled[CommandId.LOCATE_NEXT_UPHILL])
        self.assertTrue(state.enabled[CommandId.EXPORT_DEM_REPORT])
        self.assertEqual(state.summary, "预览待修改 2，逆坡冲突 2")

        self.assertFalse(without_cache_facts.dem_cache_ready)
        self.assertFalse(
            without_cache_state.enabled[CommandId.EVALUATE_DEM_PREVIEW]
        )

    def test_flow_status_uses_supplied_view_state_summary(self) -> None:
        app = FlowStatusHarness()
        view_state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=3,
                preview_exists=True,
                preview_changes=2,
                dem_conflicts=1,
            )
        )

        app.update_mode_status(view_state)
        app._update_flow_assist_text(view_state)

        self.assertEqual(
            app.flow_status_var.get(),
            "流向辅助：预览待修改 2，逆坡冲突 1",
        )
        self.assertTrue(
            app.flow_assist_var.get().startswith("预览待修改 2，逆坡冲突 1\n")
        )
        self.assertEqual(
            app.flow_assist_var.get().splitlines()[1],
            "已锁定河道 2 组 / 3 像元  出口 (2, 2)  汇流模式 范围SHP  最大距 12  "
            "周边预览 需修改 2 / 已一致 1  DEM 逆坡 1",
        )

    def test_unified_flow_assist_refresh_reuses_one_view_state(self) -> None:
        app = FlowAssistUiRefreshHarness()

        app._refresh_flow_assist_ui()

        self.assertEqual(app.view_state_calls, 1)
        self.assertIs(app.text_view_state, app.view_state)
        self.assertIs(app.controls_view_state, app.view_state)

    def test_segment_preview_caller_does_not_refresh_after_setting_preview(self) -> None:
        app = FlowPreviewCallerHarness()

        app.preview_selected_flow_segment()

        self.assertEqual(app.refresh_calls, 1)


    def test_refresh_flow_controls_consumes_model_enablement_once(self) -> None:
        app = FlowControlRefreshHarness()

        app._refresh_flow_controls()

        self.assertEqual(app.view_state_calls, 1)
        self.assertIsNotNone(app.status_view_state)
        self.assertIs(app.status_view_state.enabled, app.enabled)
        self.assertEqual(app.btn_add_locked_cell.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_remove_locked_region.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_reverse_segment.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_apply_flow_preview.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_flow_apply.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_flow_apply.configure_calls[-1]["text"], "apply")
        self.assertEqual(app.btn_preview_segment.configure_calls[-1]["state"], "disabled")
        self.assertEqual(app.btn_clear_flow_preview.configure_calls[-1]["state"], "disabled")
        self.assertEqual(app.btn_confirm_segment.configure_calls[-1]["state"], "normal")
        self.assertEqual(app.btn_clear_flow_marks.configure_calls[-1]["state"], "normal")

    def test_refresh_flow_controls_reuses_supplied_view_state(self) -> None:
        app = FlowControlRefreshHarness()

        app._refresh_flow_controls(app.view_state)

        self.assertEqual(app.view_state_calls, 0)
        self.assertIs(app.status_view_state, app.view_state)

    def test_tool_change_derives_flow_assist_state_once(self) -> None:
        app = ToolChangeRefreshHarness()

        app.on_tool_changed()

        self.assertEqual(app.view_state_calls, 1)
        self.assertIs(app.status_view_state, app.view_state)

    def test_mode_change_preserves_flow_state_before_single_refresh(self) -> None:
        app = ModeChangeRefreshHarness()
        app.mode_var.set("stream")

        app.on_mode_changed()

        self.assertEqual(app.view_state_calls, 1)
        self.assertEqual(
            app.derived_snapshots,
            [(app.selected_flow_cell, True, ((0, 0),), ((1, 2),), ((1, 1),))],
        )
        self.assertEqual(
            app.btn_apply_flow_preview.configure_calls[-1]["state"],
            "normal",
        )
        self.assertEqual(
            app.btn_clear_flow_preview.configure_calls[-1]["state"],
            "normal",
        )
        self.assertEqual(
            app.flow_status_var.get(),
            f"流向辅助：{app.last_view_state.summary}",
        )
        self.assertEqual(
            app.flow_assist_var.get().splitlines()[0],
            app.last_view_state.summary,
        )
        self.assertEqual(app.assist_text_states, [app.last_view_state])

    def test_flow_mode_change_keeps_global_and_assist_summaries_aligned(self) -> None:
        app = ModeChangeRefreshHarness()

        app.on_mode_changed()

        self.assertEqual(app.view_state_calls, 1)
        self.assertEqual(app.assist_text_states, [app.last_view_state])
        self.assertEqual(
            app.flow_status_var.get(),
            f"流向辅助：{app.last_view_state.summary}",
        )
        self.assertEqual(
            app.flow_assist_var.get().splitlines()[0],
            app.last_view_state.summary,
        )

    def test_apply_preview_mode_switch_reuses_tool_change_view_state(self) -> None:
        app = ApplyPreviewModeSwitchHarness()

        app.apply_flow_preview()

        self.assertEqual(app.mode_var.get(), "flow")
        self.assertEqual(app.view_state_calls, 1)
        self.assertIs(app.text_view_state, app.view_state)


if __name__ == "__main__":
    unittest.main()
