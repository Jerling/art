# Art Git Workflow — 详细参考

> 本文档是 `CONTRIBUTING.md` 的补充，提供 GitHub 平台配置和命令级细节。
> 适用于 `git-workflow-master` 和 `project-shepherd` 在 Sprint 开始前执行初始化配置。

---

## 1. GitHub 仓库初始化（一次性）

### 1.1 创建 GitHub Repo

```bash
# 在 GitHub 上创建私有仓库后，本地初始化
cd /home/jer/data/Code/art
git init
git remote add origin https://github.com/<org>/art.git
git add .
git commit -m "docs: initial project skeleton"
git branch -M main
git push -u origin main
```

### 1.2 设置 Branch Protection（main）

在 GitHub Web UI：`Settings → Branches → Add rule`

| 设置项 | 勾选 |
|--------|------|
| Branch name pattern | `main` |
| ☑ Require pull request reviews before merging | ✅ |
| Required approving reviewers | `1` |
| ☑ Dismiss stale reviews | ✅ |
| ☑ Require status checks to pass before merging | ✅ |
| Search for required status checks | `lint`, `typecheck`, `test`, `coverage` |
| ☑ Require branches to be up to date before merging | ✅ |
| ☑ Do not allow bypassing the above settings | ✅ |

### 1.3 配置 GitHub Actions Secrets

在 GitHub Web UI：`Settings → Secrets and variables → Actions`

| Secret 名 | 说明 | 来源 |
|-----------|------|------|
| `JWT_SECRET` | JWT 签名密钥（>= 32 random chars） | `openssl rand -hex 32` |
| `WECHAT_APP_ID` | 微信测试号 AppID | 微信公众平台 |
| `WECHAT_APP_SECRET` | 微信测试号 AppSecret | 微信公众平台 |
| `REDIS_URL` | Redis 连接 URL | Phase 2 开始使用 |

### 1.4 配置 GitHub Actions Variables

`Settings → Secrets and variables → Actions → Variables`

| Variable 名 | 值 |
|-------------|-----|
| `PYTHON_VERSION` | `3.11` |
| `MIN_COVERAGE` | `60` |

---

## 2. 分支创建（项目启动时一次性执行）

```bash
cd /home/jer/data/Code/art

# main 已在第一步创建并推送

# 创建 feature 分支模板（可选，用 alias 简化）
# 在 ~/.gitconfig 添加：
# [alias]
#   new = "!f() { git checkout main && git pull && git checkout -b feature/$1; }; f"

# 查看所有分支
git branch -a
```

---

## 3. Phase 1 Milestone 和 Tag 初始化

### 3.1 创建 GitHub Milestone

```bash
# 使用 gh CLI
gh api repos/{owner}/art/milestones \
  --method POST \
  --field title="Phase 1 MVP" \
  --field state=open \
  --field description="角色 CRUD + 任务 CRUD + 微信消息 Webhook + AI 意图解析 + 微信通知推送（4 周）" \
  --field due_on=2026-06-30T00:00:00Z
```

或在 GitHub Web UI：`Issues → Milestones → New milestone`

### 3.2 初始 Tag（Phase 1 MVP 起点）

```bash
cd /home/jer/data/Code/art

# 创建 v0.1.0-alpha 起点 tag
git tag -a v0.1.0-alpha -m "Art Phase 1 MVP start — pre-blocker-fix baseline"
git push origin v0.1.0-alpha

# 里程碑 checkpoint tags（每周或每个 blocker 修复后）
# 示例：Blocker 全部修复后
git tag -a v0.1.0-alpha.1 -m "Week 1: All 4 Must-Fix blockers resolved"
git push origin v0.1.0-alpha.1
```

### 3.3 版本与 Tag 对照表

| 事件 | Tag | 说明 |
|------|-----|------|
| 项目初始化/骨架完成 | `v0.1.0-alpha` | 起点 tag |
| 4 个 Blocker 全部修复并合并 | `v0.1.0-alpha.1` | 可开始 Phase 1 功能开发 |
| Week 2: 角色+任务 CRUD 完成 | `v0.1.0-alpha.2` | 核心 CRUD checkpoint |
| Week 3: AI Brain 集成完成 | `v0.1.0-alpha.3` | AI 功能 checkpoint |
| Week 4: 微信集成完成，MVP 达成 | `v0.1.0` | Phase 1 正式完成 |

---

## 4. 合并流程详解

### 4.1 标准 Feature 合并

```bash
# 1. 确保 main 最新
git checkout main && git pull origin main

# 2. 创建 feature 分支
git checkout -b feature/my-feature

# 3. 开发 + commit（遵循 Conventional Commits）

# 4. 推送（首次推送设置上游）
git push -u origin feature/my-feature

# 5. 在 GitHub 打开 PR
gh pr create \
  --title "feat(tasks): add bulk complete endpoint" \
  --body "<!-- 使用 PR 模板 -->"

# 6. PR 合并（Squash & Merge）
gh pr merge feature/my-feature --squash --delete-branch

# 7. 删除本地分支
git checkout main && git branch -d feature/my-feature
```

### 4.2 Hotfix 合并

```bash
git checkout -b hotfix/fix-wechat-signature
# ... 修复 ...
git push -u origin hotfix/fix-wechat-signature
gh pr create --title "fix(wechat): implement real signature verification"
# PR 需要 1 Approve，然后 Merge Commit（不要 squash）
gh pr merge hotfix/fix-wechat-signature --merge --delete-branch
```

### 4.3 处理冲突

```bash
# 在 feature 分支中
git fetch origin
git rebase origin/main

# 解决冲突后
git add .
git rebase --continue

# 强制推送（仅在你自己独占的分支上）
git push --force-with-lease
```

---

## 5. CHANGELOG 维护（手动）

在每次正式 release tag 时更新 `CHANGELOG.md`：

```markdown
# Changelog

## [v0.1.0-alpha] — 2026-06-xx
### Added
- Role CRUD API (`/api/v1/roles`)
- Task CRUD API (`/api/v1/tasks`)
- JWT authentication with env-injected secret
- WeChat webhook signature verification
- AI intent parsing via MiniMax-M2.7

### Fixed
- JWT token expiry reduced from 720h to 24h (#x)
- Redis URL format corrected (#y)
- intent_data now validated via Pydantic schema (#z)

### Changed
- Python minimum version: 3.11
```

---

## 6. 常用工具配置

### 6.1 pyproject.toml dev dependencies（参考）

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.9",
]
```

### 6.2 ruff 配置（pyproject.toml）

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]
ignore = ["E501"]  # line too long (handled by formatter)
```

### 6.3 mypy 配置

```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = false  # MVP phase, relax to true later
```

---

## 7. 发布检查清单（每 Release 前执行）

- [ ] 所有 CI checks 绿灯
- [ ] `CHANGELOG.md` 已更新
- [ ] `git tag` 已打并推送
- [ ] GitHub Milestone 已关闭
- [ ] 无未关闭的 blocker
- [ ] 文档已更新（CONTRIBUTING.md、architecture.md）
