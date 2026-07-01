# Review 评审框架 — 顶层索引（R6 + R5）

> **Source**: Sprint 4 复盘 `docs/post-mortem/sprint4-process-gap.md` §4 Q5 + §5 R5 + §5 R6
> **Owner**: product-manager（矩阵设计 + PM 层 review）+ code-reviewer / test-lead / OpenCode（执行层 review）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_7c0bf7af 任务产物）
> **本文件角色**: 顶层"每层 review 看不到什么"框架索引,具体矩阵在子文档

---

## 1. 本文件角色

R6 (review matrix) + R5 (PM 三问) 的具体规则在以下子文档:

| 文件 | 范围 | 来源 |
|---|---|---|
| [`review-matrix.md`](./review-matrix.md) | **R6 详细**: 4 层 review × 6 维度矩阵 + 每层 verdict 模板 + 盲区识别 + 评审串联规则 + PM 自检清单 | t_add2601d (R6 deep-dive) |
| `../.project-memory.md` → PM 角色职责 / Pre-merge checklist | **R5 详细**: PM 三问 (入口/验证/迁移) 完整定义 + 触发条件 | t_45525d1f (R5 inline,已 commit) |

本文档是**框架视角**——讲"为什么每层 review 都有盲区,需要 PM 这一层来补",不讲具体矩阵细节。**要看具体矩阵,打开 `review-matrix.md`**。

---

## 2. 4 层 review (R6)

| 层 | 谁 | 触发 | 主责范围 | 看不到的 |
|---|---|---|---|---|
| OpenCode 对比评审 | OpenCode agent | >3 文件 PR / 触达 middleware/auth/dependency/router / Sprint N 收尾 | 代码 diff 合规性 | 用户路径、PRD 一致性、feature completeness |
| code-reviewer | code-reviewer profile | 任何 PR | 安全 / 架构 / 可维护性 / 风格 | 测试覆盖度、产品意图、用户旅程 |
| test-lead | test-lead profile | 任何 PR (修复类/新功能必走;docs 类可免) | 测试覆盖度 / 场景设计 / E2E 复现 | 功能完整性的产品层判断 |
| **PM (产品完整性)** | product-manager | 任何 PR (尤其触达 runtime gate 时 R5 必答三问) | **E2E 用户路径** + **PRD ↔ 实现一致性** | (catch 其他层都 catch 不到的事) |

**关键洞察**: **E2E 用户路径** 和 **PRD ↔ 实现一致性** 这 2 个维度**只有 PM 能 cover**。其他三层 review 都"通过"但这两维度可能完全没 cover —— 这就是 Sprint 4 gap 的位置。

详细: `review-matrix.md` §2 + `../post-mortem/sprint4-process-gap.md` §4 Q5

---

## 3. PM 的"功能完整性"三问 (R5)

当 PR 触达 `middleware/` / `auth/` / `dependency` / `router/` 时,PM 必答 (in PR 评论):

1. **入口路径是什么?** 用户从哪里触发这个新行为? (login endpoint / OAuth callback / 定时任务入口 / 路由前缀)
2. **验证路径是什么?** 怎么证明入口到出口的链路是通的? (curl 命令 + 输出 / Playwright 脚本 + trace / 手动截图 / e2e_evidence URL)
3. **现有 flow 被破坏怎么办?** migration 怎么处理、数据怎么迁、文档/SDK/前端如何同步更新? (含回滚路径)

**判定**: 三问任意一问没答案 → **阻断 PR**,要求 developer 先补齐入口/验证/迁移方案再合入。

**完整 R5 规则**: `../.project-memory.md` → PM 角色职责 / Pre-merge checklist

---

## 4. 盲区速查 (每层 review 看不到什么)

> **本节是这份 doc 的核心**——Sprint 4 暴露的核心问题是"每一层 review 都假设其他层 catch 缺口"。本节明确每层 review 看不到的 gap,让 PM / jerry 知道哪里需要补防线。

