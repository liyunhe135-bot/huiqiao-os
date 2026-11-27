# 汇桥 OS（HuiQiao OS）乐高施工实时进度账本（PROGRESS_LEDGER）

> **维护铁律**：每完成一块乐高积木（或单会话超过 15 轮准备切换会话前），必须更新本账本的「进度表」与「最新交接快照」，实现新会话 **0 失忆、低 Token 秒接力**。

## 一、12 块乐高积木实时状态表

| 编号 | 积木名称 | 推荐主力岗 / 模型 | 当前状态 | 单测通过率 | 验收 DoD | 备注 / 实际消耗 |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **磨刀** | AGY Skill + Rules + `forge_guard.py` | 管大脑 + 管电脑 | `done` | 实跑通过 | ✅ | 已实测硬件(64G+4070 12G+Ollama/Docker就绪)并验证 `preflight`/`brief` |
| `M00` | 宪章核心、契约总线与工程底座 | 管大脑：`Gemini 4 Neon (Extra High)` | `done` | 100% | ✅ | `CONSTITUTION.md` + 统一契约 + 双模式热插拔 `BrickRegistry` + CLI 6/6 全绿 |
| `M01` | 本地模型网关、显存亲和与思考剥离 | 管大脑 + 管编码 | `done` | 100% | ✅ | `packages/llm_gateway/` + `tests/test_m01_gateway.py` 已通过 |
| `M02` | 装机离线科学能力摸底器 | 管编码：`Gemini 4 Carbon (Medium)` | `done` | 100% | ✅ | `packages/profiler/` + `tests/test_m02_profiler.py` 已通过（Phase 0 达标） |
| `M03` | 核心 MCP 总线与全格式文档解析 | 管编码：`Gemini 4 Carbon (Medium)` | `done` | 100% | ✅ | `packages/mcp_bus/` + `packages/doc_ingest/` + 单测全绿（全库 57/57 通过） |
| `M04` | 确定性生命周期 Hooks 与三档模式守卫 | 管编码/安全：`Gemini 4 Neon / Carbon` | `done` | 100% | ✅ | `packages/governance/` + `config/policies.yaml` + 22 项越权与 <5ms 性能全绿（全库 79/79） |
| `M05` | 持久化 ADK 五原语编排与流式状态机 | 管大脑：`Gemini 4 Neon (Extra High)` | `done` | 100% | ✅ | `packages/orchestrator/`（WAL+ADK五原语+HITL+改向+子进程强杀续跑，全库 89/89） |
| `M06` | 柔硬结合路由与语义共生执行内核 | 管编码：`Gemini 4 Carbon (Medium)` | `done` | 100% | ✅ | `packages/router/` + `packages/workers/`（20题评测通过/0误塞CodeAct，全库 97/97） |
| `M07` | 统一网关、CLI/WebUI 与 5 创世种子技能 | 管编码：`Gemini 4 Carbon (Medium)` | `done` | 100% | ✅ | **Alpha MVP 达成**（FastAPI/WS+CLI+零CDN离线WebUI+5创世Skill，全库 105/105） |
| `M08` | 分级本地安全沙箱 | 管大脑：`Claude Opus 5.5 / Gemini 4 Neon` | `done` | 100% | ✅ | `packages/sandbox/`（T1纯计算AST插桩 / T2 Windows Job+POSIX rlimit+PEP578审计钩子 / T3硬化容器Fail-Closed + 16项红队全绿，全库 127/127） |
| `M09` | CodeAct、上下文四件套与亲和 Subagent | 管大脑：`Gemini 4 Neon (Extra High)` | `next` | — | ⬜ | Phase 2 里程碑块：完成后达 **Beta** 里程碑 |
| `M10` | 分层本地记忆引擎与 1 秒反馈闭环 | 管编码：`Gemini 4 Carbon / Claude Sonnet 5.5` | `pending` | — | ⬜ | — |
| `M11` | 双闸门防坍塌自演化引擎与普惠导出 | 管大脑：`Gemini 4 Neon / Claude Opus 5.5` | `pending` | — | ⬜ | 完成后达 RC 里程碑 |
| `INT-4` | 五维整体测试、离线打包与正式上线 | 管编码 + 管电脑 + 大脑抽检 | `pending` | — | ⬜ | `v1.0.0` 发布 |

---

## 二、最新会话无缝交接快照（供下一次新会话直接接棒）

- **更新时间**：2026-11-27 12:45
- **已完成**：
  1. `M00`–`M07`（Phase 1 Alpha MVP `v0.1.0-alpha`）全部绿灯并公开备份；
  2. **`M08`（`B07` 分级本地安全沙箱：`packages/sandbox/` — T1 轻量 AST 插桩防死循环/内存炸弹与可选 WASM、T2 OS 原生受限子进程 + Windows Job Object / POSIX rlimit + 不可移除 PEP 578 C 级审计钩子、T3 硬化无网 Docker 容器适配器 Fail-Closed、以及热插拔 `SandboxManager`）完整落盘**；
  3. **全仓库 `127 / 127` 项单测（含 `M08` 16 项红队越权/断网/符号链接/路径穿越/进程派生/内存/输出/写配额对抗测试 100% 拦截遏制）全部绿灯**，开源隐私卫生扫描 `HYGIENE_100_CLEAN`！
- **单写者锁状态**：`forge/.active_writer.lock` 持续开启，严禁其他智能体并发修改本目录。
- **下一块待施工**：**`M09`（`B05` CodeAct 执行内核、上下文四件套 [清理 / 双触发压缩 / 摘要化 / 宪章重注] 与逻辑隔离/物理显存亲和 Subagent → Phase 2 Beta 里程碑）**
- **推荐切换模型**：
  - 优先：**`Gemini 4 Neon (Extra High)`**（当前大脑模型即可无缝续接！`M09` 涉及把 `M08` 沙箱接入 `CodeActWorker` 闭环、上下文压缩重注不丢 `C00` 与显存亲和子代理调度，正是大脑岗核心职责）
- **下一会话极简开场指令**（执行 `python forge/scripts/forge_guard.py brief M09` 也可自动生成）：
  > 请激活 `huiqiao-forge-os` 技能，开始施工汇桥 OS 积木 `M09`（CodeAct、上下文四件套与亲和 Subagent → Beta 里程碑）。仅读取 `forge/BRICK_CONTEXT_CARD.md`、`forge/PROGRESS_LEDGER.md`、`packages/sandbox/manager.py` 和 `packages/workers/react.py`，先输出模块接口与验收清单（<100 行），落盘并跑通 `forge_guard.py test`。
