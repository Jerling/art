# Python 多角色个人 AI Agent 技术架构设计

> 版本: v0.2 (修订版)
> 日期: 2026-05-18
> 状态: 草稿，待评审

---

## 一、项目背景与愿景

### 1.1 产品定位

**类型**: 个人 AI Agent（ SaaS + 私有部署）
**目标用户**: 身兼多职的技术人（Team Lead + Committer + 项目负责人 + 软件经理等）
**核心差异**: "AI 原生 + 多角色合一" + "微信即终端"——任务和通知无缝推送到微信，微信消息直接创建任务

### 1.2 核心功能矩阵

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 多角色标签系统 | 同一人的不同角色有独立任务池和视角 | P0 |
| 跨角色协调 | 检测角色间利益冲突、智能推荐优先级 | P0 |
| 任务闭环追踪 | 创建→分配→执行→完成全链路 | P0 |
| 微信通知推送 | 任务状态变更、待办提醒推送到微信 | P0 |
| 微信消息创建任务 | 微信发消息 → AI解析 → 自动创建任务 | P0 |
| AI 原生 | 自然语言录入、意图识别、角色自动推断 | P1 |
| 数据分析 | 角色维度/时间维度/项目维度的效能统计 | P2 |
| 开放集成 | 支持 Linear/飞书/GitHub 等外部系统 | P2 |

### 1.3 技术约束（明确方向）

- **语言**: Python（FastAPI 生态）
- **AI**: 云端优先（OpenAI / Anthropic / MiniMax），本地可选
- **客户端**: Web（PWA），微信内嵌浏览器优先兼容
- **消息推送**: 微信（通过企业微信 or 微信客服消息）
- **不复用**: Hermes / Nomad Kanban 现有代码

---

## 二、技术架构设计

### 2.1 技术栈全景

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层（Web/PWA）                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │   Vue 3      │  │   PWA       │  │   微信内嵌    │           │
│  │  (TypeScript)│  │  (离线支持)  │  │   浏览器适配  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       API 网关层 (API Gateway)                   │
│         Python FastAPI + JWT Auth + Rate Limiting + CORS         │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Task Core     │  │    AI Brain     │  │  Integration    │
│   (任务核心)     │  │   (AI 大脑)     │  │   (集成模块)     │
│                 │  │                 │  │                 │
│ · Role Manager  │  │ · Intent Parse  │  │ · WeChat Adapt  │
│ · Task Manager  │  │ · Role Infer    │  │ · Linear Adapt  │
│ · Scheduler     │  │ · Priority Eng  │  │ · GitHub Adapt  │
│                 │  │ · Summary Gen   │  │ · Feishu Adapt  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       存储层 (Storage)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   SQLite      │  │  Redis        │  │  File Store  │         │
│  │  (结构化数据)  │  │ (缓存/队列)   │  │ (附件/媒体)   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Python 异步框架选择

**推荐: FastAPI + uvicorn (ASGI)**

| 维度 | FastAPI | Flask | Django |
|------|---------|-------|--------|
| 异步支持 | 原生 (uvicorn) | 需 Flask-Ayncio | 有 (ASGI) |
| 类型安全 | 高 (Pydantic) | 低 | 中 |
| 性能 | 一流 | 中 | 中 |
| OpenAPI/Swagger | 自动生成 | 需第三方 | 需第三方 |
| 生态(AI/ML) | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |

**理由**: FastAPI 生态与 AI/LLM 无缝集成，Pydantic 类型安全，开发效率高。

### 2.3 AI / LLM 集成方案

**架构原则: Provider 抽象 + 云端优先**

```python
# 核心 Provider Trait (用 Protocol 模拟)
from abc import ABC, abstractmethod
from typing import Protocol

class LLMProvider(Protocol):
    async def complete(self, prompt: str) -> str: ...
    async def embed(self, text: str) -> list[float]: ...

# 实现
class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o"): ...

class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4"): ...

class MiniMaxProvider:
    def __init__(self, api_key: str, model: str = "MiniMax-M2.7"): ...
```

**Provider 优先级**:

1. **MiniMax** (默认) - 低成本，高性价比，支持 Agent
2. **OpenAI** - GPT-4o 作为高精度任务
3. **Anthropic** - Claude 作为高精度任务备选
4. **本地 Ollama** (可选) - 隐私敏感场景

### 2.4 数据库选型

**主数据库: SQLite → PostgreSQL (未来)**

| 阶段 | 选型 | 理由 |
|------|------|------|
| MVP | SQLite | 零部署，单文件，够用 |
| 正式版 | PostgreSQL | 更好的并发/JSON/向量支持 |

**缓存/队列: Redis**

- AI 响应缓存（节省 token）
- 任务队列（异步处理）
- WebSocket 会话存储

### 2.5 前端技术选择

**推荐: Vue 3 + TypeScript + Vite + Pinia**

| 维度 | Vue 3 + TS | React + TS | 微信内嵌 |
|------|------------|------------|----------|
| 开发体验 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 兼容好 |
| 类型安全 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 兼容好 |
| 包体积 | 轻量 | 中等 | 无影响 |
| PWA 支持 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 需额外适配 |

**备选: 微信小程序** (需要时扩展)

---

## 三、核心模块详细设计

### 3.1 角色管理模块 (Role Manager)

**核心职责**: 角色定义、切换、权限隔离

