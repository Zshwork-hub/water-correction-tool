from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import tkinter as tk

from water_core import ChangeBatch


class EditingHistoryMixin:
    def take_snapshot(self, silent: bool = False) -> None:
        raster = self.get_active_raster()
        if raster is None:
            return
        mode = self.active_mode()
        tag = f"{mode}_{Path(raster.path).stem}_{len(self.snapshots[mode]) + 1}"
        self.snapshots[mode].append((tag, raster.copy()))
        if len(self.snapshots[mode]) > 50:
            self.snapshots[mode] = self.snapshots[mode][-50:]
        self.refresh_snapshot_list()
        if not silent:
            self.info_var.set(f"已创建快照 {tag}")

    def refresh_snapshot_list(self) -> None:
        self.snapshot_list.delete(0, tk.END)
        for i, (name, _) in enumerate(self.snapshots[self.active_mode()]):
            self.snapshot_list.insert(tk.END, f"{i + 1}. {name}")

    def restore_selected_snapshot(self) -> None:
        selection = self.snapshot_list.curselection()
        if not selection:
            return
        idx = selection[0]
        mode = self.active_mode()
        snapshots = self.snapshots[mode]
        if idx >= len(snapshots):
            return
        name, snap = snapshots[idx]
        current = self.get_active_raster()
        if current is None:
            return
        batch = ChangeBatch(mode=mode, tool="snapshot_restore", note=f"restore snapshot {name}")
        if current.data.shape == snap.data.shape:
            rows, cols = np.where(current.data != snap.data)
            for row, col in zip(rows.tolist(), cols.tolist()):
                old = int(current.data[row, col])
                new = int(snap.data[row, col])
                batch.add(int(row), int(col), old, new)
        if mode == "stream":
            self.stream_raster = snap.copy()
            self._clear_flow_skeleton_state()
        else:
            self.flow_raster = snap.copy()
        if batch.ops:
            self.histories[mode].append(batch)
            if len(self.histories[mode]) > 50:
                self.histories[mode] = self.histories[mode][-50:]
            self.redo_stacks[mode].clear()
            self.log_batch(batch)
        self.selected_flow_cell = None
        self.selected_flow_region = None
        self._invalidate_viewport_cache()
        self.render(full=True)
        if batch.ops:
            self.info_var.set(f"已恢复快照 {name}，可撤销本次恢复")
        else:
            self.info_var.set(f"已恢复快照 {name}，当前数据与快照一致")

    def undo(self) -> None:
        history = self.histories[self.active_mode()]
        if not history:
            return
        batch = history.pop()
        raster = self.get_active_raster()
        if raster is None:
            return
        batch.undo(raster)
        self.redo_stacks[self.active_mode()].append(batch)
        self._full_render_requested = True
        self.selected_flow_cell = None
        self.selected_flow_region = None
        if batch.mode == "stream":
            self._clear_flow_skeleton_state()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.info_var.set(f"已撤销 {len(batch.ops)} 个像元修改")

    def redo(self) -> None:
        redo_stack = self.redo_stacks[self.active_mode()]
        if not redo_stack:
            return
        batch = redo_stack.pop()
        raster = self.get_active_raster()
        if raster is None:
            return
        batch.apply(raster)
        self.histories[self.active_mode()].append(batch)
        self._full_render_requested = True
        self.selected_flow_cell = None
        self.selected_flow_region = None
        if batch.mode == "stream":
            self._clear_flow_skeleton_state()
        self._invalidate_viewport_cache()
        self.render(full=True)
        self.info_var.set(f"已重做 {len(batch.ops)} 个像元修改")

    def log_batch(self, batch: ChangeBatch) -> None:
        with self.log_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for op in batch.ops:
                writer.writerow([batch.created_at, batch.mode, batch.tool, op.row, op.col, op.old, op.new, batch.note])
