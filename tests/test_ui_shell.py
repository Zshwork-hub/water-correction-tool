from __future__ import annotations

import unittest

from water_tool.water_project_panel import ProjectDataDialog
from water_tool.water_shell_model import (
    DISPLAY_CONTROL_KEYS,
    FLOW_CONTROL_KEYS,
    HISTORY_CONTROL_KEYS,
    NAV_ITEMS,
    PROJECT_DATA_ITEMS,
    STREAM_CONTROL_KEYS,
    STREAM_PAGE_COMMANDS,
    NavigationId,
    navigation_mode,
    shell_metrics,
)
from water_tool.water_legacy_pages import build_display_page, build_flow_compatibility_page, build_history_page
from water_tool.water_stream_page import build_stream_page
from water_tool.water_ui_shell import UiShellHandles, bind_control_registry, merge_control_registries
from water_tool.water_ui_commands import CommandId
from water_tool.water_ui_components import ScrollableTaskPanel, normalize_wheel_steps
from water_tool.water_ui_theme import UI_COLORS, UI_SPACING, apply_ui_theme


class RecordingStyle:
    def __init__(self) -> None:
        self.configured = {}
        self.mapped = {}

    def configure(self, name, **options) -> None:
        self.configured[name] = options

    def map(self, name, **options) -> None:
        self.mapped[name] = options


