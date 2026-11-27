# 汇桥 OS（HuiQiao OS）v1.0.0 五分钟快速上手手册

> **核心承诺**：100% 本地离线优先 · 零外部云端锁死 · 记忆透明可手改可遗忘 · 高配沉淀反哺低配电脑。

---

## 一、环境准备与一键启动

### 1. 基础环境要求
- **操作系统**：Windows 10/11、macOS 或 Ubuntu Linux
- **Python**：`3.11+`
- **硬件弹性适配**：
  - **Lite 普惠档（4GB–8GB RAM，无独立显卡）**：可直接零大模型运行全部创世确定性技能与导入的 `.hqskill.zip` 普惠技能包，或搭配 `Ollama` 运行 `4B Q4` 轻量模型；
  - **Standard 主力档（32GB–64GB RAM + 12GB VRAM 独显）**：完整支持多通道智能路由、本地 `CodeAct` 安全沙箱自愈、显存亲和子代理与双闸门技能自演化。

### 2. 安装轻量依赖（首次执行一次）
```powershell
pip install -e ".[dev]"
```

### 3. 一键启动本地离线工作台
- **Windows PowerShell**：
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/start_huiqiao.ps1
  ```
- **Linux / macOS**：
  ```bash
  bash scripts/start_huiqiao.sh
  ```
启动后用浏览器打开 **`http://127.0.0.1:8765`**（系统安全守卫默认严格锁定本机回环地址，绝不擅自暴露公网或局域网端口）。

---

## 二、核心心智：三档安全模式（Ask / Plan / Execute）

| 模式 | 适用场景 | 内核硬安全保证 |
| :---: | :--- | :--- |
| **`Ask`（只读启发）** | 文档摘要、表格统计、每日复盘、苏格拉底难题拆解 | **内核级物理禁写**：绝不修改任何业务文件 |
| **`Plan`（方案预审）** | 整理杂乱文件夹、批量改写配置或代码前预览 | **必出 Unified Diff 变更预览**，未经您点击「批准并继续」绝不落盘 |
| **`Execute`（受控执行）** | 授权目录内自动执行脚本或归档 | 仅限白名单工作区内运行，敏感目录（`.ssh` / `.env` / 系统盘）与联网企图仍被物理阻断 |

---

## 三、常用命令行（CLI）速查

```powershell
# 1. 查看 C00 宪章指纹与全系统 8 大模块健康状态
python -m apps.cli.main status

# 2. 查看已安装的创世与自演化技能包
python -m apps.cli.main skills

# 3. 只读模式直接体验创世技能
python -m apps.cli.main ask "今日复盘：完成了项目核心交付；明天梳理复盘模板"
python -m apps.cli.main ask "请提炼文档精华摘要" -a README.md

# 4. 管理本地透明记忆（您也可以直接用记事本打开编辑 workspace/MEMORY.md！）
python -m apps.cli.main memories --add "周报优先使用三点式精简列表"
python -m apps.cli.main memories -q "周报"

# 5. 对任意历史运行做 1 秒反馈（praise / dislike / correct / save_skill_seed）
python -m apps.cli.main feedback <run_id> save_skill_seed -n "团队周报三点提炼法"

# 6. 双闸门自演化（自动过独立安全沙箱单测 + C00 宪章四问审查）并经人工确认上线
python -m apps.cli.main evolve <seed_id> --approve

# 7. 导出与导入普惠便携技能包（分享给低配 8GB 笔记本朋友零云端离线使用）
python -m apps.cli.main export-skill genesis-daily-reflect dist/daily-reflect.hqskill.zip
python -m apps.cli.main import-skill dist/daily-reflect.hqskill.zip --overwrite
```

---

## 四、一键自检与构建离线便携发行包

```powershell
# 运行 INT-4 五维终极自动评测
python -m evals.run_int4_eval

# 运行全仓库单元测试套件
python forge/scripts/forge_guard.py test tests/

# 构建零个人数据残留的离线便携发行包 (dist/huiqiao-os-v1.0.0-portable.zip)
python scripts/build_portable_bundle.py
```
