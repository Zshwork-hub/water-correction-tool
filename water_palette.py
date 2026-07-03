from __future__ import annotations

import json
from typing import Dict, Tuple

from tkinter import messagebox, simpledialog

from water_core import DIR_ORDER, direction_text
from water_ui import PaletteEditorDialog


RGBA = Tuple[int, int, int, int]

ASSIST_PALETTE_ITEMS = [
    ("预览需修改-填充", "preview_change_fill"),
    ("预览需修改-边框", "preview_change_outline"),
    ("预览需修改-箭头", "preview_change_arrow"),
    ("预览已一致-填充", "preview_same_fill"),
    ("预览已一致-边框", "preview_same_outline"),
    ("预览已一致-箭头", "preview_same_arrow"),
    ("锁定河道-线", "locked_line"),
    ("锁定河道-填充", "locked_fill"),
    ("当前选中-线", "selected_line"),
    ("当前选中-填充", "selected_fill"),
    ("框选区域-边框", "region_outline"),
    ("框选区域-填充", "region_fill"),
    ("源头标记-填充", "source_fill"),
    ("源头标记-边框", "source_outline"),
    ("出口标记-填充", "outlet_fill"),
    ("出口标记-边框", "outlet_outline"),
    ("节点标记-填充", "node_fill"),
    ("节点标记-边框", "node_outline"),
]


class PaletteMixin:
    def _palette_color_state(self) -> Dict[str, object]:
        return {
            "stream_palette": {k: list(v) for k, v in self.stream_palette.items()},
            "flow_palette": {str(k): list(v) for k, v in self.flow_palette.items()},
            "vector_color": list(self.vector_color),
            "confluence_polygon_color": list(self.confluence_polygon_color),
            "assist_palette": {k: list(v) for k, v in self.assist_palette.items()},
        }

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

    def pick_assist_palette(self) -> None:
        dialog = PaletteEditorDialog(
            self,
            "辅助标记颜色",
            [(label, self.assist_palette[key]) for label, key in ASSIST_PALETTE_ITEMS],
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        for label, key in ASSIST_PALETTE_ITEMS:
            self.assist_palette[key] = dialog.result[label]
        self.render(full=True)

    def _palette_state(self) -> Dict[str, object]:
        state = {
            "show_grid": self.show_grid_var.get(),
            "show_scale": self.show_scale_var.get(),
            "show_flow_arrows": self.show_flow_arrows_var.get(),
            "compare_original": self.compare_original_var.get(),
            "show_confluence_polygon": self.show_confluence_polygon_var.get(),
            "confluence_polygon_width": int(self.confluence_polygon_width_var.get()),
            "autosave": self.autosave_var.get(),
        }
        state.update(self._palette_color_state())
        return state

    def _apply_palette_state(self, state: Dict[str, object]) -> None:
        stream = state.get("stream_palette")
        if isinstance(stream, dict):
            for key in ("nodata", "river", "background"):
                value = stream.get(key)
                if isinstance(value, (list, tuple)) and len(value) == 4:
                    self.stream_palette[key] = tuple(int(v) for v in value)
        flow = state.get("flow_palette")
        if isinstance(flow, dict):
            for key, value in flow.items():
                try:
                    code = int(key)
                except Exception:
                    continue
                if isinstance(value, (list, tuple)) and len(value) == 4:
                    self.flow_palette[code] = tuple(int(v) for v in value)
        vector_color = state.get("vector_color")
        if isinstance(vector_color, (list, tuple)) and len(vector_color) == 4:
            self.vector_color = tuple(int(v) for v in vector_color)
        confluence_polygon_color = state.get("confluence_polygon_color")
        if isinstance(confluence_polygon_color, (list, tuple)) and len(confluence_polygon_color) == 4:
            self.confluence_polygon_color = tuple(int(v) for v in confluence_polygon_color)
        assist = state.get("assist_palette")
        if isinstance(assist, dict):
            for key, value in assist.items():
                if key in self.assist_palette and isinstance(value, (list, tuple)) and len(value) == 4:
                    self.assist_palette[key] = tuple(int(v) for v in value)
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
        name = name.strip()
        if not name:
            return
        if name in self.palette_presets and not messagebox.askyesno("覆盖预设", f"预设“{name}”已存在，是否覆盖？", parent=self):
            return
        self.palette_presets[name] = self._palette_state()
        self._save_palette_presets()
        self._refresh_palette_preset_list()
        self.preset_var.set(name)
        self.info_var.set(f"已保存预设 {name}")

    def load_palette_preset_dialog(self) -> None:
        if not self.palette_presets:
            messagebox.showinfo("提示", "暂无可加载的预设。")
            return
        name = self.preset_var.get().strip()
        if not name or name not in self.palette_presets:
            messagebox.showinfo("提示", "请先在配色预设下拉框中选择一个预设。", parent=self)
            return
        self._apply_palette_state(self.palette_presets[name])
        self.render(full=True)
        self.preset_var.set(name)
        self.info_var.set(f"已加载预设 {name}")

    def delete_palette_preset_dialog(self) -> None:
        if not self.palette_presets:
            messagebox.showinfo("提示", "暂无可删除的预设。", parent=self)
            return
        name = self.preset_var.get().strip()
        if not name or name not in self.palette_presets:
            messagebox.showinfo("提示", "请先在配色预设下拉框中选择一个预设。", parent=self)
            return
        if not messagebox.askyesno("删除预设", f"是否删除配色预设“{name}”？\n当前显示不会改变。", parent=self):
            return
        del self.palette_presets[name]
        self._save_palette_presets()
        self.preset_var.set("")
        self._refresh_palette_preset_list()
        self.info_var.set(f"已删除预设 {name}")

    def reset_palette_defaults(self) -> None:
        if not messagebox.askyesno("恢复默认颜色", "是否恢复默认颜色？显示开关和数据不会改变。", parent=self):
            return
        self._apply_palette_state(self.default_palette_state)
        self.render(full=True)
        self.info_var.set("已恢复默认颜色")

    def _refresh_palette_preset_list(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        names = sorted(self.palette_presets.keys())
        self.preset_combo.configure(values=names)
        current = self.preset_var.get()
        if current and current not in self.palette_presets:
            self.preset_var.set("")

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
        self._refresh_palette_preset_list()
