# Art 团队开发流程 — 8 步框架

> **Source**: `.project-memory.md` → "团队通用流程" 章节下沉淀 (Sprint 4 复盘 R3/R5/R6/R7 之后的版本)
> **Owner**: product-manager
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_7c0bf7af 任务产出）

---

## 0. 为什么从 7 步变 8 步

Sprint 4 JWT 事件（commit `b2e30a1`）暴露的核心问题不是"代码有 bug"，而是"流程被跳过"：
1 个 commit 涵盖 9 文件改动，没父任务、没 PRD、没子任务、没 review、没测试、没 PM 确认、没用户验证，直接合入 main。
33 天后 jerry 上手才发现系统不可用。

Sprint 4 复盘（`docs/post-mortem/sprint4-process-gap.md`）给出 7 条改进（R1-R7），其中 4 条直接影响 dev 流程：R3（拆子任务）、R5（PM 功能完整性 checklist）、R6（retro 强制化）、R7（小改动阈值）。**R4（user-verify 5 business day deadline）单独抽出**——见 `user-verification.md`。

加上这 4 条强制 sub-rule 后，原 7 步流程变为 **8 步框架**：原 step 4（PM 确认）拆成"PM 功能完整性 review"+"Sprint 收尾 retro 流程"两个独立关卡。

---

## 1. 8 步框架

### Step 1 — 立项 (proposal)

**触发**: 任何≥中等规模的改动（>1 文件 / 跨模块 / 新功能 / 协议层变化）。
**Owner**: software-architect 写技术方案，PM 主持，jerry 评审价值。
**输入**: 一句话需求 / jerry 提的 idea / 反例中暴露的 gap。
**输出**:
- `docs/planning/sprint<N>-prd.md` — 1 页 PRD：scope / non-scope / 验收标准 / 风险点
- 至少 3 个独立审阅记录（developer / code-reviewer / test-lead 各自签字）
- jerry 评审意见 → 通过则立项，不通过则打回或终止

**关键判定**: 评审项有不通过 → 打回 architect 补充 → 重新走审阅。循环直至通过或团队接受有保留意见（需明确记录）。

### Step 2 — Sprint 拆解 (R3 强制)

**Owner**: product-manager
**强制规则**: 见 `kanban-rules.md` §2（最少子任务数 + Integration Verification 子任务 + Frontend build artifact 子任务）
**输入**: Step 1 产出的 PRD
**输出**:
- Sprint N 父任务在 board 上建好
- ≥5 个子任务卡片（修复类 ≥3，文档类 ≥2）
- Integration Verification 子任务的 `parents` 字段 link 到 Sprint N 所有其他子任务
- 涉及前端时额外 1 个 "Frontend build artifact → backend integration" 子任务
- 每个子任务的 `body` 含可独立验收的 acceptance criteria

**关键判定**: 6 项 verify checklist（见 `kanban-rules.md` §4）全过 → 拆解合规；任一不过 → Sprint N 不准启动。

### Step 3 — 任务派发 + assignee 接收

**Owner**: product-manager（指派） + assignee（接收并自检范围）
**输入**: Step 2 拆出的子任务卡片
**输出**:
- `assignee` 字段填具体 profile（developer / mobile-developer / sre / security-engineer 等）
- assignee 收到后 1 个工作日内确认：能接 / 不能接（不能接则 PM 重新派）
- 子任务开始 ≤ 2 个工作日内（kickoff 之后）

### Step 4 — 开发 (developer / mobile-developer)

**Owner**: developer / mobile-developer
**规则**:
- **R7 强制**: 任何 PR 改动 >3 文件，**或** 涉及 `middleware/` / `auth/` / `dependency/` / `router/` 任一目录 → **必须**先在 board 建任务并提交。commit message 必须带 `(#t_*)` 引用。
  - 判定: 单 PR 文件改动数 + 受影响路径类型，二者满足任一即触发。
  - code-reviewer 在 PR review 时检查并拒绝无 task ID 的此类 PR。
