# UI Feedback And Layer Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复本轮 UI 回归问题，并让编辑目标、地图显示图层和流向辅助页面形成清晰、可扩展且向后兼容的交互模型。

**Architecture:** `mode_var` 只表示写入目标，新增 `display_mode_var` 只表示地图显示目标。所有渲染和屏幕坐标换算使用显示栅格，所有数据修改使用编辑栅格，并在业务入口统一检查二者是否一致。右侧任务页按工作阶段组织，流向页用三个页签承载手动改向、河网辅助和 DEM 审核，底部保留稳定操作区。

**Tech Stack:** Python 3.9+, Tkinter/ttk, NumPy, pytest, 现有 `water_tool` 模块化架构。

---

## 文件边界与职责

- `water_tool/water_app.py`：显示/编辑栅格入口、地图坐标换算、鼠标编辑保护、显示图层切换协调。
- `water_tool/water_state.py`：保存 `display_mode_var` 以及跨页面选择状态的初始化和清理规则。
- `water_tool/water_ui_shell.py`：顶部显示图层选择器和固定模式状态条的宿主布局。
- `water_tool/water_flow_status.py`：生成正常/只读模式提示文本。
- `water_tool/water_ui_state.py`：派生编辑/显示一致性和控件启用状态；页面切换时不清除河道选择。
- `water_tool/water_ui_components.py`：滚轮事件安全归一化和导航选中样式结构。
- `water_tool/water_ui_theme.py`：可读的导航、主按钮和只读警告样式。
- `water_tool/water_editing.py`：选择像元写入、矢量批量写入和统一修改前置检查。
- `water_tool/water_flow_workflow.py`：删除建议方向，修复选择加入/预览应用入口和统一写入检查。
- `water_tool/water_history.py`：撤销/重做调用统一写入检查。
- `water_tool/water_legacy_pages.py`：流向三页签和固定 footer，移除建议方向控件。
- `water_tool/water_shell_model.py`、`water_tool/water_ui_commands.py`：同步控件注册和命令目录。
- `water_tool/water_project_workflow.py`：保存、打开、自动保存和旧项目的 `display_mode` 兼容。
- `tests/test_ui_shell.py`、`tests/test_ui_model.py`、`tests/test_history_and_state.py`、`tests/test_project_persistence.py`：纯契约和回归测试。
- 新增时优先放入已有对应模块；本轮不继续拆主窗口，也不修改河网、汇流或 DEM 算法。

## Task 1: 修复选择契约和 Windows 滚轮异常

**Files:**
- Modify: `water_tool/water_editing.py:35-60`
- Modify: `water_tool/water_flow_workflow.py:28-60,155-180`
- Modify: `water_tool/water_ui_components.py:1-20,132-143`
- Test: `tests/test_ui_model.py`, `tests/test_ui_shell.py`

- [ ] **Step 1: 写失败测试**

增加最小测试：`selected_flow_cell=(1, 2)` 时 `apply_selected_direction()` 读写 `(row, col)`；有效 `Stream=1` 单元加入锁定集合；越界和非河道单元给出明确状态；`normalize_wheel_steps(delta=120, button="??")` 不抛异常并返回 `-1`。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_ui_shell.py -q`，预期当前选择消费者出现四元组解包错误，滚轮字符串输入出现 `ValueError`。

- [ ] **Step 3: 最小实现**

统一使用 `row, col = selection` 或 `_require_selected_flow_cell()` 返回的二元组；加入河道单元前检查 `0 <= row < rows`、`0 <= col < cols`、对应河道栅格值等于 `1` 和未重复。滚轮 helper 先尝试整数转换，失败按 `0` 处理，Windows 优先使用 `delta`，X11 仅对数值按钮 `4/5` 响应。

- [ ] **Step 4: 运行通过测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_ui_shell.py -q`，预期通过且无 Tk callback 异常路径。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool/water_editing.py water_tool/water_flow_workflow.py water_tool/water_ui_components.py tests/test_ui_model.py tests/test_ui_shell.py
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Fix cell selection and wheel event handling"
```

## Task 2: 删除低价值的建议方向功能

**Files:**
- Modify: `water_tool/water_flow_workflow.py`
- Modify: `water_tool/water_legacy_pages.py`, `water_tool/water_shell_model.py`, `water_tool/water_ui_commands.py`
- Modify: `water_tool/water_ui_state.py`
- Test: `tests/test_ui_shell.py`, `tests/test_ui_model.py`, `tests/test_ui_commands.py`

- [ ] **Step 1: 写失败测试**

断言流向页控件注册表、命令目录和源码不再暴露“建议方向”；保留“写入所选方向”且可在有效选择上执行。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_shell.py tests/test_ui_model.py tests/test_ui_commands.py -q`，预期旧控件或命令仍存在。

