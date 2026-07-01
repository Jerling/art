# 用户验证触发机制（R5）

> **Source**: Sprint 4 复盘 `docs/post-mortem/sprint4-process-gap.md` §5 R4（注：retro 原标号 R4；本任务 spec 改称 R5 — 是同一机制的命名差异，下文统一使用 R5）
> **Owner**: product-manager（机制设计 + 通知发送 + 超时处理）+ jerry（验证执行人）+ sre（cron + board schema 实现）
> **生效**: Sprint 5 起强制
> **Last updated**: 2026-07-02（t_add2601d 任务产出）
> **实现文档**（sre 维护）: `docs/operations/user-verify-deadline.md`

---

## 1. 为什么需要这条机制

Sprint 4 JWT 改动（commit `b2e30a1` + `60e6236`）：

- 6/3 commit 落 main
- 6/15 merge 到 main
- 6/17 "Sprint 1-4 全部 ✅ 完成" 写进 `.project-memory.md`
- 7/1（**33 天后**）jerry 第一次在部署环境跑 → 全 API 401/404

**问题**：流程定义了 step 6 "用户验证通过"（见 `.project-memory.md` → 开发阶段流程），但：

1. **没有 deadline** — 验证可以无限期延后
2. **没有触发机制** — 没人主动提醒 jerry 该去验证
3. **没有兜底** — developer 自己宣告 done 后即视为"已验证"

**根因**："done" 完全由 commit-merge 驱动，step 6 是个软目标，没人 push 它执行。

**R5 的修法**：
1. 给 step 6 加 **4 天 hard deadline**
2. 加 **PM 自动通知**（developer 标 done 当天 + 第 3 天）
3. 加 **超时自动 block**（4 天内没 verify → 任务进 blocked 状态）
4. 推送（step 7）必须等 step 6 通过

---

## 2. 4 天 deadline 规则

### 2.1 时间口径

**4 个日历日**（不是工作日）。例如：

- 周一 done → 周五 23:59 前必须 verify（4 天 = 周一/二/三/四）
- 周五 done → 周二 23:59 前（4 天 = 周五/六/日/一）
- 节假日同样计算（不剔除春节/国庆等）

**为什么用日历日不是工作日**：Sprint 4 反例中从 commit 到发现 bug 33 天，按工作日 ≈ 23 天 — 太长。4 个日历日 ≈ 最长跨越 1 个周末 = jerry 最迟 5 天后必须看到。无论如何不能拖过 1 周。

### 2.2 ⚠️ 与 sre 已落地实现的差异（待 reconcile）

sre 已实现 `docs/operations/user-verify-deadline.md`，使用的是 **5 个工作日**（board.json 字段 `user_verify_business_days: 5`）。差异：

| 来源 | 口径 |
|---|---|
| 本任务 spec（R5） | 4 个**日历日** |
| Sprint 4 retro R4 | 5 个**工作日** |
| sre 已实现 (`user-verify-deadline.md`) | 5 个**工作日**（已 ship） |

**PM 决策建议**：
- 短期：保留 sre 已实现的 5 工作日（不要让 PM 文档和 sre 实现打架 — 用户拿到时疑惑）
- 中期：jerry 在下次 retro 决定是否改成 4 日历日；若改，PM 文档定稿 + sre 同步修改 board.json + cron

本文档**以 R5 spec 的 4 日历日为准**写流程，**但承认 sre 实现仍在 5 工作日上跑**。这条差异在下次 retro 必须解决。

---

## 3. 触发流程

### 3.1 时间线

```
T+0  developer 调 kanban_complete（含 e2e_evidence）→ 任务进入 done
     ├─ board 自动记录 completed_at
     └─ PM 在 board 评论里 ping jerry："<task_id> 已 done，请 <4 天 deadline 前> 验证"
T+1  若 jerry 已 verify：流程结束（happy path）
T+2  若仍未 verify：PM 在 board 二次 ping（提醒，不升级）
T+3  若仍未 verify：PM 升级通知 — 通过 Feishu DM 给 jerry 发卡片
T+4  23:59 deadline 到期
     ├─ 若仍未 verify：cron 自动 block 任务 + Feishu 通知 jerry + PM
     └─ 若已 verify：流程结束
```

### 3.2 通知模板

#### T+0 / T+2 — board 评论模板

```
@jerry <task_id> 已 done（含 e2e_evidence）。请在 4 个日历日内 verify：
- hermes kanban verify <task_id> --by jerry --note "<一句话说明>"

deadline: <YYYY-MM-DD 23:59>
未按时 verify → cron 自动 block。

证据链接：<e2e_evidence URL / 路径>
```

#### T+3 — Feishu 卡片模板

```
[Art] 待验证任务提醒

任务: <task_title> (<task_id>)
done 时间: <YYYY-MM-DD HH:MM>
deadline: <YYYY-MM-DD 23:59>（剩 1 天）
e2e_evidence: <URL / 路径>

动作: hermes kanban verify <task_id> --by jerry --note "..."

不 verify → 任务明天 23:59 自动 block。
```

#### T+4 — Feishu 通知（cron 自动）

```
[Art] 任务已自动 block — 用户验证超时

任务: <task_title> (<task_id>)
done 时间: <YYYY-MM-DD HH:MM>
超时: 4 个日历日（deadline <YYYY-MM-DD 23:59> 已过）

任务状态: done → blocked
事件: user_verify_deadline_exceeded
reason: Sprint 4 retro R5: user-verify deadline exceeded

解法:
1. jerry 实际验证后: hermes kanban verify <task_id> --by jerry
2. 任务回 done
3. PM 在 retro 报告本次超时
```

### 3.3 谁负责通知

