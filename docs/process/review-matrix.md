# 三层评审范围矩阵（R6）

> **Source**: Sprint 4 复盘 `docs/post-mortem/sprint4-process-gap.md` §2.4 + §3 + §5 R5 + § Q5
> **Owner**: product-manager（矩阵设计 + PM 层 review）+ code-reviewer / test-lead / OpenCode（执行层 review）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_add2601d 任务产出）

---

## 1. 为什么需要这个矩阵

Sprint 4 JWT 改动（commit `b2e30a1`）同时经历了 4 层 review：

| 层 | 谁 | review 什么 | 抓到 gap 了吗 |
|---|---|---|---|
| OpenCode 对比评审 | OpenCode agent | 代码 delta（`b2e30a1` 改的 9 文件） | ❌ 没抓到"没 login 入口" |
| code-reviewer | code-reviewer profile | Vue 组件 RBAC 权限门控（**另一层 concerns**） | ❌ 不相关，未触及后端鉴权 |
| test-lead | test-lead profile | 单元 + golden dataset + 集成套件 | ❌ fixture override 后测试全绿，但"用户能否认证"无测试 |
| PM | product-manager | Roadmap / PRD acceptance | ❌ **没有 PRD 可审** — Sprint 4 没有父任务 |

**结果**：4 层 review 全过，但生产环境 401/404。**核心 gap 在 PM 层 — 没有 PRD → PM 无从 review → 其他层各自"通过"但 cover 不到"功能完整性"这个维度**。

**R5 + R6 的修法**：
1. **R5**：PM 持有"功能完整性"三问 checklist（在 `user-verification.md` 详述）
2. **R6（本文件）**：明确每层 review 的**范围边界** + 明确"哪一层**漏**了什么" — 防止把"代码 review 通过"误解为"功能 review 通过"

---

## 2. 评审矩阵（4 层 × 6 个 review 维度）

### 2.1 主表

| 维度 ↓ \ 评审层 → | OpenCode 对比评审 | code-reviewer | test-lead | **PM（产品完整性）** |
|---|---|---|---|---|
| **代码 diff 合规性** | ✅ 主责 | 辅助 | — | — |
| **安全 / 架构合理性** | 辅助 | ✅ 主责 | — | — |
| **可维护性 / 风格** | 辅助 | ✅ 主责 | — | — |
| **测试覆盖度 / 场景设计** | 辅助 | — | ✅ 主责 | — |
| **E2E / 用户路径** | ❌ **不验** | ❌ **不验** | 辅助 | ✅ 主责 |
| **PRD ↔ 实现一致性** | ❌ **不验** | ❌ **不验** | ❌ **不验** | ✅ 主责 |

**关键洞察**：**E2E 用户路径** 和 **PRD ↔ 实现一致性** 两个维度**只有 PM 能 cover**。其他三层 review 都"通过"但这两维度可能完全没 cover — 这就是 Sprint 4 gap 的位置。

### 2.2 每层 review 的产出物（PR 评论模板）

#### 2.2.1 OpenCode 对比评审 — 产出：代码层 verdict

```
OpenCode Review — Sprint N.X
- 文件: <list>
- 主要改动: <1-2 句>
- 代码 diff 合规性: ✅ / ❌ <理由>
- 安全 implication: <备注>
- 已知限制: <如有>
Verdict: APPROVE / REQUEST_CHANGES
```

**明确不覆盖**：用户路径、PRD 一致性、feature completeness。代码 review 通过 ≠ 功能 review 通过。

#### 2.2.2 code-reviewer — 产出：质量层 verdict

```
Code Review — Sprint N.X
- 安全: ✅ / ❌ <如 JWT secret 硬编码、SQL 拼接等>
- 架构: ✅ / ❌ <如分层、依赖方向、ADR 一致性>
- 可维护性: ✅ / ❌ <如命名、注释、复杂度>
- Sprint 4 必查清单（middleware/auth/dependency/router）:
  [ ] 不引入新的硬编码 secret
  [ ] 不引入新的 SQL 字符串拼接
  [ ] 新增依赖项有 ADR 或 issue 引用
  [ ] 路由权限门控与 RBAC matrix 一致
Verdict: APPROVE / REQUEST_CHANGES
```

**明确不覆盖**：测试用例是否覆盖 happy path、用户能否跑通流程、PRD 是否被实现完整。

