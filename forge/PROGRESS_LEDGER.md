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
| `M06` | 柔硬结合路由与语义共生执行内核 | 管编码：`Gemini 4 Carbon (Medium)` | `next` | — | ⬜ | 下一块开工目标（建议切 Carbon 省 55% 额度） |
| `M07` | 统一网关、CLI/WebUI 与 5 创世种子技能 | 管编码：`Gemini 4 Carbon (Medium)` | `pending` | — | ⬜ | 轻量单页 WebUI 壳 → Alpha MVP |
| `M08` | 分级本地安全沙箱 | 管大脑：`Claude Opus 5.5 / Gemini 4 Neon` | `pending` | — | ⬜ | — |
| `M09` | CodeAct、上下文四件套与亲和 Subagent | 管大脑：`Gemini 4 Neon (Extra High)` | `pending` | — | ⬜ | 完成后达 Beta 里程碑 |
| `M10` | 分层本地记忆引擎与 1 秒反馈闭环 | 管编码：`Gemini 4 Carbon / Claude Sonnet 5.5` | `pending` | — | ⬜ | — |
| `M11` | 双闸门防坍塌自演化引擎与普惠导出 | 管大脑：`Gemini 4 Neon / Claude Opus 5.5` | `pending` | — | ⬜ | 完成后达 RC 里程碑 |
| `INT-4` | 五维整体测试、离线打包与正式上线 | 管编码 + 管电脑 + 大脑抽检 | `pending` | — | ⬜ | `v1.0.0` 发布 |

---

## 二、最新会话无缝交接快照（供下一次新会话直接接棒）

- **更新时间**：2026-11-27 08:55
- **已完成**：
  1. `M00`–`M04` 已完成公开开源发布（`https://github.com/liyunhe135-bot/huiqiao-os`，云端 CI 绿灯）；
  2. **`M05`（持久化 ADK 五原语编排引擎、SQLite WAL 强杀续跑、HITL `interrupt()` 挂起恢复、中途改向 `steer()`、部分产物保留与 YAML 声明流）完整落盘**；
  3. **全仓库 `89 / 89` 项单测 100% 绿灯**，`python -m packages.core.cli` 6/6 全通过。
- **单写者锁状态**：`forge/.active_writer.lock` 持续开启，严禁其他智能体并发修改本目录。
- **下一块待施工**：**`M06`（柔硬结合路由与语义共生执行内核 `L2-S` + `ReActWorker`）**
- **推荐切换模型**：
  - 优先：**`Gemini 4 Carbon (Medium)`**（管编码，比 `Extra High` 省 55% 额度，完全胜任！）
- **下一会话极简开场指令**（执行 `python forge/scripts/forge_guard.py brief M06` 也可自动生成）：
  > 请激活 `huiqiao-forge-os` 技能，开始施工汇桥 OS 积木 `M06`（柔硬结合路由与语义共生执行内核）。仅读取 `forge/BRICK_CONTEXT_CARD.md`、`forge/PROGRESS_LEDGER.md` 和 `packages/orchestrator/engine.py`，先输出文件清单、路由与 Worker 接口骨架（<100 行），确认后落盘并跑通 `forge_guard.py test`。
