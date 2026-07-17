from __future__ import annotations

import unittest

from water_tool.water_ui_commands import COMMANDS, CommandId, get_command


class UiCommandCatalogTests(unittest.TestCase):
    def test_command_ids_have_stable_names_and_values(self) -> None:
        expected = {
            "OPEN_PROJECT": "project.open",
            "SAVE_PROJECT": "project.save",
            "EXPORT_ASC": "project.export_asc",
            "LOAD_STREAM_ASC": "data.load_stream_asc",
            "LOAD_FLOW_ASC": "data.load_flow_asc",
            "LOAD_RIVER_SHP": "data.load_river_shp",
            "LOAD_CONFLUENCE_SHP": "data.load_confluence_shp",
            "LOAD_DEM": "data.load_dem",
            "UNDO": "history.undo",
            "REDO": "history.redo",
            "CREATE_SNAPSHOT": "history.create_snapshot",
            "RESTORE_AUTOSAVE": "history.restore_autosave",
            "FIT_CONTENT": "map.fit_content",
            "CENTER_RIVER": "map.center_river",
            "WRITE_FLOW_DIRECTION": "flow.manual.write_direction",
            "SUGGEST_FLOW_DIRECTION": "flow.manual.suggest_direction",
            "APPLY_VECTOR_CORRECTION": "stream.apply_vector_correction",
            "ADD_SELECTED_RIVERS": "flow.objects.add_selected_rivers",
            "ADD_SELECTED_CELL": "flow.objects.add_selected_cell",
            "ADD_POLYGON_RIVERS": "flow.objects.add_polygon_rivers",
            "REMOVE_SELECTED_RIVERS": "flow.objects.remove_selected_rivers",
            "RESET_FLOW_ASSIST": "flow.assist.reset",
            "SET_DOWNSTREAM_OUTLET": "flow.direction.set_outlet",
            "GENERATE_FLOW_PREVIEW": "flow.preview.generate",
            "APPLY_FLOW_PREVIEW": "flow.preview.apply",
            "CLEAR_FLOW_PREVIEW": "flow.preview.clear",
            "BUILD_DEM_CACHE": "dem.cache.build",
            "CANCEL_DEM_CACHE": "dem.cache.cancel",
            "EVALUATE_DEM_PREVIEW": "dem.preview.evaluate",
            "LOCATE_NEXT_UPHILL": "dem.conflict.locate_next",
            "EXPORT_DEM_REPORT": "dem.report.export_all",
            "EXPORT_UPHILL_CONFLICTS": "dem.report.export_conflicts",
        }
        actual = {name: item.value for name, item in CommandId.__members__.items()}

        self.assertEqual(actual, expected)
        self.assertEqual(len(actual.values()), len(set(actual.values())))

    def test_catalog_contains_every_command_id_once(self) -> None:
        expected_ids = set(CommandId)

        self.assertEqual(set(COMMANDS), expected_ids)
        self.assertEqual(
            {item.command_id for item in COMMANDS.values()},
            expected_ids,
        )

    def test_command_labels_are_unique(self) -> None:
        labels = [item.label for item in COMMANDS.values()]

        self.assertEqual(len(labels), len(set(labels)))

    def test_mutating_command_set_is_stable(self) -> None:
        expected = {
            CommandId.UNDO,
            CommandId.REDO,
            CommandId.RESTORE_AUTOSAVE,
            CommandId.WRITE_FLOW_DIRECTION,
            CommandId.APPLY_VECTOR_CORRECTION,
            CommandId.APPLY_FLOW_PREVIEW,
        }

        self.assertEqual(
            {command_id for command_id, command in COMMANDS.items() if command.mutates_data},
            expected,
        )

    def test_commands_reject_external_assignment(self) -> None:
        with self.assertRaises(TypeError):
            COMMANDS[CommandId.OPEN_PROJECT] = COMMANDS[CommandId.OPEN_PROJECT]

    def test_commands_reject_external_deletion(self) -> None:
        command = COMMANDS[CommandId.OPEN_PROJECT]
        try:
            with self.assertRaises(TypeError):
                del COMMANDS[CommandId.OPEN_PROJECT]
        finally:
            if CommandId.OPEN_PROJECT not in COMMANDS:
                COMMANDS[CommandId.OPEN_PROJECT] = command

    def test_preview_and_reset_commands_explain_their_scope(self) -> None:
        preview = get_command(CommandId.GENERATE_FLOW_PREVIEW)
        apply = get_command(CommandId.APPLY_FLOW_PREVIEW)
        clear = get_command(CommandId.CLEAR_FLOW_PREVIEW)
        reset = get_command(CommandId.RESET_FLOW_ASSIST)

        self.assertFalse(preview.mutates_data)
        self.assertTrue(apply.mutates_data)
        self.assertFalse(clear.mutates_data)
        self.assertFalse(reset.mutates_data)
        self.assertIn("不修改", preview.tooltip)
        self.assertIn("写入", apply.tooltip)
        self.assertIn("保留订正对象", clear.tooltip)
        self.assertIn("不回滚", reset.tooltip)

    def test_renamed_commands_use_approved_labels(self) -> None:
        expected = {
            CommandId.FIT_CONTENT: "适配内容",
            CommandId.CENTER_RIVER: "居中河流线",
            CommandId.WRITE_FLOW_DIRECTION: "写入所选方向",
            CommandId.SUGGEST_FLOW_DIRECTION: "建议方向",
            CommandId.APPLY_VECTOR_CORRECTION: "按河流线修正",
            CommandId.ADD_SELECTED_RIVERS: "加入所选河道",
            CommandId.REMOVE_SELECTED_RIVERS: "移除所选河道",
            CommandId.SET_DOWNSTREAM_OUTLET: "设为下游出口",
        }

        for command_id, label in expected.items():
            self.assertEqual(get_command(command_id).label, label)


if __name__ == "__main__":
    unittest.main()
