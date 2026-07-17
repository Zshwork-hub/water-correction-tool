# UI Shell 与河道订正页实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 GIS 计算、项目格式和现有工作流行为不变的前提下，完成全局 UI Shell、项目与数据入口、河道订正页和可滚动右侧任务面板，并消除 ASC 替换后旧 DEM 缓存继续可用的问题。

**Architecture:** 继续使用 Tkinter + ttk。新增纯 Shell 模型、统一主题、可复用滚动任务面板和按职责拆分的页面构建器；`WaterCorrectionApp` 保留业务状态和回调，UI 构建代码迁出 `water_app.py`。流向、显示和历史功能在本阶段完整接入新 Shell，但只做滚动与固定操作区适配，业务入口合并留到下一阶段。

**Tech Stack:** Python 3.9+, Tkinter/ttk, dataclasses, enum, unittest, existing NumPy/Pillow/GIS stack

---

## Scope

本计划对应 `docs/superpowers/specs/2026-07-17-ui-interaction-redesign-design.md` 的阶段 2。

本阶段交付：

- 顶部全局命令栏、左侧主导航、中央地图、右侧上下文面板和底部状态栏。
- 右侧所有页面具备滚动内容区，页面主要操作区固定在底部。
- 河道订正页按“手动工具 / 按河流线修正”重新组织。
- 项目与数据使用独立面板，不再长期占据主界面。
- 流向、显示和历史功能全部可访问，流向页底部操作不再被动态信息挤出。
- 1366 x 768 可完成主要工作流。
- 替换河道或流向 ASC 时，当前 DEM 缓存失效，但已加载 DEM 路径保留。

本阶段不做：

- 不合并流向辅助的订正对象和预览入口。
- 不重写 DEM 计算、河道修正、渲染或鼠标编辑算法。
- 不修改项目和自动保存格式。
- 不重构显示配色和历史恢复的业务逻辑。
- 不增加新的 GIS 功能。

### 用户确认的测试安排

DEM 缓存失效不设置独立人工测试阶段。它在实现任务内增加一条轻量自动回归，并随本阶段完整工作流回归一起验证。

## File Structure

- Create `water_tool/water_shell_model.py`: 主导航、响应式尺寸和项目数据行定义等纯 UI 契约。
- Create `water_tool/water_ui_theme.py`: ttk 主题颜色、间距、控件样式和应用函数。
- Create `water_tool/water_ui_components.py`: 可滚动任务面板、折叠区和左侧导航组件。
- Create `water_tool/water_ui_shell.py`: 顶部命令栏、左侧导航、地图容器、右侧页面宿主和底部状态栏。
- Create `water_tool/water_project_panel.py`: 项目与数据独立面板。
- Create `water_tool/water_stream_page.py`: 河道订正页。
- Create `water_tool/water_legacy_pages.py`: 本阶段流向、显示和历史页的兼容构建器。
- Modify `water_tool/water_app.py`: 初始化导航状态并委托新 UI 构建器；移除原 `_build_ui` 大段组装代码。
- Modify `water_tool/water_ui_state.py`: 导航切换、页面显示和模式同步。
- Modify `water_tool/water_dem_workflow.py`: 提供保留 DEM 路径的缓存失效入口。
- Modify `water_tool/water_ui.py`: 只保留通用对话框和 ToolTip；复用新主题常量。
- Create `tests/test_ui_shell.py`: 纯 Shell 契约、导航和布局测试。
- Modify `tests/test_dem.py`: ASC 替换触发缓存失效的轻量回归。
- Modify `docs/项目总说明.md`: 记录阶段 2 的模块边界和验证结果。

## Task 1: Invalidate DEM Cache When ASC Is Replaced

**Files:**
- Modify: `water_tool/water_dem_workflow.py:24-84`
- Modify: `water_tool/water_app.py:735-782`
- Test: `tests/test_dem.py`

- [ ] **Step 1: Add the integrated regression test**

在 `tests/test_dem.py` 增加一个不创建 Tk 根窗口的 harness：