- 写代码 + 单元测试 + 必要时更新 golden dataset
- 提交时附 `e2e_evidence` 占位（见 `kanban-rules.md` §3 done 判定）

**输出**: 1 个或多个 commit（带 `(#t_xxx)` 引用），本地的 dev branch ready for review。

### Step 5 — Code Review (code-reviewer)

**Owner**: code-reviewer
**范围**: 见 `review-checklist.md` §1（code-reviewer scope + 盲区）
**强制项**:
- R7 检查：>3 文件改动 或 触达 middleware/auth/dependency/router → 必须有 task ID 引用，否则打回
- B1-B4 级 blocker（安全/正确性）必须 0 个
- 给出 major / minor 分类 + 是否 blocking

**输出**: PR 评论含 verdict（APPROVE / REQUEST CHANGES / BLOCKING），附上主要 finding。

### Step 6 — 测试验证 (test-lead)

**Owner**: test-lead
**范围**: 见 `review-checklist.md` §2（test-lead scope + 盲区）
**强制项**:
- 单测 + 集成测试 + golden dataset 必须全过
- 新功能 / 改动的 acceptance criteria 必须有对应测试覆盖
- Sprint N 的 Integration Verification 子任务（Step 2 建的那个）必须**独立**走一遍 happy path，附 e2e_evidence

**失败处理**: test-lead 不通过 → 直接打回 developer 重测（**不**重经 code-reviewer），打回从 test-lead 重新走。

### Step 7 — PM 确认 (R5 强制)

**Owner**: product-manager
**强制项**（仅当改动触达以下任一目录时）: `middleware/` / `auth/` / `dependency` / `router/` / 任何 runtime gate
- **PM 必须在 PR 评论里逐条回答三问**（R5 feature completeness checklist）:
  1. **入口路径是什么?** 用户从哪里触发这个新行为?（login endpoint / OAuth callback / 定时任务入口 / 路由前缀）
  2. **验证路径是什么?** 怎么证明入口到出口的链路是通的?（curl 命令 / Playwright 脚本 / 手动截图 / `e2e_evidence` URL）
  3. **现有 flow 被破坏怎么办?** migration 怎么处理、数据怎么迁、文档/SDK/前端如何同步更新?（含回滚路径）
- 三问任意一问没答案 → **阻断 PR**,要求 developer 先补齐入口/验证/迁移方案再合入
- 见 `.project-memory.md` → "PM 角色职责 / Pre-merge checklist"

**输出**: PM 评论带三答（触达时）/ sprint N 全部子任务清单 review 通过（未触达时）→ 进入 Step 8。

### Step 8 — 用户验证 (R4 强制) + push

**Owner**: jerry（用户验证）+ developer（push）
**规则**: 见 `user-verification.md` §1-§3
- developer 编译部署安装本地 commit → 通知 jerry 验证
- jerry 在 ≤ 5 business days 内执行 `hermes kanban verify <task_id> --by jerry` 完成 user-verify
- 未通过 → 回到 Step 4 修复（不计 R4 deadline，因为是 dev 重做）
- 通过 → developer push 远程 → 任务进入 `done + user_verified` 状态
- **Push (step 7 of the legacy 7-step) 现在被显式 gate 在 user-verify 之后**——见 `user-verification.md` §2

**Sprint close 时额外**: PM 写 `docs/post-mortem/sprint<N>-retro.md`（无 gap）或 `sprint<N>-process-gap.md`（有 gap），同时更新 `.project-memory.md` 的 Sprint 状态——**必须在同一 merge PR 内提交**（R6 强制化）。见 `sprint-decomposition.md` §6（这是 R3 doc，但 Sprint close 流程在 R6 章节）。

---

## 2. 流程判定的边界

