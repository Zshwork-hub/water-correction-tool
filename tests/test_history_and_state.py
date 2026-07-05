from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from water_tool.water_core import AscHeader, RasterData
from water_tool.water_history import EditingHistoryMixin
from water_tool.water_state import FlowPreviewState, FlowStateMixin


def tiny_header() -> AscHeader:
    raw = [
        "ncols 2\n",
        "nrows 2\n",
        "xllcorner 0\n",
        "yllcorner 0\n",
        "cellsize 1\n",
        "NODATA_value -9999\n",
    ]
    return AscHeader(
        raw,
        {
            "ncols": 2,
            "nrows": 2,
            "xllcorner": 0,
            "yllcorner": 0,
            "cellsize": 1,
            "nodata_value": -9999,
        },
    )


class DummyListbox:
    def __init__(self, selection=(0,)) -> None:
        self.selection = selection
        self.items = []

    def curselection(self):
        return self.selection

    def delete(self, *_args) -> None:
        self.items.clear()

    def insert(self, *_args) -> None:
        self.items.append(_args[-1])


class DummyVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class HistoryHarness(FlowStateMixin, EditingHistoryMixin):
    def __init__(self) -> None:
        self._init_flow_state()
        header = tiny_header()
        self.flow_raster = RasterData(Path("flow.asc"), header, np.array([[1, 2], [4, 8]], dtype=np.int32))
        snapshot = RasterData(Path("flow.asc"), header, np.array([[1, 2], [4, 16]], dtype=np.int32))
        self.snapshots = {"flow": [("snap1", snapshot)]}
        self.histories = {"flow": []}
        self.redo_stacks = {"flow": []}
        self.snapshot_list = DummyListbox()
        self.info_var = DummyVar()
        self.logged_batches = []
        self.render_calls = []

    def active_mode(self) -> str:
        return "flow"

    def get_active_raster(self):
        return self.flow_raster

    def _invalidate_viewport_cache(self) -> None:
        pass

    def render(self, full: bool = False) -> None:
        self.render_calls.append(full)

    def log_batch(self, batch) -> None:
        self.logged_batches.append(batch)


class FlowStateHarness(FlowStateMixin):
    def __init__(self) -> None:
        self._init_flow_state()


