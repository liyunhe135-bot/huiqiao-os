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
| `M09` | CodeAct、上下文四件套与亲和 Subagent | 管大脑：`Gemini 4 Neon (Extra High)` | `done` | 100% | ✅ | **Phase 2 Beta 里程碑达成（`v0.2.0-beta`）**：`context_engine.py` + `codeact.py` + `subagent.py` + 网关接入，全库 138/138 |
| `M10` | 分层本地记忆引擎与 1 秒反馈闭环 | 管编码：`Gemini 4 Carbon / Claude Sonnet 5.5` | `done` | 100% | ✅ | `packages/memory/`（`MEMORY.md`双向同步+每日日志+中英FTS5/向量混合双时态+4键反馈<200ms+种子捕获），全库 145/145 |
| `M11` | 双闸门防坍塌自演化引擎与普惠导出 | 管大脑：`Gemini 4 Neon / Claude Opus 5.5` | `next` | — | ⬜ | Phase 3 收官块：完成后达 **RC** 里程碑 |
| `INT-4` | 五维整体测试、离线打包与正式上线 | 管编码 + 管电脑 + 大脑抽检 | `pending` | — | ⬜ | `v1.0.0` 发布 |

---

## 二、最新会话无缝交接快照（供下一次新会话直接接棒）

- **更新时间**：2026-11-27 13:09
- **已完成**：
  1. `M00`–`M09`（含 Alpha `v0.1.0-alpha` 与 Beta `v0.2.0-beta`）全部通过并公开备份；
  2. **`M10`（`B08` File-First 分层本地记忆引擎：`packages/memory/` — `MEMORY.md` 人类第一真相源自动双向同步 + `memory/YYYY-MM-DD.md` 每日情景日志 + SQLite WAL/中英 FTS5/128维特征向量混合双时态检索 + 一键遗忘 + 1 秒 4 键反馈闭环［赞/踩/纠偏/存为技能种子］ + FastAPI/CLI/零CDN WebUI 全栈挂接）完整落盘**；
  3. **全仓库 `145 / 145` 项单测与端到端验收 100% 绿灯（4.11s）**，开源隐私卫生扫描 `HYGIENE_100_CLEAN`！
- **单写者锁状态**：`forge/.active_writer.lock` 持续开启，严禁其他工具并发写入本目录。
- **下一块待施工**：**`M11`（`B09` 双闸门防坍塌自演化引擎［闸门1：独立 `M08` 沙箱客观回归单测 + 闸门2：`C00` 增上四问一票否决审查 + 人类可逆签发］ + 高配反哺低配普惠便携技能包导出 `.hqskill.zip` → Phase 3 RC 里程碑 `v0.9.0-rc1`）**
- **推荐切换模型**：
  - 优先：**`Gemini 4 Neon (Extra High)`** 或 **`Claude Opus 5.5 (Thinking)`**（`M11` 是全系统防 Model Collapse 自演化与 `C00` 强扶弱普惠导出的最高治理闭环，强烈建议切回“管大脑”模型把关！）
- **下一会话极简开场指令**（执行 `python forge/scripts/forge_guard.py brief M11` 也可自动生成）：
  > 请激活 `huiqiao-forge-os` 技能，开始施工汇桥 OS 积木 `M11`（B09 双闸门防坍塌自演化引擎与普惠技能导出 → RC 里程碑）。仅读取 `forge/BRICK_CONTEXT_CARD.md`、`forge/PROGRESS_LEDGER.md`、`packages/memory/feedback.py` 和 `packages/core/constitution.py`，先输出模块接口与验收清单（<100 行），落盘并跑通 `forge_guard.py test`。
