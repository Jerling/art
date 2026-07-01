# "done" 判定标准 v2.0（R7）

> **Source**: Sprint 4 复盘 `docs/post-mortem/sprint4-process-gap.md` §5 R2 + §5 R7 + § Q2
> **Owner**: product-manager（判定者）+ developer（执行者）+ sre（看板字段强制）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_add2601d 任务产出）

---

## 1. 为什么 v2.0

旧定义（v1.0）：**commit 落 main + CI 绿 + summary 写完 = done**

问题：Sprint 4 JWT auth gate 在 v1.0 意义下"done"了 — commit `b2e30a1` 合入 main，CI 绿，summary 写完。但部署后：

- 所有业务 API 返回 401（没有 login 入口）
- `GET /` 返回 404（没有 StaticFiles 挂载）
- 用户根本用不起来

**根因**：v1.0 是代码层定义，看不见语义层 gap。"CI 绿"不能回答"用户能不能用"。

**R2 + R7 的修法**：done 必须有四件套 — 代码、CI、PRD 验收、**端到端证据**。本文件把这四件套固化为可检查的规则。

---

## 2. done v2.0 四件套

任何任务卡片从 `in_progress` → `done`，**必须**全部满足：

| # | 检查项 | 谁负责 | 如何验证 |
|---|---|---|---|
| 1 | **代码已合入**（commit 在目标分支） | developer | `git log` 显示 commit hash 在分支上 |
| 2 | **CI 全绿**（lint + type + test） | sre | CI status check ✅ |
| 3 | **PRD / 任务 acceptance criteria 逐条满足** | developer 自检 + PM 复审 | 任务 `body` 中的每条 ✅ 有证据 |
| 4 | **`e2e_evidence` 字段非空**（见 §3） | developer 提供 | board metadata 含非空 `e2e_evidence` |

**判定**：4 项缺任一 → 不允许 done，必须补齐后再标记。

---

## 3. e2e_evidence 字段规则（R2）

### 3.1 为什么必有

Sprint 4 的反例直接证明了这件事：`require_auth` 加上去但没有任何路径可以 mint token，所以"代码完整"在用户视角 = "系统不可用"。`e2e_evidence` 强制 worker 在 done 之前附上"用户实际跑得通"的证据。

### 3.2 字段位置

任务卡片的 `metadata.e2e_evidence` 字段。board 政策 `require_e2e_evidence: true` 时，kernel 拒绝任何不带此字段的 `kanban_complete` 调用（exit 3）。

完整实施文档：`docs/operations/kanban-e2e-evidence.md`（sre 维护）。

### 3.3 接受的三种 evidence 形式

按优先级排序：

1. **自动 E2E 证据**（首选）— Playwright trace、curl 日志、CI artifact
   ```python
   metadata={"e2e_evidence": "https://ci.example.com/artifacts/login-trace-2026-07-02.zip"}
   ```

2. **手工验证 note**（次选）— 不可自动跑通的改动（CI 配置、删除 dead code、纯文档）
   ```python
   metadata={"e2e_evidence": {"note": "manually verified: workflow file present + ruff dry-run passes 2026-07-02"}}
   ```

3. **显式 bypass + 理由**（最后手段）— 改动纯静态、连手工验证都 overkill 时
   ```python
   metadata={"e2e_evidence_override": "docs-only change, no runtime path affected"}
   ```
   ⚠️ bypass 会被审计为 `completion_override_no_e2e_evidence` 事件，PM 在下次 retro 应扫描。

### 3.4 SPA / Web UI 类任务的强制 evidence 类型

凡是涉及前端路由（`vue-router`、`react-router`、SvelteKit、Nuxt 等 SPA 框架）的任务，**只接受**：

- Playwright trace（点击导航后 URL 变化 + DOM 渲染正确）
- `w3m -dump <URL>` 输出（验证 SPA fallback 不返回 404）
- 浏览器截图（首屏 + 至少 1 个深层路径，如 `/admin/dashboard` 直接访问）

**不接受**：

- ❌ 单独的 `curl http://localhost:8000/` 200（无法验证 SPA 深层路径）
- ❌ 单独的 UI 首页截图（看不到路由跳转）

**反例**：Sprint 4 fix 任务 `t_0e04abde` 的验证只跑了 `curl` + 首页截图，`w3m` 没跑深层路径 → SPA fallback 没测出来 → 7/1 才发现 `/admin/dashboard` 仍 404。这个反例直接催生了 §3.4 的强制规则。

---

