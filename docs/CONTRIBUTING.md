# Art 项目贡献指南

> 本文档定义 Art 项目的 Git 工作流、分支策略、代码合并流程和发布节奏。
> 版本：v1.0.0 | 状态：用于 Phase 1 MVP（4 周）

---

## 一、分支策略

### 1.1 总体策略：Trunk-Based Development

Art Phase 1 采用 **Trunk-Based Development**（主分支优先），原因：

- MVP 周期短（4 周），团队小，避免长生命期分支带来的合并冲突
- 所有代码最终汇入 `main`，保持 `main` 始终可部署
- 紧急修复通过 `hotfix/*` 短分支处理

### 1.2 分支布局

```
main  ────●────────────●────────────●────────────●──  (always deployable)
         │            │            │            │
      sprint0/     sprint1/     sprint2/     sprint3/
      fix-blockers crud-skeleton wechat-ai   mvp-launch
```

> **注意**：Phase 1 MVP 使用 Sprint-Based 分支（而非纯 trunk）。每个 Sprint 结束时整个分支 PR 合并到 main。
> Sprint 完成后 feature 分支被删除，main 保持线性历史（通过 Squash & Merge）。

| 分支 | 生命周期 | 保护策略 |
|------|----------|----------|
| `main` | 永久 | 必须 PR + 1 Approve + CI 绿灯 |
| `sprint0/fix-blockers` | Sprint 0（~1周） | PR + CI 绿灯 |
| `sprint1/crud-skeleton` | Sprint 1（~1周） | PR + CI 绿灯 |
| `sprint2/wechat-ai` | Sprint 2（~1周） | PR + CI 绿灯 |
| `sprint3/mvp-launch` | Sprint 3（~1周） | PR + CI 绿灯 |
| `hotfix/<description>` | < 2 天 | PR + 1 Approve + CI 绿灯 |

### 1.3 命名规范

```bash
# Sprint 分支（Phase 1 MVP — 每个 Sprint 一个分支）
sprint0/fix-blockers      # Sprint 0：修复 4 个 Must-Fix blockers
sprint1/crud-skeleton      # Sprint 1：FastAPI 骨架 + 角色/任务 CRUD
sprint2/wechat-ai          # Sprint 2：微信 Webhook + AI 意图解析
sprint3/mvp-launch         # Sprint 3：通知 + Web + SRE + MVP 上线

# Hotfix 分支（任意 Sprint 中的紧急修复）
hotfix/jwt-token-expiry-24h
hotfix/wechat-crypto-verify
```

### 1.4 主分支保护规则

`main` 分支保护规则（GitHub Settings → Branch Protection Rule）：

- ✅ Require pull request reviews before merging（至少 1 Approve）
- ✅ Require status checks to pass before merging（CI 必须绿灯）
- ✅ Require branches to be up to date before merge（禁止 stacked PRs 堆积）
- ✅ Do not allow bypassing the above rules（maintainer 也不能跳过）
- ❌ Do NOT set "Require signed commits"（MVP 阶段暂不启用 GPG signing）

---

## 二、代码合并流程（PR Lifecycle）

### 2.1 流程总览

```
1. Create feature branch from main
2. Implement + commit (atomic, conventional commits)
3. Push + open Pull Request
4. CI runs (lint + test)
5. Code review (≥1 Approve required for main)
6. Squash & Merge into main
7. Delete feature branch
```

### 2.2 PR 前置条件（Gate）

PR 合并到 `main` 必须满足：

| 检查项 | 工具 | 阈值 |
|--------|------|------|
| 语法/风格检查 | `ruff check` | 0 errors |
| 类型检查 | `mypy src/` | 0 errors |
| 单元测试 | `pytest tests/unit_tests/` | 全部通过 |
| 覆盖率 | `pytest --cov=src` | 覆盖率 > 60% |

### 2.3 Phase 1 前置条件：Must-Fix Blockers

> 根据代码评审报告（t_4c7a4dc9），Phase 1 代码合并前必须完成以下 4 个 blocker 修复。

