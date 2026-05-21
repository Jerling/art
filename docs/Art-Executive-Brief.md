# Art 项目高管简报

**日期**: 2026-05-21
**状态**: 技术方案复审完成，安全审计 / 开发视角评审进行中
**简报作者**: executive-brief

---

## 一句话定位

Art 是**微信里的个人 AI 执行力教练**——多角色 AI Agent 系统，通过微信消息触发任务创建、AI 解析、自动规划与确认推送，形成完整闭环。

---

## 核心进展摘要

| 评审维度 | 结论 | 关键产出 |
|----------|------|----------|
| 技术方案 | ✅ 通过 | ADR-001 确立，technical-plan.md v0.3 |
| 竞品调研 | ✅ 通过 | research-report.md 扩充至 320 行 |
| 产品路线图 | ✅ 通过 | v0.3 发布，新增 AI 质量指标体系 |
| 测试策略 | ⚠️ 需重建 | 缺乏 AI 验证方法论、MCP Client mock |
| 测试分析 | ✅ 通过 | 35 个场景、30 项 Checklist、3 项高优风险 |
| SRE 方案 | ✅ 通过 | 5 条 MVP SLO、Prometheus + OpenTelemetry 三层设计 |
| 代码评审 | ⚠️ 4 个阻断项 | JWT 安全配置、WeChat 签名占口、JSON Schema 缺失 |
| 安全审计 | 🔄 进行中 | — |
| 开发视角 | 🔄 进行中 | — |

---

## 各角色识别的关键风险

### 🔴 高优先级风险（需高管决策）

| 风险 | 来源评审 | 影响 | 建议处理 |
|------|----------|------|----------|
| JWT secret 硬编码 + token 有效期 720h | 代码评审 | 账户劫持风险 | 环境变量注入，24h 有效期 |
| WeChatCrypto.verify_signature 是占位符 | 代码评审 | 消息伪造风险 | 安全关键路径，优先实现 |
| 微信 API 限制（小厂个人测试号） | 技术方案 | 无法企业微信发布 | Phase 1 后评估企业微信申请 |

### 🟡 中优先级风险（技术团队处理）

| 风险 | 来源评审 | 影响 |
|------|----------|------|
| SQLite 并发写锁 | 技术方案 | 单用户够用，多用户需迁 PostgreSQL |
| AI 幻觉导致错误任务 | 测试分析 | 需 Golden Dataset + Schema 验证层 |
| intent_data JSON 无 schema 校验 | 代码评审 | Service 层需 Pydantic model_validate |
| Redis URL 语法错误（`***@` 非标准） | 代码评审 | 配置层 bug，测试可发现 |

---

## 待决策事项

以下问题需要高管明确结论后方可推进：

1. **JWT 安全配置落地** — token 有效期是否接受 24h？secret 注入方式？
2. **微信签名验证实现优先级** — 是否在 MVP 就完整实现？
3. **企业微信 vs 个人测试号** — Phase 1 发布形态决策？
4. **Phase 2 PostgreSQL 迁移时机** — MVP 后还是增长触发后？

---

## 建议下一步行动

| 行动 | 负责方 | 前置条件 |
|------|--------|----------|
| 修复 4 个阻断性代码问题 | developer | 安全审计结论后优先 |
| 完成安全审计 + 开发视角评审 | security-engineer / developer | 预计 1-2 天 |
| 启动 Phase 1 MVP 功能开发 | android-dev / coder | 阻断项全部修复 |
| 确认企业微信发布策略 | pm | 高管决策 |

---

## 技术架构定稿

```
微信消息 → Webhook → AI 解析（MiniMax-M2.7）
                         ↓ 意图识别 + 任务创建
                    MCP Client ←→ OpenViking MCP（工具执行层）
                         ↓
                   任务存储（SQLite MVP / PostgreSQL 正式）
                         ↓
                   每日规划 → 微信推送确认
```

**ADR-001 核心结论**: OpenViking MCP = 工具执行层，MiniMax-M2.7 = 推理层，两者解耦，架构清晰，~100-300ms 延迟代价可接受。

---

## 备注

- 安全审计（t_5a02cf10）和开发视角评审（t_cbc51836）仍在进行中，简报基于已完成的 7 项评审
- Phase 边界已修正：Channel Adapter 归入 Phase 3，精力曲线 / 冲突检测 MVP 不做
- 测试覆盖率目标：Unit 70% / Integration 25% / E2E 5%
