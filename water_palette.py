from __future__ import annotations

import json
from typing import Dict, Tuple

from tkinter import messagebox, simpledialog

from water_core import DIR_ORDER, direction_text
from water_ui import PaletteEditorDialog


RGBA = Tuple[int, int, int, int]


class PaletteMixin:
    def pick_stream_palette(self) -> None:
        dialog = PaletteEditorDialog(
            self,
            "河道配色",
            [
                ("NoData", self.stream_palette["nodata"]),
                ("河道", self.stream_palette["river"]),
                ("背景", self.stream_palette["background"]),
            ],
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.stream_palette["nodata"] = dialog.result["NoData"]
        self.stream_palette["river"] = dialog.result["河道"]
        self.stream_palette["background"] = dialog.result["背景"]
        self.render(full=True)

    def pick_flow_palette(self) -> None:
        dialog = PaletteEditorDialog(
            self,
            "流向配色",
            [(f"{code} {direction_text(code)}", self.flow_palette.get(code, (200, 200, 200, 255))) for code in DIR_ORDER],
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        for code in DIR_ORDER:
            self.flow_palette[code] = dialog.result[f"{code} {direction_text(code)}"]
        self.render(full=True)

    def pick_vector_color(self) -> None:
        dialog = PaletteEditorDialog(self, "矢量颜色", [("矢量线", self.vector_color)])
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.vector_color = dialog.result["矢量线"]
        self.render(full=True)

    def pick_confluence_polygon_color(self) -> None:
        dialog = PaletteEditorDialog(self, "汇流范围颜色", [("范围边界", self.confluence_polygon_color)])
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.confluence_polygon_color = dialog.result["范围边界"]
        self.render(full=True)

    def _palette_state(self) -> Dict[str, object]:
        return {
            "stream_palette": {k: list(v) for k, v in self.stream_palette.items()},
            "flow_palette": {str(k): list(v) for k, v in self.flow_palette.items()},
            "vector_color": list(self.vector_color),
            "confluence_polygon_color": list(self.confluence_polygon_color),
            "show_grid": self.show_grid_var.get(),
            "show_scale": self.show_scale_var.get(),
            "show_flow_arrows": self.show_flow_arrows_var.get(),
            "compare_original": self.compare_original_var.get(),
            "show_confluence_polygon": self.show_confluence_polygon_var.get(),
            "confluence_polygon_width": int(self.confluence_polygon_width_var.get()),
            "autosave": self.autosave_var.get(),
        }

    def _apply_palette_state(self, state: Dict[str, object]) -> None:
        stream = state.get("stream_palette")
        if isinstance(stream, dict):
            for key in ("nodata", "river", "background"):
                value = stream.get(key)
                if isinstance(value, list) and len(value) == 4:
                    self.stream_palette[key] = tuple(int(v) for v in value)
        flow = state.get("flow_palette")
        if isinstance(flow, dict):
            for key, value in flow.items():
                try:
                    code = int(key)
                except Exception:
                    continue
                if isinstance(value, list) and len(value) == 4:
                    self.flow_palette[code] = tuple(int(v) for v in value)
        vector_color = state.get("vector_color")
        if isinstance(vector_color, list) and len(vector_color) == 4:
            self.vector_color = tuple(int(v) for v in vector_color)
        confluence_polygon_color = state.get("confluence_polygon_color")
        if isinstance(confluence_polygon_color, list) and len(confluence_polygon_color) == 4:
            self.confluence_polygon_color = tuple(int(v) for v in confluence_polygon_color)
        self.show_grid_var.set(bool(state.get("show_grid", self.show_grid_var.get())))
        self.show_scale_var.set(bool(state.get("show_scale", self.show_scale_var.get())))
        self.show_flow_arrows_var.set(bool(state.get("show_flow_arrows", self.show_flow_arrows_var.get())))
        self.compare_original_var.set(bool(state.get("compare_original", self.compare_original_var.get())))
        self.show_confluence_polygon_var.set(bool(state.get("show_confluence_polygon", self.show_confluence_polygon_var.get())))
        self.confluence_polygon_width_var.set(int(state.get("confluence_polygon_width", self.confluence_polygon_width_var.get())))
        self.autosave_var.set(bool(state.get("autosave", self.autosave_var.get())))

    def save_palette_preset_dialog(self) -> None:
        name = simpledialog.askstring("保存预设", "请输入预设名称：", parent=self)
        if not name:
            return
        self.palette_presets[name] = self._palette_state()
        self._save_palette_presets()
        self.preset_var.set(name)
        self.info_var.set(f"已保存预设 {name}")

    def load_palette_preset_dialog(self) -> None:
        if not self.palette_presets:
            messagebox.showinfo("提示", "暂无可加载的预设。")
            return
        names = list(self.palette_presets.keys())
        name = simpledialog.askstring("加载预设", f"可用预设：{', '.join(names)}\n请输入名称：", parent=self)
        if not name or name not in self.palette_presets:
            return
        self._apply_palette_state(self.palette_presets[name])
        self.render(full=True)
        self.preset_var.set(name)
        self.info_var.set(f"已加载预设 {name}")

    def _save_palette_presets(self) -> None:
        payload = {"presets": self.palette_presets}
        self._presets_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_palette_presets(self) -> None:
        if not self._presets_path.exists():
            return
        try:
            payload = json.loads(self._presets_path.read_text(encoding="utf-8"))
            presets = payload.get("presets", {})
            if isinstance(presets, dict):
                self.palette_presets = presets
        except Exception:
            self.palette_presets = {}