所有 Phase 1 功能分支必须等 `sprint0/fix-blockers` PR 合并后才能开始。

| # | Blocker | 分支名 | 状态 |
|---|---------|--------|------|
| 1 | JWT secret 环境变量注入 + token 有效期改为 24h | `sprint0/fix-blockers` | Sprint 0 |
| 2 | Redis URL 格式修正（`***@` → 标准格式） | `sprint0/fix-blockers` | Sprint 0 |
| 3 | WeChatCrypto.verify_signature 真实实现 | `sprint0/fix-blockers` | Sprint 0 |
| 4 | intent_data JSON Pydantic schema 验证 | `sprint0/fix-blockers` | Sprint 0 |

**依赖关系**：`t_4c7a4dc9`（Sprint 0，4 个 blocker 修复）先于所有后续 Sprint 分支合并。

### 2.4 PR 描述模板

```markdown
## 描述
<!-- 一句话说明本次改动 -->

## 改动类型
- [ ] feat: 新功能
- [ ] fix: 缺陷修复
- [ ] chore: 构建/工具变更
- [ ] docs: 文档
- [ ] refactor: 重构（无功能变化）
- [ ] test: 测试

## 关联任务
<!-- 关联 kanban 任务，如 t_xxxxxxxx -->

## 检查清单
- [ ] `ruff check` 0 errors
- [ ] `mypy src/` 0 errors
- [ ] `pytest tests/unit_tests/` 全部通过
- [ ] 新增测试覆盖了新代码
```

### 2.5 合并方式

- **Feature 分支 → main**：`Squash and merge`（保持 main 历史线性）
- **Hotfix 分支 → main**：`Create a merge commit`（保留热修复完整上下文）

### 2.6 Review 要求

| 目标分支 | 必须 Approve 数 | Reviewer |
|----------|----------------|----------|
| → `main` | ≥ 1 | `code-reviewer` 或 `security-engineer`（涉及安全时） |

---

## 三、Commit 规范

### 3.1 格式：Conventional Commits

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

### 3.2 Type 分类

| Type | 使用场景 | 示例 |
|------|----------|------|
| `feat` | 新功能 | `feat(auth): add JWT token refresh endpoint` |
| `fix` | 缺陷修复 | `fix(wechat): correct signature verification logic` |
| `chore` | 构建/依赖/工具 | `chore(deps): upgrade FastAPI to 0.115.0` |
| `docs` | 文档 | `docs: update API endpoint documentation` |
| `refactor` | 重构（无行为变化） | `refactor(task_service): extract status transition logic` |
| `test` | 测试 | `test: add unit tests for intent parser` |
| `perf` | 性能优化 | `perf(db): add index on tasks.status` |

### 3.3 Scope（按模块）

| Scope | 含义 |
|-------|------|
| `auth` | 认证模块 |
| `roles` | 角色管理 |
| `tasks` | 任务管理 |
| `ai` | AI/LLM 集成 |
| `wechat` | 微信集成 |
| `plans` | 每日规划 |
| `db` | 数据库/存储层 |
| `api` | API handler 层 |
| `infra` | 基础设施（Docker 等） |

### 3.4 Breaking Change 标注

如果提交包含破坏性变更，在 footer 中注明：

```
feat(auth)!: change JWT token expiry from 720h to 24h

BREAKING CHANGE: JWT token max age is now 24 hours.
Update client refresh logic accordingly.
```

### 3.5 提交原子性原则

每个 commit 应该：
- ✅ 独立完整（可以单独 revert）
- ✅ 只做一件事（一个 feature 或一个 fix）
- ❌ 不要在同一个 commit 中做功能 + 重构 + 修复混在一起

```bash
# Good: 3 个原子 commit
git commit -m "feat(auth): add JWT secret env injection"
git commit -m "fix(auth): reduce token expiry to 24h"
git commit -m "chore: update .env.example with JWT_SECRET"

# Bad: 1 个巨大的 commit
git commit -m "fix auth issues and update config"
```

