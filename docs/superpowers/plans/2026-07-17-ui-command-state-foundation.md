# UI Command and State Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested command catalog and pure UI state derivation layer, then make the existing interface consume that state without changing its layout or GIS behavior.

**Architecture:** New pure-Python modules define stable command IDs, labels, tooltips, flow-assist facts, derived control state, and status summaries. Existing Tkinter mixins adapt current raster/project state into those pure models; widgets remain in their current locations during this phase, so later UI Shell work can reuse the same contracts without duplicating business rules.

**Tech Stack:** Python 3.9+, dataclasses, enum, Tkinter/ttk, unittest

---

## Scope and Follow-up Plans

This is the first of four implementation plans derived from `docs/superpowers/specs/2026-07-17-ui-interaction-redesign-design.md`.

1. This plan: command catalog and state foundation.
2. Follow-up: global UI Shell and river-correction page.
3. Follow-up: flow-correction interaction consolidation and DEM review.
4. Follow-up: display/history/project panels and complete regression.

This plan intentionally keeps the current layout and existing button callbacks. It creates the contracts required to change those surfaces safely in later plans.

## File Structure

- Create `water_tool/water_ui_commands.py`: stable command IDs, labels, tooltips, mutation metadata, and lookup helpers.
- Create `water_tool/water_ui_model.py`: pure flow-assist facts, derived enablement, current-stage selection, and concise task summaries.
- Modify `water_tool/water_ui_state.py`: adapt current application state into the pure model and consume derived enablement.
- Modify `water_tool/water_flow_status.py`: use the pure summary model instead of rebuilding the same status in multiple methods.
- Modify `water_tool/water_app.py`: initialize a single preview-target variable required by the derived model; do not change layout.
- Create `tests/test_ui_commands.py`: command catalog contract tests.
- Create `tests/test_ui_model.py`: state derivation and summary tests.
- Modify `docs/项目总说明.md`: record the new UI foundation boundary after implementation passes verification.

### Task 1: Add the Stable Command Catalog

**Files:**
- Create: `water_tool/water_ui_commands.py`
- Test: `tests/test_ui_commands.py`

- [ ] **Step 1: Write the failing command-catalog tests**

Create `tests/test_ui_commands.py`:

```python
from __future__ import annotations

import unittest

from water_tool.water_ui_commands import COMMANDS, CommandId, get_command


class UiCommandCatalogTests(unittest.TestCase):
    def test_command_ids_and_labels_are_unique(self) -> None:
        ids = [item.command_id for item in COMMANDS.values()]
        labels = [item.label for item in COMMANDS.values()]

        self.assertEqual(len(ids), len(set(ids)))
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
```

- [ ] **Step 2: Run the test and verify the catalog is missing**

Run:

```powershell
python -B -m unittest tests.test_ui_commands
```

Expected: `ERROR` with `ModuleNotFoundError: No module named 'water_tool.water_ui_commands'`.

- [ ] **Step 3: Implement the command catalog**

Create `water_tool/water_ui_commands.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict


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


COMMANDS: Dict[CommandId, CommandDefinition] = {
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


def get_command(command_id: CommandId) -> CommandDefinition:
    return COMMANDS[command_id]
```

- [ ] **Step 4: Run the command-catalog tests**

Run:

```powershell
python -B -m unittest tests.test_ui_commands
```

Expected: `Ran 3 tests` and `OK`.

- [ ] **Step 5: Commit the catalog**

```powershell
git add -- water_tool/water_ui_commands.py tests/test_ui_commands.py
git commit -m "Add UI command catalog"
```

### Task 2: Derive Flow-Assist UI State from Pure Facts

**Files:**
- Create: `water_tool/water_ui_model.py`
- Test: `tests/test_ui_model.py`

- [ ] **Step 1: Write failing state-derivation tests**

Create `tests/test_ui_model.py`:

