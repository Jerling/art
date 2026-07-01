# Art 流程文档目录

> **Owner**: product-manager
> **Last updated**: 2026-07-02（t_7c0bf7af 任务产出）
> **目的**: jerry + 团队成员翻这个目录,5 秒内能找到当前需要的流程规则

---

## 1. 我要找什么? 跳哪里?

| 我想... | 跳到 |
|---|---|
| 了解当前团队怎么开发（8 步流程） | [`dev-workflow.md`](./dev-workflow.md) |
| 看 Sprint 拆任务时怎么拆、为什么这么拆 (R3 详细) | [`sprint-decomposition.md`](./sprint-decomposition.md) |
| 看 task 什么时候算 done、e2e_evidence 怎么填 (R7 + R2 详细) | [`done-criteria.md`](./done-criteria.md) |
| 看 R3 / R7 / R2 顶层索引 + 什么时候用哪个 | [`kanban-rules.md`](./kanban-rules.md) |
| 看 review 各自 catch 什么、catch 不到什么 (R6 详细) | [`review-matrix.md`](./review-matrix.md) |
| 看 review 框架的顶层视角 (R6 + R5 索引) | [`review-checklist.md`](./review-checklist.md) |
| 看用户验证 4 天 deadline 怎么算、什么时候 auto-block (R5) | [`user-verification.md`](./user-verification.md) |
| 看 CI 强制 task ID 检查怎么跑、白名单场景 (R1) | [`ci-rules.md`](./ci-rules.md) |
| 看 whitelist.json schema (PM-controlled 紧急 bypass 机制) | [`whitelist-schema.md`](./whitelist-schema.md) |
| 看 Sprint close 时 retro 怎么写 | [`.project-memory.md`](../.project-memory.md) → Sprint close 流程 |
| 看 PM 持有 feature completeness 三问 (R5 详细) | [`.project-memory.md`](../.project-memory.md) → PM 角色职责 |

---

## 2. 文件清单 — 按 R-item 分组

| R-item | 详细文档 | 顶层索引 |
|---|---|---|
| **R1** CI 强制 task ID 检查 | (sre 实施) `../operations/ci-parent-task-check.md` | [`ci-rules.md`](./ci-rules.md) §2 |
| **R2** e2e_evidence 字段 | (sre 实施) `../operations/kanban-e2e-evidence.md` + (PM 详细) [`done-criteria.md`](./done-criteria.md) §3 | [`kanban-rules.md`](./kanban-rules.md) §4 |
| **R3** Sprint 拆解粒度 | (PM 详细) [`sprint-decomposition.md`](./sprint-decomposition.md) | [`kanban-rules.md`](./kanban-rules.md) §2 |
| **R4** 4-day user-verify deadline (sre 实施用 5 business days) | (PM 详细) [`user-verification.md`](./user-verification.md) + (sre 实施) `../operations/user-verify-deadline.md` | — |
| **R5** PM 功能完整性三问 | (PM 详细) `../.project-memory.md` → PM 角色职责 | [`review-checklist.md`](./review-checklist.md) §3 |
| **R6** 4 层 review 矩阵 | (PM 详细) [`review-matrix.md`](./review-matrix.md) | [`review-checklist.md`](./review-checklist.md) §2 |
| **R7** 小改动阈值 + done v2.0 | (PM 详细) [`done-criteria.md`](./done-criteria.md) §2 | [`kanban-rules.md`](./kanban-rules.md) §3 |
| **R6 retro 强制化** (Sprint close 流程) | (PM 详细) `../.project-memory.md` → Sprint close 流程 | [`dev-workflow.md`](./dev-workflow.md) §1 Step 8 |

---

## 3. 文件状态表 (本目录所有文件)

| 文件 | 范围 | Owner | 来源 | 状态 |
|---|---|---|---|---|
| [`index.md`](./index.md) | 本文件 - 目录导航 | PM | t_7c0bf7af | ✅ |
| [`dev-workflow.md`](./dev-workflow.md) | 8 步开发流程 + R3/R5/R6/R7 整合 | PM | t_7c0bf7af | ✅ |
| [`sprint-decomposition.md`](./sprint-decomposition.md) | R3 Sprint 拆解模板（深度） | PM | t_add2601d | ✅ |
| [`done-criteria.md`](./done-criteria.md) | R7 done v2.0 + R2 e2e_evidence（深度） | PM | t_add2601d | ✅ |
| [`kanban-rules.md`](./kanban-rules.md) | R3 + R7 + R2 顶层索引 | PM | t_7c0bf7af | ✅ |
| [`review-matrix.md`](./review-matrix.md) | R6 4 层 review × 6 维度（深度） | PM | t_add2601d | ✅ |
| [`review-checklist.md`](./review-checklist.md) | R6 + R5 顶层索引 | PM | t_7c0bf7af | ✅ |
| [`user-verification.md`](./user-verification.md) | R4 user-verify 4 day deadline (实际跑 5 business days) | PM | t_add2601d | ✅ |
| [`ci-rules.md`](./ci-rules.md) | R1 parent-task-check + 白名单 + 失败模式 | PM | t_7c0bf7af | ✅ |
| [`whitelist-schema.md`](./whitelist-schema.md) | whitelist.json schema (PM-controlled bypass 机制) | PM | t_add2601d | ✅ |

