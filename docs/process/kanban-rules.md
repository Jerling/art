# Kanban 任务拆分 + Done 判定 — 顶层索引（R3 + R7 + R2）

> **Source**: Sprint 4 复盘 R3（拆子任务）+ R7（小改动阈值）+ R2（e2e_evidence 字段）
> **Owner**: product-manager（拆解 + 验证）+ sre（e2e_evidence 实施）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_7c0bf7af 任务产物）
> **本文件角色**: 顶层"什么时候用哪个"索引,具体规则在子文档

---

## 1. 本文件角色

R3 + R7 + R2 的具体规则分别在以下子文档:

| 文件 | 范围 | 来源 |
|---|---|---|
| [`sprint-decomposition.md`](./sprint-decomposition.md) | **R3 详细**: Sprint 拆解粒度 (≥5 子任务) + Integration Verification 子任务模板 + Frontend build artifact 子任务模板 + 拆解工作流 + verify checklist | t_add2601d (R3 deep-dive) |
| [`done-criteria.md`](./done-criteria.md) | **R7 详细 + R2 详细**: done v2.0 四件套 (代码/CI/PRD/e2e_evidence) + e2e_evidence 三种形式 + SPA 类任务 e2e_evidence 强制类型 + Integration Verification 子任务的 e2e_evidence 特殊要求 + PM 自检清单 | t_add2601d (R7 + R2 deep-dive) |

本文档是**索引视角**——讲"什么时候用 R3 / 什么时候用 R7 / 什么时候用 R2",不讲具体规则细节。**要看具体规则,直接打开上面 2 个子文档**。

---

## 2. R3 — 任务拆分粒度（什么时候必须拆）

### 2.1 拆解规则触发

| 场景 | 必须拆吗? | 至少多少子任务 | 看哪里 |
|---|---|---|---|
| 任何新 Sprint kickoff | 是 | 通用 ≥5,修复类 ≥3,文档类 ≥2 | `sprint-decomposition.md` §2.1 |
| Bug fix | 是 | ≥3 (复现 + 修复 + 回归) | `sprint-decomposition.md` §2.1 |
| 文档/流程类改动 | 是 | ≥2 (起草 + review/merge) | `sprint-decomposition.md` §2.1 |
| 单文件 typo | 否 | — | `sprint-decomposition.md` §1 |
| CI 工具链改动 | 是 (但走白名单) | 视情况 | `ci-rules.md` §3 |

### 2.2 拆解必含的固定项

| 固定项 | 何时必有 | 看哪里 |
|---|---|---|
| **Integration Verification 子任务** | 每个 Sprint 必有 (R3 硬规则) | `sprint-decomposition.md` §2.2.1 |
| **Frontend build artifact → backend integration 子任务** | 涉及前端改动时必有 | `sprint-decomposition.md` §2.2.2 |
| **e2e_evidence 字段** | 每个子任务 done 时必有 (R2) | `done-criteria.md` §3 |

### 2.3 拆解工作流

见 `sprint-decomposition.md` §3:
- PM 写 PRD (1 页,scope/non-scope/验收/风险)
- software-architect 评审 PRD 5 分钟
- PM 拆子任务卡片
- 建 Integration Verification 子任务 + link parent
- jerry review 签字 → Sprint N 启动

---

## 3. R7 — 小改动阈值（什么时候必须有 board 任务）

### 3.1 触发条件

任何 PR/commit **变更文件数 > 3**,**或** 涉及 `middleware/` / `auth/` / `dependency/` / `router/` → **必须**先在 board 建任务并提交。详见 `dev-workflow.md` §1 Step 4 + `ci-rules.md` §2。

### 3.2 完整规则 (含白名单 + 违规处理)

见 `ci-rules.md` §3 (本目录内 PM-owned 规则文档) + `docs/operations/ci-parent-task-check.md` (sre-owned 实施文档)。

**关键判定**:
- 白名单场景: 单文件 typo / 依赖 bump / CI 配置文件本身 / 文档 typo / 已废弃代码删除 (≤3 文件) — 不需 task
- 违规处理: code-reviewer 在 PR review 时检查并拒绝 (强制)
- 触达 + 无 task ID → R1 CI 自动拦截 (workflow fail)

---

## 4. R2 — Done 判定标准

### 4.1 Done 必须满足的 4 件套 (R7 详细)

| # | 检查项 | 谁负责 | 详细 |
|---|---|---|---|
| 1 | 代码已合入 | developer | `done-criteria.md` §2 #1 |
| 2 | CI 全绿 | sre | `done-criteria.md` §2 #2 |
| 3 | PRD / 任务 acceptance criteria 逐条满足 | developer + PM | `done-criteria.md` §2 #3 |
| 4 | `e2e_evidence` 字段非空 | developer | `done-criteria.md` §2 #4, §3 |

**判定**: 4 项缺任一 → 不允许 done → kernel 拒绝 `kanban_complete` (exit 3)。

### 4.2 e2e_evidence 三种形式 (按优先级)