```python
from __future__ import annotations

import unittest

from water_tool.water_ui_commands import CommandId
from water_tool.water_ui_model import FlowAssistFacts, FlowAssistStage, derive_flow_assist_state


class UiModelTests(unittest.TestCase):
    def test_missing_data_points_to_project_data(self) -> None:
        state = derive_flow_assist_state(FlowAssistFacts())

        self.assertEqual(state.stage, FlowAssistStage.DATA)
        self.assertEqual(state.summary, "需要加载河道 ASC 和流向 ASC")
        self.assertFalse(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_selected_cell_can_be_added_before_lock_exists(self) -> None:
        facts = FlowAssistFacts(has_stream=True, has_flow=True, has_selected_cell=True)
        state = derive_flow_assist_state(facts)

        self.assertEqual(state.stage, FlowAssistStage.OBJECTS)
        self.assertEqual(state.primary_command, CommandId.ADD_SELECTED_RIVERS)
        self.assertTrue(state.enabled[CommandId.ADD_SELECTED_RIVERS])

    def test_river_preview_requires_outlet(self) -> None:
        facts = FlowAssistFacts(has_stream=True, has_flow=True, locked_count=12, preview_target="river")
        state = derive_flow_assist_state(facts)

        self.assertEqual(state.stage, FlowAssistStage.DIRECTION)
        self.assertEqual(state.primary_command, CommandId.SET_DOWNSTREAM_OUTLET)
        self.assertFalse(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_confluence_preview_only_requires_locked_river(self) -> None:
        facts = FlowAssistFacts(has_stream=True, has_flow=True, locked_count=12, preview_target="confluence")
        state = derive_flow_assist_state(facts)

        self.assertEqual(state.primary_command, CommandId.GENERATE_FLOW_PREVIEW)
        self.assertTrue(state.enabled[CommandId.GENERATE_FLOW_PREVIEW])

    def test_preview_with_changes_prioritizes_apply(self) -> None:
        facts = FlowAssistFacts(
            has_stream=True,
            has_flow=True,
            locked_count=12,
            outlet_set=True,
            preview_target="river",
            preview_exists=True,
            preview_changes=4,
        )
        state = derive_flow_assist_state(facts)

        self.assertEqual(state.stage, FlowAssistStage.REVIEW)
        self.assertEqual(state.primary_command, CommandId.APPLY_FLOW_PREVIEW)
        self.assertTrue(state.enabled[CommandId.CLEAR_FLOW_PREVIEW])

    def test_dem_conflicts_are_reflected_in_summary(self) -> None:
        facts = FlowAssistFacts(
            has_stream=True,
            has_flow=True,
            locked_count=12,
            preview_exists=True,
            preview_changes=4,
            dem_conflicts=3,
        )
        state = derive_flow_assist_state(facts)

        self.assertIn("逆坡冲突 3", state.summary)
        self.assertTrue(state.enabled[CommandId.LOCATE_NEXT_UPHILL])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify the model is missing**

Run:

```powershell
python -B -m unittest tests.test_ui_model
```

Expected: `ERROR` with `ModuleNotFoundError: No module named 'water_tool.water_ui_model'`.

- [ ] **Step 3: Implement the pure UI model**

Create `water_tool/water_ui_model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from .water_ui_commands import CommandId


class FlowAssistStage(str, Enum):
    DATA = "data"
    OBJECTS = "objects"
    DIRECTION = "direction"
    REVIEW = "review"


@dataclass(frozen=True)
class FlowAssistFacts:
    has_stream: bool = False
    has_flow: bool = False
    has_selected_cell: bool = False
    has_selected_region: bool = False
    selection_in_locked: bool = False
    locked_count: int = 0
    outlet_set: bool = False
    preview_target: str = "river"
    preview_exists: bool = False
    preview_changes: int = 0
    dem_cache_ready: bool = False
    dem_running: bool = False
    dem_scores_ready: bool = False
    dem_conflicts: int = 0


@dataclass(frozen=True)
class FlowAssistViewState:
    stage: FlowAssistStage
    primary_command: Optional[CommandId]
    enabled: Dict[CommandId, bool]
    summary: str