class ShellModelTests(unittest.TestCase):
    def test_navigation_ids_and_labels_are_stable(self) -> None:
        self.assertEqual(
            [(item.navigation_id, item.label) for item in NAV_ITEMS],
            [
                (NavigationId.STREAM, "河道订正"),
                (NavigationId.FLOW, "流向订正"),
                (NavigationId.DISPLAY, "显示与配色"),
                (NavigationId.HISTORY, "历史与恢复"),
            ],
        )

    def test_control_registries_bind_once_and_reject_duplicates(self) -> None:
        class DummyApp:
            pass

        app = DummyApp()
        controls = merge_control_registries(
            {"btn_vector_batch": object()},
            {"direction_box": object()},
        )
        bind_control_registry(app, controls)

        self.assertIs(app.btn_vector_batch, controls["btn_vector_batch"])
        self.assertIs(app.direction_box, controls["direction_box"])
        with self.assertRaises(ValueError):
            merge_control_registries({"shared": object()}, {"shared": object()})

    def test_final_build_ui_delegates_without_notebook(self) -> None:
        import inspect

        from water_tool.water_app import WaterCorrectionApp

        source = inspect.getsource(WaterCorrectionApp._build_ui)
        self.assertIn("build_application_shell", source)
        self.assertNotIn("ttk.Notebook", source)
        self.assertNotIn("radio_stream", source)
        self.assertNotIn("radio_flow", source)

    def test_project_and_autosave_restore_synchronize_edit_navigation(self) -> None:
        import inspect

        from water_tool.water_project_workflow import ProjectWorkflowMixin

        self.assertIn("_show_edit_navigation", inspect.getsource(ProjectWorkflowMixin.open_project))
        self.assertIn("_show_edit_navigation", inspect.getsource(ProjectWorkflowMixin._restore_autosave))

    def test_navigation_changes_edit_mode_only_for_edit_pages(self) -> None:
        self.assertEqual(navigation_mode(NavigationId.DISPLAY, "flow"), "flow")
        self.assertEqual(navigation_mode(NavigationId.HISTORY, "stream"), "stream")
        self.assertEqual(navigation_mode(NavigationId.STREAM, "flow"), "stream")
        self.assertEqual(navigation_mode(NavigationId.FLOW, "stream"), "flow")

    def test_shell_handles_show_only_requested_page(self) -> None:
        class FakeFrame:
            def __init__(self) -> None:
                self.visible = False

            def grid_remove(self) -> None:
                self.visible = False

            def grid(self, **_options) -> None:
                self.visible = True

        class FakeNavigation:
            def __init__(self) -> None:
                self.selected = None

            def set_selected(self, navigation_id) -> None:
                self.selected = navigation_id

        pages = {item.navigation_id: FakeFrame() for item in NAV_ITEMS}
        navigation = FakeNavigation()
        handles = UiShellHandles(navigation, FakeFrame(), FakeFrame(), FakeFrame(), pages)

        handles.show_page(NavigationId.DISPLAY)

        self.assertTrue(pages[NavigationId.DISPLAY].visible)
        self.assertFalse(pages[NavigationId.STREAM].visible)
        self.assertEqual(navigation.selected, NavigationId.DISPLAY)

    def test_stream_page_has_one_data_command(self) -> None:
        self.assertEqual(STREAM_PAGE_COMMANDS, (CommandId.APPLY_VECTOR_CORRECTION,))

    def test_stream_page_exposes_required_compatibility_controls(self) -> None:
        self.assertEqual(
            STREAM_CONTROL_KEYS,
            (
                "radio_brush_tool",
                "radio_eraser_tool",
                "brush_size_spin",
                "btn_shortcuts",
                "btn_vector_batch",
                "vector_hint",
            ),
        )

    def test_stream_page_builder_keeps_flow_controls_out(self) -> None:
        import inspect

        source = inspect.getsource(build_stream_page)
        for forbidden in ("direction_box", "flow_suggest", "locked", "outlet", "dem_"):
            self.assertNotIn(forbidden, source.lower())

    def test_compatibility_page_control_contracts_are_complete_and_disjoint(self) -> None:
        required_flow = {
            "direction_box", "btn_apply_direction",
            "btn_pick_flow_segment", "btn_add_locked_cell", "btn_remove_locked_region",
            "btn_set_flow_outlet", "btn_preview_river_flow", "btn_set_downstream",
            "btn_reverse_segment", "btn_preview_segment", "btn_confirm_segment",
            "btn_flow_preview", "btn_flow_apply", "btn_preview_confluence",
            "btn_apply_flow_preview", "btn_clear_flow_preview", "btn_clear_flow_marks",
            "btn_load_dem", "btn_build_dem_cache", "btn_cancel_dem_cache",
            "btn_evaluate_dem_preview", "btn_locate_dem_conflict",
            "btn_export_dem_report", "btn_export_dem_conflicts",
        }
        required_display = {
            "chk_grid", "chk_scale", "chk_arrows", "chk_compare",
            "btn_stream_palette", "btn_flow_palette", "btn_vector_color",
            "btn_confluence_polygon_color", "btn_assist_palette", "btn_reset_palette",
            "preset_combo", "btn_load_preset", "btn_save_preset", "btn_delete_preset",
        }
        required_history = {"snapshot_list", "btn_restore_snapshot", "btn_snapshot", "btn_restore_autosave"}

        self.assertTrue(required_flow.issubset(FLOW_CONTROL_KEYS))
        self.assertEqual(set(DISPLAY_CONTROL_KEYS), required_display)
        self.assertEqual(set(HISTORY_CONTROL_KEYS), required_history)
        all_keys = list(FLOW_CONTROL_KEYS + DISPLAY_CONTROL_KEYS + HISTORY_CONTROL_KEYS)
        self.assertEqual(len(all_keys), len(set(all_keys)))

    def test_flow_page_does_not_expose_direction_suggestion(self) -> None:
        import inspect

        source = inspect.getsource(build_flow_compatibility_page)
        self.assertNotIn("btn_flow_suggest", source)
        self.assertNotIn("suggest_flow_direction", source)

    def test_compatibility_builders_use_scrollable_panels(self) -> None:
        import inspect

        for builder in (build_flow_compatibility_page, build_display_page, build_history_page):
            source = inspect.getsource(builder)
            self.assertIn("ScrollableTaskPanel", source)
            self.assertIn("return panel, controls", source)

    def test_flow_page_uses_a_fixed_footer_for_primary_actions(self) -> None:
        import inspect

        source = inspect.getsource(build_flow_compatibility_page)
        self.assertIn("panel.footer", source)
        self.assertNotIn("ttk.Notebook", source)

    def test_project_data_items_have_stable_order_and_commands(self) -> None:
        expected = [
            ("stream", "河道 ASC", CommandId.LOAD_STREAM_ASC),
            ("flow", "流向 ASC", CommandId.LOAD_FLOW_ASC),
            ("river", "河流线 SHP", CommandId.LOAD_RIVER_SHP),
            ("confluence", "汇流范围 SHP", CommandId.LOAD_CONFLUENCE_SHP),
            ("dem", "DEM", CommandId.LOAD_DEM),
        ]

        self.assertEqual(
            [(item.key, item.label, item.command_id) for item in PROJECT_DATA_ITEMS],
            expected,
        )

    def test_project_data_dialog_requires_variables_and_callbacks(self) -> None:
        import inspect

        parameters = inspect.signature(ProjectDataDialog.__init__).parameters
        self.assertIn("file_variables", parameters)
        self.assertIn("callbacks", parameters)

    def test_notebook_layout_keeps_map_usable_at_1366_by_768(self) -> None:
        metrics = shell_metrics(1366, 768)
        self.assertLessEqual(metrics.navigation_width, 148)
        self.assertGreaterEqual(metrics.context_width, 340)
        self.assertLessEqual(metrics.context_width, 380)
        self.assertGreaterEqual(metrics.map_width, 760)

    def test_wide_layout_gives_extra_space_to_map(self) -> None:
        notebook = shell_metrics(1366, 768)
        desktop = shell_metrics(1920, 1080)
        self.assertGreater(desktop.map_width, notebook.map_width)
        self.assertLessEqual(desktop.context_width, 380)

    def test_theme_has_distinct_semantic_colors(self) -> None:
        keys = {"background", "panel", "primary", "success", "warning", "error", "text", "muted"}
        self.assertTrue(keys.issubset(UI_COLORS))
        self.assertEqual(len({UI_COLORS[key] for key in keys}), len(keys))
        self.assertGreaterEqual(UI_SPACING["control_height"], 28)

    def test_wheel_delta_is_normalized_across_platform_events(self) -> None:
        self.assertEqual(normalize_wheel_steps(delta=120, button=0), -1)
        self.assertEqual(normalize_wheel_steps(delta=-120, button=0), 1)
        self.assertEqual(normalize_wheel_steps(delta=0, button=4), -1)
        self.assertEqual(normalize_wheel_steps(delta=0, button=5), 1)
        self.assertEqual(normalize_wheel_steps(delta=120, button="??"), -1)
        self.assertEqual(normalize_wheel_steps(delta="??", button="??"), 0)

    def test_scrollable_panel_does_not_capture_global_mousewheel(self) -> None:
        import inspect

        source = inspect.getsource(ScrollableTaskPanel)
        self.assertNotIn("bind_all", source)
        self.assertNotIn("unbind_all", source)

    def test_theme_registers_required_widget_styles(self) -> None:
        style = RecordingStyle()

        apply_ui_theme(style)

        self.assertTrue(
            {
                "App.TFrame",
                "Panel.TFrame",
                "Nav.TButton",
                "NavSelected.TButton",
                "Primary.TButton",
                "Status.TLabel",
                "Muted.TLabel",
            }.issubset(style.configured)
        )


if __name__ == "__main__":
    unittest.main()
