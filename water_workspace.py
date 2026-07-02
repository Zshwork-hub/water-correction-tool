from __future__ import annotations

import csv
import json
from pathlib import Path

from tkinter import filedialog, messagebox

from water_core import parse_asc, parse_shapefile_lines


class WorkspaceMixin:
    def _setup_log_file(self) -> None:
        if not self.log_path.exists():
            with self.log_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "mode", "tool", "row", "col", "old_value", "new_value", "note"])

    def _prefer_path(self, relative_path: str) -> Path:
        candidate = (self.workspace_dir / relative_path).resolve()
        if candidate.exists():
            return candidate
        return (self.base_dir / relative_path).resolve()

    def _load_workspace_dir(self) -> Path:
        if self.config_path.exists():
            try:
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
                stored = payload.get("workspace_dir")
                if isinstance(stored, str) and stored:
                    path = Path(stored)
                    if path.exists():
                        return path.resolve()
            except Exception:
                pass
        chosen = filedialog.askdirectory(title="请选择工作目录")
        if chosen:
            path = Path(chosen).resolve()
            self._save_workspace_dir(path)
            return path
        return self.base_dir

    def _save_workspace_dir(self, path: Path) -> None:
        self.config_path.write_text(json.dumps({"workspace_dir": str(path.resolve())}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_defaults(self) -> None:
        try:
            if self.default_stream.exists():
                self.stream_raster = parse_asc(self.default_stream)
                self.original_stream_raster = self.stream_raster.copy()
                self.stream_file_var.set(self._store_path(self.default_stream))
            if self.default_flow.exists():
                self.flow_raster = parse_asc(self.default_flow)
                self.original_flow_raster = self.flow_raster.copy()
                self.flow_file_var.set(self._store_path(self.default_flow))
            if self.default_shp.exists():
                self.vector_layer = parse_shapefile_lines(self.default_shp)
                self.shp_var.set(self._store_path(self.default_shp))
            self._maybe_setup_transformer()
            self.take_snapshot(silent=True)
            self.render(full=True)
        except Exception as exc:
            messagebox.showwarning("初始化提示", f"默认文件加载未完全成功。\n{exc}")