def derive_flow_assist_state(facts: FlowAssistFacts) -> FlowAssistViewState:
    has_data = facts.has_stream and facts.has_flow
    locked_ready = facts.locked_count > 0
    has_selection = facts.has_selected_cell or facts.has_selected_region
    can_generate = locked_ready and (facts.preview_target == "confluence" or facts.outlet_set)
    enabled = {
        CommandId.ADD_SELECTED_RIVERS: has_data and has_selection,
        CommandId.ADD_SELECTED_CELL: has_data and facts.has_selected_cell,
        CommandId.REMOVE_SELECTED_RIVERS: locked_ready and has_selection,
        CommandId.RESET_FLOW_ASSIST: locked_ready or facts.preview_exists,
        CommandId.SET_DOWNSTREAM_OUTLET: locked_ready and facts.selection_in_locked,
        CommandId.GENERATE_FLOW_PREVIEW: can_generate,
        CommandId.APPLY_FLOW_PREVIEW: facts.preview_exists and facts.preview_changes > 0,
        CommandId.CLEAR_FLOW_PREVIEW: facts.preview_exists,
        CommandId.BUILD_DEM_CACHE: locked_ready and not facts.dem_running,
        CommandId.CANCEL_DEM_CACHE: facts.dem_running,
        CommandId.EVALUATE_DEM_PREVIEW: facts.preview_exists and facts.dem_cache_ready and not facts.dem_running,
        CommandId.LOCATE_NEXT_UPHILL: facts.dem_conflicts > 0,
        CommandId.EXPORT_DEM_REPORT: facts.dem_scores_ready,
        CommandId.EXPORT_UPHILL_CONFLICTS: facts.dem_conflicts > 0,
    }

    if not has_data:
        return FlowAssistViewState(FlowAssistStage.DATA, None, enabled, "需要加载河道 ASC 和流向 ASC")
    if not locked_ready:
        primary = CommandId.ADD_SELECTED_RIVERS if has_selection else None
        return FlowAssistViewState(FlowAssistStage.OBJECTS, primary, enabled, "尚未确定订正对象")
    if facts.preview_exists:
        primary = CommandId.APPLY_FLOW_PREVIEW if facts.preview_changes > 0 else CommandId.CLEAR_FLOW_PREVIEW
        summary = f"预览待修改 {facts.preview_changes}"
        if facts.dem_conflicts > 0:
            summary += f"，逆坡冲突 {facts.dem_conflicts}"
        return FlowAssistViewState(FlowAssistStage.REVIEW, primary, enabled, summary)
    if facts.preview_target == "river" and not facts.outlet_set:
        return FlowAssistViewState(FlowAssistStage.DIRECTION, CommandId.SET_DOWNSTREAM_OUTLET, enabled, "需要设置下游出口")
    return FlowAssistViewState(FlowAssistStage.DIRECTION, CommandId.GENERATE_FLOW_PREVIEW, enabled, "可以生成方向预览")
```

- [ ] **Step 4: Run the UI-model tests**

Run:

```powershell
python -B -m unittest tests.test_ui_model
```

Expected: `Ran 6 tests` and `OK`.

- [ ] **Step 5: Commit the pure model**

```powershell
git add -- water_tool/water_ui_model.py tests/test_ui_model.py
git commit -m "Add flow assist UI state model"
```

### Task 3: Adapt Existing Application State into Flow-Assist Facts

**Files:**
- Modify: `water_tool/water_app.py:80-120`
- Modify: `water_tool/water_ui_state.py:34-62`
- Test: `tests/test_ui_model.py`

- [ ] **Step 1: Add a failing adapter test**

Append to `tests/test_ui_model.py`:

```python
from water_tool.water_ui_state import build_flow_assist_facts


class FakePreview:
    def has_preview(self) -> bool:
        return True

    change_count = 5
    dem_score_details = [object(), object()]


class UiStateAdapterTests(unittest.TestCase):
    def test_build_flow_assist_facts_preserves_current_app_state(self) -> None:
        facts = build_flow_assist_facts(
            has_stream=True,
            has_flow=True,
            has_selected_cell=True,
            has_selected_region=False,
            selection_in_locked=True,
            locked_count=8,
            outlet_set=True,
            preview_target="confluence",
            preview=FakePreview(),
            dem_cache_ready=True,
            dem_running=False,
            dem_conflicts=2,
        )

        self.assertEqual(facts.locked_count, 8)
        self.assertTrue(facts.preview_exists)
        self.assertEqual(facts.preview_changes, 5)
        self.assertTrue(facts.dem_scores_ready)
        self.assertEqual(facts.dem_conflicts, 2)