- [ ] **Step 3: 最小实现**

删除 `CommandId.SUGGEST_FLOW_DIRECTION`、按钮、tooltip、控件 key、`suggest_flow_direction()`、`_suggest_flow_candidates()` 及仅供其使用的导入；不删除方向下拉框和“写入所选方向”。

- [ ] **Step 4: 运行通过测试**

运行同一组测试，确认没有 UI 注册残留或动态属性访问残留。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Remove low-value flow direction suggestions"
```

## Task 3: 建立显示/编辑状态模型和持久化兼容

**Files:**
- Modify: `water_tool/water_state.py`, `water_tool/water_app.py`
- Modify: `water_tool/water_ui_state.py`, `water_tool/water_project_workflow.py`
- Modify: `tests/test_ui_model.py`, `tests/test_project_persistence.py`, `tests/test_history_and_state.py`

- [ ] **Step 1: 写失败测试**

覆盖 `get_edit_raster()`、`get_display_raster()`、`can_modify_active_raster()`：相同模式可写，不同模式只读，目标未加载不可写。旧项目没有 `display_mode` 时回退到 `mode`；新项目保存并恢复 `display_mode`。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_project_persistence.py tests/test_history_and_state.py -q`，预期方法或字段不存在、旧保存逻辑没有新字段。

- [ ] **Step 3: 最小实现**

初始化 `display_mode_var`；保留 `get_active_raster()` 作为编辑目标兼容别名。渲染前只从显示目标取栅格，业务编辑只从编辑目标取栅格。项目、自动保存 payload 写入可选 `display_mode`，打开时校验为 `stream/flow` 且对应栅格存在，否则回退并给状态提示。模式切换不清除 `selected_flow_cell`、框选区域和锁定对象。

- [ ] **Step 4: 运行通过测试**

运行三组测试，确认状态和项目恢复通过，且既有历史测试仍通过。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Separate edit and display raster state"
```

## Task 4: 接入顶部显示图层与显眼只读状态条

**Files:**
- Modify: `water_tool/water_ui_shell.py`, `water_tool/water_flow_status.py`
- Modify: `water_tool/water_ui_state.py`, `water_tool/water_app.py`
- Modify: `water_tool/water_ui_theme.py`
- Test: `tests/test_ui_model.py`, `tests/test_ui_shell.py`

- [ ] **Step 1: 写失败测试**

断言顶部存在“显示图层”选择器；模式/显示一致时状态为“可编辑”；不一致时状态包含“只读选择状态”和“切换显示图层后才能写入”，且状态条固定存在。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_ui_shell.py -q`，预期没有显示状态变量、控件或状态文本。

- [ ] **Step 3: 最小实现**

在 top command bar 增加只读 `ttk.Combobox`，只允许已加载图层；切换不改变视图中心/缩放。增加固定高度状态条，失配时使用浅黄色背景、深色粗体和“只读”标识，正常时显示编辑目标、显示图层和可编辑状态。缺图层切换只提示，不改变当前选择。

- [ ] **Step 4: 运行通过测试**

运行同一组测试，并执行 `python -m py_compile water_correction_tool.py water_tool/*.py`。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Add display layer selector and read-only status"
```

## Task 5: 迁移渲染、缩放和坐标换算到显示栅格

**Files:**
- Modify: `water_tool/water_app.py`, `water_tool/water_flow_render.py`, `water_tool/water_render.py`
- Modify: `tests/test_ui_model.py`, add focused render coordinate tests if needed

- [ ] **Step 1: 写失败测试**

使用不同的 stream/flow harness 断言 `canvas_to_rc()`、视窗适配、滚动范围和渲染调用选择 `display_mode` 栅格；编辑目标和显示目标不一致时地图仍可选择但不写入。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_flow_render.py -q`，预期坐标和渲染仍绑定 `get_active_raster()`。

- [ ] **Step 3: 最小实现**

将渲染入口、缩放、居中、滚动条范围、`canvas_to_rc()`、鼠标命中和地图信息查询改用 `get_display_raster()`；所有 overlay 统一使用显示栅格坐标。若两 ASC 网格头信息不一致，拒绝混合显示并给出状态提示，避免像元位置错位。

- [ ] **Step 4: 运行通过测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_flow_render.py -q`，再执行全量测试。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Render and navigate using selected display layer"
```

## Task 6: 集中保护全部写入入口

**Files:**
- Modify: `water_tool/water_editing.py`, `water_tool/water_flow_workflow.py`, `water_tool/water_history.py`, `water_tool/water_app.py`
- Modify: `water_tool/water_ui_state.py`
- Test: `tests/test_ui_model.py`, `tests/test_history_and_state.py`