```python
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID, uuid4

class Role(BaseModel):
    id: UUID = uuid4()
    name: str                    # "Team Lead", "Developer", "PM"
    description: str = ""
    color: str = "#6366f1"      # UI 显示颜色
    is_active: bool = True
    created_at: datetime = datetime.utcnow()

class RoleContext:
    """角色上下文（当前视角）"""
    role_id: UUID
    perspective: Perspective
    filter_rules: list[FilterRule]

class Perspective(str, Enum):
    ALL = "all"
    MINE = "mine"
    UNASSIGNED = "unassigned"
    PROJECT = "project"
    CUSTOM = "custom"
```

### 3.2 任务管理模块 (Task Manager)

**核心职责**: 任务生命周期、状态机、role_tag 隔离

```python
class TaskStatus(str, Enum):
    INBOX = "inbox"           # 收集箱（新任务入口）
    TODO = "todo"             # 待办
    IN_PROGRESS = "in_progress"  # 执行中
    DONE = "done"             # 完成
    CANCELLED = "cancelled"   # 取消

class TaskSource(str, Enum):
    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    WECHAT_MESSAGE = "wechat_message"  # 微信消息创建
    EXTERNAL = "external"

class Task(BaseModel):
    id: UUID = uuid4()
    title: str
    description: str | None = None

    # 多角色支持
    role_tags: list[UUID] = []

    # 生命周期
    status: TaskStatus = TaskStatus.INBOX
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
    completed_at: datetime | None = None

    # 执行信息
    assignee: str | None = None
    priority: int = 2  # 0=P0, 1=P1, 2=P2, 3=P3
    due_date: datetime | None = None

    # AI 元数据
    ai_summary: str | None = None
    intent: TaskIntent | None = None

    # 外部集成
    external_id: str | None = None
    source: TaskSource = TaskSource.MANUAL

class TaskIntent(BaseModel):
    action: str                    # feature/bug/refactor/docs...
    estimated_hours: float | None = None
    required_roles: list[UUID] = []
    suggested_priority: int = 2
    related_tasks: list[UUID] = []
```

**role_tag 隔离设计**:

- `role_tags` 是**多值字段**，一个任务可同时属于 [Team Lead, Project X]
- **视角过滤**: SQL `WHERE role_tags @> ?` 或 JSON 过滤
- **跨角色查看**: 用户主动切换视角时可见其他角色任务

### 3.3 微信集成模块 (WeChat Integration)

**核心职责**: 接收微信消息、推送任务通知、双向通信

```python
class WeChatAdapter:
    """微信集成适配器"""

    async def receive_message(self, message: WeChatMessage) -> Task | None:
        """
        接收微信消息，AI 解析后创建任务
        微信消息格式:
        - 纯文本: 直接 AI 解析
        - 语音: 转换为文本后再解析
        - 图片: OCR + AI 解析（可选）
        """
        ...

    async def push_notification(self, task: Task, event: str) -> bool:
        """
        推送任务通知到微信
        事件类型:
        - task_created: 新任务创建
        - task_assigned: 任务分配给你
        - task_due_soon: 截止日期临近
        - task_completed: 任务完成
        - daily_summary: 每日任务摘要
        """
        ...

    async def reply_to_message(self, message_id: str, content: str) -> bool:
        """回复微信消息（可选）"""
        ...
```

**微信消息接收架构**:

```
微信服务器 → Webhook → FastAPI → WeChatAdapter → AI Brain 解析 → Task 创建
                                      ↓
                               微信消息确认回复
```

**微信推送方式**:

| 方式 | 适用场景 | 限制 |
|------|----------|------|
| 企业微信应用消息 | 正式推送 | 需要企业微信账号 |
| 微信客服消息 | 客服场景 | 需要用户先互动 |
| 个人微信（测试） | 开发调试 | 有频率限制 |

### 3.4 AI Brain 模块

**核心职责**: 意图识别、角色推断、优先级推荐、摘要生成

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str | None = None) -> str:
        pass

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        pass

class AIBrain:
    def __init__(
        self,
        llm: LLMProvider,
        embedder: LLMProvider | None = None
    ):
        self.llm = llm

    async def parse_natural_input(self, text: str) -> TaskIntent:
        """
        自然语言任务解析
        示例:
        输入: "下周三前给 API Gateway 提个 PR review 请求，需要张明审批"
        输出: TaskIntent { action: review, estimated_hours: 0.5, required_roles: [...], suggested_priority: P1 }
        """
        prompt = f"""
        解析以下任务描述，提取结构化信息:
        {text}

        返回 JSON 格式: {{"action": "...", "estimated_hours": 0.5, "suggested_priority": 1}}
        """
        return await self.llm.complete(prompt)

    async def infer_roles(self, task: Task, available_roles: list[Role]) -> list[UUID]:
        """AI 推断任务应归属的角色"""
        ...

    async def recommend_priority(
        self,
        task: Task,
        context: AppContext
    ) -> int:
        """推荐优先级"""
        ...

    async def summarize(self, task: Task) -> str:
        """生成任务摘要"""
        ...

    async def detect_conflicts(self, tasks: list[Task]) -> list[Conflict]:
        """检测跨角色冲突"""
        ...

    async def generate_daily_summary(self, role_id: UUID) -> str:
        """生成每日任务摘要（推送到微信）"""
        ...
```

### 3.5 任务规划模块 (Task Planner)

**核心职责**: AI 智能规划每个角色每天的任务分配、优先级调度、时间块安排

```python
class DailyPlan(BaseModel):
    """每日任务规划"""
    id: UUID = uuid4()
    role_id: UUID                          # 归属角色
    date: date                             # 规划日期
    slots: list[TimeSlot] = []            # 时间块列表
    total_hours: float = 0                # 规划总时长
    estimated_completion: float = 0       # 预计完成率
    generated_at: datetime = datetime.utcnow()
    is_committed: bool = False            # 是否已确认发布