## 4. 子任务 ↔ Sprint 收尾的依赖规则（R3 联动）

### 4.1 强制依赖

```
Sprint N 子任务全部 done
  ↓
[Sprint N] Integration Verification 子任务才能开始
  ↓
Integration Verification 子任务 done（含 e2e_evidence）
  ↓
Sprint N 才算收尾（PM 才能宣告 Sprint N 完成）
  ↓
Sprint N+1 kickoff 才能启动
```

**判定**：Integration Verification 子任务未 done → Sprint N 不算收尾 → Sprint N+1 kickoff 任务不能从 `ready` 升 `running`。

### 4.2 Integration Verification 子任务的 e2e_evidence 特殊要求

`[Sprint N] Integration Verification` 子任务的 `e2e_evidence` 必须包含：

- 完整的 happy path 视频 / trace（如 Playwright `npx playwright test --trace on`）
- 至少 3 张关键节点截图（登录前 / 登录后 / 业务操作后）
- 一句话 human-readable summary："user can [操作 X] → [操作 Y] → [操作 Z] in [环境] on [日期]"

**反例**：Sprint 3 close 时 evidence 只有"CI 全绿 + 单元测试 100%"，没有 happy path 视频。Sprint 4 一加 JWT，整个 happy path 就断了。

---

## 5. 自检清单（PM 在 Sprint close 时逐条过）

```
[ ] §2 四件套：所有 Sprint N 子任务都满足 4 条
[ ] §3.4 SPA 类任务：每个涉及前端路由的子任务的 e2e_evidence 含 Playwright / w3m / 截图
[ ] §4 Integration Verification 子任务存在且 done
[ ] §4.2 Integration Verification 的 e2e_evidence 含 happy path trace + 3 张截图 + 一句话 summary
[ ] git blame 验证 retro 文件在 Sprint N merge PR 内（见 `docs/post-mortem/sprint5-retro.md` 占位）
[ ] .project-memory.md 中 Sprint N 状态已标 ✅
```

**判定**：6 条全过 → Sprint N 收尾合规；任一不过 → retro 必须记录 process gap。

---

## 6. 反例 / 教训

### 反例 1 — Sprint 4 JWT（核心反例）

- **v1.0 done 状态**：commit 合入 + CI 绿 + summary ✅
- **实际**：API 401 / UI 404
- **为何过**：v1.0 不要求 e2e_evidence
- **修复**：v2.0 加 §2 第 4 项；§3.4 加 SPA 类强制类型
- **未来如何防**：任何 done 缺 §3 证据 → kernel 拒绝；PM retro 时扫描 bypass 使用

### 反例 2 — Sprint 4 fix `t_0e04abde`

- **现象**：修了 `/api/v1/auth/login` + `mount web/dist SPA`，验证只有 `curl /api/v1/auth/login` 200 + 首页截图
- **遗漏**：SPA fallback 没测 — `w3m http://localhost:8000/admin/dashboard` 返回 404
- **为何过**：curl + 首页截图满足当时的最低 evidence 标准
- **修复**：§3.4 把 SPA 类任务的 evidence 收紧到 Playwright / w3m dump / 深层路径截图
- **未来如何防**：Sprint 4 fix `t_a6893d76` 已加 SPA fallback；本规则防止下次同类问题再过

### 反例 3 — Sprint 3 close 无 Integration Verification

- **现象**：Sprint 3 宣布"MVP final deliverables"，但没有任何"用户在部署环境跑通 happy path"的子任务
- **修复**：§2.2.1（在 `sprint-decomposition.md`）把 Integration Verification 子任务设为强制
- **未来如何防**：§4 的依赖链让"无 IV 子任务 → 不能 done"成为机制

---

## 7. 与其他文档的关系

- **R2 来源**：`docs/post-mortem/sprint4-process-gap.md` §5 R2；实施在 `docs/operations/kanban-e2e-evidence.md`
- **R3 联动**：`sprint-decomposition.md` §2.2.1（Integration Verification 子任务强制存在）— 本文件 §4 规定 IV 子任务的 done 判定
- **R7 来源**：`docs/post-mortem/sprint4-process-gap.md` §5 R7；当前在 `.project-memory.md` → 开发阶段流程的强制 sub-rule
- **R5 联动**：`user-verification.md` 规定 IV 子任务 done 后触发 4 天用户验证 deadline
- **R6 联动**：`review-matrix.md` 规定 e2e_evidence 在哪几层 review 里被 check
- **框架索引**：`docs/process/dev-workflow.md`（t_7c0bf7af 任务产物，pending）