```

- [ ] **Step 2: Run the adapter test and verify it fails**

Run:

```powershell
python -B -m unittest tests.test_ui_model
```

Expected: `ImportError` because `build_flow_assist_facts` does not exist.

- [ ] **Step 3: Add the pure adapter function**

At the top of `water_tool/water_ui_state.py`, import the model and add:

```python
from .water_ui_model import FlowAssistFacts, derive_flow_assist_state


def build_flow_assist_facts(
    *,
    has_stream: bool,
    has_flow: bool,
    has_selected_cell: bool,
    has_selected_region: bool,
    selection_in_locked: bool,
    locked_count: int,
    outlet_set: bool,
    preview_target: str,
    preview,
    dem_cache_ready: bool,
    dem_running: bool,
    dem_conflicts: int,
) -> FlowAssistFacts:
    return FlowAssistFacts(
        has_stream=has_stream,
        has_flow=has_flow,
        has_selected_cell=has_selected_cell,
        has_selected_region=has_selected_region,
        selection_in_locked=selection_in_locked,
        locked_count=locked_count,
        outlet_set=outlet_set,
        preview_target=preview_target,
        preview_exists=preview.has_preview(),
        preview_changes=preview.change_count,
        dem_cache_ready=dem_cache_ready,
        dem_running=dem_running,
        dem_scores_ready=bool(getattr(preview, "dem_score_details", [])),
        dem_conflicts=dem_conflicts,
    )
```

- [ ] **Step 4: Add the future preview-target state without changing layout**

In `WaterCorrectionApp.__init__` near the existing `river_flow_mode_var`, add:

```python
self.flow_preview_target_var = tk.StringVar(value="river")
```

The existing preview buttons continue calling their current callbacks. Before `preview_locked_river_flow` runs, set the variable to `"river"`; before `preview_confirmed_confluence` runs, set it to `"confluence"`. Add these assignments at the start of the two existing workflow methods in `water_tool/water_flow_workflow.py`:

```python
self.flow_preview_target_var.set("river")
```

and:

```python
self.flow_preview_target_var.set("confluence")
```

- [ ] **Step 5: Add `_flow_assist_view_state` to `UIStateMixin`**

Add this method to `UIStateMixin`:

```python
def _flow_assist_view_state(self):
    locked_cells = self._locked_flow_cells_set()
    has_selected_cell = self.selected_flow_cell is not None
    has_selected_region = self.selected_flow_region is not None
    selection_in_locked = self.selected_flow_cell in locked_cells if self.selected_flow_cell is not None else False
    facts = build_flow_assist_facts(
        has_stream=self.stream_raster is not None,
        has_flow=self.flow_raster is not None,
        has_selected_cell=has_selected_cell,
        has_selected_region=has_selected_region,
        selection_in_locked=selection_in_locked,
        locked_count=len(locked_cells),
        outlet_set=self.flow_skeleton_outlet is not None,
        preview_target=self.flow_preview_target_var.get(),
        preview=self.flow_preview_state,
        dem_cache_ready=getattr(self, "dem_cache_arrays", None) is not None and getattr(self, "dem_cache_metadata", None) is not None,
        dem_running=self._dem_cache_is_running() if hasattr(self, "_dem_cache_is_running") else False,
        dem_conflicts=len(self._dem_conflict_scores()) if hasattr(self, "_dem_conflict_scores") else 0,
    )
    return derive_flow_assist_state(facts)
