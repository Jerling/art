# Art Phase 1 Sprint Plan

> **项目**: Art — 个人多角色 AI Agent
> **阶段**: Phase 1 MVP
> **周期**: 4 周（2026-05-xx 起，Week 0–3）
> **版本**: v1.0（初稿）
> **最后更新**: 2026-05-22

---

## 一、决策摘要

### Sprint 粒度：1 周（Sprint 0 / Sprint 1 / Sprint 2 / Sprint 3）

| 选项 | 优点 | 缺点 |
|------|------|------|
| **1 周（选中）** | 快速验证；适应 small team； blocker 处理及时 | 仪式开销相对高 |
| 2 周 | 仪式少，深度工作时间长 | 反馈慢，blocker 拖一周才暴露 |

**选中理由**：团队规模小（android-dev/coder/reviewer/qa），无重型 CI，Phase 1 只有 4 周，1 周 sprint 更适合快速迭代和问题早发现。

---

## 二、Phase 1 总览

**目标**：用户发微信 `/任务 xxx` → AI 解析 → 任务创建 → Web 端可查看 → 微信推送确认。

**4 Must-Fix Blockers**（必须在 Sprint 0 全部解决后才能开始 Sprint 1）：

| # | Blocker | 严重性 | 根因 |
|---|---------|--------|------|
| B1 | JWT secret 硬编码 + token 有效期 720h | 🔴 阻断 | 代码评审 |
| B2 | Redis URL 语法错误（`***@` 非标准） | 🟡 高 | 代码评审 |
| B3 | WeChatCrypto.verify_signature 是占位符 | 🔴 阻断 | 代码评审 |
| B4 | intent_data JSON 无 schema 校验 | 🟡 高 | 代码评审 |

---

## 三、Sprint 分解

### Sprint 0 — 阻断项清除 + 基础设施准备
**周期**：Week 0（约 5 个工作日）

**目标**：修复全部 4 个 Must-Fix blockers；搭建测试骨架；完成 WeChat 开发者账号申请。

| 任务 | 类型 | Owner | 完成标准 |
|------|------|-------|----------|
| B1: JWT secret 移至环境变量，token 有效期改为 24h | bugfix | coder | 安全审计通过 |
| B2: Redis URL 语法修复 | bugfix | coder | 单元测试通过 |
| B3: WeChatCrypto.verify_signature 完整实现 | TDD | coder | crypto 测试 100% 覆盖 |
| B4: intent_data Pydantic model_validate 校验 | feature | coder | schema 验证测试通过 |
| WeChat 客服消息测试号申请 | setup | pm | AppID/AppSecret 已配置 |
| 测试骨架搭建（pytest + httpx mock + Golden Dataset 目录） | infra | qa | 35 个测试场景框架就绪 |

**Git branch**: `sprint0/fix-blockers` → PR → `main`
**Exit criterion**: 4 个 blockers 全部 resolved，安全审计结论可查

---

### Sprint 1 — 骨架 + 角色/任务 CRUD
**周期**：Week 1（约 5 个工作日）

**目标**：FastAPI 骨架运行；角色 CRUD API；任务 CRUD API；SQLite schema 初始化。

| 任务 | 类型 | Owner | 完成标准 |
|------|------|-------|----------|
| 项目骨架搭建（FastAPI + uvicorn + SQLAlchemy 2.0 async） | infra | coder | `uvicorn main:app` 启动成功 |
| SQLite 数据库初始化脚本（001_initial.sql） | infra | coder | migration 脚本可重复执行 |
| 角色 CRUD API（/roles） | feature | coder | reviewer 通过，单元测试 > 80% |
| 任务 CRUD API（/tasks）含状态流转 | feature | coder | reviewer 通过，单元测试 > 80% |
| 角色-任务多对多关联 API | feature | coder | reviewer 通过 |
| Vue 3 基础项目初始化（Vite + Pinia） | frontend | android-dev | npm run dev 启动成功 |
| 角色管理 Web 页面（创建/切换/列表） | frontend | android-dev | 手动测试通过 |
| 任务列表 Web 页面（按角色筛选） | frontend | android-dev | 手动测试通过 |

**Git branch**: `sprint1/crud-skeleton` → PR → `main`
**Exit criterion**: 角色和任务 CRUD 端到端可用的 MVP 基础骨架

---

### Sprint 2 — 微信接入 + AI 意图解析
**周期**：Week 2（约 5 个工作日）