| 改动类型 | 走哪些 step | 跳哪些 step |
|---|---|---|
| **Sprint N 立项（≥5 子任务 / 跨模块）** | 全 8 步 | 无 |
| **Bug fix（独立 commit）** | Step 3, 4, 5, 6, 7, 8 | Step 1, 2 (走 `kanban-rules.md` §2.1 修复类规则: ≥3 子任务) |
| **文档/流程类** | Step 1, 2, 3, 8 | Step 5, 6, 7 (不走 review/test) |
| **Hotfix（紧急）** | Step 4, 5, 6, 8 (合并) | Step 1, 2, 3 (用 `ci-rules.md` §3 hotfix 白名单 + jerry 知情) |
| **CI/工具链改动** | Step 4, 5, 8 | Step 2, 6, 7 (走 `kanban-rules.md` §2.1 文档/流程类规则) |

**判定原则**: 任何走 Step 4-5-6 的改动,都必须能映射回 Step 2 拆出的子任务卡片;无卡片 = R7 违规 = 阻断。

---

## 3. 与其他文档的关系

- **Step 2 拆解粒度**: `kanban-rules.md` (R3 + R7 详细规则)
- **Step 5-7 review 范围 + 盲区**: `review-checklist.md`
- **Step 8 用户验证 + deadline**: `user-verification.md`
- **CI 自动检查**: `ci-rules.md` (R1 实施,PM 拥有规则文档)
- **R2 e2e_evidence 字段**: `../operations/kanban-e2e-evidence.md` (sre 实施,PM 引用)
- **R4 user-verify 5-day 实施细节**: `../operations/user-verify-deadline.md` (sre 实施,PM 引用)
- **R6 retro 强制化流程**: `.project-memory.md` → "Sprint close 流程" (历史沉淀,本 doc 不重复)

---

## 4. 快速失败模式速查（如果发生以下情况，看哪里）

| 现象 | 根因 / 修复 |
|---|---|
| "Sprint N 收尾了但有 task 没 user_verified_at" | 触发 R4 auto-block 倒计时,看 `user-verification.md` §3 |
| "developer 自评 done 但 PM 不知道改了什么" | Step 7 漏,看 R5 三问,见 `.project-memory.md` → PM 角色职责 |
| "PR 没有 `(#t_*)` 引用,被 CI 拒了" | R7 触发,看 `ci-rules.md` §2 |
| "子任务数 < 5" | R3 强制,看 `kanban-rules.md` §2.1 |
| "Sprint close 时 retro 还没写" | R6 触发,看 `.project-memory.md` → Sprint close 流程 |
| "CI 跑过但 e2e_evidence 是空" | R2 触发,看 `../operations/kanban-e2e-evidence.md` |

---

## 5. 与 Sprint 4 之前的版本对比

| 项 | Sprint 1-4 旧版 | Sprint 5+ 新版 |
|---|---|---|
| 总步数 | 7 | 8 (PM 确认 + user-verify 拆开) |
| 子任务粒度 | 自由拆,没下限 | 通用 ≥5, bug ≥3, docs ≥2 (R3) |
| Integration Verification 子任务 | 无 (Sprint 3 没建) | 强制,link 到所有 Sprint N 子任务 (R3) |
| Frontend build artifact 子任务 | 无 (Sprint 4 反例) | 涉及前端时强制 (R3 §2.2.2) |
| 小改动阈值 | 无 | >3 文件 或 middleware/auth 触达 → 强制 board 任务 (R7) |
| PM 三问 | 无 | 触达 runtime gate 必答 (R5) |
| User-verify deadline | 无 (33 天后才验) | 5 business days 自动 block (R4) |
| Retro 强制化 | 无 | Sprint close 时必写,同 PR commit (R6) |
| e2e_evidence 字段 | 无 | done 必填 (R2) |
| CI 强制 task ID 检查 | 无 | R1: PR commit message 必带 `(#t_*)` 引用 |

---

## 6. 例外与不适用范围

- **Pre-Sprint 1 历史 commit**: 流程不追溯 (`8bd2911` 之前的 commit 视为既有)
- **External 贡献 (fork PR)**: Step 1 由 PM 主持复审,Sprint 拆解归入现有 Sprint;其他 step 照走
- **本 doc 自身**: 本文件是流程文档,不参与 R7 (改动的是 docs/process/ 而非代码)
- **Sprint 5 retro 占位**: `docs/post-mortem/sprint5-retro.md` 是占位文件,本 doc 不重写它
