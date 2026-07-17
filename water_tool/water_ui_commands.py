from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Dict, Mapping


class CommandId(str, Enum):
    OPEN_PROJECT = "project.open"
    SAVE_PROJECT = "project.save"
    EXPORT_ASC = "project.export_asc"
    LOAD_STREAM_ASC = "data.load_stream_asc"
    LOAD_FLOW_ASC = "data.load_flow_asc"
    LOAD_RIVER_SHP = "data.load_river_shp"
    LOAD_CONFLUENCE_SHP = "data.load_confluence_shp"
    LOAD_DEM = "data.load_dem"
    UNDO = "history.undo"
    REDO = "history.redo"
    CREATE_SNAPSHOT = "history.create_snapshot"
    RESTORE_AUTOSAVE = "history.restore_autosave"
    FIT_CONTENT = "map.fit_content"
    CENTER_RIVER = "map.center_river"
    WRITE_FLOW_DIRECTION = "flow.manual.write_direction"
    SUGGEST_FLOW_DIRECTION = "flow.manual.suggest_direction"
    APPLY_VECTOR_CORRECTION = "stream.apply_vector_correction"
    ADD_SELECTED_RIVERS = "flow.objects.add_selected_rivers"
    ADD_SELECTED_CELL = "flow.objects.add_selected_cell"
    ADD_POLYGON_RIVERS = "flow.objects.add_polygon_rivers"
    REMOVE_SELECTED_RIVERS = "flow.objects.remove_selected_rivers"
    RESET_FLOW_ASSIST = "flow.assist.reset"
    SET_DOWNSTREAM_OUTLET = "flow.direction.set_outlet"
    GENERATE_FLOW_PREVIEW = "flow.preview.generate"
    APPLY_FLOW_PREVIEW = "flow.preview.apply"
    CLEAR_FLOW_PREVIEW = "flow.preview.clear"
    BUILD_DEM_CACHE = "dem.cache.build"
    CANCEL_DEM_CACHE = "dem.cache.cancel"
    EVALUATE_DEM_PREVIEW = "dem.preview.evaluate"
    LOCATE_NEXT_UPHILL = "dem.conflict.locate_next"
    EXPORT_DEM_REPORT = "dem.report.export_all"
    EXPORT_UPHILL_CONFLICTS = "dem.report.export_conflicts"


@dataclass(frozen=True)
class CommandDefinition:
    command_id: CommandId
    label: str
    tooltip: str
    mutates_data: bool = False


def _command(command_id: CommandId, label: str, tooltip: str, mutates_data: bool = False) -> CommandDefinition:
    return CommandDefinition(command_id, label, tooltip, mutates_data)


_COMMANDS: Dict[CommandId, CommandDefinition] = {
    item.command_id: item
    for item in [
        _command(CommandId.OPEN_PROJECT, "打开项目", "打开项目并恢复数据路径、显示设置和项目状态。"),
        _command(CommandId.SAVE_PROJECT, "保存项目", "保存当前项目、数据副本和界面设置。"),
        _command(CommandId.EXPORT_ASC, "导出 ASC", "将当前活动栅格导出为 ASC 文件。"),
        _command(CommandId.LOAD_STREAM_ASC, "加载河道 ASC", "加载或替换河道 ASC。"),
        _command(CommandId.LOAD_FLOW_ASC, "加载流向 ASC", "加载或替换流向 ASC。"),
        _command(CommandId.LOAD_RIVER_SHP, "加载河流线 SHP", "加载或替换河流参考线 SHP。"),
        _command(CommandId.LOAD_CONFLUENCE_SHP, "加载汇流范围 SHP", "加载或替换汇流范围面 SHP。"),
        _command(CommandId.LOAD_DEM, "加载 DEM", "加载或替换用于预览审核的 DEM。"),
        _command(CommandId.UNDO, "撤销", "撤销最近一次已应用编辑。", True),
        _command(CommandId.REDO, "重做", "恢复最近一次被撤销的编辑。", True),
        _command(CommandId.CREATE_SNAPSHOT, "创建快照", "创建当前活动栅格的版本快照。"),
        _command(CommandId.RESTORE_AUTOSAVE, "恢复自动保存会话", "恢复最近一次自动保存会话。", True),
        _command(CommandId.FIT_CONTENT, "适配内容", "选择数据或图层并适配到地图窗口。"),
        _command(CommandId.CENTER_RIVER, "居中河流线", "保持当前缩放并将河流线移到地图中央。"),
        _command(CommandId.WRITE_FLOW_DIRECTION, "写入所选方向", "把所选 D8 方向写入当前选中像元。", True),
        _command(CommandId.SUGGEST_FLOW_DIRECTION, "建议方向", "根据相邻流向给出人工参考建议，不修改数据。"),
        _command(CommandId.APPLY_VECTOR_CORRECTION, "按河流线修正", "按河流参考线批量修正河道栅格。", True),
        _command(CommandId.ADD_SELECTED_RIVERS, "加入所选河道", "将当前地图选区内的河道加入订正对象。"),
        _command(CommandId.ADD_SELECTED_CELL, "加入所选像元", "将当前选中的河道像元加入订正对象。"),
        _command(CommandId.ADD_POLYGON_RIVERS, "加入范围内河道", "将汇流范围 SHP 内的河道加入订正对象。"),
        _command(CommandId.REMOVE_SELECTED_RIVERS, "移除所选河道", "只从订正对象中移除当前选区内河道。"),
        _command(CommandId.RESET_FLOW_ASSIST, "重置辅助状态", "清除订正对象、出口和预览，不回滚已应用数据。"),
        _command(CommandId.SET_DOWNSTREAM_OUTLET, "设为下游出口", "将当前选中且已加入的河道像元设为下游出口。"),
        _command(CommandId.GENERATE_FLOW_PREVIEW, "生成预览", "根据当前目标和参数生成临时方向，不修改 FDR。"),
        _command(CommandId.APPLY_FLOW_PREVIEW, "应用预览", "将待修改预览写入 FDR 并创建历史记录。", True),
        _command(CommandId.CLEAR_FLOW_PREVIEW, "清除预览", "只清除临时预览，保留订正对象和出口。"),
        _command(CommandId.BUILD_DEM_CACHE, "生成 DEM 缓存", "为当前订正范围生成 DEM 粗像元缓存。"),
        _command(CommandId.CANCEL_DEM_CACHE, "取消缓存任务", "取消正在运行的 DEM 缓存任务。"),
        _command(CommandId.EVALUATE_DEM_PREVIEW, "使用 DEM 评估预览", "用 DEM 缓存审核当前方向预览，不修改 FDR。"),
        _command(CommandId.LOCATE_NEXT_UPHILL, "定位下一处逆坡", "跳转到下一处 DEM 逆坡冲突。"),
        _command(CommandId.EXPORT_DEM_REPORT, "导出 DEM 评估报告", "导出当前 DEM 评估的完整 CSV。"),
        _command(CommandId.EXPORT_UPHILL_CONFLICTS, "导出逆坡冲突", "只导出 DEM 逆坡冲突 CSV。"),
    ]
}

COMMANDS: Mapping[CommandId, CommandDefinition] = MappingProxyType(_COMMANDS)


def get_command(command_id: CommandId) -> CommandDefinition:
    return COMMANDS[command_id]
