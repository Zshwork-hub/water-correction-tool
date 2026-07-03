from __future__ import annotations


class FlowStatusMixin:
    def update_mode_status(self) -> None:
        if not hasattr(self, "mode_status_var"):
            return
        mode_text = "订正河道" if self.mode_var.get() == "stream" else "订正流向"
        tool_text = "画笔" if self.tool_var.get() == "brush" else "橡皮擦" if self.tool_var.get() == "eraser" else self.tool_var.get()
        locked_count = len(self._locked_flow_cells_set()) if hasattr(self, "confirmed_flow_segment_cells") else 0
        if self.flow_preview_kind == "river_skeleton":
            preview_text = f"河道流向预览 需修改 {len(self.flow_preview_ops)} / 已一致 {len(self.flow_preview_unchanged_ops)}"
        elif self.flow_preview_kind == "confluence":
            preview_text = f"周边汇流预览 需修改 {len(self.flow_preview_ops)} / 已一致 {len(self.flow_preview_unchanged_ops)}"
        elif self.flow_preview_ops:
            preview_text = f"流向预览 {len(self.flow_preview_ops)} 个像元"
        else:
            preview_text = "无预览"
        outlet_text = f"出口 {self.flow_skeleton_outlet}" if self.flow_skeleton_outlet is not None else "未设出口"
        autosave_text = "开启" if self.autosave_var.get() else "关闭"
        stream_loaded = "已加载" if self.stream_raster is not None else "未加载"
        flow_loaded = "已加载" if self.flow_raster is not None else "未加载"
        range_loaded = "，范围SHP已加载" if self.confluence_polygon_layer is not None else ""
        self.mode_status_var.set(f"当前模式：{mode_text}")
        self.tool_status_var.set(f"当前工具：{tool_text}  快捷键 {self._shortcut_label('brush')}=画笔 / {self._shortcut_label('eraser')}=橡皮擦")
        self.flow_status_var.set(f"流向辅助：锁定 {locked_count} 个河道像元，{outlet_text}，{preview_text}{range_loaded}；{self._flow_next_step_text()}")
        self.session_status_var.set(f"数据：河道{stream_loaded}，流向{flow_loaded}；自动保存{autosave_text}")

    def _flow_apply_button_text(self) -> str:
        if self.flow_preview_kind == "river_skeleton":
            return "应用河道流向"
        if self.flow_preview_kind == "confluence":
            return "应用周边汇流"
        if self.flow_preview_kind == "segment":
            return "应用河道流向"
        return "应用预览"

    def _update_flow_assist_text(self) -> None:
        preview = len(self.flow_preview_ops)
        unchanged = len(self.flow_preview_unchanged_ops)
        locked_cells = sum(len(cells) for cells in self.confirmed_flow_segment_cells.values())
        if locked_cells:
            selected = f"已锁定河道 {len(self.confirmed_flow_segments)} 组 / {locked_cells} 像元"
        else:
            selected = "未锁定河道"
        outlet = f"出口 {self.flow_skeleton_outlet}" if self.flow_skeleton_outlet is not None else "未设出口"
        preview_label = "河道预览" if self.flow_preview_kind == "river_skeleton" else "周边预览"
        max_distance = int(self.confluence_max_distance_var.get())
        distance_text = "不限距" if max_distance <= 0 else f"最大距 {max_distance}"
        if self.flow_preview_kind in {"confluence", "river_skeleton"}:
            preview_detail = f"{preview_label} 需修改 {preview} / 已一致 {unchanged}"
        else:
            preview_detail = f"{preview_label} {preview} 个像元"
        self.flow_assist_var.set(
            f"{selected}  {outlet}  汇流模式 {self.confluence_mode_var.get()}  {distance_text}  {preview_detail}\n"
            f"{self._flow_next_step_text()}"
        )

    def _flow_next_step_text(self) -> str:
        if self.stream_raster is None or self.flow_raster is None:
            return "下一步：先加载河道 ASC 和流向 ASC。"
        if self.mode_var.get() != "flow":
            return "下一步：切换到“订正流向”后使用流向辅助。"
        locked_cells = self._locked_flow_cells_set()
        if not locked_cells:
            return "下一步：右键单点或拖框选择目标河道，然后点击“锁定选区河道”。"
        if self.flow_preview_kind:
            if self.flow_preview_ops:
                return f"下一步：点击“{self._flow_apply_button_text()}”写入橙色像元，或“清除当前预览”后重新计算。"
            if self.flow_preview_unchanged_ops:
                return "下一步：当前预览没有需修改像元，可“清除当前预览”或调整范围后重试。"
            return "下一步：当前没有可预览像元，可调整锁定河道、出口或汇流范围。"
        if self.flow_skeleton_outlet is None:
            if self.selected_flow_cell in locked_cells:
                return "下一步：点击“设为出口”，再预览河道流向。"
            return "下一步：右键单点选择已锁定河道上的出口像元。"
        return "下一步：点击“预览河道流向”，应用后再预览周边汇流。"
