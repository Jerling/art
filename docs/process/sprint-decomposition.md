# Sprint 任务分解模板（R3）

> **Source**: Sprint 4 复盘 `docs/post-mortem/sprint4-process-gap.md` §5 R3
> **Owner**: product-manager（每个 Sprint kickoff 时由 PM 主导拆解）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_add2601d 任务产出）

---

## 1. 为什么需要这个模板

Sprint 4 JWT 中间件是一个 9 文件改动（commit `b2e30a1`），被打包成单个 commit 直接合入 `sprint3/mvp-launch`，**没有父任务、没有 PRD、没有子任务、没有验收标准**。结果：

- 没有 `POST /auth/login` 入口（业务 API 401）
- 没有 `app.mount("/", StaticFiles(...))` 服务挂载（Web UI 404）
- 没有"用户能登录后调用受保护接口"的 E2E 测试
- 33 天后 jerry 上手才发现系统不可用

**根因**：Sprint 4 是一整个 commit，但实际涉及 3 个独立可交付物（登录、路由鉴权、Web 端 token 流）。合在一起 → 每个子目标的 acceptance criteria 被合并吞掉 → "missing entry path" 这种语义性 gap 在 review 层看不见。

**R3 的修法**：把 Sprint 强制拆成 ≥5 个子任务 + 每个子任务必须有独立 acceptance criteria，让"缺入口路径"在子任务层面就暴露出来。

---

## 2. Sprint 拆解强制规则

### 2.1 子任务数量下限

| Sprint 类型 | 最少子任务数 | 说明 |
|---|---|---|
| 通用 Sprint | **5** | 任何 Sprint kickoff 时，PM 必须在 board 上建 ≥5 个子任务 |
| 修复类 Sprint（bug fix） | **3** | bug 复现 + 根因修复 + 回归验证（最低三件套） |
| 文档/流程类 Sprint | **2** | 起草 + review/merge（低风险，但仍要拆） |

**为什么是 5？** Sprint 4 反例是 1 个 commit 顶 9 文件；按"逻辑可独立交付单元"切，最少也应该是：① 入口（login）② 路由鉴权 ③ Web 端 token 流 ④ E2E 验证 ⑤ 文档/部署更新 = 5 个。如果连 5 个都拆不出来，多半是 scope 没想清楚。

### 2.2 子任务必须包含的固定项

#### 2.2.1 每个 Sprint 必含 1 个 Integration Verification 子任务

**这是 R3 的硬规则**，不可省略：

```
任务标题: [Sprint N] Integration Verification
父任务:   Sprint N 所有子任务的 parent（即 Sprint N 的 integration verify 阻塞 Sprint N+1）
验收标准（固定文案，不可改）:
  "user can complete the entire happy path of Sprint N in a deployed
   environment, with e2e_evidence attached"
```

引用：`.project-memory.md` → 开发阶段流程 → step 6 已强制此条。

**为什么是固定文案**：防止 PM 把验收标准写成"系统能跑"这种模糊话术 — 必须是"happy path 跑通 + 证据附上"两条都得满足。

#### 2.2.2 Web UI 类 Sprint 必含"前端构建产物接入后端"项

凡是 Sprint 涉及任何前端改动（`.vue`、`.tsx`、`.jsx`、`web/dist/`、`index.html`、`assets/` 等），**必须**额外有 1 个独立的子任务，标题模板：

```
[Sprint N] Frontend build artifact → backend integration
```

验收标准模板：
- [ ] 前端 `npm run build`（或等价命令）产物存在于 `web/dist/` 或等价目录
- [ ] 后端有对应的服务挂载（如 `app.mount("/", StaticFiles(...))`、CDN 配置、SPA fallback）
- [ ] E2E 验证：浏览器访问根路径 → 200 + 加载到带 auth 的入口页

**反例**：Sprint 4 的 `web/dist/index.html` 已经在仓库里（npm build 过），但 `main.py` 没有 `StaticFiles` 挂载 — 前端产物 = 死文件。这个反例直接催生了 2.2.2 这条规则。

### 2.3 每个子任务的最小元数据

