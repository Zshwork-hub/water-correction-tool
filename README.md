# 水系订正工具

水系订正工具是一个 Windows 桌面应用，用于对河道 ASC 栅格和 D8 流向 ASC 栅格进行人工可视化订正，并以 SHP 水系线作为参考。

当前稳定发布：V2.1.0

V2.1.0 已加入汇流范围面 SHP 加载、显示、面内河道锁定、范围 SHP 汇流预览和配色管理优化。

## 主要功能

- 加载河道 ASC、流向 ASC 和水系 SHP。
- 河道模式：画笔、橡皮擦、矢量批量修正。
- 流向模式：左键改方向、右键选中像元后应用方向。
- 流向辅助：锁定局部河道、设出口、预览并应用河道流向、预览并应用周边汇流。
- 汇流范围面 SHP：独立加载、边界显示、颜色/线宽设置、面内河道锁定、范围内周边汇流预览和最大距离限制。
- 撤销/重做、版本快照、自动保存、崩溃恢复。
- 中键拖动、滚轮缩放、适配窗口、居中 SHP。
- 配色预设、网格、比例尺、流向箭头、原始对比。
- 画笔/橡皮擦快捷键设置。

## 开发运行

```powershell
python water_correction_tool.py
```

首次运行时请选择工作目录。数据文件不随代码仓库发布，请用户自行加载河道 ASC、流向 ASC 和 SHP 文件。

## 依赖安装

```powershell
pip install -r requirements.txt
```

说明：Tkinter 随 Python 安装提供，不写入 `requirements.txt`。

## 打包

```powershell
python -m PyInstaller water_correction_tool_v2_1.spec --noconfirm
```

当前已验证的发布文件：

```text
dist\水系订正工具_V2.1.0.exe
```

## 项目保存与导出

保存项目用于继续编辑，会生成：

- `xxx.waterproj`
- `xxx.waterproj.npz`

其中 `.waterproj` 保存项目配置，`.waterproj.npz` 保存当前编辑后的河道和流向栅格数组。移动项目时请两个文件一起移动。

导出 ASC 才是最终成果输出：

- 当前为“订正河道”模式时，导出当前河道栅格。
- 当前为“订正流向”模式时，导出当前流向栅格。

## 数据文件说明

本仓库不包含实际业务数据。以下文件默认不会提交到 Git：

- `*.asc`
- `*.shp`、`*.shx`、`*.dbf`、`*.prj`
- `build/`
- `dist/`
- `user_data/`
- `.waterproj`、`.waterproj.npz`

## 文档

- `docs/项目总说明.md`
- `docs/V2.1工作流测试清单.md`
- `docs/V2.1发布说明.md`
- `docs/V2.1打包发布清单.md`
- `docs/V2.2需求池.md`
- `docs/V2.0发布说明.md`
- `docs/V2.0审查与优化记录.md`