```python
from water_tool.water_dem_workflow import DemWorkflowMixin
from water_tool.water_state import FlowPreviewState


class DummyVar:
    def __init__(self, value="") -> None:
        self.value = value

    def set(self, value) -> None:
        self.value = value

    def get(self):
        return self.value


class DemInvalidationHarness(DemWorkflowMixin):
    def __init__(self) -> None:
        self.dem_path = Path("dem.tif")
        self.dem_cache_arrays = {"mean": np.ones((2, 2), dtype=np.float32)}
        self.dem_cache_metadata = {"raster": {"path": "old.asc"}}
        self.dem_cache_data_path = Path("old.npz")
        self.dem_cache_meta_path = Path("old.json")
        self.dem_cache_status_var = DummyVar("已生成")
        self.dem_score_status_var = DummyVar("逆坡冲突 2")
        self.flow_preview_state = FlowPreviewState.create([(0, 0, 1)], kind="confluence")
        self.flow_preview_state.dem_score_summary = {"uphill": 2}
        self.flow_preview_state.dem_score_details = [object(), object()]
        self._dem_conflict_cursor = 1
        self._dem_cache_task_id = 3

    def cancel_dem_cache_task(self, silent=False) -> None:
        self.cancelled = silent

    def _refresh_dem_controls(self) -> None:
        pass
```

测试行为：

```python
def test_raster_change_invalidates_cache_but_keeps_loaded_dem(self) -> None:
    app = DemInvalidationHarness()

    app._invalidate_dem_cache_for_raster_change()

    self.assertEqual(app.dem_path, Path("dem.tif"))
    self.assertIsNone(app.dem_cache_arrays)
    self.assertIsNone(app.dem_cache_metadata)
    self.assertIsNone(app.dem_cache_data_path)
    self.assertIsNone(app.dem_cache_meta_path)
    self.assertEqual(app.dem_cache_status_var.get(), "已加载DEM，尚未生成缓存")
    self.assertEqual(app.dem_score_status_var.get(), "未评估")
    self.assertEqual(app.flow_preview_state.dem_score_details, [])
    self.assertEqual(app.flow_preview_state.dem_score_summary, {})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -B -m unittest tests.test_dem.DemWorkflowTests.test_raster_change_invalidates_cache_but_keeps_loaded_dem
```

Expected: `AttributeError` because `_invalidate_dem_cache_for_raster_change` does not exist.

- [ ] **Step 3: Implement the cache lifecycle method**

在 `DemWorkflowMixin` 增加：

```python
def _invalidate_dem_cache_for_raster_change(self) -> None:
    self.cancel_dem_cache_task(silent=True)
    self._dem_cache_task_id += 1
    self.dem_cache_arrays = None
    self.dem_cache_metadata = None
    self.dem_cache_data_path = None
    self.dem_cache_meta_path = None
    self._dem_conflict_cursor = -1
    preview = getattr(self, "flow_preview_state", None)
    if preview is not None:
        preview.dem_score_status.clear()
        preview.dem_score_summary.clear()
        preview.dem_score_label = ""
        preview.dem_score_details.clear()
    if hasattr(self, "dem_cache_status_var"):
        text = "已加载DEM，尚未生成缓存" if self.dem_path is not None else "未生成"
        self.dem_cache_status_var.set(text)
    if hasattr(self, "dem_score_status_var"):
        self.dem_score_status_var.set("未评估")
    self._refresh_dem_controls()
```

该方法不得清除 `dem_path`、`dem_file_var` 或 DEM 参数。

- [ ] **Step 4: Call invalidation only after a replacement file is accepted**

在 `load_stream` 和 `load_flow` 中，放在 `parse_asc` 和 `_confirm_raster_kind` 成功之后、替换 raster 对象之前：

```python
self._invalidate_dem_cache_for_raster_change()
```

用户取消类型确认或文件解析失败时不得清除已有缓存。

- [ ] **Step 5: Verify and commit**

Run:

```powershell
python -B -m unittest tests.test_dem
python -B -m unittest discover -s tests
git -c safe.directory='C:/Users/86176/Desktop/水系订正' diff --check
```

Commit:

```powershell
git add -- water_tool/water_dem_workflow.py water_tool/water_app.py tests/test_dem.py
git commit -m "Invalidate DEM cache on raster replacement"
```

