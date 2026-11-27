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
| `M11` | 双闸门防坍塌自演化引擎与普惠导出 | 管大脑：`Gemini 4 Neon / Claude Opus 5.5` | `done` | 100% | ✅ | **Phase 3 RC 里程碑达成（`v0.9.0-rc1`）**：`packages/evolution/`（Gate1 沙箱单测 + Gate2 C00 一票否决 + 人工签发 + 回滚 + `.hqskill.zip` 普惠导出导入），全库 151/151 |
| `INT-4` | 五维整体测试、离线打包与正式上线 | 管编码 + 管电脑 + 大脑抽检 | `next` | — | ⬜ | Phase 4 收官冲刺：`v1.0.0` 正式发布 |

---

## 二、最新会话无缝交接快照（供下一次新会话直接接棒）

- **更新时间**：2026-11-27 13:24
- **已完成**：
  1. **全部 12 块核心乐高积木（`M00–M11`：`C00` 宪章 + `B01–B10` 全部槽位）100% 施工闭环**；
  2. **`M11`（`B09` 双闸门防坍塌自演化引擎：`packages/evolution/` — Gate 1 独立 `M08` T2 离线沙箱客观单测 + Gate 2 `C00` 增上四问一票否决 + 人类审阅签发热刷新 `HybridRouter` + 一键回滚 + 高配反哺低配 `.hqskill.zip` 隐私体检/SHA-256 防篡改/防 Zip-Slip 导出导入；并顺手根治了 Windows `python -I` 隔离模式下 `-X utf8` 中文编码问题）完整落盘**；
  3. **全仓库 `151 / 151` 项单测与全栈验收 100% 绿灯（4.70s）**，开源隐私扫描 `HYGIENE_100_CLEAN`，正式达成 **`v0.9.0-rc1`（Phase 3 RC 里程碑）**！
- **单写者锁状态**：`forge/.active_writer.lock` 持续开启，严禁其他工具并发写入本目录。
- **下一块待施工**：**`INT-4`（Phase 4 终极五维整体评测、离线便携打包脚本、用户快速上手手册与 `v1.0.0` 正式发布）**：
  1. 断网 E2E 闭环压测（覆盖全部 5 通道 + 记忆 + 自演化 + 普惠包导入导出）；
  2. 轨迹与路由评测报告自动生成（`evals/run_int4_eval.py` → 输出 Markdown 五维验收报告）；
  3. 安全红队总复检 + 显存亲和调度压测 + C00 增上盲测打分卡；
  4. 一键离线便携启动与打包脚本（`scripts/start_huiqiao.ps1` / `scripts/build_portable_bundle.py`）+ `v1.0.0` 正式发版！
- **推荐切换模型**：
  - 优先：**`Gemini 4 Carbon (Medium)`**（编排评测脚本与离线打包）或 **保持当前 `Gemini 4 Neon (Extra High)`** 一鼓作气完成 `INT-4` 五维终审并打标 **`v1.0.0`**！
- **下一会话极简开场指令**：
  > 请激活 `huiqiao-forge-os` 技能，开始执行汇桥 OS 终极收官 `INT-4`（五维整体评测、离线一键打包脚本与 `v1.0.0` 正式发版）。仅读取 `forge/BRICK_CONTEXT_CARD.md` 与 `forge/PROGRESS_LEDGER.md`，输出五维验收清单，落盘 `evals/` 评测器与 `scripts/` 离线启动打包脚本，跑通全量测试并发布 `v1.0.0`。