class TimeSlot(BaseModel):
    """时间块"""
    id: UUID = uuid4()
    start_time: time
    end_time: time
    task_id: UUID | None = None           # 分配的任务
    task_snapshot: str | None = None      # 任务快照（避免任务变更影响）
    status: SlotStatus = SlotStatus.FREE
    energy_level: EnergyLevel = EnergyLevel.MEDIUM  # 精力等级
    notes: str = ""

class SlotStatus(str, Enum):
    FREE = "free"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"

class EnergyLevel(str, Enum):
    HIGH = "high"     # 高精力：复杂任务、深度工作
    MEDIUM = "medium" # 中精力：常规任务
    LOW = "low"       # 低精力：简单任务、碎片工作

class PlanningContext(BaseModel):
    """规划上下文（供 AI 决策）"""
    role: Role
    unfinished_tasks: list[Task]          # 未完成任务
    soft_deadlines: list[Deadline]         # 软截止（可协商）
    hard_deadlines: list[Deadline]        # 硬截止（必须完成）
    available_hours: float               # 可用时长
    energy_curve: list[EnergyPoint]       # 一天精力曲线
    recent_completion_rate: float         # 最近完成率（用于调整计划）

class EnergyPoint(BaseModel):
    hour: int                              # 0-23
    level: EnergyLevel

class Deadline(BaseModel):
    task_id: UUID
    due_date: datetime
    is_hard: bool                         # True=硬截止，False=软截止
    urgency_score: float                  # 紧急程度 0-1
```

### 3.5.1 每日规划生成算法

```python
class TaskPlanner:
    """任务规划器"""

    def __init__(self, ai_brain: AIBrain):
        self.ai = ai_brain

    async def generate_daily_plan(
        self,
        role_id: UUID,
        date: date,
        working_hours: tuple[time, time] = (9, 18)
    ) -> DailyPlan:
        """
        生成每日任务规划

        流程:
        1. 收集角色所有未完成任务
        2. AI 分析任务优先级和精力匹配
        3. 生成时间块分配
        4. 评估计划可行性
        """
        context = await self._build_planning_context(role_id, date)

        # AI 生成规划
        plan_prompt = f"""
        你是一个任务规划专家。为角色「{context.role.name}」规划 {date} 的任务。

        可用时间: {working_hours[0]} ~ {working_hours[1]}
        可用时长: {context.available_hours} 小时

        未完成任务（按优先级排序）:
        {self._format_tasks(context.unfinished_tasks)}

        截止日期任务:
        {self._format_deadlines(context.soft_deadlines + context.hard_deadlines)}

        精力曲线（一天中各时段的工作效率）:
        {self._format_energy_curve(context.energy_curve)}

        要求:
        1. 将任务分配到具体时间块
        2. 匹配任务复杂度与精力等级（高精力时段做复杂任务）
        3. 留出缓冲时间（总时长的 15%）
        4. 确保高优先级任务优先安排
        5. 如果任务过多无法完成，明确标注需要延期的任务

        返回 JSON 格式:
        {{
            "slots": [
                {{
                    "start_time": "09:00",
                    "end_time": "10:30",
                    "task_id": "xxx or null",
                    "energy_level": "high/medium/low",
                    "notes": "任务描述或说明"
                }}
            ],
            "total_hours": 7.5,
            "estimated_completion": 0.85,
            "deferred_tasks": ["task_id1"],
            "reasoning": "规划理由说明"
        }}
        """
        response = await self.ai.llm.complete(plan_prompt)
        return self._parse_plan_response(response, role_id, date)

    async def auto_reschedule(
        self,
        role_id: UUID,
        date: date,
        reason: RescheduleReason
    ) -> DailyPlan:
        """
        自动重新规划（任务完成/取消/新增时触发）

        触发条件:
        - 任务提前完成 → 填充空闲时间
        - 任务取消 → 重新分配时间
        - 新任务加入 → 插入或替换低优先级任务
        """
        current_plan = await self._get_current_plan(role_id, date)
        if not current_plan:
            return await self.generate_daily_plan(role_id, date)

        # 增量调整而非全量重排
        adjustment_prompt = f"""
        当前计划需要调整:
        原因: {reason.value}

        当前计划:
        {self._format_plan(current_plan)}

        调整策略:
        - 若任务完成: 寻找下一个最适合的任务填充
        - 若任务取消: 重新分配该时间块
        - 若新任务加入: 评估是否需要替换/插入
        """
        ...

    async def evaluate_plan_feasibility(self, plan: DailyPlan) -> PlanFeasibility:
        """
        评估计划可行性
        返回: 评分、风险点、调整建议
        """
        issues = []
        score = 1.0

        # 检查时间冲突
        if self._has_time_conflicts(plan.slots):
            issues.append("存在时间块冲突")
            score -= 0.2

        # 检查精力匹配
        mismatched = self._check_energy_mismatch(plan.slots)
        if mismatched:
            issues.append(f"{len(mismatched)} 个任务精力匹配不当")
            score -= 0.1 * len(mismatched)

        # 检查硬截止保障
        hard_deadline_tasks = [s for s in plan.slots if self._is_hard_deadline(s.task_id)]
        if not hard_deadline_tasks:
            issues.append("硬截止任务未安排")
            score -= 0.3

        return PlanFeasibility(score=max(0, score), issues=issues)

    async def generate_plan_summary(self, plan: DailyPlan) -> str:
        """生成计划摘要（推送到微信）"""
        summary = f"""
📋 {plan.date} 任务规划

⏱️ 可用时间: {plan.total_hours}h
🎯 预计完成率: {plan.estimated_completion:.0%}

"""
        for slot in plan.slots:
            emoji = "✅" if slot.status == "completed" else "⏳" if slot.status == "in_progress" else "📌"
            energy_icon = "🔋" if slot.energy_level == "high" else "🔌" if slot.energy_level == "low" else "⚡"
            task_info = slot.task_snapshot or "空闲"
            summary += f"{emoji} {slot.start_time}-{slot.end_time} {energy_icon} {task_info}\n"

        if plan.deferred_tasks:
            summary += f"\n⏸️ 延期任务: {len(plan.deferred_tasks)} 个"

        return summary