---

## 四、CI/CD 流水线

### 4.1 CI 触发条件

| 事件 | 是否运行 |
|------|----------|
| Push to any branch | ✅（lint + type check + unit tests） |
| PR opened / updated | ✅（full gate） |
| Merge to main | ✅（deploy trigger） |

### 4.2 CI 阶段（GitHub Actions）

```yaml
# .github/workflows/ci.yml 概览
jobs:
  lint:
    runs: ruff check src/ tests/
  typecheck:
    runs: mypy src/
  test:
    runs: pytest tests/unit_tests/ --cov=src --cov-report=xml
  coverage:
    # 覆盖率必须 > 60%
  premerge-check:
    # 综合检查（lint + type + test 必须全部通过）
```

### 4.3 覆盖率要求

| 分支类型 | 最低覆盖率 |
|----------|-----------|
| `main` | ≥ 60% |
| Feature PR | ≥ 50%（鼓励超过） |

---

## 五、发布节奏

### 5.1 Phase 1 MVP 版本计划

| 里程碑 | 版本号 | 目标日期 | 说明 |
|--------|--------|----------|------|
| 项目启动 | `v0.1.0-alpha` | Week 0 | 起点 tag，分支策略确认，CI 搭建 |
| Sprint 0 完成 | `v0.1-sprint0` | Week 0 末 | 4 个 Must-Fix 全部修复并合并 |
| Sprint 1 完成 | `v0.1-sprint1` | Week 1 末 | FastAPI 骨架 + 角色/任务 CRUD |
| Sprint 2 完成 | `v0.1-sprint2` | Week 2 末 | 微信 Webhook + AI 意图解析 |
| Sprint 3 / Phase 1 完成 | `v0.1-sprint3` | Week 3 末 | 通知 + Web + SRE + MVP 上线 |
| Phase 1 正式发布 | `v0.1.0` | Week 3 末 | MVP 可对外发布 |

> `gh` CLI 未安装，无法自动创建 GitHub Milestone。Milestone 需在 GitHub Web UI 手动创建：`Issues → Milestones → New milestone`，命名为 `Phase 1 MVP`，截止日期设为 `2026-06-30`。

### 5.2 版本号规范（Semantic Versioning）

Art MVP 阶段版本格式：

```
v0.1.<patch>
```

| 字段 | 含义 | 示例 |
|------|------|------|
| `major` | 不兼容的 API 变更 | `v1.0`（Phase 2+ 使用） |
| `minor` | Phase 区分 | Phase 1 = 0, Phase 2 = 1, ... |
| `patch` | Sprint checkpoint | `v0.1.0` = Sprint 0 完成 |

> **Alpha 后缀说明**：Phase 1 MVP 开发期间使用 `-alpha` 后缀（如 `v0.1.0-alpha`），表示功能开发中。
> Sprint checkpoint tags 使用 `v0.1-sprintN` 格式（如 `v0.1-sprint0`），表示里程碑快照。

### 5.3 Tag 策略

```bash
# Phase 1 起点 tag
git tag -a v0.1.0-alpha -m "Art Phase 1 MVP start"
git push origin v0.1.0-alpha

# Sprint checkpoint tags（每个 Sprint 结束时打）
git tag -a v0.1-sprint0 -m "Sprint 0 done: 4 Must-Fix blockers resolved"
git tag -a v0.1-sprint1 -m "Sprint 1 done: CRUD skeleton + SQLite init"
git tag -a v0.1-sprint2 -m "Sprint 2 done: WeChat + AI intent parsing"
git tag -a v0.1-sprint3 -m "Sprint 3 done: MVP launch ready"

# Phase 1 正式完成（覆盖 alpha）
git tag -a v0.1.0 -m "Art v0.1.0 — Phase 1 MVP complete"
git push origin v0.1-sprint0 v0.1-sprint1 v0.1-sprint2 v0.1-sprint3 v0.1.0
```