```

- [ ] **Step 6: Run focused and full tests**

Run:

```powershell
python -B -m unittest tests.test_ui_model
python -B -m unittest discover -s tests
```

Expected: focused tests pass; full suite reports `OK` with no regression.

- [ ] **Step 7: Commit the adapter**

```powershell
git add -- water_tool/water_app.py water_tool/water_ui_state.py water_tool/water_flow_workflow.py tests/test_ui_model.py
git commit -m "Adapt application state for UI model"
```

### Task 4: Drive Existing Flow-Control Enablement from the Pure Model

**Files:**
- Modify: `water_tool/water_ui_state.py:34-62`
- Test: `tests/test_ui_model.py`

- [ ] **Step 1: Add a regression test for existing control semantics**

Append to `tests/test_ui_model.py`:

```python
class UiControlSemanticsTests(unittest.TestCase):
    def test_view_state_matches_existing_clear_and_apply_semantics(self) -> None:
        facts = FlowAssistFacts(
            has_stream=True,
            has_flow=True,
            locked_count=5,
            outlet_set=True,
            preview_exists=True,
            preview_changes=0,
        )

        state = derive_flow_assist_state(facts)

        self.assertTrue(state.enabled[CommandId.CLEAR_FLOW_PREVIEW])
        self.assertFalse(state.enabled[CommandId.APPLY_FLOW_PREVIEW])
        self.assertTrue(state.enabled[CommandId.RESET_FLOW_ASSIST])
```

- [ ] **Step 2: Run the focused test and confirm the expected behavior is locked in**

Run:

```powershell
python -B -m unittest tests.test_ui_model
```

Expected: the new test passes because Task 2 already defines this pure behavior. This is a characterization test before replacing widget-level conditions.

- [ ] **Step 3: Replace duplicated booleans in `_refresh_flow_controls`**

At the beginning of `_refresh_flow_controls`, replace the local `has_flow_data`, `locked_ready`, `apply_ready`, and `preview_ready` derivation with:

```python
from .water_ui_commands import CommandId

view_state = self._flow_assist_view_state()
enabled = view_state.enabled
has_flow_data = self.stream_raster is not None and self.flow_raster is not None
locked_ready = bool(self.confirmed_flow_segments)
apply_ready = enabled[CommandId.APPLY_FLOW_PREVIEW]
preview_ready = enabled[CommandId.CLEAR_FLOW_PREVIEW]
```

Then replace the matching control conditions:

```python
self.btn_add_locked_cell.configure(state=state(enabled[CommandId.ADD_SELECTED_CELL]))
self.btn_remove_locked_region.configure(state=state(enabled[CommandId.REMOVE_SELECTED_RIVERS]))
self.btn_reverse_segment.configure(state=state(enabled[CommandId.APPLY_FLOW_PREVIEW]), text=apply_text)
self.btn_preview_segment.configure(state=state(enabled[CommandId.CLEAR_FLOW_PREVIEW]))
self.btn_confirm_segment.configure(state=state(enabled[CommandId.RESET_FLOW_ASSIST]))
self.btn_apply_flow_preview.configure(state=state(enabled[CommandId.APPLY_FLOW_PREVIEW]), text=apply_text)
self.btn_clear_flow_preview.configure(state=state(enabled[CommandId.CLEAR_FLOW_PREVIEW]))
```

Keep the old river-preview and confluence-preview button conditions in this phase because they still represent separate legacy callbacks. They will be merged behind `GENERATE_FLOW_PREVIEW` in the flow-page plan.

- [ ] **Step 4: Run full tests and compile checks**

Run:

```powershell
python -B -m unittest discover -s tests
python -B -m py_compile water_correction_tool.py water_tool/water_app.py water_tool/water_ui_commands.py water_tool/water_ui_model.py water_tool/water_ui_state.py water_tool/water_flow_workflow.py
git -c safe.directory='C:/Users/86176/Desktop/水系订正' diff --check
```

Expected: all tests pass, compilation succeeds, and `diff --check` reports no errors.

- [ ] **Step 5: Commit the control-state migration**

```powershell
git add -- water_tool/water_ui_state.py tests/test_ui_model.py
git commit -m "Drive flow controls from UI state model"
```

### Task 5: Present Concise Status from the Same State Model

**Files:**
- Modify: `water_tool/water_flow_status.py:4-80`
- Test: `tests/test_ui_model.py`

- [ ] **Step 1: Add failing summary tests**

Append to `tests/test_ui_model.py`:

```python
class UiSummaryTests(unittest.TestCase):
    def test_summary_prioritizes_missing_data_over_normal_details(self) -> None:
        state = derive_flow_assist_state(FlowAssistFacts(has_stream=True, has_flow=False))

        self.assertEqual(state.summary, "需要加载河道 ASC 和流向 ASC")

    def test_summary_prioritizes_conflict_over_preview_count(self) -> None:
        state = derive_flow_assist_state(
            FlowAssistFacts(
                has_stream=True,
                has_flow=True,
                locked_count=9,
                preview_exists=True,
                preview_changes=4,
                dem_conflicts=2,
            )
        )

        self.assertEqual(state.summary, "预览待修改 4，逆坡冲突 2")