```

### 3.5.2 规划 API 端点

|| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/roles/{id}/plans/{date}` | 获取某日规划 |
| POST | `/roles/{id}/plans/generate` | 生成每日规划 |
| POST | `/roles/{id}/plans/{date}/reschedule` | 重新规划 |
| PATCH | `/roles/{id}/plans/{date}/slots/{slot_id}` | 更新时间块 |
| POST | `/roles/{id}/plans/{date}/commit` | 确认并发布规划 |
| GET | `/roles/{id}/plans/{date}/feasibility` | 评估计划可行性 |

### 3.5.3 规划触发时机

| 触发类型 | 时机 | 行为 |
|---------|------|------|
| **定时生成** | 每日 20:00 | 自动生成次日规划并推送微信 |
| **手动触发** | 用户请求 | `/规划` 命令或 Web 端按钮 |
| **增量调整** | 任务完成/取消/新增 | 自动重新安排受影响时间块 |
| **周视图生成** | 每周日 | 生成下周整体规划框架 |

### 3.6 同步/集成模块

```python
class IntegrationAdapter(ABC):
    name: str
    source: ExternalSystem

    async def fetch_tasks(self, since: datetime) -> list[SyncedTask]:
        """拉取外部任务"""
        ...

    async def push_update(self, task: Task) -> bool:
        """推送更新到外部"""
        ...

    async def sync(self) -> SyncReport:
        """双向同步"""
        ...

# 实现的适配器
class WeChatAdapter:
    """微信消息接收 + 推送"""
    ...

class LinearAdapter:
    """Linear 双向同步"""
    ...

class GitHubAdapter:
    """GitHub Issue/PR 关联"""
    ...

class FeishuAdapter:
    """飞书消息通知"""
    ...
```

---

## 四、数据库设计

### 4.1 Schema 设计（SQLite MVP / PostgreSQL 正式版）

```sql
-- 角色表
CREATE TABLE roles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    color TEXT DEFAULT '#6366f1',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 任务表（核心）
CREATE TABLE tasks (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'inbox'
        CHECK (status IN ('inbox','todo','in_progress','done','cancelled')),
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 0 AND 3),

    -- 时间戳
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    due_date TEXT,

    -- 归属
    assignee TEXT,
    source TEXT DEFAULT 'manual'
        CHECK (source IN ('manual','ai_generated','wechat_message','external')),

    -- AI 元数据（JSON 存储）
    ai_summary TEXT,
    intent_data TEXT,  -- JSON: {action, estimated_hours, suggested_priority...}

    -- 外部引用
    external_id TEXT,
    external_source TEXT
);

-- 任务-角色多对多关系
CREATE TABLE task_roles (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, role_id)
);

-- 微信会话/消息记录
CREATE TABLE wechat_messages (
    id TEXT PRIMARY KEY,
    openid TEXT NOT NULL,
    msg_type TEXT,
    content TEXT,
    raw_data TEXT,  -- 原始 XML/JSON
    is_processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 任务通知记录
CREATE TABLE notifications (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    channel TEXT DEFAULT 'wechat',  -- wechat/feishu/email
    event TEXT,  -- task_created/task_assigned/task_due_soon/daily_summary
    status TEXT DEFAULT 'pending',  -- pending/sent/failed
    sent_at TEXT,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 同步记录
CREATE TABLE sync_log (
    id TEXT PRIMARY KEY,
    external_source TEXT NOT NULL,
    direction TEXT CHECK (direction IN ('in','out','sync')),
    status TEXT CHECK (status IN ('success','failed','partial')),
    external_id TEXT,
    local_id TEXT,
    error TEXT,
    synced_at TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assignee ON tasks(assignee);
CREATE INDEX idx_tasks_created ON tasks(created_at);
CREATE INDEX idx_task_roles_role ON task_roles(role_id);
CREATE INDEX idx_notifications_task ON notifications(task_id);
CREATE INDEX idx_wechat_messages_openid ON wechat_messages(openid);
```

### 4.2 任务视图表设计

#### 4.2.1 角色视角任务视图（Role Task View）

```sql
-- 按角色过滤的任务聚合视图
CREATE VIEW v_tasks_by_role AS
SELECT
    t.id,
    t.title,
    t.description,
    t.status,
    t.priority,
    t.due_date,
    t.created_at,
    t.assignee,
    t.source,
    t.ai_summary,
    t.intent_data,
    GROUP_CONCAT(r.name, ', ') AS role_names,
    GROUP_CONCAT(tr.role_id, ',') AS role_ids
FROM tasks t
LEFT JOIN task_roles tr ON t.id = tr.task_id
LEFT JOIN roles r ON tr.role_id = r.id
GROUP BY t.id;

-- 角色「我的任务」视图（当前激活角色的任务）
CREATE VIEW v_my_tasks AS
SELECT
    t.*,
    r.name AS primary_role,
    r.color AS primary_role_color
FROM tasks t
JOIN task_roles tr ON t.id = tr.task_id
JOIN roles r ON tr.role_id = r.id
WHERE r.is_active = 1
ORDER BY t.priority ASC, t.due_date ASC;
```