### 5.4 Changelog 生成

使用 `git-cliff` 或手动维护 `CHANGELOG.md`：

```bash
# 安装 git-cliff（可选）
# 基于 conventional commits 自动生成 changelog
git cliff -o CHANGELOG.md
```

手动维护格式：

```markdown
# Changelog

## [v0.1-sprint3] — 2026-06-xx
### Added
- WeChat notification push (task assignment + completion)
- Web UI improvements (role switching, task status flow)
- Prometheus metrics + health endpoints
- Docker Compose local deployment

### Fixed
- (from Sprint 0-2 checkpoints)

## [v0.1-sprint2] — 2026-06-xx
### Added
- WeChat Webhook with real signature verification
- MiniMax intent parsing pipeline
- WeChat message → task auto-creation

## [v0.1-sprint1] — 2026-06-xx
### Added
- FastAPI skeleton + SQLite init
- Role CRUD API (`/api/v1/roles`)
- Task CRUD API (`/api/v1/tasks`) with state machine

## [v0.1-sprint0] — 2026-06-xx
### Fixed
- JWT token expiry reduced from 720h to 24h
- Redis URL format corrected
- WeChatCrypto.verify_signature implemented
- intent_data validated via Pydantic schema
```

---

## 六、项目结构与 .gitignore

### 6.1 当前 .gitignore 覆盖范围

Python + IDE + OS + 环境变量已覆盖。补充项见下方。

### 6.2 建议补充的 .gitignore 项

```gitignore
# ── Python / pip / uv ─────────────────────────────────
*.egg-info/
dist/
build/
*.whl

# ── Test / Coverage ──────────────────────────────────
htmlcov/
.coverage
.coverage.*
.pytest_cache/
.mypy_cache/
.ruff_cache/

# ── Virtual Environment ───────────────────────────────
.venv/
venv/
ENV/

# ── FastAPI / Uvicorn ────────────────────────────────
*.pid

# ── SQLite (data files) ─────────────────────────────
*.db
*.sqlite
*.sqlite3
data/

# ── Config with secrets ──────────────────────────────
config.json          # 运行时配置（不要提交含 secrets 的版本）
config.example.json  # 示例配置（提交）

# ── PWA / Frontend (Phase 2+) ───────────────────────
node_modules/
dist/
*.vue.hbc
```

---

## 七、Phase 1 开发协议（Summary）

1. **分支**：所有改动从 `main` 创建短生命期 feature 分支，合并使用 Squash & Merge
2. **PR 前置**：CI 必须全部绿灯（lint + typecheck + test，coverage > 60%）
3. **Blocker 优先**：4 个 Must-Fix blocker（t_4c7a4dc9）必须先于 Phase 1 功能代码合并
4. **Commit 格式**：严格遵循 Conventional Commits（feat/fix/chore/docs/refactor/test: scope: description）
5. **版本**：Phase 1 MVP 目标版本 `v0.1.0-alpha`，通过 `git tag` 标记
6. **Review**：合入 main 至少需要 1 Approve

---

## 附录 A：常用 Git 命令速查

```bash
# 创建 feature 分支
git checkout main && git pull origin main
git checkout -b feature/my-feature

# 在 PR 前 rebase 保持线性历史
git fetch origin
git rebase origin/main

# 查看状态（合入 main 前）
git log --oneline main..HEAD

# Squash 本地多个 commit（用于 PR 前整理）
git rebase -i origin/main

# 打 tag
git tag -a v0.1.0-alpha -m "Phase 1 MVP start"
git push origin v0.1.0-alpha
```

## 附录 B：相关文档

| 文档 | 路径 |
|------|------|
| 技术方案 | `docs/planning/technical-plan.md` |
| 产品路线图 | `docs/product-roadmap.md` |
| 架构设计 | `docs/python-agent-architecture.md` |
| 高管简报 | `docs/Art-Executive-Brief.md` |
| 本文档 | `docs/CONTRIBUTING.md` |