#### 2.2.3 test-lead — 产出：测试层 verdict

```
Test Review — Sprint N.X
- 单元测试: N 个 / 通过率 X%
- 集成测试: N 个 / 通过率 X%
- Golden dataset: N 个 case / 准确率 X%
- 新增场景: <list>
- 回归风险: <备注>
- E2E（若 Sprint 涉及前端 / 用户路径）:
  - [ ] Playwright trace 存在
  - [ ] 至少覆盖 happy path 1 个 + 异常路径 2 个
  - [ ] w3m / curl 验证 SPA 深层路径不 404
Verdict: APPROVE / REQUEST_CHANGES
```

**明确不覆盖**：功能完整性的产品层判断（"用户故事是否真的实现"），这层只验"测试是否充分"，不验"产品意图是否对齐"。

#### 2.2.4 PM（R5 三问）— 产出：产品层 verdict

```
PM Review — Sprint N.X
1. 入口路径是什么？
   → <答：login endpoint / OAuth callback / 定时任务入口 / etc.>
2. 验证路径是什么？
   → <答：curl 命令 + 输出 / Playwright 脚本 + trace / 手动截图 / e2e_evidence URL>
3. 现有 flow 被破坏怎么办？
   → <答：migration 步骤 / 数据迁移 / 前端 SDK 同步 / 回滚路径>
PRD ↔ 实现一致性: ✅ / ❌
Verdict: APPROVE / REQUEST_CHANGES
```

**判定**：三问任意一问没答案 → 阻断 PR，要求 developer 先补齐入口/验证/迁移方案再合入。

完整 R5 规则见 `user-verification.md` §3。

---

## 3. 盲区识别 — 每层"漏了什么"

把 Sprint 4 当 case study，看每层漏的具体内容：

### 3.1 OpenCode 对比评审 漏了什么

| 漏的 | 为什么漏 |
|---|---|
| "require_auth 没有可满足的入口" | OpenCode 只看 `b2e30a1` 的 9 文件 delta；没问"用户怎么拿到 token" |
| "web/dist 已 build 但 FastAPI 不服务" | OpenCode 只看代码改动；不看 `main.py` 是否挂载 — `main.py` 本身没改 |
| "无任何 /auth/login handler" | OpenCode 只看 delta；不看整个 codebase 是否存在对应 handler |

**未来如何防**：OpenCode review 必须产出 §2.2.1 模板，并在 verdict 里显式声明"未覆盖用户路径 / PRD 一致性"。这层 verdict 通过 ≠ 功能 OK，**必须有 PM verdict 才能合入**。

### 3.2 code-reviewer 漏了什么

| 漏的 | 为什么漏 |
|---|---|
| JWT secret 来源、有效期等（**实际抓到**，B1） | ✅ 这一层抓到了环境变量注入 + 24h 有效期 |
| "功能是否完整可用" | code-review 视角是"代码质量"，不是"产品意图" |
| RBAC 在后端的实现 | code-review 被 scope 到 Vue 组件 RBAC 门控，**不相关 concern** |

**未来如何防**：code-reviewer 评审 scope 必须按 §2.2.2 模板显式声明；R5 三问是 PM 责任，code-reviewer 不背"功能完整性"。

### 3.3 test-lead 漏了什么

| 漏的 | 为什么漏 |
|---|---|
| "用户能拿到 token" 流程 | `4d460df` fixture override 让测试绕过 auth 后全绿，没有端到端 token flow 测试 |
| "前端 SPA 深层路径不 404" | 当时的 E2E 只跑 `curl /`，没跑 `w3m /admin/dashboard` |
| "Web UI token 注入到 request header" | 没有 Playwright 测试 |

**未来如何防**：Sprint 涉及前端 / 用户路径时，test-lead 必须按 §2.2.3 模板执行；E2E 强制 Playwright / w3m dump（见 `done-criteria.md` §3.4）。

### 3.4 PM 漏了什么 — **核心 gap**

| 漏的 | 为什么漏 |
|---|---|
| "JWT auth 加了之后登录入口在哪" | 没有 PRD → PM 无可审 |
| "Web UI 怎么调用受保护接口" | 同上 |
| "登录失败、token 过期等异常流如何处理" | 同上 |

