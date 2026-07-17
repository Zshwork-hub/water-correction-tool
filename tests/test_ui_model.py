from __future__ import annotations

import unittest
from unittest.mock import patch

from water_tool.water_flow_status import FlowStatusMixin
from water_tool.water_flow_workflow import FlowWorkflowMixin
from water_tool.water_state import FlowPreviewState
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


class FakeControlPreview:
    def has_apply_ops(self) -> bool:
        return False

    def has_preview(self) -> bool:
        return True


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
        return type("FakeViewState", (), {"enabled": self.enabled})()

    def _flow_apply_button_text(self) -> str:
        return "apply"

    def update_mode_status(self, view_state=None) -> None:
        self.update_mode_status_calls += 1
        self.status_view_state = view_state


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


if __name__ == "__main__":
    unittest.main()