#### 4.2.2 任务状态统计视图

```sql
-- 各状态任务数量统计
CREATE VIEW v_task_status_summary AS
SELECT
    r.id AS role_id,
    r.name AS role_name,
    r.color AS role_color,
    COUNT(CASE WHEN t.status = 'inbox' THEN 1 END) AS inbox_count,
    COUNT(CASE WHEN t.status = 'todo' THEN 1 END) AS todo_count,
    COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) AS in_progress_count,
    COUNT(CASE WHEN t.status = 'done' THEN 1 END) AS done_count,
    COUNT(CASE WHEN t.status = 'done'
        AND t.completed_at >= date('now', '-7 days') THEN 1 END) AS done_this_week,
    COUNT(CASE WHEN t.due_date IS NOT NULL
        AND t.due_date < datetime('now', '+1 day')
        AND t.status NOT IN ('done', 'cancelled') THEN 1 END) AS overdue_count,
    COUNT(CASE WHEN t.due_date >= datetime('now', '-1 day')
        AND t.due_date < datetime('now', '+1 day')
        AND t.status NOT IN ('done', 'cancelled') THEN 1 END) AS due_today_count
FROM roles r
LEFT JOIN task_roles tr ON r.id = tr.role_id
LEFT JOIN tasks t ON tr.task_id = t.id
WHERE r.is_active = 1
GROUP BY r.id;
```

#### 4.2.3 每日规划视图

```sql
-- 规划时间块状态聚合
CREATE VIEW v_daily_plans AS
SELECT
    p.id AS plan_id,
    p.role_id,
    p.date,
    p.total_hours,
    p.estimated_completion,
    p.is_committed,
    p.generated_at,
    r.name AS role_name,
    COUNT(s.id) AS total_slots,
    COUNT(CASE WHEN s.status = 'completed' THEN 1 END) AS completed_slots,
    COUNT(CASE WHEN s.status = 'in_progress' THEN 1 END) AS in_progress_slots,
    COUNT(CASE WHEN s.status = 'planned' THEN 1 END) AS planned_slots,
    COUNT(CASE WHEN s.status = 'free' THEN 1 END) AS free_slots,
    SUM(CASE WHEN s.task_id IS NOT NULL
        AND s.status = 'completed' THEN 1 ELSE 0 END) AS completed_task_count
FROM daily_plans p
JOIN roles r ON p.role_id = r.id
LEFT JOIN plan_slots s ON p.id = s.plan_id
GROUP BY p.id;
```

#### 4.2.4 AI 推荐视图

```sql
-- 待规划的高优先级任务（用于 AI 生成规划）
CREATE VIEW v_tasks_for_planning AS
SELECT
    t.id,
    t.title,
    t.description,
    t.priority,
    t.due_date,
    t.intent_data,
    r.name AS role_name,
    CASE
        WHEN t.due_date < datetime('now', '+1 day') THEN 'urgent'
        WHEN t.due_date < datetime('now', '+3 days') THEN 'soon'
        ELSE 'normal'
    END AS urgency_level,
    json_extract(t.intent_data, '$.estimated_hours') AS estimated_hours
FROM tasks t
JOIN task_roles tr ON t.id = tr.task_id
JOIN roles r ON tr.role_id = r.id
WHERE t.status IN ('inbox', 'todo')
    AND t.due_date IS NOT NULL
    AND r.is_active = 1
ORDER BY t.priority ASC, t.due_date ASC;
```

#### 4.2.5 通知就绪视图

```sql
-- 待发送通知聚合
CREATE VIEW v_pending_notifications AS
SELECT
    n.id,
    n.task_id,
    n.channel,
    n.event,
    n.created_at,
    t.title AS task_title,
    t.assignee,
    CASE n.event
        WHEN 'task_created' THEN '新任务: ' || t.title
        WHEN 'task_assigned' THEN '任务分配: ' || t.title
        WHEN 'task_due_soon' THEN '即将到期: ' || t.title
        WHEN 'task_completed' THEN '已完成: ' || t.title
        WHEN 'daily_summary' THEN '每日任务摘要'
        ELSE n.event
    END AS notification_content
FROM notifications n
JOIN tasks t ON n.task_id = t.id
WHERE n.status = 'pending'
ORDER BY n.created_at ASC;
```

#### 4.2.6 视图使用示例

```python
# 获取当前角色的任务看板
def get_role_dashboard(role_id: UUID) -> dict:
    """角色仪表盘数据"""
    with get_db() as db:
        # 状态统计
        status_summary = db.execute(
            text("SELECT * FROM v_task_status_summary WHERE role_id = :role_id"),
            {"role_id": str(role_id)}
        ).fetchone()

        # 待完成任务（用于规划）
        tasks_for_planning = db.execute(
            text("SELECT * FROM v_tasks_for_planning WHERE role_id = :role_id"),
            {"role_id": str(role_id)}
        ).fetchall()

        # 待发送通知
        pending_notifications = db.execute(
            text("SELECT * FROM v_pending_notifications WHERE task_id IN (SELECT task_id FROM task_roles WHERE role_id = :role_id)"),
            {"role_id": str(role_id)}
        ).fetchall()

        return {
            "status": dict(status_summary),
            "tasks_for_planning": [dict(t) for t in tasks_for_planning],
            "pending_notifications": [dict(n) for n in pending_notifications]
        }
```

### 4.3 Redis 用途