class HistoryAndStateTests(unittest.TestCase):
    def test_flow_preview_state_exposes_preview_metadata(self) -> None:
        state = FlowPreviewState.create(
            [(1, 1, 4), (1, 2, 8)],
            [(2, 2, 16)],
            label="河道本体流向",
            kind="river_skeleton",
            segment_key=((1, 1), (2, 2)),
        )

        self.assertTrue(state.has_preview())
        self.assertTrue(state.has_apply_ops())
        self.assertEqual(state.change_count, 2)
        self.assertEqual(state.unchanged_count, 1)
        self.assertEqual(state.apply_button_text(), "应用河道流向")
        self.assertEqual(state.apply_tool, "river_skeleton")
        self.assertEqual(state.apply_note, "locked river skeleton flow")
        self.assertEqual(state.status_label(), "河道流向预览")
        self.assertIn("修改 2", state.applied_message(2))

    def test_flow_preview_state_handles_unchanged_only_preview(self) -> None:
        state = FlowPreviewState.create(
            [],
            [(2, 2, 16)],
            label="范围SHP汇流",
            kind="confluence",
        )

        self.assertTrue(state.has_preview())
        self.assertFalse(state.has_apply_ops())
        self.assertEqual(state.change_count, 0)
        self.assertEqual(state.unchanged_count, 1)
        self.assertEqual(state.apply_button_text(), "应用周边汇流")
        self.assertEqual(state.apply_tool, "manual_assist")
        self.assertEqual(state.apply_note, "manual confluence flow preview")

    def test_flow_preview_segment_uses_river_apply_path(self) -> None:
        state = FlowPreviewState.create(
            [(1, 1, 4)],
            label="河段预览",
            kind="segment",
        )

        self.assertEqual(state.apply_button_text(), "应用河道流向")
        self.assertEqual(state.apply_tool, "river_skeleton")
        self.assertEqual(state.apply_note, "manual segment flow preview")

    def test_legacy_flow_preview_properties_update_state_object(self) -> None:
        app = FlowStateHarness()

        app.flow_preview_ops = [(1, 1, 4)]
        app.flow_preview_unchanged_ops = [(1, 0, 1)]
        app.flow_preview_kind = "river_skeleton"
        app.flow_preview_segment_key = ((0, 0), (1, 1))

        self.assertEqual(app.flow_preview_state.ops, [(1, 1, 4)])
        self.assertEqual(app.flow_preview_state.unchanged_ops, [(1, 0, 1)])
        self.assertEqual(app.flow_preview_state.kind, "river_skeleton")
        self.assertEqual(app.flow_preview_state.apply_tool, "river_skeleton")
        self.assertEqual(app.flow_preview_state.apply_note, "locked river skeleton flow")
        self.assertEqual(app.flow_preview_state.segment_key, ((0, 0), (1, 1)))

    def test_snapshot_restore_is_undoable_and_redoable(self) -> None:
        app = HistoryHarness()

        app.restore_selected_snapshot()
        self.assertEqual(int(app.flow_raster.data[1, 1]), 16)
        self.assertEqual(len(app.histories["flow"]), 1)
        self.assertEqual(len(app.redo_stacks["flow"]), 0)
        self.assertEqual(len(app.logged_batches), 1)

        app.undo()
        self.assertEqual(int(app.flow_raster.data[1, 1]), 8)
        self.assertEqual(len(app.histories["flow"]), 0)
        self.assertEqual(len(app.redo_stacks["flow"]), 1)

        app.redo()
        self.assertEqual(int(app.flow_raster.data[1, 1]), 16)
        self.assertEqual(len(app.histories["flow"]), 1)
        self.assertEqual(len(app.redo_stacks["flow"]), 0)

    def test_flow_state_reset_helpers_clear_expected_fields(self) -> None:
        app = FlowStateHarness()
        app.selected_flow_cell = (1, 1)
        app.selected_flow_region = (0, 1, 0, 1)
        app.selected_flow_segment = object()
        app.flow_segment_downstream = (2, 2)
        app.flow_preview_ops = [(1, 1, 4)]
        app.flow_preview_unchanged_ops = [(1, 0, 1)]
        app.flow_preview_kind = "confluence"
        app.flow_preview_segment_key = ((0, 0), (1, 1))
        app.confirmed_flow_segments = {((0, 0), (1, 1)): (1, 1)}
        app.confirmed_flow_segment_cells = {((0, 0), (1, 1)): [(0, 0), (1, 1)]}
        app.flow_skeleton_outlet = (1, 1)

        app._reset_flow_preview_state()
        self.assertIsInstance(app.flow_preview_state, FlowPreviewState)
        self.assertEqual(app.flow_preview_ops, [])
        self.assertEqual(app.flow_preview_unchanged_ops, [])
        self.assertEqual(app.flow_preview_kind, "")
        self.assertIsNone(app.flow_preview_segment_key)

        app._reset_flow_selection_state(clear_cell=False, clear_region=True, clear_segment=True)
        self.assertEqual(app.selected_flow_cell, (1, 1))
        self.assertIsNone(app.selected_flow_region)
        self.assertIsNone(app.selected_flow_segment)
        self.assertIsNone(app.flow_segment_downstream)

        app._reset_flow_lock_state()
        self.assertEqual(app.confirmed_flow_segments, {})
        self.assertEqual(app.confirmed_flow_segment_cells, {})
        self.assertIsNone(app.flow_skeleton_outlet)


if __name__ == "__main__":
    unittest.main()