| Layer | 看不到的 gap | 谁来补 |
|---|---|---|
| **code-reviewer** | PR 范围外的代码 / 部署后的实际行为 / 未提交的未来设计 / E2E 用户旅程 / 历史反例变体 | OpenCode 跨层 + PM R5 三问 |
| **test-lead** | 测试 fixture 绕过的问题 / PR 外的代码路径 / 业务逻辑正确性 / 用户真实场景 / 回归范围 | code-reviewer 审查 fixture + OpenCode + Integration Verification |
| **OpenCode 对比评审** | PM 视角的"产品完整性" / 运行时真实行为 / 业务流程正确性 / 未来可扩展性 | PM R5 三问 + Integration Verification + jerry user-verify |
| **PM (R5)** | 实现细节 / 单元测试覆盖 / 静态 lint / 类型 / 历史反例的具体 match | 各 review layer 各自的主责 |
| **CI** (任何) | 语义性 gap / 端到端真实路径 / 业务正确性 | **全部 review layer + R5 PM 三问** |

**关键 takeaway**: **CI 只能 catch 可机检的 gap**。任何"missing entry path" / "missing migration" / "wrong business logic" 这类**语义性 gap**,CI 永远看不到。Sprint 4 暴露的 JWT gap 全部落在 CI 看不到的语义层。

详细: `review-matrix.md` §3

---

## 5. 评审串联顺序

```
developer 提交 PR (含 #t_xxx + e2e_evidence 占位 + R5 三问草稿)
  ↓
OpenCode 对比评审 (auto/semi-auto) → review-matrix.md §2.2.1 verdict
  ↓
code-reviewer → review-matrix.md §2.2.2 verdict
  ↓
test-lead → review-matrix.md §2.2.3 verdict (含 E2E)
  ↓
PM (product-manager) → review-matrix.md §2.2.4 verdict (含 R5 三问)
  ↓
全部 APPROVE → 允许合入
任一 REQUEST_CHANGES → 打回 developer,从该层重新走
```

详细: `review-matrix.md` §4

---

## 6. 评审合入门槛 (合并门槛)

| Verdict 类型 | 数量要求 |
|---|---|
| 任意 REQUEST_CHANGES | **不允许合入** (哪怕其他层都 APPROVE) |
| OpenCode + code-reviewer + test-lead + PM 全 APPROVE | 允许合入 |

**判定**: 4 层 verdict 必须显式写在 PR 评论里,缺任一层 → 不算 review 通过。这是 code-reviewer 在 review 阶段检查的。

**例外 (紧急 hotfix)**: 标注 `[hotfix]` 的 PR 允许跳过 PM 三问 + test-lead,但**不能**跳过 OpenCode + code-reviewer。hotfix 合入后必须 24h 内补完 PM 三问 + test-lead 的 e2e 验证 + retro。

详细: `review-matrix.md` §4.3

---

## 7. PM 自检清单 (review 时)

```
[ ] §2 review-matrix §2.2.1 OpenCode verdict 存在且显式声明"未覆盖用户路径 / PRD 一致性"
[ ] §2 review-matrix §2.2.2 code-reviewer verdict 存在,覆盖安全/架构/可维护性
[ ] §2 review-matrix §2.2.3 test-lead verdict 存在,含 E2E 子项 (如涉及前端)
[ ] §3 R5 PM verdict 存在,三问逐条有答案 (不能是 N/A 或跳过)
[ ] §6 4 层 APPROVE 才算 review 通过
[ ] §4 R5 PM 三问对齐 sprint-decomposition §2 拆出的子任务边界
```

**判定**: 6 条全过 → 允许合入;任一不过 → 阻断并打回对应层。

---

## 8. 与其他文档的关系

- **R6 详细**: `review-matrix.md` (PM-owned)
- **R5 详细**: `../.project-memory.md` → PM 角色职责 / Pre-merge checklist
- **R3 联动**: `sprint-decomposition.md` §2 — 拆出独立子任务才能被各层独立 review
- **R2 联动**: `done-criteria.md` §3 — review 链终点必须验 e2e_evidence
- **R7 联动**: `kanban-rules.md` §3 (本目录) — 小改动阈值
- **来源 retro**: `../post-mortem/sprint4-process-gap.md` §2.4 / §3 / §4 Q5 / §5 R5+R6
- **8 步开发流程**: `dev-workflow.md`
