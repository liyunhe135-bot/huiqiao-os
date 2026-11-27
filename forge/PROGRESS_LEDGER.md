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
| `INT-4` | 五维整体测试、离线打包与正式上线 | 管编码 + 管电脑 + 大脑抽检 | `done` | 100% | ✅ | **`v1.0.0` 正式发版达成**：五维评测 `5/5` PASS + 离线便携包(232KB) + `USER_GUIDE.md` + 全库 `155/155` 全绿 |

---

## 二、最新会话无缝交接快照（全周期圆满收官 · `v1.0.0` GA 正式版）

- **更新时间**：2026-11-27 13:42
- **圆满完成（`M00–M11 + INT-4` 100% 闭环）**：
  1. **全部 12 块核心乐高积木（`C00` 众生和谐增上宪章 + `B01–B10` 十大可插拔模块）+ `INT-4` 终极收官 100% 完工闭环**；
  2. **五维整体自动评测（`evals/run_int4_eval.py`）`5 / 5` 全维度 PASS**，已正式生成 [08_v1.0.0_五维验收与评估报告.md](../docs/08_v1.0.0_五维验收与评估报告.md)；
  3. **离线便携发行包与一键启动体系就绪**：`scripts/build_portable_bundle.py` 已实打出零个人数据残留、内置 5 个 `.hqskill.zip` 普惠技能包与 SHA-256 完整性清单的 `dist/huiqiao-os-v1.0.0-portable.zip`（104 文件 / 232 KB），配套 `scripts/start_huiqiao.ps1` / `start_huiqiao.sh` 与 `USER_GUIDE.md`；
  4. **全仓库 `155 / 155` 项单测与红队/端到端测试 100% 绿灯（5.84s）**，开源隐私扫描 `HYGIENE_100_CLEAN`，正式打标发布 **`v1.0.0`**！
- **后续日常演进建议**：
  - 平时在本机打开工作台：运行 `powershell -ExecutionPolicy Bypass -File scripts/start_huiqiao.ps1` 访问 `http://127.0.0.1:8765`；
  - 积累新的高价值运行后：用 WebUI「存为技能种子」→ `evolve <seed_id> --approve` 双闸门沉淀为本地新技能，并可用 `export-skill` 导出 `.hqskill.zip` 反哺低配设备。
- **汇桥（DeepSeek 版）验证轮（2026-11-27 15:20）**：
  - 接管锁后全量复验发现 `test_rt08_ctypes_ffi_escape_blocked` 回归变红：此前对 `packages/sandbox/t2_os.py` 的修复（审计钩子 ctypes/winreg/msvcrt 分支改抛非 OSError 专用异常 `_HQBlockedError`，防 `ctypes.LibraryLoader.__getattr__` 以 `except OSError` 吞并拦截）曾被并发写入覆盖丢失；
  - 已重新落盘该修复；`forge_guard.py preflight` 与 `forge_guard.py test tests/` **全量 ALL PASS**（exit 0），`v1.0.0` 状态复核一致；
  - 交接：`packages/sandbox/t2_os.py` 的 `_HQBlockedError` 为安全关键修复，后续合并/重写该文件时请勿回退为 `PermissionError`。
- **汇桥（DeepSeek 版）自举实战（2026-11-27 16:15）**：
  - 用系统自身 `run`（L2C_CODEACT + 本地模型 + M08 沙箱）生成「俱舍诵疏·背诵」单文件小程序 → `workspace/demo_apps/jushe_recite.html`（11.9KB，零外部依赖）；
  - 人工验收发现 3 处功能性伪造（`saveProgress` 拼写错误、遮罩 CSS `content` 对普通元素无效、随机隐藏缺 mode 类）→ 已修复为 `data-orig + textContent` 切换方案；
  - 已通过 CLI `feedback … correct` 走通 M10 1 秒反馈闭环（5.04ms 落盘 `mem_be33ce2f021d`）；顺带修复 `apps/cli/main.py` 的 GBK 控制台 `UnicodeEncodeError`（stdout 统一 UTF-8）。
