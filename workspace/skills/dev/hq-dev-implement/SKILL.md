---
name: hq-dev-implement
description: 按 tasks.md 逐任务实现代码。当规格冻结、开始写代码时使用。每步先跑验证门再进下一步；单次改动 ≤400 行。
---

# 实现器（Implement，逐任务 + 每步验证）

## 触发
spec/plan/tasks 已冻结，开始施工某一块积木。

## 输入
tasks.md + 相关 spec/AC + 目标包目录。

## 步骤
1. 取下一个未完成 task（按依赖顺序）。
2. 写实现（单次改动 ≤400 行；先写测试骨架再写实现——先测后写）。
3. 跑该 task 声明的验证命令（lint/typecheck/test/脚本）。
4. 通过 → 记录到 tasks.md 勾选并提交；失败 → 本地修复（同错 2 次后升级到 Brain 档并记入账本）。
5. 全部 task 完成 → 生成变更清单，交给 hq-dev-review。

## 验证
- 每 task 的验证命令执行记录保留（执行日志）。
- 不通过不得进入下一 task。

## 坑
- 禁止顺手重构任务范围外的文件（范围蔓延）。
- 大文件读用 offset/limit；禁止整仓 dump。
- 模型档位由 hq-model-router 裁决，不得自行升级。
