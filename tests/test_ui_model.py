from __future__ import annotations

import unittest

from water_tool.water_ui_commands import CommandId
from water_tool.water_ui_model import (
    FlowAssistFacts,
    FlowAssistStage,
    derive_flow_assist_state,
)


class FlowAssistUiModelTests(unittest.TestCase):
    def test_missing_data_requires_stream_and_flow(self) -> None:
        state = derive_flow_assist_state(FlowAssistFacts())

        self.assertEqual(state.stage, FlowAssistStage.DATA)
        self.assertEqual(state.summary, "需要加载河道 ASC 和流向 ASC")
        self.assertFalse(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

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


if __name__ == "__main__":
    unittest.main()
