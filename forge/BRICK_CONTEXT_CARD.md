# 汇桥 OS（HuiQiao OS）极简总控上下文卡（BRICK_CONTEXT_CARD）

> **用途**：任何新会话启动时只需读本卡（< 90 行）+ `forge/PROGRESS_LEDGER.md`，即可掌握全盘骨架，**严禁每次重复通读 48KB PRD 与调研报告**！需查深层细节时再按章节定向翻阅 `docs/`。

## 一、项目定位与灵魂
- **目录**：本仓库根目录（便携独立，不依赖系统盘）
- **参考硬件档位（Standard 主力档示例）**：Windows 10/11 | Python 3.11+ | **64GB RAM + RTX 4070 12GB VRAM** | `git`/`pytest`/`ollama`/`docker` 就绪（推荐 4B Q8_0 路由 + 14B Q5/Q6 全显存主力或 24B–32B 统一内存热切）。
- **技术栈**：Python 3.11+（兼容 `pip`/`uv`）+ Pydantic v2 + FastAPI + Typer CLI + SQLite（WAL / FTS5 / `sqlite-vec`）+ 原生 MCP SDK；物理采用**模块化单体**（`packages/<brick>/` + 独立 `tests/`）。
- **C00 最高灵活核心**：助众生和谐增上（反人矿化、非对立共生、强扶弱共向上、全域利他、知限谦卑）。
- **刚柔原则**：只写死 **安全隔离 + C00 方向 + 客观验真** 三条硬底线；过程路径、工具组合与解法充分留给模型自由发挥。

## 二、积木地图（C00 + B01–B10 ↔ 施工单元 M00–M11）

| 施工块 | 对应模块 | 核心交付与标准契约 | 所属阶段 |
| :---: | :---: | :--- | :--- |
| `M00` | `C00` + Core | `CONSTITUTION.md` + Pydantic 契约 + `BrickRegistry` 热插拔加载器 | Phase 0 |
| `M01` | `B04` | 本地模型网关（Ollama/`llama-swap`）+ 角色量化 + VRAM 亲和队列 + `<think>` 剥离 + 前缀缓存锁 | Phase 0 |
| `M02` | `B10-Profiler` | 离线能力摸底器（微型 BFCL/RULER/CodeAct）→ `config/capability_profile.json` | Phase 0 |
| `M03` | `B06` + `DocIngest` | 本地 MCP 总线 + `Tool Search` 延迟加载 + FS/Git/SQLite/全格式文档解析 | Phase 1 |
| `M04` | `B10-Hooks` | 6 点生命周期 Hooks + Evidence Gate + WorkBuddy `Ask/Plan/Execute` 硬锁 | Phase 1 |
| `M05` | `B03` | ADK 五原语编排 + SQLite WAL Checkpoint 续跑 + HITL + 流式进度/中途改向/部分产物保留 | Phase 1 |
| `M06` | `B02` + `B05(L2-S)` | 柔硬结合五通道路由 + `SemanticCoCreator`（代劳/增上双态）+ `ReActWorker` | Phase 1 |
| `M07` | `B01` + 种子 Skill | FastAPI/WS 网关 + CLI + 轻量 WebUI + 5 个创世种子技能 → **Alpha MVP** | Phase 1 |
| `M08` | `B07` | 三级安全沙箱（T1 WASM / T2 OS 原生 / T3 `microsandbox` 或无网 Docker） | Phase 2 |
| `M09` | `B05(CodeAct/Sub)` | `CodeActWorker` + 上下文四件套（清理/双触发压缩/重注宪章）+ 逻辑隔离/物理亲和 Subagent | Phase 2 |
| `M10` | `B08` + 反馈 UX | File-First 分层记忆（`MEMORY.md` + 每日日志 + SQLite 混合双时态）+ 1 秒 4 键反馈 | Phase 3 |
| `M11` | `B09` | 双闸门防坍塌自演化（客观沙箱单测 + C00 增上四问）+ 低配普惠技能导出 | Phase 3 |
| `INT-4` | 全系统评测 | 断网 E2E + 轨迹评测 + 安全红队 + 显存压测 + 真人增上盲测 + 离线打包上线 | Phase 4 |

## 三、PRD v3.0 核心业务主线与防偏移四条死规（必读）
- **铸泽 SFDP 规格先行交付流水线（设计态 × 运行态双闭环）**：
  `① 澄清门 (<=5问写回spec)` → `② 规格工坊 (spec.md + plan.md + tasks + 可观察AC)` → `③ M08 沙箱构建` → `④ 只读 AC 逐条收敛 (未过只追加任务，严禁改AC)` → `⑤ 交付包五件套 (产物+变更清单+日志+B10客观自检+验收回滚协议)`。
- **防偏移死规 #1（防摘要漏斗失真）**：浓缩上下文卡时，必须用零 Token 脚本扫描最高版本 PRD（如 `06_PRD_v3.0`）全部二级标题，严禁遗漏核心交付流水线。
- **防偏移死规 #2（禁 Mock 自嗨假绿灯）**：单测绿灯不等于交付可用；每个用户可见里程碑必须完成「真本机模型 + 真界面点击生成并打开运行产物」冒烟验证。
- **防偏移死规 #3（公众白话默认 + 专业/禅意可切换）**：面向公众界面默认采用零门槛科技白话；保留禅意/专业语境一键切换并附悬停白话释义，严禁让新用户看不懂按钮。
- 详细章节按需查：`docs/06_汇桥OS_PRD_v3.0_合并优化版.md`、`docs/04_汇桥OS_产品需求文档_PRD_v2.2.md`、`forge/LESSONS_LEARNED.md`。