**目标**：微信 Webhook 接收消息；MiniMax 意图解析；消息记录存储。

| 任务 | 类型 | Owner | 完成标准 |
|------|------|-------|----------|
| 微信 Webhook 接收端点（/wechat/webhook） | feature | coder | 签名验证通过，本地 ngrok 可调通 |
| 微信消息存储（wechat_messages 表） | feature | coder | reviewer 通过 |
| MiniMax API 集成（意图解析） | feature | coder | Mock 测试通过，P99 < 5s |
| AI 意图 → 结构化字段解析（title/priority/estimated_hours） | feature | coder | Golden Dataset 验证 intent 准确率 |
| 微信消息 → 任务自动创建流程 | feature | coder | 集成测试通过 |
| 基础微信推送（任务创建通知 via 客服消息） | feature | coder | 推送送达手机 |
| MiniMax 容错（httpx mock 6 种故障场景） | test | qa | 6 个降级场景测试通过 |
| MCP Client 集成（OpenViking localhost:1933） | feature | coder | ADR-001 符合，延迟 < 300ms |

**Git branch**: `sprint2/wechat-ai` → PR → `main`
**Exit criterion**: 微信发消息 → 任务自动创建 → 推送确认，整条链路打通

---

### Sprint 3 — 收尾 + 集成 + MVP 上线
**周期**：Week 3（约 5 个工作日）

**目标**：通知推送完善；Web 端美化；SRE/监控就绪；MVP 内部测试。

| 任务 | 类型 | Owner | 完成标准 |
|------|------|-------|----------|
| WeChat 推送通知完善（任务分配/完成状态变更） | feature | coder | 推送送达 |
| Web 端 UI 完善（任务状态流转 + 角色视角切换） | frontend | android-dev | 手动测试通过 |
| Prometheus metrics + 健康检查端点（/health, /health/detailed） | infra | coder | SLO 埋点就绪 |
| SQLite 在线备份脚本 | infra | coder | VACUUM INTO 脚本可执行 |
| Docker Compose 本地部署配置 | infra | ops | docker-compose up 成功 |
| MVP 集成测试（35 场景，30 项 Checklist） | test | qa | 全部通过 |
| MVP 内测（内部用户 3 天连续使用验证） | test | qa | 意图识别准确率 > 90%，P99 < 5s |
| Sprint 回顾 + Phase 1 总结报告 | pm | pm | 报告输出给 Jerry |

**Git branch**: `sprint3/mvp-launch` → PR → `main`
**Exit criterion**: Phase 1 MVP 功能完整，4 个 Must-Fix 已解决，SRE 埋点就绪，可进入 Phase 2 规划

---

## 四、Git 工作流协作（git-workflow-master 对应关系）

每个 Sprint 产生 **1 个 feature branch → 1 个 PR → 合并至 main**。

```
main
  └── sprint0/fix-blockers        (Week 0)
  └── sprint1/crud-skeleton        (Week 1)
  └── sprint2/wechat-ai            (Week 2)
  └── sprint3/mvp-launch           (Week 3)
```

| Sprint | Branch | PR 标题模式 | Reviewer | 合并后 |
|--------|--------|-------------|----------|--------|
| Sprint 0 | `sprint0/fix-blockers` | `[Sprint 0] Fix blockers: B1-B4` | reviewer + security-engineer | main |
| Sprint 1 | `sprint1/crud-skeleton` | `[Sprint 1] CRUD skeleton + SQLite init` | reviewer | main |
| Sprint 2 | `sprint2/wechat-ai` | `[Sprint 2] WeChat webhook + MiniMax intent parsing` | reviewer + qa | main |
| Sprint 3 | `sprint3/mvp-launch` | `[Sprint 3] MVP launch: notifications + web + SRE` | reviewer + qa + pm | main |

**与 git-workflow-master 协调**：
- 每个 Sprint 结束时，ops 在 `main` 上打 tag：`v0.1-sprint0` / `v0.1-sprint1` / ...
- Kanban 任务（t_xxxx）作为 sprint planning 的底层载体，每个 sprint goal 对应一个 kanban card
- Phase 1 完成后，整体 tag 为 `v0.1-mvp`

---

## 五、日常协作机制

