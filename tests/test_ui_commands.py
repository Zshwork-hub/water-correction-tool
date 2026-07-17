from __future__ import annotations

import unittest

from water_tool.water_ui_commands import COMMANDS, CommandId, get_command


class UiCommandCatalogTests(unittest.TestCase):
    def test_command_ids_are_complete_and_unique(self) -> None:
        expected_names = {
            "OPEN_PROJECT",
            "SAVE_PROJECT",
            "EXPORT_ASC",
            "LOAD_STREAM_ASC",
            "LOAD_FLOW_ASC",
            "LOAD_RIVER_SHP",
            "LOAD_CONFLUENCE_SHP",
            "LOAD_DEM",
            "UNDO",
            "REDO",
            "CREATE_SNAPSHOT",
            "RESTORE_AUTOSAVE",
            "FIT_CONTENT",
            "CENTER_RIVER",
            "WRITE_FLOW_DIRECTION",
            "SUGGEST_FLOW_DIRECTION",
            "APPLY_VECTOR_CORRECTION",
            "ADD_SELECTED_RIVERS",
            "ADD_SELECTED_CELL",
            "ADD_POLYGON_RIVERS",
            "REMOVE_SELECTED_RIVERS",
            "RESET_FLOW_ASSIST",
            "SET_DOWNSTREAM_OUTLET",
            "GENERATE_FLOW_PREVIEW",
            "APPLY_FLOW_PREVIEW",
            "CLEAR_FLOW_PREVIEW",
            "BUILD_DEM_CACHE",
            "CANCEL_DEM_CACHE",
            "EVALUATE_DEM_PREVIEW",
            "LOCATE_NEXT_UPHILL",
            "EXPORT_DEM_REPORT",
            "EXPORT_UPHILL_CONFLICTS",
        }
        values = [item.value for item in CommandId.__members__.values()]

        self.assertEqual(set(CommandId.__members__), expected_names)
        self.assertEqual(len(CommandId.__members__), 32)
        self.assertEqual(len(values), len(set(values)))

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