**Legend**:
- ✅ 已 ship
- ⏳ pending review / merge
- ❌ 不推荐 (冲突或已废弃)

---

## 4. 配套文件 (其他目录)

### 4.1 实施类 - sre / 工程团队拥有

| 文件 | 范围 | Owner | 关联本目录的哪个 |
|---|---|---|---|
| [`../operations/ci-parent-task-check.md`](../operations/ci-parent-task-check.md) | R1 实施细节: workflow YAML / script / test / 失败模式 | sre | `ci-rules.md` |
| [`../operations/kanban-e2e-evidence.md`](../operations/kanban-e2e-evidence.md) | R2 e2e_evidence 字段: 接受形式 / 失败模式 / override | sre | `done-criteria.md` §3 |
| [`../operations/user-verify-deadline.md`](../operations/user-verify-deadline.md) | R4 cron 实施 / CAS / business_days 计算 (5 business days) | sre | `user-verification.md` |
| [`../operations/spa-fallback.md`](../operations/spa-fallback.md) | Sprint 4 SPA fallback fix 的 manual smoke test | sre | (历史 fix 文档,非流程) |

### 4.2 复盘类 - 历史参考

| 文件 | 范围 |
|---|---|
| [`../post-mortem/sprint4-process-gap.md`](../post-mortem/sprint4-process-gap.md) | Sprint 4 JWT 事件 post-mortem,本目录所有 R1-R7 规则的来源 |
| [`../post-mortem/sprint5-retro.md`](../post-mortem/sprint5-retro.md) | Sprint 5 retro 占位 (R6 强制化产物) |

### 4.3 规划类 - 高层文档

| 文件 | 范围 |
|---|---|
| [`../planning/technical-plan.md`](../planning/technical-plan.md) | 技术方案（v0.3） |
| [`../planning/product-roadmap.md`](../planning/product-roadmap.md) | 产品路线图（v0.3） |
| [`../planning/research-report.md`](../planning/research-report.md) | 竞品调研（320 行） |
| [`../SPRINT-PLAN.md`](../SPRINT-PLAN.md) | Sprint 0-3 详细规划 |

### 4.4 根目录 quick reference

| 文件 | 范围 |
|---|---|
| [`../.project-memory.md`](../.project-memory.md) | 团队阵型 / 角色 / 简报（流程章节已抽到本目录,此文件保持"快速 reference"）|

---

## 5. 阅读路径建议

### 5.1 新成员上手

```
1. ../.project-memory.md  (团队阵型 + Sprint 历史)
   ↓
2. ./dev-workflow.md  (8 步流程 + 反例)
   ↓
3. ./review-checklist.md + ./review-matrix.md  (4 层 review + 盲区,理解"每个 role 看不到什么")
   ↓
4. ./user-verification.md + ./ci-rules.md  (gate 机制)
```

### 5.2 准备 kickoff 一个新 Sprint

```
1. ./sprint-decomposition.md  (拆解模板,最少 5 子任务)
2. ./kanban-rules.md §2  (R3 + R7 触发条件 + 顶层索引)
3. ./user-verification.md §3  (Integration Verification 触发机制)
4. ../.project-memory.md → PM 角色职责  (R5 三问)
```

### 5.3 review 一个 PR

```
1. ./review-checklist.md  (4 层 scope + 盲区)
2. ./review-matrix.md §2  (4 层 × 6 维度详细矩阵)
3. ./kanban-rules.md §3  (R7 检查: >3 文件 / 触达路径)
4. ./ci-rules.md §4  (R1 失败模式速查)
5. ../.project-memory.md → PM 角色职责  (R5 三问 - 触达 middleware/auth 时)
```

### 5.4 Sprint close

```
1. ../.project-memory.md → Sprint close 流程  (R6 强制)
2. ./user-verification.md §7  (R4 user-verify 合规自检)
3. ./kanban-rules.md §6  (R3+R7+R2 11 条自检)
4. ./ci-rules.md §6  (R1 CI 合规自检)
5. ./review-checklist.md §7  (review 合规自检)
```

### 5.5 找具体规则

| 我想... | 跳到 |
|---|---|
| Sprint ≥5 子任务怎么拆? | `sprint-decomposition.md` §2 |
| e2e_evidence 怎么填? | `done-criteria.md` §3 |
| SPA 类 e2e_evidence 强制什么? | `done-criteria.md` §3.4 |
| PM 三问全文? | `../.project-memory.md` → PM 角色职责 |
| review 4 层 verdict 模板? | `review-matrix.md` §2.2 |
| 4 天 deadline 怎么算? | `user-verification.md` §2 |
| whitelist 怎么加 entry? | `whitelist-schema.md` |
| CI R1 怎么跑? | `../operations/ci-parent-task-check.md` |
| Sprint close 强制 retro 流程? | `../.project-memory.md` → Sprint close 流程 |