## Task 2: Add Pure Shell Contracts and Theme Tokens

**Files:**
- Create: `water_tool/water_shell_model.py`
- Create: `water_tool/water_ui_theme.py`
- Create: `tests/test_ui_shell.py`

- [ ] **Step 1: Write shell contract tests**

创建 `tests/test_ui_shell.py`：

```python
from __future__ import annotations

import unittest

from water_tool.water_shell_model import NAV_ITEMS, NavigationId, shell_metrics
from water_tool.water_ui_theme import UI_COLORS, UI_SPACING


class ShellModelTests(unittest.TestCase):
    def test_navigation_ids_and_labels_are_stable(self) -> None:
        self.assertEqual(
            [(item.navigation_id, item.label) for item in NAV_ITEMS],
            [
                (NavigationId.STREAM, "河道订正"),
                (NavigationId.FLOW, "流向订正"),
                (NavigationId.DISPLAY, "显示与配色"),
                (NavigationId.HISTORY, "历史与恢复"),
            ],
        )

    def test_notebook_layout_keeps_map_usable_at_1366_by_768(self) -> None:
        metrics = shell_metrics(1366, 768)
        self.assertLessEqual(metrics.navigation_width, 148)
        self.assertGreaterEqual(metrics.context_width, 340)
        self.assertLessEqual(metrics.context_width, 380)
        self.assertGreaterEqual(metrics.map_width, 760)

    def test_wide_layout_gives_extra_space_to_map(self) -> None:
        notebook = shell_metrics(1366, 768)
        desktop = shell_metrics(1920, 1080)
        self.assertGreater(desktop.map_width, notebook.map_width)
        self.assertLessEqual(desktop.context_width, 380)

    def test_theme_has_distinct_semantic_colors(self) -> None:
        keys = {"background", "panel", "primary", "success", "warning", "error", "text", "muted"}
        self.assertTrue(keys.issubset(UI_COLORS))
        self.assertEqual(len({UI_COLORS[key] for key in keys}), len(keys))
        self.assertGreaterEqual(UI_SPACING["control_height"], 28)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -B -m unittest tests.test_ui_shell
```

Expected: module import errors for `water_shell_model` and `water_ui_theme`.

- [ ] **Step 3: Implement pure navigation and responsive metrics**

Create `water_tool/water_shell_model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class NavigationId(str, Enum):
    STREAM = "stream"
    FLOW = "flow"
    DISPLAY = "display"
    HISTORY = "history"


@dataclass(frozen=True)
class NavigationItem:
    navigation_id: NavigationId
    label: str


NAV_ITEMS: Tuple[NavigationItem, ...] = (
    NavigationItem(NavigationId.STREAM, "河道订正"),
    NavigationItem(NavigationId.FLOW, "流向订正"),
    NavigationItem(NavigationId.DISPLAY, "显示与配色"),
    NavigationItem(NavigationId.HISTORY, "历史与恢复"),
)


@dataclass(frozen=True)
class ShellMetrics:
    navigation_width: int
    context_width: int
    map_width: int
    status_height: int


def shell_metrics(width: int, height: int) -> ShellMetrics:
    safe_width = max(1024, int(width))
    navigation_width = 136 if safe_width <= 1366 else 156
    context_width = max(340, min(380, int(safe_width * 0.22)))
    map_width = max(640, safe_width - navigation_width - context_width - 96)
    return ShellMetrics(navigation_width, context_width, map_width, 28)
```

- [ ] **Step 4: Implement theme tokens**

Create `water_tool/water_ui_theme.py` with plain mappings plus `apply_ui_theme(style)`:

```python
UI_COLORS = {
    "background": "#F3F4F6",
    "panel": "#FFFFFF",
    "primary": "#2563EB",
    "primary_active": "#1D4ED8",
    "success": "#15803D",
    "warning": "#B45309",
    "error": "#B91C1C",
    "text": "#111827",
    "muted": "#6B7280",
    "border": "#D1D5DB",
}

UI_SPACING = {
    "shell": 8,
    "section": 8,
    "control": 6,
    "control_height": 30,
}
```