### Standup 节奏
- **形式**：异步 via Kanban 任务评论 + Feishu 简短更新
- **频率**：每个工作日结束（17:00 前）
- **内容模板**：
  ```
  Sprint [N] Day [X] — [日期]
  ✅ 完成：[今日完成的任务]
  🔜 下一步：[明日计划]
  ⚠️ Blocker：[如有]
  ```

### Blocker 处理流程
```
1. Blocker 发现 → 立即在对应 kanban card 评论 @project-shepherd
2. project-shepherd 评估：
   - 2h 内可在 sprint 内消化 → 重新分配任务
   - 影响 sprint goal → 立即 @pm + 发起 scope 讨论
3. 24h 内未解决 → 升级至 Jerry（Feishu）
```

### 进度同步（Jerry/Stakeholder）
- **每日**：Sprint health snapshot 发 Feishu（如有 blocker 或 scope 变化）
- **每周 Sprint Review**：每周五，发 Sprint Summary（含 velocity、blockers、scope changes）给 Jerry
- **格式**：

```markdown
## Sprint [N] Summary — [周日期]

**Sprint Goal**: [目标]
**Velocity**: [X] pts planned / [Y] pts delivered
**Blockers Resolved**: [N]
**New Blockers**: [列表或"无"]

### Scope Changes
| 请求 | 来源 | 决策 | 理由 |
|------|------|------|------|

### 下周目标
[描述]
```

---

## 六、Decision Records

### DR-2026-05-22: Sprint 粒度选择 1 周

**Decision**: Phase 1 使用 1 周 Sprint，共 4 个 Sprint（Week 0–3）
**Rationale**: 团队规模小、无重型 CI 流程、Phase 1 仅 4 周，1 周 sprint 可实现快速反馈；blocker 在 1 周内暴露比 2 周更及时
**Alternatives considered**: 2 周 Sprint（反馈周期太长，blocker 拖沓风险高）
**Revisit date**: Sprint 3 结束时复盘，如 1 周节奏过碎则 Phase 2 调整为 2 周

### DR-2026-05-22: Sprint 0 包含 Must-Fix Blockers

**Decision**: Sprint 0 专注清除 4 个 Must-Fix blockers + 测试骨架 + WeChat 账号申请，不做功能开发
**Rationale**: 4 个阻断性代码问题是 MVP 发布的安全底线，不清除无法进行后续开发；WeChat 账号申请为外部依赖，需尽早启动
**Alternatives considered**: 将 blockers 分散到各 sprint（不采纳，blocker 分散会导致技术债积累）
**Revisit date**: Sprint 0 结束复盘

---

## 七、Sprint Calendar（概览）

```
        Mon       Tue       Wed       Thu       Fri
Week 0  Planning  B1-B4 Fix WeChat申请 Review   Review
Week 1  Planning  CRUD开发   CRUD开发   CRUD+Review  Sprint Review
Week 2  Planning  WeChat+AI  WeChat+AI  Integration  Sprint Review
Week 3  Planning  Web+Notify SRE+Test   MVP Test  Sprint Review + Jerry Report
```

---

## 八、附录：Kanban 任务映射

| Sprint | 任务 Title Pattern | 数量估算 |
|--------|---------------------|----------|
| Sprint 0 | `[Sprint0] B1: JWT fix`, `[Sprint0] B2: Redis fix`, `[Sprint0] B3: WeChatCrypto`, `[Sprint0] B4: intent_data`, `[Sprint0] WeChat账号`, `[Sprint0] 测试骨架` | 6 |
| Sprint 1 | `[Sprint1] FastAPI骨架`, `[Sprint1] SQLite init`, `[Sprint1] 角色CRUD API`, `[Sprint1] 任务CRUD API`, `[Sprint1] Vue项目初始化`, `[Sprint1] 角色Web页面`, `[Sprint1] 任务列表Web` | 7 |
| Sprint 2 | `[Sprint2] WeChat Webhook`, `[Sprint2] 消息存储`, `[Sprint2] MiniMax集成`, `[Sprint2] 意图解析`, `[Sprint2] 微信推送`, `[Sprint2] MCP集成`, `[Sprint2] 容错测试` | 7 |
| Sprint 3 | `[Sprint3] 通知完善`, `[Sprint3] Web UI完善`, `[Sprint3] SRE埋点`, `[Sprint3] Docker部署`, `[Sprint3] 集成测试`, `[Sprint3] MVP内测`, `[Sprint3] 复盘报告` | 7 |