| Key Pattern | 用途 | TTL |
|-------------|------|-----|
| `ai:cache:{hash}` | AI 响应缓存 | 1h |
| `task:queue` | 异步任务队列 | - |
| `wechat:session:{openid}` | 微信会话状态 | 24h |
| `rate:wechat:{openid}` | 微信 API 限流 | 1min |

---

## 五、API 设计

### 5.1 API 风格: REST + JSON

**Base URL**: `http://localhost:8765/api/v1`

### 5.2 认证

**MVP**: 简化的 token 认证
**未来**: 可升级到 OAuth2 / OIDC

```http
POST /api/v1/auth/token
Content-Type: application/json

{"username": "user", "password": "pass"}

---
Response 200
{"token": "eyJhbGc...", "expires_at": "2026-06-18T00:00:00Z"}

Authorization: Bearer eyJhbGc...
```

### 5.3 微信 Webhook 接收

```http
# 微信服务器回调（GET 验证 + POST 接收消息）
GET  /api/v1/wechat/webhook?signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx
POST /api/v1/wechat/webhook

# 微信消息格式（XML）
<xml>
    <ToUserName><![CDATA[toUser]]></ToUserName>
    <FromUserName><![CDATA[fromUser]]></FromUserName>
    <CreateTime>12345678</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[任务：下周三前完成 API 设计]]></Content>
</xml>
```

### 5.4 核心 API 端点

**角色管理**:

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/roles` | 列出所有角色 |
| POST | `/roles` | 创建角色 |
| GET | `/roles/{id}` | 获取角色详情 |
| PATCH | `/roles/{id}` | 更新角色 |
| DELETE | `/roles/{id}` | 删除角色 |

**任务管理**:

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/tasks` | 列出任务（支持 `?role_id=&status=` 过滤） |
| POST | `/tasks` | 创建任务 |
| POST | `/tasks/from-natural` | AI 解析自然语言创建任务 |
| POST | `/tasks/from-wechat` | 微信消息创建任务 |
| GET | `/tasks/{id}` | 获取任务详情 |
| PATCH | `/tasks/{id}` | 更新任务 |
| DELETE | `/tasks/{id}` | 删除任务 |
| POST | `/tasks/{id}/complete` | 完成任务 |
| POST | `/tasks/{id}/notify` | 推送任务通知到微信 |

**AI 能力**:

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/ai/parse` | 解析自然语言输入 |
| POST | `/ai/summarize` | 生成任务摘要 |
| POST | `/ai/recommend-priority` | 推荐优先级 |
| POST | `/ai/detect-conflicts` | 检测跨角色冲突 |
| POST | `/ai/daily-summary` | 生成每日摘要并推送微信 |

**微信集成**:

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/wechat/webhook` | 微信服务器验证回调 |
| POST | `/wechat/webhook` | 接收微信消息 |
| POST | `/wechat/push` | 手动推送消息到微信 |
| GET | `/wechat/status` | 微信连接状态 |

**集成**:

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/integrations` | 列出已配置集成 |
| POST | `/integrations/{name}/connect` | 连接外部系统 |
| POST | `/integrations/{name}/sync` | 触发同步 |
| GET | `/integrations/{name}/status` | 同步状态 |

### 5.5 API 请求/响应示例

**创建任务**:

```http
POST /api/v1/tasks
Authorization: Bearer ***
Content-Type: application/json

{
  "title": "Review API Gateway PR",
  "description": "Need to review the PR for rate limiting changes",
  "priority": 1,
  "role_tags": ["uuid1", "uuid2"],
  "due_date": "2026-05-27T00:00:00Z"
}

Response 201
{
  "id": "uuid",
  "title": "Review API Gateway PR",
  "status": "inbox",
  "priority": 1,
  "role_tags": ["uuid1", "uuid2"],
  "created_at": "2026-05-18T15:00:00Z"
}
```

**AI 自然语言创建**:

```http
POST /api/v1/tasks/from-natural
Authorization: Bearer ***
Content-Type: application/json

{
  "text": "下周三前给 API Gateway 提个 PR review 请求，需要张明审批"
}

Response 201
{
  "id": "uuid",
  "title": "Review API Gateway PR",
  "status": "inbox",
  "priority": 1,
  "role_tags": ["team-lead", "api-gateway-owner"],
  "due_date": "2026-05-27T00:00:00Z",
  "intent": {
    "action": "review",
    "estimated_hours": 0.5,
    "suggested_priority": 1
  }
}
```

---

## 六、微信集成详细设计

### 6.1 微信消息接收流程

```
微信用户发送消息
      ↓
微信服务器 POST 到我们服务器
      ↓
FastAPI /wechat/webhook 接收
      ↓
WeChatAdapter.parse_message()
      ↓
检查是否 AI 命令（以 "/" 开头）
      ↓
AI Brain 解析意图 → 创建 Task
      ↓
存入 wechat_messages 表
      ↓