---

## 6. 文档关系图

```
                      .project-memory.md (quick ref)
                              │
                              │ 引用
                              ▼
                       dev-workflow.md (8 步框架)
                       /    │    │    \
                      /     │    │     \
                     ▼      ▼    ▼      ▼
       sprint-decomposition.md  kanban-rules.md  review-checklist.md  user-verification.md
       (R3 深度)               (R3+R7+R2 索引) (R6+R5 索引)         (R4 deadline)
                                     │    │              │
                                     │    │              │
                                     ▼    ▼              ▼
                                done-criteria.md ────► review-matrix.md
                                (R7 + R2 深度)        (R6 4 层 × 6 维度)
                                     │
                                     │
                                     ▼
                                ci-rules.md ──────────────────────► ../operations/*
                                (R1 + 白名单)                          (sre 实施)
                                     │
                                     ▼
                                whitelist-schema.md
                                (whitelist.json schema)
```

**关键不变量**:
- 本目录的 `*.md` 是 **PM 拥有的规则文档** ——讲"为什么"和"什么时候用"
- `../operations/*.md` 是 **sre 拥有的实施文档** ——讲"具体怎么实现"和"代码位置"
- 顶层索引 doc (`dev-workflow.md` / `kanban-rules.md` / `review-checklist.md`) → 详细 sub-doc (sprint-decomposition.md / done-criteria.md / review-matrix.md / user-verification.md)
- 任何改动都先改本目录规则 → 改 ../operations/ 实施 → 改 ../post-mortem/ 复盘引用

---

## 7. 维护规则

### 7.1 何时更新本目录

| 触发 | 更新什么 |
|---|---|
| Sprint 复盘发现新的 R-item | 新建对应 `*.md`,加到本 index |
| 现有 R-item 规则有调整 | 更新对应 `*.md`,commit message 引用 PM 任务 |
| 团队角色变更 | 更新 `dev-workflow.md` §2 流程判定边界 |
| 工具链变更 (CI / kanban / hermes) | 通知 sre 同步 `../operations/*.md`,本目录引用更新 |

### 7.2 谁可以改

- **PM 任务** 引用: 任何改本目录的 PR 都必须 reference 一个 PM 任务 id
- **不**强制 R7 (改动的是 docs/process/ 而非代码),但建议在 commit message 加 `(#t_xxx)` 跟踪

### 7.3 何时不同步

- `dev-workflow.md` §1 8 步 vs `../.project-memory.md` "Sprint close 流程" — 后者是历史沉淀,前者是当前规则。**如有冲突,以 `dev-workflow.md` 为准**。
- 任何"快速参考"放在 `../.project-memory.md`,详细规则在本目录。
- **t_add2601d vs t_7c0bf7af 冲突**: t_add2601d 4 个深度 doc (sprint-decomposition / done-criteria / review-matrix / user-verification) + whitelist-schema; t_7c0bf7af 5 个 spec'd 文件 (dev-workflow / kanban-rules / review-checklist / user-verification / ci-rules)。冲突解决: t_7c0bf7af 的 5 个文件覆盖 t_add2601d 的 4 个同主题 doc 中 (user-verification) — 其他 4 个 doc 共存,kanban-rules.md / review-checklist.md 变成"顶层索引"指向 t_add2601d 的深度 doc,避免重复。

---

## 8. R-number reconcile 备注

> 本目录的 R-number 体系有两个来源,jerry 看时会有 confusion。**两边都保留,各自 internal 一致**:
> - **retro §5 R-number** (Sprint 4 post-mortem 原始标号): R1=parent-task-check, R2=e2e_evidence, R3=Integration Verification, R4=user-verify deadline, R5=PM feature completeness, R6=retro cadence, R7=small change threshold
> - **t_add2601d 改称 R-number** (PM doc 内部,任务 spec 改的): R3=same, R5=user-verify (≠ retro R5), R6=review matrix (≠ retro R6), R7=done v2.0 (≠ retro R7)
> - **t_7c0bf7af 沿用 retro R-number** (本任务 spec 沿用 retro,但用得较松): R3+R5+R6+R7 都指 retro §5 编号

**判定原则**:
- 看 `sprint-decomposition.md` / `done-criteria.md` / `review-matrix.md` / `user-verification.md` / `whitelist-schema.md` → 用 t_add2601d R-number
- 看 `dev-workflow.md` / `kanban-rules.md` / `review-checklist.md` / `ci-rules.md` → 用 retro R-number
- 跨文件引用时,**两个 doc 都明确写出"本 doc 使用 R-number 来源"**

下次 retro (Sprint 5 close) 必须 reconcile: 决定是统一用 retro §5 R-number,还是 t_add2601d 改称 R-number。
