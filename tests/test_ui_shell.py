from __future__ import annotations

import unittest

from water_tool.water_project_panel import ProjectDataDialog
from water_tool.water_shell_model import NAV_ITEMS, PROJECT_DATA_ITEMS, NavigationId, navigation_mode, shell_metrics
from water_tool.water_ui_shell import UiShellHandles
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