**未来如何防**：见 `sprint-decomposition.md` §2（每个 Sprint 必拆 ≥5 子任务 + 必含 Integration Verification 子任务）— PRD 强制存在是 PM review 能发生的前提。

---

## 4. 评审串联规则

### 4.1 顺序

```
developer 提交 PR（含 §2.2.4 PM 三问模板草稿）
  ↓
OpenCode 对比评审（自动 / 半自动）→ §2.2.1 verdict
  ↓
code-reviewer → §2.2.2 verdict
  ↓
test-lead → §2.2.3 verdict
  ↓
PM（product-manager）→ §2.2.4 verdict（含 R5 三问）
  ↓
全部 APPROVE → 允许合入
任一 REQUEST_CHANGES → 打回 developer，从该层重新走
```

### 4.2 合并门槛（"通过"的定义）

| Verdict 类型 | 数量要求 |
|---|---|
| 任意 REQUEST_CHANGES | **不允许合入**（哪怕其他层都 APPROVE） |
| OpenCode / code-reviewer / test-lead / PM 全 APPROVE | 允许合入 |

**判定**：4 层 verdict 必须显式写在 PR 评论里，缺任一层 → 不算 review 通过。这是 code-reviewer 在 review 阶段检查的。

### 4.3 例外（紧急 hotfix）

- 标注 `[hotfix]` 的 PR 允许跳过 PM 三问 + test-lead，但**不能**跳过 OpenCode + code-reviewer
- hotfix 合入后必须 24h 内补完 PM 三问 + test-lead 的 e2e 验证 + retro
- 详细 hotfix 流程见 `docs/planning/release-process.md` §X hotfix 章节

---

## 5. 自检清单（PM 在 review 时逐条过）

```
[ ] §2.2.1 OpenCode verdict 存在且显式声明"未覆盖用户路径 / PRD 一致性"
[ ] §2.2.2 code-reviewer verdict 存在，覆盖安全/架构/可维护性
[ ] §2.2.3 test-lead verdict 存在，含 E2E 子项（如涉及前端）
[ ] §2.2.4 PM verdict 存在，三问逐条有答案（不能是 N/A 或跳过）
[ ] §4.2 全 4 层 APPROVE 才算 review 通过
[ ] §3.4 PM 三问对齐 §2 sprint-decomposition 拆出的子任务边界
```

**判定**：6 条全过 → 允许合入；任一不过 → 阻断并打回对应层。

---

## 6. 反例 / 教训

### 反例 1 — Sprint 4 JWT（核心反例）

- **现象**：4 层 review 全 APPROVE，生产 401/404
- **gap 在哪**：PM 层 — 没有 PRD → 无可审
- **修复**：
  - 拆子任务（`sprint-decomposition.md`）→ 强制 PRD 存在
  - PM 三问（`user-verification.md` + 本文件 §2.2.4）→ 功能完整性显式 check
  - E2E 强制（`done-criteria.md` §3.4）→ test-lead 强制覆盖前端 / 用户路径
- **未来如何防**：§4.2 合并门槛；§5 PM 自检清单

### 反例 2 — Sprint 4 fix `t_0e04abde`（fix 后 fix）

- **现象**：修了 login + StaticFiles，curl + 首页截图过 review
- **gap 在哪**：test-lead 没强制 SPA 深层路径验证
- **修复**：`done-criteria.md` §3.4 + 本文件 §2.2.3 E2E 子项
- **未来如何防**：§2.2.3 模板 E2E 子项包含"w3m / curl SPA 深层路径不 404"

---

## 7. 与其他文档的关系

- **R5 来源**：`docs/post-mortem/sprint4-process-gap.md` §5 R5；本文件 §2.2.4 是其模板化
- **R6 来源**：`docs/post-mortem/sprint4-process-gap.md` §2.4 + § Q5；本文件是矩阵化
- **与 R2 联动**：`done-criteria.md` §3 — review 链终点必须验 e2e_evidence
- **与 R3 联动**：`sprint-decomposition.md` §2 — 拆出独立子任务才能被本矩阵各层独立 review
- **与 R7 联动**：`.project-memory.md` → R7 sub-rule（文件 > 3 或涉及 middleware/auth/dependency/router → code-reviewer 检查 task ID）
- **框架索引**：`docs/process/dev-workflow.md`（t_7c0bf7af 任务产物，pending）