- [ ] **Step 1: 写失败测试**

在 `mode != display_mode` 时断言画笔/橡皮擦、沿线刷写、写入所选方向、矢量批量修正、应用预览、撤销和重做均不改变数组并返回状态提示；选择、锁定、预览生成和 DEM 评估仍可执行。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_model.py tests/test_history_and_state.py -q`，预期至少一个入口仍能绕过 UI 按钮直接写入。

- [ ] **Step 3: 最小实现**

添加统一 `can_modify_active_raster()`/`_guard_raster_write(action)` 业务检查，所有写入方法第一行调用；拒绝时更新底部状态，不弹重复模态框。`apply_selected_direction()` 和矢量修正同时修复二元组选择。撤销/重做在失配时不弹出历史状态而是拒绝。

- [ ] **Step 4: 运行通过测试**

运行回归测试，验证合法一致模式下原有写入、历史和快照行为不变。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Guard raster writes when display and edit differ"
```

## Task 7: 重整流向页、选择保留和按钮状态

**Files:**
- Modify: `water_tool/water_legacy_pages.py`, `water_tool/water_shell_model.py`, `water_tool/water_ui_state.py`
- Modify: `water_tool/water_ui_components.py`, `water_tool/water_ui_theme.py`
- Test: `tests/test_ui_shell.py`, `tests/test_ui_model.py`

- [ ] **Step 1: 写失败测试**

断言流向页只暴露“手动改向”“河网辅助”“DEM 审核”三组内容；固定 footer 包含应用、清除、重置；河道页选择后切换流向仍保留；失配时写入按钮禁用但选择/预览按钮可用；导航文字不使用白色前景。

- [ ] **Step 2: 运行失败测试**

运行 `python -m pytest tests/test_ui_shell.py tests/test_ui_model.py -q`，预期旧纵向页面结构和旧样式断言不满足。

- [ ] **Step 3: 最小实现**

按既定顺序将控件放入三个 tab；DEM 报告只在 DEM tab；三个 footer 控件始终在固定 footer。导航当前项以 `tk.Frame` 左侧蓝色指示条和深色粗体字表示，`NavSelected.TButton`/`Primary.TButton` 不设置白色前景。模式切换不清空选择数据。

- [ ] **Step 4: 运行通过测试**

运行 UI 测试并以最小可用 harness 检查 `1366x768` 下滚动条和 footer 仍可达。

- [ ] **Step 5: 提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Organize flow page and readable navigation states"
```

## Task 8: 全量验证、文档和交付检查

**Files:**
- Modify: `docs/项目总说明.md`
- Modify: `docs/V2.2维护总结.md` or current UI maintenance note if required by existing branch conventions
- Test: all `tests/*.py`

- [ ] **Step 1: 运行自动测试**

运行 `python -m pytest -q`，预期全量通过；运行 `python -m py_compile water_correction_tool.py water_tool/*.py`，预期无输出且退出码为 0。

- [ ] **Step 2: 运行 GUI smoke**

使用现有不弹首次工作区对话框的 harness，在 `1366x768` 和 `1920x1080` 检查：只读状态条、可读导航、流向三个页签、DEM 报告按钮、固定 footer、侧栏滚轮和地图滚轮。

- [ ] **Step 3: 更新文档**

在项目总说明中补充显示/编辑解耦、只读组合、右键选择契约、流向页三页签和回归验证日期；明确本轮没有修改河网/汇流/DEM 算法。

- [ ] **Step 4: 检查提交范围**

运行 `git status --short` 和 `git diff --check`，确认不触碰用户保留的删除文件、恢复码、测试目录及未提交设计文档改动。

- [ ] **Step 5: 最终提交**

```powershell
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river add water_tool tests docs/项目总说明.md
git -c safe.directory=C:/tmp/water-correction-tool-ui-shell-river commit -m "Complete UI feedback and layer decoupling"
```

## 自审结果

- 规格覆盖：选择契约、滚轮兼容、建议方向移除、显示/编辑解耦、只读保护、河道选择跨页保留、流向页信息重排、选中样式、项目兼容和验证均有任务覆盖。
- 非目标保持：不改河网方向算法、周边汇流算法、DEM 评分算法和范围 SHP 算法。
- 兼容性：保留 `get_active_raster()` 编辑目标别名；旧项目缺 `display_mode` 时回退到 `mode`。
- 关键风险：两个 ASC 若网格头不一致不能直接混合显示；必须在切换时给出明确提示并保持原显示图层。
- 提交粒度：每个任务在测试通过后单独提交，便于回滚和定位。