`apply_ui_theme` 只配置 ttk 样式，不修改系统主题和字体设置。至少定义 `App.TFrame`、`Panel.TFrame`、`Nav.TButton`、`NavSelected.TButton`、`Primary.TButton`、`Status.TLabel` 和 `Muted.TLabel`。

- [ ] **Step 5: Verify and commit**

```powershell
python -B -m unittest tests.test_ui_shell
python -B -m unittest discover -s tests
git add -- water_tool/water_shell_model.py water_tool/water_ui_theme.py tests/test_ui_shell.py
git commit -m "Add UI shell contracts and theme"
```

## Task 3: Build Reusable Scrollable Task Components

**Files:**
- Create: `water_tool/water_ui_components.py`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Add pure helper tests**

在 `tests/test_ui_shell.py` 测试滚轮归一化和折叠状态：

```python
from water_tool.water_ui_components import normalize_wheel_steps


def test_wheel_delta_is_normalized_across_platform_events(self) -> None:
    self.assertEqual(normalize_wheel_steps(delta=120, button=0), -1)
    self.assertEqual(normalize_wheel_steps(delta=-120, button=0), 1)
    self.assertEqual(normalize_wheel_steps(delta=0, button=4), -1)
    self.assertEqual(normalize_wheel_steps(delta=0, button=5), 1)
```

- [ ] **Step 2: Verify RED**

Run `python -B -m unittest tests.test_ui_shell`.

Expected: import failure for `water_ui_components`.

- [ ] **Step 3: Implement `ScrollableTaskPanel`**

Public contract:

```python
class ScrollableTaskPanel(ttk.Frame):
    def __init__(self, master, *, title_var=None, summary_var=None, padding=8): ...

    @property
    def body(self) -> ttk.Frame: ...

    @property
    def footer(self) -> ttk.Frame: ...

    def scroll_to_top(self) -> None: ...
```

结构固定为：

1. 可选标题和摘要区。
2. `Canvas + vertical Scrollbar + inner Frame` 可滚动内容区。
3. 独立 `footer`，始终位于组件底部，不属于 Canvas。

滚轮绑定仅在鼠标进入该组件后生效，离开时解除；不得使用永久 `bind_all`，避免抢占地图滚轮。

- [ ] **Step 4: Implement `CollapsibleSection` and `NavigationRail`**

```python
class CollapsibleSection(ttk.Frame):
    def __init__(self, master, text: str, *, expanded: bool = False): ...
    @property
    def content(self) -> ttk.Frame: ...
    def set_expanded(self, expanded: bool) -> None: ...


class NavigationRail(ttk.Frame):
    def __init__(self, master, variable, command): ...
    def set_selected(self, navigation_id: NavigationId) -> None: ...
```

导航按钮使用 `NAV_ITEMS` 生成，不在组件内修改 `mode_var`。

- [ ] **Step 5: Verify and commit**

```powershell
python -B -m unittest tests.test_ui_shell
python -B -m unittest discover -s tests
python -B -m py_compile water_tool/water_ui_components.py
git add -- water_tool/water_ui_components.py tests/test_ui_shell.py
git commit -m "Add reusable task panel components"
```

## Task 4: Build the Project and Data Panel

**Files:**
- Create: `water_tool/water_project_panel.py`
- Modify: `water_tool/water_shell_model.py`
- Modify: `water_tool/water_app.py:66-120, 620-665`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Define and test project-data row contracts**

在 `water_shell_model.py` 新增 `ProjectDataItem` 和只读 `PROJECT_DATA_ITEMS`。测试精确顺序：

```python
expected = [
    ("stream", "河道 ASC", CommandId.LOAD_STREAM_ASC),
    ("flow", "流向 ASC", CommandId.LOAD_FLOW_ASC),
    ("river", "河流线 SHP", CommandId.LOAD_RIVER_SHP),
    ("confluence", "汇流范围 SHP", CommandId.LOAD_CONFLUENCE_SHP),
    ("dem", "DEM", CommandId.LOAD_DEM),
]
self.assertEqual(
    [(item.key, item.label, item.command_id) for item in PROJECT_DATA_ITEMS],
    expected,
)
```

- [ ] **Step 2: Implement `ProjectDataDialog`**

构造函数：