| 字段 | 必填 | 示例 |
|---|---|---|
| `title` | ✅ | `[Sprint 5] L-001 dotenv 加载顺序修复` |
| `body` (acceptance criteria) | ✅ | "user can start the server with `uvicorn main:app` and see all 12 env vars loaded; tests pass" |
| `assignee` | ✅ | `developer` / `mobile-developer` / `sre` 等具体 profile |
| `priority` | 建议 | High/Medium/Low |
| `parents` | ✅ | 至少 link 到 Sprint N 父任务；若属于"Integration Verification"类，需 link 到 §2.2.1 |
| `e2e_evidence` (完成时) | ✅ | URL / 路径 / note（见 `done-criteria.md`） |

---

## 3. 拆解工作流（PM 主导）

### 3.1 步骤

1. **PRD 先行** — Sprint kickoff 会议前，PM 写 1 页 PRD：scope / non-scope / 验收标准 / 风险点。PRD 路径 `docs/planning/sprint<N>-prd.md`。
2. **架构对齐** — software-architect 评审 PRD 5 分钟，标出技术风险点 → 必要时反馈调整 scope。
3. **拆子任务** — PM 把 PRD 拆成 ≥5 个子任务卡片，每个卡片填 §2.3 的最小元数据。
4. **建 Integration Verification 子任务** — 按 §2.2.1 固定模板建。
5. **link 父子** — 所有子任务的 `parents` 字段填 Sprint N 父任务 ID；Integration Verification 子任务的 `parents` 反向 link 到所有 Sprint N 子任务（双向依赖）。
6. **评审** — jerry 在 board 上 review 拆解结果，签字确认 → Sprint N 正式启动。

### 3.2 时间约束

- Sprint kickoff 当天完成 PRD + 拆子任务
- jerry review ≤ 1 个工作日内完成
- Sprint N 启动后 ≤ 2 个工作日内开始第一张子任务卡片的工作

---

## 4. 验收（verify 模板）

PM 在 Sprint N 收尾前自检：

- [ ] `hermes kanban show <sprint-N-parent>` 列出 ≥5 个子任务
- [ ] 其中 1 个的标题严格匹配 `[Sprint N] Integration Verification`
- [ ] Integration Verification 子任务的 `parents` 包含所有其他 Sprint N 子任务 ID
- [ ] 每个子任务的 `body` 都有可独立验收的 acceptance criteria（不是"完成开发"这种模糊话）
- [ ] 若 Sprint 涉及前端：存在 1 个标题含"Frontend build artifact → backend integration"的子任务
- [ ] 全部子任务的 `assignee` 字段不为空

**判定**：6 条全过 → Sprint N 拆解合规；任一不过 → PM 必须在 Sprint close 前补齐，否则 retro 记录为 process gap。

---

## 5. 反例 / 教训

### 反例 1 — Sprint 4 JWT（核心反例）

- **现象**：1 个 commit `b2e30a1` 涵盖 login 缺失 + StaticFiles 缺失 + require_auth 挂载 3 个独立逻辑
- **为何过 review**：被打包成"小改动"，没有拆出 acceptance criteria
- **修复**：拆成 Sprint 4.1（login endpoint）/ Sprint 4.2（auth gate on /admin 起逐步铺开）/ Sprint 4.3（StaticFiles + Web token flow）
- **未来如何防**：见 §2.2.1 + §2.2.2

### 反例 2 — Sprint 3 close 时无 Integration Verification

- **现象**：Sprint 3 "MVP final deliverables" commit `662ea27` 没有 Integration Verification 子任务就直接宣布收尾
- **为何过 review**：当时的流程没有强制这条
- **修复**：§2.2.1 把这条固化到每个 Sprint kickoff
- **未来如何防**：Sprint N 的 Integration Verification 子任务未 done → 不允许开 Sprint N+1（见 `done-criteria.md` §4）

---

## 6. 与其他文档的关系

- **R3 来源**：`docs/post-mortem/sprint4-process-gap.md` §5 R3
- **与 R7 联动**：`done-criteria.md` 规定每个子任务"done"的判定；本文件规定子任务"存在性 + 拆解粒度"的判定
- **与 R6 联动**：`review-matrix.md` 规定每个子任务 review 走哪几层；本文件确保拆出的子任务能被独立 review
- **与 R5 联动**：`user-verification.md` 规定 Integration Verification 子任务完成后的 4 天 deadline 倒计时
- **框架索引**：`docs/process/dev-workflow.md`（t_7c0bf7af 任务产物，pending）— 本文件是 R3 的深度展开