```

- [ ] **Step 2: Run the summary tests**

Run:

```powershell
python -B -m unittest tests.test_ui_model
```

Expected: tests pass against the Task 2 model, providing characterization before replacing status text assembly.

- [ ] **Step 3: Make current status methods consume `view_state.summary`**

In `FlowStatusMixin.update_mode_status`, obtain:

```python
view_state = self._flow_assist_view_state()
```

Keep current mode, tool, file, and autosave labels during this phase, but replace the flow-assist sentence with:

```python
self.flow_status_var.set(f"流向辅助：{view_state.summary}")
```

In `_update_flow_assist_text`, keep detailed counts needed by the current page, and use `view_state.summary` as the first line:

```python
view_state = self._flow_assist_view_state()
self.flow_assist_var.set(
    f"{view_state.summary}\n"
    f"{selected}  {outlet}  汇流模式 {self.confluence_mode_var.get()}  {distance_text}  {preview_detail}"
)
```

Do not remove `_flow_next_step_text` yet; the global Shell plan will replace it with stage-aware task guidance.

- [ ] **Step 4: Run focused and full verification**

Run:

```powershell
python -B -m unittest tests.test_ui_model
python -B -m unittest discover -s tests
python -B -m py_compile water_tool/water_flow_status.py water_tool/water_ui_state.py
git -c safe.directory='C:/Users/86176/Desktop/水系订正' diff --check
```

Expected: all tests pass and compile/diff checks are clean.

- [ ] **Step 5: Commit the status migration**

```powershell
git add -- water_tool/water_flow_status.py tests/test_ui_model.py
git commit -m "Present flow status from UI model"
```

### Task 6: Document and Verify the Foundation Boundary

**Files:**
- Modify: `docs/项目总说明.md`

- [ ] **Step 1: Update the project overview**

Add a V2.3 UI-maintenance entry describing:

```markdown
- 已建立稳定 UI 命令目录：命令 ID、名称、提示和数据修改属性集中管理。
- 已建立纯流向辅助 UI 状态模型：从现有业务状态派生阶段、主要操作、启用条件和摘要。
- 现有布局暂未改变；后续 UI Shell 和页面重构必须复用该命令与状态模型。
```

- [ ] **Step 2: Run the complete verification suite**

Run:

```powershell
python -B -m unittest discover -s tests
python -B -m compileall -q water_tool
git -c safe.directory='C:/Users/86176/Desktop/水系订正' diff --check
```

Expected: all tests pass, all modules compile, and `diff --check` reports no errors.

- [ ] **Step 3: Perform a focused manual smoke test**

Launch:

```powershell
python -B water_correction_tool.py
```

Verify:

1. Application opens with the existing layout.
2. River and flow files still load.
3. Flow mode still disables the eraser.
4. Selecting and locking river cells updates control states.
5. River-flow and confluence previews still enable clear/apply correctly.
6. DEM conflict navigation and report buttons retain their existing behavior.
7. Closing the application follows the existing save/autosave behavior.

- [ ] **Step 4: Commit documentation and any verification-only adjustments**

```powershell
git add -- docs/项目总说明.md
git commit -m "Document UI state foundation"
```

## Completion Criteria

- Stable command definitions exist and are covered by tests.
- Flow-assist UI state is derived by a pure function covered by tests.
- Existing control enablement and status presentation consume the pure model where behavior is one-to-one.
- Existing layout and all GIS calculations remain unchanged.
- Full automated tests, compilation, diff checks, and manual smoke workflow pass.
- The next UI Shell plan can use command IDs and `FlowAssistViewState` without reading widget internals.