```python
class ProjectDataDialog(tk.Toplevel):
    def __init__(self, parent, *, file_variables, callbacks): ...
```

要求：

- 每个数据对象一行：业务名称、当前文件状态、加载/替换按钮。
- 状态标签可换行，路径不撑宽窗口。
- 加载按钮复用现有 `load_stream_dialog`、`load_flow_dialog`、`load_shp_dialog`、`load_confluence_polygon_dialog` 和 `load_dem_dialog`。
- 不复制解析、投影或项目保存逻辑。
- 使用 `get_command(item.command_id)` 提供按钮名称和悬浮提示。
- 面板底部提供关闭按钮，不把“保存项目”重复放入面板。

- [ ] **Step 3: Add a single app entry point**

在 `WaterCorrectionApp` 初始化：

```python
self.navigation_var = tk.StringVar(value="stream")
self._project_data_dialog = None
```

新增：

```python
def open_project_data_panel(self) -> None:
    if self._project_data_dialog is not None and self._project_data_dialog.winfo_exists():
        self._project_data_dialog.lift()
        self._project_data_dialog.focus_set()
        return
    self._project_data_dialog = ProjectDataDialog(
        self,
        file_variables={
            "stream": self.stream_file_var,
            "flow": self.flow_file_var,
            "river": self.shp_var,
            "confluence": self.confluence_shp_var,
            "dem": self.dem_file_var,
        },
        callbacks={
            "stream": self.load_stream_dialog,
            "flow": self.load_flow_dialog,
            "river": self.load_shp_dialog,
            "confluence": self.load_confluence_polygon_dialog,
            "dem": self.load_dem_dialog,
        },
    )
```

- [ ] **Step 4: Verify and commit**

```powershell
python -B -m unittest tests.test_ui_shell
python -B -m unittest discover -s tests
git add -- water_tool/water_project_panel.py water_tool/water_shell_model.py water_tool/water_app.py tests/test_ui_shell.py
git commit -m "Add project and data panel"
```

## Task 5: Build the Global UI Shell

**Files:**
- Create: `water_tool/water_ui_shell.py`
- Modify: `water_tool/water_shell_model.py`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Add navigation transition tests**

创建不依赖 Tk 的 `navigation_mode` helper：

```python
def navigation_mode(navigation_id: NavigationId, current_mode: str) -> str:
    if navigation_id == NavigationId.STREAM:
        return "stream"
    if navigation_id == NavigationId.FLOW:
        return "flow"
    return current_mode
```

测试显示与历史导航不修改当前编辑栅格：

```python
self.assertEqual(navigation_mode(NavigationId.DISPLAY, "flow"), "flow")
self.assertEqual(navigation_mode(NavigationId.HISTORY, "stream"), "stream")
self.assertEqual(navigation_mode(NavigationId.STREAM, "flow"), "stream")
self.assertEqual(navigation_mode(NavigationId.FLOW, "stream"), "flow")
```

- [ ] **Step 2: Implement shell handles and builder**

`water_ui_shell.py` 提供：

```python
@dataclass
class UiShellHandles:
    navigation: NavigationRail
    map_frame: ttk.Frame
    page_host: ttk.Frame
    status_bar: ttk.Frame
    pages: Dict[NavigationId, ttk.Frame]

    def show_page(self, navigation_id: NavigationId) -> None: ...


def build_application_shell(app) -> UiShellHandles: ...
```

Shell 结构：

- row 0：单行顶部全局命令栏。
- row 1：左侧导航 / 中央地图 / 右侧页面宿主。
- row 2：底部状态栏。

顶部命令栏只创建：

- 项目与数据
- 打开项目
- 保存项目
- 导出 ASC
- 撤销
- 重做
- 适配内容
- 居中河流线
- 放大、缩小、缩放输入
- 自动保存

按钮名称从 `water_ui_commands.get_command` 获取；没有稳定命令 ID 的缩放细项使用图标或短文字，并保留现有回调。

- [ ] **Step 3: Keep the builder disconnected until all pages exist**

本任务只提供 Shell 构建器和纯导航转换，不修改 `WaterCorrectionApp._build_ui`，也不迁移 Canvas 或现有控件。测试通过一个最小 fake app 校验 builder 需要的回调名称；正式应用仍使用旧界面，因此本提交必须保持可启动。