| 时点 | 谁发 | 通过什么 | 备注 |
|---|---|---|---|
| T+0 | PM | board 评论 | 任务 done 后由 PM 手动发（或自动 ping） |
| T+2 | PM | board 评论 | 同上 |
| T+3 | PM | Feishu DM 给 jerry | 升级为外部通道 |
| T+4 | **cron（自动）** | Feishu | 无需人工介入；详见实现文档 |

---

## 4. 超时处理

### 4.1 自动 block 规则

4 个日历日到期仍未 verify：

1. cron（每天 09:00 跑）扫所有 `status='done' AND user_verified_at IS NULL` 的任务
2. 计算 `completed_at` 到 now 的日历日数
3. 若 ≥4 天：原子 CAS 把 `status` 改成 `blocked`，记 `user_verify_deadline_exceeded` 事件 + `blocked` 事件
4. 写一条 comment 说明 deadline + 链接到本文档

完整实现细节：`docs/operations/user-verify-deadline.md` §"What auto-block looks like"。

### 4.2 block 后如何恢复

jerry 实际验证后：

```bash
hermes kanban verify <task_id> --by jerry --note "实际测试内容"
```

- `user_verified_at` 写入 now
- `status` 从 blocked → done（自动）
- `user_verified` 事件记入 event log
- PM 在下次 Sprint close 报告本任务曾 block + 恢复

**反悔 verify**（测错了分支）：

```bash
hermes kanban verify <task_id> --by jerry --unverify
```

清空 `user_verified_at` / `user_verified_by`，下次 cron 仍会再次 block（如未重新 verify）。

### 4.3 跳过机制（仅限 hotfix）

标注 `[hotfix]` 的任务允许：

1. developer 标 done 后立即 push（不等 verify）
2. jerry 在 24h 内补 verify

未按时 verify → 同样按 §4.1 block。hotfix 流程详见 `docs/planning/release-process.md`。

---

## 5. 推送（step 7）门控

### 5.1 当前流程回顾

`.project-memory.md` → 开发阶段流程 → step 7 = "developer push 远程"。

### 5.2 R5 加的约束

**step 7 必须在 step 6 通过后才能执行**：

```
step 5 (developer 编译部署安装本地 commit)
  ↓
step 6 (用户验证通过 — R5 4 天 deadline 内)
  ├─ 已 verify → 进 step 7
  └─ 超时 → 任务 block（见 §4），不许 step 7
  ↓
step 7 (developer push 远程)
```

**判定**：`user_verified_at IS NOT NULL` → 允许 push；否则 → 阻断。

### 5.3 实施方式

短期：人工 gate — developer 在 push 前自查任务 board status + `user_verified_at`。
中期：CI check — pre-push hook 或 GitHub Action 检查最近 commit 对应任务的 `user_verified_at`（sre 范围，本任务不动）。

---

## 6. 反例 / 教训

### 反例 1 — Sprint 4 JWT（核心反例）

- **done 时间**：6/3（commit `b2e30a1`）
- **实际 verify 时间**：7/1（33 天后）
- **deadline 缺口**：无任何 deadline；33 天里 board 状态一直是 done
- **结果**：Sprint 3 + Sprint 4 都被标"✅ 完成"，但生产系统不可用
- **修复**：§2 加 4 天 deadline；§3 加 PM 自动通知；§4 加自动 block；§5 加推送门控
- **未来如何防**：cron 每天扫 + 自动 block；PM 在 Sprint close 报告超时率

### 反例 2 — Sprint 4 fix `t_0e04abde`

- **done 时间**：6/15（commit `6588dcd`）
- **实际 verify**：6/15 当天 jerry 验过，但**只 curl + UI 截图**，没验 SPA 深层路径
- **deadline 缺口**：4 天 deadline 内确实 verify 了，但 verify 质量不够
- **修复**：本机制不解决"verify 质量"问题；那是 `done-criteria.md` §3.4（e2e_evidence 收紧） + `review-matrix.md` §2.2.4（PM 三问）的职责
- **未来如何防**：verify 必须基于 e2e_evidence（playwright trace / w3m dump / 深层截图），不能仅靠 curl 200

---

## 7. 自检清单（PM 在任务 done 当天）

```
[ ] §2.1 deadline 已计算（4 日历日）并写到 board comment
[ ] §3.2 T+0 通知模板已发送
[ ] §3.3 通知负责人（PM 自己）已确认
[ ] §5.1 step 7 push 暂缓，等 verify
[ ] 若任务涉及前端路由：参考 `done-criteria.md` §3.4 核对 e2e_evidence 类型
[ ] calendar reminder 已设（T+3 Feishu 升级通知）
```

---

## 8. 与其他文档的关系

- **R5 来源**（本任务 spec）：done 后 4 天 deadline + 自动 block + Feishu 通知
- **retro R4 来源**：`docs/post-mortem/sprint4-process-gap.md` §5 R4 — 原文是 5 工作日，本任务 spec 改为 4 日历日
- **sre 实现**：`docs/operations/user-verify-deadline.md` — 当前按 5 工作日跑，与本任务 spec 有差异（见 §2.2）
- **R7 联动**：`done-criteria.md` §3 — e2e_evidence 必须非空才能 done，进而才能进入 R5 4 天倒计时
- **R3 联动**：`sprint-decomposition.md` §2.2.1 — Integration Verification 子任务 done 后立即触发 R5
- **R6 联动**：`review-matrix.md` §2.2.4 — PM 三问在 PR 阶段已发生，R5 是 PR 合并后的最终验证
- **R2 联动**：`docs/operations/kanban-e2e-evidence.md` — R2 确保 e2e_evidence 必填，R5 确保 e2e_evidence 被实际消费
- **框架索引**：`docs/process/dev-workflow.md`（t_7c0bf7af 任务产物，pending）