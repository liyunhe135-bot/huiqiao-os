# 文件夹安全分类预览 (`genesis-folder-organizer`)

## 定位与 C00 原则
- **零盲删铁律（C00 A1 & A2）**：永远不自动删除任何用户文件；同名冲突自动追加序号保护。
- **默认先预览后执行**：输出清晰的分类清单与 Unified Diff 变更预览，只有在 `EXECUTE` 模式且显式开启 `apply_changes=True` 时才执行移动。