- [ ] **Step 4: Verify and commit**

```powershell
python -B -m unittest tests.test_ui_shell
python -B -m unittest discover -s tests
python -B water_correction_tool.py --smoke-test
python -B -m compileall -q water_tool
git add -- water_tool/water_ui_shell.py water_tool/water_shell_model.py tests/test_ui_shell.py
git commit -m "Add disconnected application shell builder"
```
## Task 6: Build the River Correction Page

**Files:**
- Create: `water_tool/water_stream_page.py`
- Modify: `water_tool/water_shell_model.py`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Define the river-page control contract**

在 `water_shell_model.py` 增加只读 `STREAM_PAGE_COMMANDS`，测试精确包含：

```python
(
    CommandId.APPLY_VECTOR_CORRECTION,
)
```

手动画笔和橡皮擦属于工具选择，不创建额外写入命令 ID；快捷键设置继续使用现有对话框入口。

- [ ] **Step 2: Implement `build_stream_page`**

Public API:

```python
def build_stream_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]: ...
```

页面结构：

1. 摘要：当前工具、画笔大小、河道 ASC/SHP 是否已加载。
2. “手动工具”常显区：画笔、橡皮擦、画笔大小、快捷键设置。
3. “按河流线修正”折叠区：矢量容差，默认值保持 `0.2`。
4. 固定 footer：`按河流线修正` 主按钮。

返回的控件注册表必须包含以下兼容属性名，供最终接入时一次性绑定给应用，继续满足现有状态刷新和 ToolTip：

```python
("radio_brush_tool", "radio_eraser_tool", "brush_size_spin", "btn_vector_batch", "vector_hint")
```

不要在该页创建方向下拉框、方向建议、锁定、出口或 DEM 控件。

- [ ] **Step 3: Keep mode-specific control behavior**

页面 builder 返回控件注册表，不直接写入现有应用。注册表至少包含以下键，供最终接入任务一次性绑定到兼容属性：

```python
{
    "radio_brush_tool": radio_brush_tool,
    "radio_eraser_tool": radio_eraser_tool,
    "brush_size_spin": brush_size_spin,
    "btn_vector_batch": btn_vector_batch,
    "vector_hint": vector_hint,
}
```

本任务不修改 `_build_ui`，正式应用继续使用旧河道页，保持提交可启动。

- [ ] **Step 4: Verify river workflow and commit**

Run automated suite, then process-level GUI smoke at 1366 x 768。手工检查：

- 左侧“河道订正”显示河道页。
- 画笔、橡皮擦和大小可用。
- 容差默认 `0.2`。
- 批量修正按钮始终位于 footer。
- 画笔/橡皮擦快捷键仍生效。

Commit:

```powershell
git add -- water_tool/water_stream_page.py water_tool/water_shell_model.py tests/test_ui_shell.py
git commit -m "Add river correction page builder"
```

## Task 7: Migrate Existing Flow, Display, and History Pages Safely

**Files:**
- Create: `water_tool/water_legacy_pages.py`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Create compatibility page builders**

Provide three functions:

```python
def build_flow_compatibility_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]: ...
def build_display_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]: ...
def build_history_page(app, parent) -> tuple[ScrollableTaskPanel, dict[str, object]]: ...
```

这些函数迁移现有控件，不改回调和业务参数。

- [ ] **Step 2: Put flow content in a scrollable body**

流向页 body 保留：

- 手动方向选择、写入方向和建议方向。
- 汇流范围、选择与锁定、河道本体、周边汇流。
- DEM 加载、缓存、评估、筛选、定位和导出。

固定 footer 只放：

- 应用预览。
- 清除预览。
- 重置辅助状态。

原有 `btn_reverse_segment`、`btn_preview_segment`、`btn_confirm_segment` 兼容属性继续指向 footer 中的真实按钮；不得创建第二套回调按钮。

- [ ] **Step 3: Move display and history controls**

显示页迁移现有显示开关、颜色编辑、预设和像元信息。历史页迁移快照列表、创建/恢复快照和自动保存恢复入口。