1. **自动 E2E 证据** (首选): Playwright trace / curl log / CI artifact
2. **手工验证 note** (次选): 不可自动跑的改动 (CI 配置 / 文档 / dead code 删)
3. **显式 bypass + 理由** (最后手段): `e2e_evidence_override` 字段,审计为 `completion_override_no_e2e_evidence` 事件

详细 + 失败模式: `done-criteria.md` §3 + `../operations/kanban-e2e-evidence.md`

### 4.3 SPA / Web UI 类任务 e2e_evidence 强制类型

凡涉及前端路由的任务,**只接受**:
- Playwright trace (URL 变化 + DOM 渲染)
- `w3m -dump <URL>` 输出 (验证 SPA fallback 不 404)
- 浏览器截图 (首屏 + 至少 1 个深层路径)

**不接受**: 单独的 `curl /` 200 / 单独的 UI 首页截图。

详细: `done-criteria.md` §3.4

---

## 5. 子任务 ↔ Sprint 收尾的依赖 (R3 + R4 联动)

```
Sprint N 子任务全部 done (含 §4 四件套 + e2e_evidence)
  ↓
[Sprint N] Integration Verification 子任务才能开始
  ↓
Integration Verification 子任务 done (含 happy path trace + 3 张截图 + 一句话 summary)
  ↓
Sprint N 才算收尾 (PM 才能宣告 Sprint N 完成)
  ↓
Sprint N+1 kickoff 才能启动
```

详细: `done-criteria.md` §4 + `sprint-decomposition.md` §2.2.1

---

## 6. PM 自检清单 (Sprint close 时逐条)

**R3 拆解合规**:
- [ ] Sprint N 父任务在 board 上,列出 ≥5 个子任务 (修复类 ≥3,docs ≥2)
- [ ] Integration Verification 子任务的 `parents` 包含所有 Sprint N 子任务 ID
- [ ] 每个子任务的 `body` 都有可独立验收的 acceptance criteria
- [ ] 涉及前端时存在 "Frontend build artifact → backend integration" 子任务

**R7 done 判定合规** (4 件套):
- [ ] 代码已合入 (git log)
- [ ] CI 全绿 (sre)
- [ ] PRD / 任务 acceptance criteria 逐条满足
- [ ] `metadata.e2e_evidence` 非空

**R2 e2e_evidence 合规**:
- [ ] SPA 类任务的 e2e_evidence 是 Playwright / w3m / 截图 (非 curl/UI 单图)
- [ ] Integration Verification 子任务的 e2e_evidence 含 happy path trace + 3 张截图 + 一句话 summary
- [ ] 任何 `e2e_evidence_override` 都有合理 reason,PM 在 retro review

**判定**: 4 + 4 + 3 = 11 条全过 → Sprint N 流程合规;任一不过 → retro 记为 process gap。

---

## 7. 与其他文档的关系

- **R3 详细**: `sprint-decomposition.md` (PM-owned, R3 deep-dive)
- **R7 + R2 详细**: `done-criteria.md` (PM-owned, R7 + R2 deep-dive)
- **R7 CI 实施**: `ci-rules.md` §3 (PM-owned 规则) + `../operations/ci-parent-task-check.md` (sre-owned 实施)
- **R2 e2e_evidence 实施**: `../operations/kanban-e2e-evidence.md` (sre-owned)
- **R5 user-verify 4 day**: `user-verification.md` (PM-owned) + `../operations/user-verify-deadline.md` (sre-owned)
- **R4 retro 强制化**: `.project-memory.md` → Sprint close 流程
- **R1 CI 强制 task ID**: `ci-rules.md` §2 + `../operations/ci-parent-task-check.md`
- **来源 retro**: `../post-mortem/sprint4-process-gap.md` §5 R3 / R7
- **8 步开发流程**: `dev-workflow.md`

---

## 8. 反例 / 教训 (顶层视角)

### 反例 1 — Sprint 4 JWT (核心反例)

| 拆解失败 | done 判定失败 | 修复 |
|---|---|---|
| 1 个 commit 顶 9 文件,没拆子任务 | 旧 v1.0 done (commit + CI 绿 + summary) | R3 拆解粒度 + R7 v2.0 四件套 |
| 无 Integration Verification 子任务 | 无 e2e_evidence | R3 §2.2.1 强制 IV 子任务 + R2 e2e_evidence 字段 |
| 无 PRD → PM 无可审 | 无 user-verify | R5 PM 三问 + R4 user-verify 4 day deadline |

详细: `sprint-decomposition.md` §5 + `done-criteria.md` §6 + `../post-mortem/sprint4-process-gap.md` §2

### 反例 2 — Sprint 4 fix `t_0e04abde` (fix 后 fix)

`done-criteria.md` §6 反例 2 + `done-criteria.md` §3.4 (SPA 类 e2e_evidence 强制) 直接催生。

### 反例 3 — Sprint 3 close 时无 Integration Verification

`done-criteria.md` §6 反例 3 + `sprint-decomposition.md` §5 反例 2 共同覆盖。