返回微信消息确认
```

### 6.2 微信消息命令格式

| 命令 | 示例 | 说明 |
|------|------|------|
| `/任务 <描述>` | `/任务 下周三完成 API 设计` | 创建任务 |
| `/完成 <任务ID>` | `/完成 abc123` | 标记任务完成 |
| `/列表` | `/列表` | 查看待办任务 |
| `/帮助` | `/帮助` | 显示命令帮助 |
| `直接输入` | `下周三前完成 API 设计` | 自动识别为创建任务 |

### 6.3 微信通知推送

```python
async def push_task_notification(task: Task, event: str) -> bool:
    """
    推送任务通知到微信
    支持的事件:
    - task_created: 新任务创建（推送给创建者确认）
    - task_assigned: 任务分配（推送给 assignee）
    - task_due_soon: 截止日期临近（提前 1 天）
    - task_completed: 任务完成（推送给创建者）
    - daily_summary: 每日早/晚报（定时任务）
    """
    import xml.etree.ElementTree as ET

    # 企业微信应用消息格式
    message = {
        "touser": wechat_user_openid,
        "msgtype": "text",
        "agentid": WECHAT_AGENT_ID,
        "text": {
            "content": format_task_notification(task, event)
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": await get_wechat_access_token()},
            json=message
        )
        return response.json()["errcode"] == 0
```

### 6.4 每日摘要推送（定时任务）

```python
# 每日早 8:30 推送
@router.cron("30 8 * * *")
async def daily_morning_summary():
    """生成并推送每日任务摘要"""
    for role in await get_active_roles():
        summary = await ai_brain.generate_daily_summary(role.id)
        await wechat_adapter.push_notification(
            event="daily_summary",
            content=summary,
            role_id=role.id
        )
```

---

## 七、项目结构

```
python-agent/
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口
│   │
│   ├── api/                       # API 层
│   │   ├── __init__.py
│   │   ├── router.py              # 路由汇总
│   │   ├── deps.py                # 依赖注入（Auth, DB Session）
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── roles.py
│   │       ├── tasks.py
│   │       ├── ai.py
│   │       ├── wechat.py
│   │       └── integrations.py
│   │
│   ├── domain/                    # 领域模型
│   │   ├── __init__.py
│   │   ├── role.py
│   │   ├── task.py
│   │   ├── intent.py
│   │   └── notification.py
│   │
│   ├── service/                   # 业务逻辑
│   │   ├── __init__.py
│   │   ├── role_service.py
│   │   ├── task_service.py
│   │   ├── ai_brain.py
│   │   ├── wechat_service.py
│   │   └── sync_service.py
│   │
│   ├── storage/                   # 存储层
│   │   ├── __init__.py
│   │   ├── database.py            # SQLite/SQLAlchemy 连接
│   │   ├── redis_client.py        # Redis 连接
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── role_repo.py
│   │       ├── task_repo.py
│   │       └── notification_repo.py
│   │
│   ├── llm/                       # LLM 集成
│   │   ├── __init__.py
│   │   ├── base.py                # Provider 基类
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   ├── minimax.py
│   │   └── ollama.py
│   │
│   ├── integrations/              # 外部系统集成
│   │   ├── __init__.py
│   │   ├── wechat/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py         # 微信适配器
│   │   │   ├── webhook.py         # 消息接收
│   │   │   └── pusher.py         # 消息推送
│   │   ├── linear.py
│   │   ├── github.py
│   │   └── feishu.py
│   │
│   ├── utils/                     # 工具
│   │   ├── __init__.py
│   │   ├── config.py              # 配置加载
│   │   └── security.py            # JWT/密码工具
│   │
│   └── worker/                     # 后台任务
│       ├── __init__.py
│       ├── cron.py                # 定时任务
│       └── notifications.py       # 通知发送队列
│
├── migrations/                    # 数据库迁移
│   └── 001_initial.sql
│
├── static/                        # Web 静态文件
│   ├── index.html
│   └── assets/
│
├── tests/
│   ├── __init__.py
│   ├── api_tests/
│   └── integration_tests/
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml         # PostgreSQL + Redis + App
│
└── docs/
    └── architecture.md
```

---

## 八、MVP 实施路径

### 8.1 第一阶段: 最小闭环 (0→1)

**目标**: 核心 CRUD + 微信消息接收 + AI 解析

**周期**: 3-4 周

**功能范围**:

1. **角色管理** - CRUD，基础视角切换
2. **任务管理** - CRUD，基础状态流转（Inbox→Todo→Done）
3. **微信消息接收** - Webhook 接收 + AI 解析创建任务
4. **微信通知推送** - 任务变更推送
5. **AI 意图解析** - 自然语言 → 结构化任务

**里程碑**: 用户发微信消息 `/任务 xxx` → AI 解析 → 任务创建 → Web 端可看

### 8.2 第二阶段: 完善 + 集成

**目标**: 完整功能 + 外部系统集成

**周期**: 3-4 周

**功能范围**:

1. **AI 能力完善** - 角色推断、优先级推荐、摘要生成
2. **每日摘要推送** - 定时任务推送到微信
3. **Linear/GitHub 集成** - 外部任务同步
4. **飞书通知** - 飞书作为备用通知渠道
5. **数据分析** - 角色时间分配统计

### 8.3 第三阶段: 优化 + 扩展

**目标**: 性能优化 + 更多集成

**周期**: 4-6 周

**功能范围**:

1. **PostgreSQL 迁移** - SQLite → PostgreSQL
2. **Redis 缓存** - AI 响应缓存 + 任务队列
3. **微信小程序** - 原生微信小程序客户端
4. **更多集成** - Jira、Trello、Notion 等

---

## 九、开发成本估算

### 9.1 按模块估算

| 模块 | 复杂度 | 估算工时 | 关键风险 |
|------|--------|----------|----------|
| 项目脚手架（FastAPI+SQLAlchemy） | 低 | 8h | 框架选型决策 |
| 角色管理 | 中 | 12h | 视角过滤逻辑 |
| 任务管理（核心） | 中 | 20h | 状态机设计 |
| 微信消息接收 | 高 | 24h | 微信签名验证/消息解密 |
| 微信消息推送 | 中 | 16h | 企业微信 API 限制 |
| AI Brain | 高 | 32h | LLM 质量/响应速度 |
| 集成模块 | 中 | 32h | API 稳定性 |
| Web 前端 | 中 | 40h | Vue 3 + TypeScript |
| 测试 + 文档 | 中 | 16h | 回归风险 |
| **总计** | | **200h (~5周)** | |

### 9.2 关键风险点

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 微信消息签名验证 | 高 | 先用测试号验证 |
| 企业微信 API 限制 | 中 | 申请企业账号，用应用消息 |
| LLM 质量不佳 | 中 | 提供手动覆盖，规则降级 |
| 微信消息延迟 | 中 | Redis 队列缓冲 |
| AI 响应超时 | 中 | 异步处理 + 微信模板消息 |

---

## 十、架构决策记录 (ADR)

### ADR-001: 使用 FastAPI 作为 Web 框架

**状态**: Accepted
**决策**: 采用 FastAPI + uvicorn 构建 REST API
**理由**: 异步原生、Pydantic 类型安全、与 AI 生态无缝集成

### ADR-002: 使用 SQLite 作为 MVP 数据库

**状态**: Accepted
**决策**: SQLite 用于结构化数据存储
**理由**: 零部署复杂度，单文件，MVP 单用户够用

### ADR-003: 云端 AI 优先

**状态**: Accepted
**决策**: MiniMax / OpenAI / Anthropic 云端调用
**理由**: 开发效率高，成本可控，本地 Ollama 作为可选备选

### ADR-004: 微信作为主要通知渠道

**状态**: Accepted
**决策**: 企业微信应用消息作为主要推送方式
**理由**: 用户最常用的触达渠道，微信消息打开率最高

### ADR-005: Web PWA 作为主要客户端

**状态**: Accepted
**决策**: Vue 3 + TypeScript + PWA
**理由**: 跨平台，开发效率高，微信浏览器兼容性好

### ADR-006: 使用 config.json 配置文件

**状态**: Accepted
**决策**: 采用 JSON 格式配置文件，不使用环境变量
**理由**: 配置集中、类型安全、层级清晰，支持多环境切换（开发/生产）

### ADR-007: Redis 用于缓存和队列

**状态**: Proposed
**决策**: Redis 作为 AI 缓存和异步任务队列
**理由**: 提升 AI 响应速度，解耦通知发送

---

## 十一、开放问题（待讨论）

1. **微信方案选型**: 企业微信 vs 个人微信测试号？企业微信需要公司主体
2. **多用户支持时机**: MVP 单用户，未来是否需要多用户？
3. **向量数据库必要性**: RAG 能力是否真的需要向量数据库？
4. **开源协议**: 选 AGPLv3（传染）还是 Apache2/MIT（友好商业）？
5. **任务持久化**: 微信消息创建的 Task 是否长期保留？

---

## 附录: 配置文件 (config.json)

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8765,
    "debug": false
  },

  "database": {
    "url": "sqlite:///./data/agent.db"
  },

  "redis": {
    "url": "redis://localhost:6379/0"
  },

  "auth": {
    "secret_key": "your-secret-key-here",
    "jwt_algorithm": "HS256",
    "jwt_expire_days": 30
  },

  "llm": {
    "provider": "minimax",
    "openai": {
      "api_key": "sk-xxx",
      "model": "gpt-4o"
    },
    "anthropic": {
      "api_key": "sk-ant-xxx",
      "model": "claude-sonnet-4"
    },
    "minimax": {
      "api_key": "xxx",
      "model": "MiniMax-M2.7"
    },
    "ollama": {
      "base_url": "http://localhost:11434",
      "model": "llama3"
    }
  },

  "wechat": {
    "app_id": "wx_xxx",
    "app_secret": "xxx",
    "token": "xxx",
    "aes_key": "xxx",
    "agent_id": 1000001
  },

  "planning": {
    "working_hours": {
      "start": "09:00",
      "end": "18:00"
    },
    "daily_plan_generation_time": "20:00",
    "energy_buffer_percent": 15
  }
}
```

### 配置加载模块

```python
# src/utils/config.py
import json
from pathlib import Path
from pydantic import BaseModel
from functools import lru_cache

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False

class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./data/agent.db"

class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"

class AuthConfig(BaseModel):
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30

class LLMProviderConfig(BaseModel):
    api_key: str
    model: str = "gpt-4o"
    base_url: str | None = None

class LLMConfig(BaseModel):
    provider: str = "minimax"
    openai: LLMProviderConfig | None = None
    anthropic: LLMProviderConfig | None = None
    minimax: LLMProviderConfig | None = None
    ollama: LLMProviderConfig | None = None

class WeChatConfig(BaseModel):
    app_id: str
    app_secret: str
    token: str
    aes_key: str
    agent_id: int

class PlanningConfig(BaseModel):
    working_hours_start: str = "09:00"
    working_hours_end: str = "18:00"
    daily_plan_generation_time: str = "20:00"
    energy_buffer_percent: int = 15

class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    auth: AuthConfig
    llm: LLMConfig = LLMConfig()
    wechat: WeChatConfig | None = None
    planning: PlanningConfig = PlanningConfig()

    @classmethod
    def load(cls, path: str = "config.json") -> "AppConfig":
        config_path = Path(path)
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            return cls(**data)
        raise FileNotFoundError(f"Config file not found: {path}")

@lru_cache
def get_config() -> AppConfig:
    return AppConfig.load()
```

### 配置文件位置优先级

```python
CONFIG_PATHS = [
    "./config.json",                    # 当前目录（开发用）
    "~/.config/agent/config.json",     # 用户目录
    "/etc/agent/config.json"           # 系统目录（生产环境）
]
```

> **注意**: 生产部署时将 `config.json` 放在 `/etc/agent/config.json`，并设置文件权限 `600` 防止非授权访问。