页面 body 使用 `ScrollableTaskPanel`；没有主要 footer 操作的页面保持 footer 隐藏，不占据空白高度。

- [ ] **Step 4: Return a complete compatibility registry**

三个 builder 返回各自的控件注册表。测试将注册表键与 `UIStateMixin`、`DemWorkflowMixin`、`PaletteMixin` 和 tooltip 安装所需属性集合比较，确保最终接入前已具备完整契约。本任务不删除旧 Notebook、顶部模式组或常驻文件状态区。

- [ ] **Step 5: Verify widget contracts**

在 `tests/test_ui_shell.py` 增加静态契约集合，列出 `UIStateMixin`、`DemWorkflowMixin`、`PaletteMixin` 和 tooltip 安装需要的 widget 属性。对页面 builder 的返回注册表断言这些 key 唯一且完整，避免运行时 `AttributeError`。

- [ ] **Step 6: Verify and commit**

```powershell
python -B -m unittest tests.test_ui_shell tests.test_ui_model
python -B -m unittest discover -s tests
python -B -m compileall -q water_tool
python -B water_correction_tool.py --smoke-test
git add -- water_tool/water_legacy_pages.py tests/test_ui_shell.py
git commit -m "Add compatibility page builders"
```

## Task 8: Responsive Layout, Documentation, and Complete Regression

**Files:**
- Modify: `water_tool/water_ui_shell.py`
- Modify: `water_tool/water_ui_theme.py`
- Modify: `water_tool/water_ui.py`
- Modify: `water_tool/water_app.py`
- Modify: `water_tool/water_ui_state.py`
- Modify: `water_tool/water_project_panel.py`
- Modify: `water_tool/water_stream_page.py`
- Modify: `water_tool/water_legacy_pages.py`
- Modify: `docs/项目总说明.md`
- Modify: `tests/test_ui_shell.py`

- [ ] **Step 1: Add final integration contract tests**

测试 `bind_control_registry` 拒绝重复键并将完整控件注册表绑定到应用；测试导航切换只在河道/流向页面更新 `mode_var`，显示和历史页面保持当前活动栅格。静态检查 `_build_ui` 不再创建 `ttk.Notebook` 或顶部模式单选组。

```python
class DummyApp:
    pass

app = DummyApp()
bind_control_registry(app, {"btn_vector_batch": object()})
self.assertTrue(hasattr(app, "btn_vector_batch"))
with self.assertRaises(ValueError):
    merge_control_registries({"shared": object()}, {"shared": object()})
```

先运行 `python -B -m unittest tests.test_ui_shell`，确认新增的绑定和最终接入契约因函数尚不存在而失败。

- [ ] **Step 2: Connect every builder in one application change**

将 `WaterCorrectionApp._build_ui` 替换为一次性组装：

```python
def _build_ui(self) -> None:
    apply_ui_theme(ttk.Style(self))
    self.ui_shell = build_application_shell(self)
    page_results = self._build_context_pages()
    controls = merge_control_registries(*(item[1] for item in page_results))
    bind_control_registry(self, controls)
    self.ui_shell.show_page(NavigationId(self.navigation_var.get()))
```

`_build_context_pages` 必须调用河道、流向、显示、历史四个 builder 并向 `ui_shell.pages` 注册页面。所有 builder 就绪后才执行这一步；不得留下调用不存在 builder 的中间提交。

将现有 Canvas、横纵滚动条及绑定逐项迁移到 `ui_shell.map_frame`，回调名称保持不变，完整保留左键编辑、右键单击/框选、中键平移、Windows/Linux 滚轮缩放、横纵滚动条、`<Configure>` 和 `<Motion>`。

- [ ] **Step 3: Synchronize navigation and remove superseded layout**

在 `UIStateMixin` 增加 `on_navigation_changed`：河道/流向导航通过 `navigation_mode` 更新 `mode_var` 并调用现有 `on_mode_changed`；显示/历史导航只切页，不改变当前编辑栅格。`on_mode_changed` 只在活动导航本来就是河道或流向时同步导航状态。

确认所有兼容控件已通过注册表绑定后，删除旧右侧 `ttk.Notebook`、顶部“工作模式”单选组、常驻文件状态大框和重复项目数据按钮。保留 `mode_var` 作为活动栅格状态。运行完整测试和 `--smoke-test`，确认应用在该提交内仍可启动。

- [ ] **Step 4: Apply responsive shell metrics**

在窗口 `<Configure>` 上只调度轻量、去抖的 Shell 布局更新：

```python
def schedule_shell_layout(self, width: int, height: int) -> None:
    if self._shell_layout_job is not None:
        self.after_cancel(self._shell_layout_job)
    self._shell_layout_job = self.after(80, lambda: self._apply_shell_layout(width, height))
```

`_apply_shell_layout` 使用 `shell_metrics` 调整导航宽度和右侧初始宽度，不在每次 resize 重建控件，不触发地图全量渲染。

- [ ] **Step 5: Complete tooltip and naming migration**

使用 `get_command` 更新本阶段可见名称：

- 适配内容。
- 居中河流线。
- 按河流线修正。
- 创建快照。
- 恢复自动保存会话。

Tooltip 由命令目录提供时不得在 `water_app.py` 再写一份不同文案。工具、颜色和参数控件的非命令提示继续保留在页面 builder 中。

- [ ] **Step 6: Update project documentation**

在 `docs/项目总说明.md` 记录：

- 新 Shell 文件职责。
- 河道页已经迁移。
- 流向页仍为兼容组织，入口合并属于下一阶段。
- 项目格式和 GIS 算法未变化。
- DEM 缓存随 ASC 替换失效。
- 1366 x 768 和 1920 x 1080 回归结果。

- [ ] **Step 7: Run complete automated verification**

```powershell
python -B -m unittest discover -s tests
python -B -m compileall -q water_tool
python -B water_correction_tool.py --smoke-test
git -c safe.directory='C:/Users/86176/Desktop/水系订正' diff --check
```

Expected: all tests `OK`, compilation/smoke/diff checks exit 0.

- [ ] **Step 8: Run process-level GUI smoke**

启动真实 Tk 进程并验证 5 秒内不退出。检查 stderr 无 traceback 后关闭测试进程。

- [ ] **Step 9: Run complete manual regression**

在 `1366 x 768` 和 `1920 x 1080` 检查：

1. 顶部命令栏不换成不可用的第三行。
2. 左侧四个导航项均可达，显示/历史切换不改变活动栅格。
3. 河道画笔、橡皮擦、大小、快捷键和按河流线修正完整可用。
4. 流向页内容可滚动，应用/清除/重置始终可见。
5. DEM 报告导出按钮不会被动态状态挤出。
6. 中键平移、滚轮缩放和横纵滚动条正常。
7. 项目与数据面板可加载或替换五类数据。
8. 替换 ASC 后 DEM 路径保留、缓存状态变为未生成。
9. 项目打开/保存、ASC 导出、撤销/重做、快照和自动保存恢复正常。
10. 关闭程序继续执行现有保存确认和自动保存策略。

- [ ] **Step 10: Commit the completed stage**

```powershell
git add -- water_tool/water_ui_shell.py water_tool/water_ui_theme.py water_tool/water_ui.py water_tool/water_app.py water_tool/water_ui_state.py water_tool/water_project_panel.py water_tool/water_stream_page.py water_tool/water_legacy_pages.py tests/test_ui_shell.py docs/项目总说明.md
git commit -m "Complete UI shell and river page migration"
```

## Completion Criteria

- `water_app.py` 不再包含完整页面组装代码。
- 顶部、左侧、地图、右侧和底部形成稳定 Shell。
- 项目与数据通过独立面板访问。
- 河道订正页符合“手动工具 / 按河流线修正”结构。
- 流向、显示和历史功能没有丢失，右侧内容全部可滚动。
- 流向页应用、清除和重置操作固定可见。
- 1366 x 768 下主要操作无裁切、无不可达控件。
- 原有鼠标导航、编辑、项目、历史、DEM 和导出工作流不回归。
- 替换 ASC 后旧 DEM 缓存不会继续被评估入口使用。
- 自动测试、编译、命令行 smoke、GUI 启动 smoke 和人工回归全部通过。
