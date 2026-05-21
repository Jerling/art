# 阿特 Art 技术实现方案

> 基于设计文档: `python-agent-architecture.md` (v0.2, 2026-05-18)
> 编写日期: 2026-05-19
> 状态: v0.3 (2026-05-20) — 技术评审复审版
>
> **评审结论**: 架构基本合理，补充 OpenViking MCP 集成层，明确 Channel Adapter 抽象范围，修正 Phase 边界

---

## 零、架构决策记录 (ADR)

### ADR-001: OpenViking MCP 在系统中的定位

**状态**: Accepted

**上下文**: Art 系统的 AI 推理使用 MiniMax-M2.7，工具执行通过 OpenViking MCP Server (localhost:1933)。两者是不同层次的组件，需要明确分工。

**决策**:
- **MiniMax-M2.7**: AI 对话推理、意图解析、摘要生成等纯 LLM 任务
- **OpenViking MCP Server**: 工具调用（文件操作、代码执行、信息检索等），作为 AI 的"手脚"
- MCP Client 层 (`mcp_client.py`) 集成到 Python Agent 服务中，通过 stdio 与 OpenViking 通信

**架构层次**:
```
AI Brain (MiniMax)
    ↓ 推理决定需要什么工具
MCP Client (Python Agent)
    ↓ stdio
OpenViking MCP Server (localhost:1933)
    ↓ 执行工具
外部世界 (文件/搜索/代码)
```

**Trade-off**:
- ✅ 工具执行与 AI 推理解耦，OpenViking 可以独立演进
- ✅ MCP 协议是标准，工具扩展不修改 Agent 核心代码
- ❌ 增加一层复杂度，工具调用延迟增加 ~100-300ms
- ❌ 本地 MCP Server 有状态，不适合无服务器部署

** alternatives considered**:
1. 直接在 Python Agent 中实现工具（耦合高，不采纳）
2. 用 LangChain Agent 封装（引入重型框架，不采纳）

---

## 一、MVP 技术方案

### 1.1 技术栈定稿

|| 层级 | 技术选型 | 版本 | 说明 |
||------|----------|------|------|
|| **Web 框架** | FastAPI | >= 0.110.0 | ASGI 异步原生，Pydantic 类型安全 |
|| **运行服务器** | uvicorn | >= 0.27.0 | ASGI 服务器，支持 hot reload |
|| **ORM** | SQLAlchemy | 2.0.x | asyncio 支持，异步查询 |
|| **数据库** | SQLite | 3.45+ | MVP 单文件，零部署 |
|| **AI 推理** | MiniMax-M2.7 (默认) | - | AI 对话/意图解析（成本低 + 国内合规） |
|| **AI 工具执行** | OpenViking MCP Server | localhost:1933 | MCP 协议，工具调用 |
|| **AI 备选** | OpenAI GPT-4o | - | 高精度任务备选 |
|| **MCP Client** | mcp-client (Python) | - | stdio 连接 OpenViking |
|| **缓存/队列** | Redis | 7.0+ | AI 响应缓存、任务队列 |
|| **前端** | Vue 3 + TypeScript | 5.x | Composition API + Vite |
|| **状态管理** | Pinia | 2.x | Vue 3 官方推荐 |
|| **PWA** | vite-plugin-pwa | 0.19+ | 离线支持 |
|| **微信集成** | 企业微信应用消息 | - | 正式环境使用 |

**关键依赖版本约束理由**:

- **FastAPI >= 0.110.0**: 支持 Pydantic v2，原生 JSON schema 生成
- **SQLAlchemy 2.0.x**: 完整的 async/await 支持，核心 API 稳定
- **Python >= 3.11**: 必需 for dataclass_transform, improved type hints

### 1.2 数据库表结构详细设计

```sql
-- =============================================
-- 001_initial.sql - MVP 数据库迁移脚本
-- =============================================

-- 角色表 (roles)
CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    color TEXT DEFAULT '#6366f1',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 任务表 (tasks) - 核心
CREATE TABLE IF NOT EXISTS tasks (
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
CREATE TABLE IF NOT EXISTS task_roles (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, role_id)
);

-- 微信会话/消息记录
CREATE TABLE IF NOT EXISTS wechat_messages (
    id TEXT PRIMARY KEY,
    openid TEXT NOT NULL,
    msg_type TEXT,
    content TEXT,
    raw_data TEXT,
    is_processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 任务通知记录
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    channel TEXT DEFAULT 'wechat',
    event TEXT,
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending','sent','failed')),
    sent_at TEXT,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 同步记录
CREATE TABLE IF NOT EXISTS sync_log (
    id TEXT PRIMARY KEY,
    external_source TEXT NOT NULL,
    direction TEXT CHECK (direction IN ('in','out','sync')),
    status TEXT CHECK (status IN ('success','failed','partial')),
    external_id TEXT,
    local_id TEXT,
    error TEXT,
    synced_at TEXT DEFAULT (datetime('now'))
);

-- 每日规划表
CREATE TABLE IF NOT EXISTS daily_plans (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    role_id TEXT NOT NULL REFERENCES roles(id),
    date TEXT NOT NULL,
    total_hours REAL DEFAULT 0,
    estimated_completion REAL DEFAULT 0,
    is_committed INTEGER DEFAULT 0,
    generated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(role_id, date)
);

-- 规划时间块表
CREATE TABLE IF NOT EXISTS plan_slots (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    plan_id TEXT NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id),
    task_snapshot TEXT,
    status TEXT DEFAULT 'free'
        CHECK (status IN ('free','planned','in_progress','completed','skipped')),
    energy_level TEXT DEFAULT 'medium'
        CHECK (energy_level IN ('high','medium','low')),
    notes TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

-- 用户认证表 (MVP 简化)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    wechat_openid TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    is_active INTEGER DEFAULT 1
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_task_roles_role ON task_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_task_roles_task ON task_roles(task_id);
CREATE INDEX IF NOT EXISTS idx_notifications_task ON notifications(task_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_wechat_messages_openid ON wechat_messages(openid);
CREATE INDEX IF NOT EXISTS idx_daily_plans_role_date ON daily_plans(role_id, date);
```

### 1.3 API 端点详细设计

#### 1.3.1 认证 API

```
POST   /api/v1/auth/register     - 用户注册 (MVP)
POST   /api/v1/auth/token        - 获取 JWT Token
GET    /api/v1/auth/me           - 获取当前用户信息
PATCH  /api/v1/auth/wechat       - 绑定微信 OpenID
```

**请求/响应示例**:

```http
POST /api/v1/auth/token
Content-Type: application/json

{"username": "user", "password": "pass"}

Response 200
{
    "access_token": "eyJhbGc...",
    "token_type": "bearer",
    "expires_in": 7200
}
```

#### 1.3.2 角色管理 API

```
GET    /api/v1/roles                    - 列出所有角色
POST   /api/v1/roles                    - 创建角色
GET    /api/v1/roles/{id}               - 获取角色详情
PATCH  /api/v1/roles/{id}               - 更新角色
DELETE /api/v1/roles/{id}               - 删除角色
GET    /api/v1/roles/{id}/stats         - 角色统计数据
GET    /api/v1/roles/{id}/tasks         - 获取角色下的任务
```

**Query 参数** (GET /roles/{id}/tasks):
- `status`: inbox|todo|in_progress|done|cancelled
- `priority`: 0|1|2|3
- `page`: int (default: 1)
- `page_size`: int (default: 20, max: 100)

#### 1.3.3 任务管理 API

```
GET    /api/v1/tasks                    - 列出任务 (支持过滤)
POST   /api/v1/tasks                    - 创建任务
POST   /api/v1/tasks/from-natural        - AI 解析自然语言创建任务
POST   /api/v1/tasks/from-wechat        - 微信消息创建任务
GET    /api/v1/tasks/{id}               - 获取任务详情
PATCH  /api/v1/tasks/{id}               - 更新任务
DELETE /api/v1/tasks/{id}               - 删除任务
POST   /api/v1/tasks/{id}/complete      - 完成任务
POST   /api/v1/tasks/{id}/cancel        - 取消任务
POST   /api/v1/tasks/{id}/notify        - 推送任务通知
PATCH  /api/v1/tasks/{id}/roles         - 更新任务角色标签
```

**Query 参数** (GET /tasks):
- `role_id`: UUID - 按角色过滤
- `status`: 任务状态过滤
- `assignee`: string - 按负责人过滤
- `due_before`: ISO date - 截止日期早于
- `due_after`: ISO date - 截止日期晚于
- `page`, `page_size`: 分页

#### 1.3.4 AI 能力 API

```
POST   /api/v1/ai/parse                 - 解析自然语言输入
POST   /api/v1/ai/summarize             - 生成任务摘要
POST   /api/v1/ai/recommend-priority    - 推荐优先级
POST   /api/v1/ai/detect-conflicts      - 检测跨角色冲突
POST   /api/v1/ai/daily-summary         - 生成每日摘要
GET    /api/v1/ai/providers             - 列出可用 AI Provider
POST   /api/v1/ai/providers/test        - 测试 AI Provider 连接
```

**请求示例** (AI Parse):

```http
POST /api/v1/ai/parse
Authorization: Bearer ***
Content-Type: application/json

{
    "text": "下周三前给 API Gateway 提个 PR review 请求，需要张明审批",
    "available_roles": [
        {"id": "uuid1", "name": "Team Lead"},
        {"id": "uuid2", "name": "Developer"}
    ]
}

Response 200
{
    "intent": {
        "action": "review",
        "estimated_hours": 0.5,
        "suggested_priority": 1,
        "required_roles": ["uuid1"],
        "related_tasks": []
    },
    "parsed_title": "Review API Gateway PR",
    "confidence": 0.92
}
```

#### 1.3.5 微信集成 API

```
GET    /api/v1/wechat/webhook           - 微信服务器验证回调 (GET)
POST   /api/v1/wechat/webhook           - 接收微信消息 (POST)
POST   /api/v1/wechat/push              - 手动推送消息到微信
GET    /api/v1/wechat/status            - 微信连接状态
POST   /api/v1/wechat/push-test         - 发送测试消息
```

#### 1.3.6 规划 API

```
GET    /api/v1/roles/{id}/plans/{date}           - 获取某日规划
POST   /api/v1/roles/{id}/plans/generate          - 生成每日规划
POST   /api/v1/roles/{id}/plans/{date}/reschedule - 重新规划
PATCH  /api/v1/roles/{id}/plans/{date}/slots/{slot_id} - 更新时间块
POST   /api/v1/roles/{id}/plans/{date}/commit     - 确认并发布规划
GET    /api/v1/roles/{id}/plans/{date}/feasibility - 评估计划可行性
```

#### 1.3.7 集成 API

```
GET    /api/v1/integrations                      - 列出已配置集成
POST   /api/v1/integrations/{name}/connect       - 连接外部系统
POST   /api/v1/integrations/{name}/sync          - 触发同步
GET    /api/v1/integrations/{name}/status        - 同步状态
DELETE /api/v1/integrations/{name}               - 断开集成
```

### 1.4 项目目录结构

```
python-agent/
├── pyproject.toml                          # 项目配置
├── uv.lock                                # 依赖锁定 (使用 uv)
├── config.json                            # 配置文件
│
├── src/
│   ├── __init__.py
│   ├── main.py                            # FastAPI 入口
│   ├── app.py                             # FastAPI 应用工厂
│   │
│   ├── api/                               # API 层
│   │   ├── __init__.py
│   │   ├── router.py                      # 路由汇总
│   │   ├── deps.py                        # 依赖注入 (Auth, DB)
│   │   └── handlers/                      # API Handler
│   │       ├── __init__.py
│   │       ├── auth.py                    # 认证 API
│   │       ├── roles.py                   # 角色 API
│   │       ├── tasks.py                   # 任务 API
│   │       ├── ai.py                      # AI 能力 API
│   │       ├── wechat.py                  # 微信 API
│   │       ├── plans.py                   # 规划 API
│   │       └── integrations.py            # 集成 API
│   │
│   ├── domain/                            # 领域模型
│   │   ├── __init__.py
│   │   ├── role.py                        # Role 实体
│   │   ├── task.py                        # Task 实体
│   │   ├── user.py                        # User 实体
│   │   ├── plan.py                        # Plan/Slot 实体
│   │   ├── intent.py                      # TaskIntent 实体
│   │   └── notification.py                 # Notification 实体
│   │
│   ├── service/                           # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── role_service.py
│   │   ├── task_service.py
│   │   ├── user_service.py
│   │   ├── ai_brain.py                    # AI Brain 服务
│   │   ├── task_planner.py                # 任务规划器
│   │   ├── wechat_service.py
│   │   ├── notification_service.py
│   │   └── sync_service.py
│   │
│   ├── storage/                           # 存储层
│   │   ├── __init__.py
│   │   ├── database.py                    # SQLite/SQLAlchemy
│   │   ├── redis_client.py               # Redis 客户端
│   │   ├── repositories/                  # Repository 模式
│   │   │   ├── __init__.py
│   │   │   ├── base.py                    # BaseRepository
│   │   │   ├── role_repo.py
│   │   │   ├── task_repo.py
│   │   │   ├── user_repo.py
│   │   │   ├── plan_repo.py
│   │   │   └── notification_repo.py
│   │   └── migrations/
│   │       └── 001_initial.sql
│   │
│   ├── llm/                              # LLM 集成
│   │   ├── __init__.py
│   │   ├── base.py                        # LLMProvider 抽象
│   │   ├── registry.py                    # Provider 注册表
│   │   ├── minimax.py                     # MiniMax 实现
│   │   ├── openai.py                      # OpenAI 实现
│   │   ├── anthropic.py                   # Anthropic 实现
│   │   └── ollama.py                      # Ollama (本地)
│   │
│   ├── integrations/                      # 外部系统集成
│   │   ├── __init__.py
│   │   ├── base.py                        # IntegrationAdapter 抽象
│   │   ├── wechat/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py                 # 微信适配器
│   │   │   ├── webhook.py                 # 消息接收
│   │   │   ├── pusher.py                  # 消息推送
│   │   │   ├── crypto.py                  # 微信签名验证
│   │   │   └── models.py                  # 微信消息模型
│   │   ├── linear.py
│   │   ├── github.py
│   │   └── feishu.py
│   │
│   ├── utils/                             # 工具
│   │   ├── __init__.py
│   │   ├── config.py                      # 配置加载
│   │   ├── security.py                    # JWT / 密码工具
│   │   └── datetime.py                    # 日期时间工具
│   │
│   └── worker/                            # 后台任务
│       ├── __init__.py
│       ├── cron.py                        # 定时任务调度
│       ├── notifications.py               # 通知发送队列
│       └── daily_planning.py              # 每日规划生成
│
├── static/                                # Web 静态文件 (PWA)
│   ├── index.html
│   ├── manifest.json
│   └── assets/
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                       # pytest 配置
│   ├── api_tests/
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_roles.py
│   │   ├── test_tasks.py
│   │   └── test_ai.py
│   ├── unit_tests/
│   │   ├── __init__.py
│   │   ├── test_role_service.py
│   │   ├── test_task_service.py
│   │   └── test_ai_brain.py
│   └── integration_tests/
│       ├── __init__.py
│       └── test_wechat_integration.py
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.dev.yml
│
└── docs/
    └── architecture.md
```

### 1.5 核心数据模型 (Pydantic)

```python
# src/domain/role.py
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional

class Role(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
    color: str = "#6366f1"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

# src/domain/task.py
class TaskStatus(str, Enum):
    INBOX = "inbox"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"

class TaskSource(str, Enum):
    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    WECHAT_MESSAGE = "wechat_message"
    EXTERNAL = "external"

class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.INBOX
    priority: int = Field(default=2, ge=0, le=3)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    assignee: Optional[str] = None
    source: TaskSource = TaskSource.MANUAL
    ai_summary: Optional[str] = None
    intent_data: Optional[dict] = None
    external_id: Optional[str] = None
    external_source: Optional[str] = None
    role_tags: list[UUID] = Field(default_factory=list)

    class Config:
        from_attributes = True

# src/domain/intent.py
class TaskIntent(BaseModel):
    action: str                              # feature/bug/refactor/docs/review
    estimated_hours: Optional[float] = None
    required_roles: list[UUID] = Field(default_factory=list)
    suggested_priority: int = 2
    related_tasks: list[UUID] = Field(default_factory=list)
    confidence: float = 1.0

# src/domain/plan.py
class SlotStatus(str, Enum):
    FREE = "free"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"

class EnergyLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class DailyPlan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    role_id: UUID
    date: date
    total_hours: float = 0
    estimated_completion: float = 0
    is_committed: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    slots: list[TimeSlot] = Field(default_factory=list)

class TimeSlot(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    plan_id: UUID
    start_time: time
    end_time: time
    task_id: Optional[UUID] = None
    task_snapshot: Optional[str] = None
    status: SlotStatus = SlotStatus.FREE
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    notes: str = ""
    sort_order: int = 0
```

### 1.6 错误处理规范

#### 1.6.1 API 错误响应格式

所有 API 错误统一返回以下 JSON 格式：

```json
{
    "detail": "错误描述信息",
    "code": "ERROR_CODE"  // 可选，业务错误码
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| detail | string | 人类可读的错误描述 |
| code | string (可选) | 机器可读的错误码，用于业务逻辑分支判断 |

#### 1.6.2 HTTP 状态码约定

| HTTP 状态码 | 含义 | 适用场景 |
|-------------|------|----------|
| 400 | 参数错误 | 请求参数校验失败、请求体格式错误 |
| 401 | 未认证 | 缺少 Token 或 Token 无效/过期 |
| 403 | 无权限 | Token 有效但无权限执行此操作 |
| 404 | 不存在 | 请求的资源（任务/角色/计划等）不存在 |
| 500 | 服务错误 | 意料之外的服务器内部错误 |

#### 1.6.3 Service 层异常统一封装

```python
# src/core/exceptions.py

class AppError(Exception):
    """应用层所有异常的基类"""
    def __init__(self, code: str, message: str, cause: Exception = None):
        self.code = code
        self.message = message
        self.cause = cause
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class ValidationError(AppError):
    """参数校验失败"""
    def __init__(self, message: str, cause: Exception = None):
        super().__init__("VALIDATION_ERROR", message, cause)


class AuthenticationError(AppError):
    """认证失败"""
    def __init__(self, message: str = "Authentication required", cause: Exception = None):
        super().__init__("AUTH_ERROR", message, cause)


class AuthorizationError(AppError):
    """权限不足"""
    def __init__(self, message: str = "Permission denied", cause: Exception = None):
        super().__init__("FORBIDDEN", message, cause)


class NotFoundError(AppError):
    """资源不存在"""
    def __init__(self, resource: str, identifier: str, cause: Exception = None):
        super().__init__("NOT_FOUND", f"{resource} '{identifier}' not found", cause)


class ConflictError(AppError):
    """数据冲突（如重复创建）"""
    def __init__(self, message: str, cause: Exception = None):
        super().__init__("CONFLICT", message, cause)
```

#### 1.6.4 各层错误传播规则

**传播链路**: `Service → API Handler → HTTP Response`

```
Service Layer                          API Handler Layer
───────────────────────────────────    ─────────────────────────────────
raise AppError (业务异常)        →      @app.exception_handler(AppError)
                                          ↓
                                     映射到 HTTP 状态码
                                     400: ValidationError
                                     401: AuthenticationError
                                     403: AuthorizationError
                                     404: NotFoundError
                                     500: 其他 AppError
                                          ↓
                                     返回 {"detail": ..., "code": ...}
```

**规则**:
1. Service 层只抛出 `AppError` 及其子类，不直接抛出 HTTP 异常
2. Service 层异常需携带足够的上下文信息用于日志记录，但不含 HTTP 状态码
3. API Handler 层统一捕获 `AppError`，按类型映射为对应 HTTP 状态码
4. 非 `AppError` 异常（如 `ValueError`、`KeyError`）在 API 层统一捕获，映射为 500 并记录完整堆栈

---

## 二、模块分解

### 2.1 模块依赖关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Handler Layer                        │
│   (auth, roles, tasks, ai, wechat, plans, integrations)         │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Service Layer                             │
│  (role_service, task_service, ai_brain, task_planner,           │
│   wechat_service, notification_service, sync_service)            │
│                        + mcp_client.py                           │
└─────────────────────────────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  LLM Layer      │     │  Repository     │     │  Integration    │
│                 │     │  Layer          │     │  Layer          │
│  (minimax,      │     │                 │     │                 │
│   openai,       │     │  (role_repo,    │     │  (wechat,       │
│   anthropic)    │     │   task_repo,    │     │   linear,       │
│                 │     │   user_repo,    │     │   github,       │
│  MCP Client     │     │   plan_repo)    │     │   feishu)       │
│  (stdio to      │     │                 │     │                 │
│   OpenViking)   │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Storage Layer                             │
│         (SQLite/SQLAlchemy)  +  (Redis)  +  (File Store)       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责与接口约定

#### 2.2.1 LLM Layer

| 模块 | 职责 | 关键接口 |
|------|------|----------|
| `llm.base` | Provider 抽象基类 | `async complete()`, `async embed()` |
| `llm.registry` | Provider 注册与获取 | `get_provider(name)`, `list_providers()` |
| `llm.minimax` | MiniMax Provider | 实现 LLMProvider |
| `llm.openai` | OpenAI Provider | 实现 LLMProvider |
| `llm.anthropic` | Anthropic Provider | 实现 LLMProvider |

**接口契约**:

```python
# llm/base.py
from abc import ABC, abstractmethod
from typing import Protocol

class LLMProvider(Protocol):
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """同步补全，返回文本"""
        ...

    async def embed(self, text: str) -> list[float]:
        """文本向量化"""
        ...

    @property
    def name(self) -> str:
        """Provider 名称"""
        ...

    @property
    def supports streaming(self) -> bool:
        """是否支持流式输出"""
        ...
```

#### 2.2.2 Repository Layer

| 模块 | 职责 | 关键接口 |
|------|------|----------|
| `repositories.base` | BaseRepository 基类 | `get()`, `create()`, `update()`, `delete()`, `list()` |
| `repositories.role_repo` | 角色仓储 | 继承 BaseRepository |
| `repositories.task_repo` | 任务仓储 | 继承 BaseRepository + 角色过滤查询 |
| `repositories.plan_repo` | 规划仓储 | 继承 BaseRepository |
| `repositories.notification_repo` | 通知仓储 | 继承 BaseRepository |

**接口契约**:

```python
# storage/repositories/base.py
from typing import TypeVar, Generic, Type, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')

class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: str) -> Optional[T]: ...
    async def create(self, data: dict) -> T: ...
    async def update(self, id: str, data: dict) -> Optional[T]: ...
    async def delete(self, id: str) -> bool: ...
    async def list(self, limit: int = 100, offset: int = 0) -> Sequence[T]: ...

# storage/repositories/task_repo.py
class TaskRepository(BaseRepository[Task]):
    async def get_by_role(
        self,
        role_id: UUID,
        status: Optional[TaskStatus] = None
    ) -> Sequence[Task]: ...

    async def get_by_assignee(
        self,
        assignee: str,
        role_id: Optional[UUID] = None
    ) -> Sequence[Task]: ...

    async def get_unfinished_by_role(
        self,
        role_id: UUID,
        before_date: Optional[datetime] = None
    ) -> Sequence[Task]: ...
```

#### 2.2.3 Service Layer

| 模块 | 职责 | 关键接口 |
|------|------|----------|
| `role_service` | 角色业务逻辑 | CRUD + 视角切换 + 统计 |
| `task_service` | 任务业务逻辑 | CRUD + 状态流转 + 角色标签 |
| `ai_brain` | AI 能力聚合 | parse_natural_input(), infer_roles(), recommend_priority() |
| `task_planner` | 每日规划生成 | generate_daily_plan(), auto_reschedule(), evaluate_plan_feasibility() |
| `wechat_service` | 微信消息处理 | receive_message(), push_notification() |
| `notification_service` | 通知发送队列 | enqueue(), process_queue(), send() |
| `sync_service` | 外部系统同步 | sync_external(), push_update() |

**Service 层约束**:
- Service 层不直接操作 HTTP 请求/响应
- Service 层通过 Repository 操作数据库
- Service 层之间通过接口调用，不直接操作对方内部状态

#### 2.2.4 Integration Layer

| 模块 | 职责 | 关键接口 |
|------|------|----------|
| `integrations.base` | 集成适配器基类 | `fetch_tasks()`, `push_update()`, `sync()` |
| `integrations.wechat` | 微信集成 | 消息接收/推送/签名验证 |
| `integrations.linear` | Linear 集成 | Issue 同步 |
| `integrations.github` | GitHub 集成 | Issue/PR 关联 |
| `integrations.feishu` | 飞书集成 | 消息通知 |

### 2.3 开发先后顺序

```
Phase 1: 基础设施
  1. 项目脚手架 (pyproject.toml, 目录结构)
  2. 配置系统 (config.py, config.json)
  3. 数据库层 (SQLite/SQLAlchemy, migrations)
  4. 认证模块 (JWT, user_service)

Phase 2: 核心 CRUD
  5. 角色管理 (role_service, role_repo, roles API)
  6. 任务管理 (task_service, task_repo, tasks API)
  7. Repository 基类 + 单元测试

Phase 3: AI 集成
  8. LLM Provider 抽象 + MiniMax 实现
  9. AI Brain 服务 (parse, summarize, priority)
  10. 自然语言任务创建 API

Phase 4: 微信集成
  11. 微信 Webhook 接收
  12. 微信消息解析 + 任务创建
  13. 微信通知推送

Phase 5: 规划功能
  14. 每日规划数据模型
  15. 任务规划器 (Task Planner)
  16. 规划 API

Phase 6: 完善
  17. Redis 集成 (缓存/队列)
  18. 通知服务
  19. 外部系统集成 (Linear/GitHub)
  20. 前端 PWA
```

---

## 三、开发序列建议

### 第 1 周: 项目启动 + 基础设施

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | 项目脚手架搭建，pyproject.toml 编写 | `pyproject.toml`, 目录结构 |
| Tue | 配置系统实现 (config.py, config.json) | `config.py`, `config.json` 示例 |
| Wed | SQLite + SQLAlchemy 集成 | `database.py`, `migrations/001_initial.sql` |
| Thu | JWT 认证实现 | `security.py`, `user_service.py`, `users` 表 |
| Fri | API 路由骨架 + 依赖注入 | `router.py`, `deps.py`, 骨架测试 |

**验收标准**:
- [ ] `uv sync` 成功安装依赖
- [ ] `uv run fastapi dev src/main.py` 启动无报错
- [ ] `POST /api/v1/auth/token` 返回有效 JWT
- [ ] 单元测试覆盖率 > 60%

### 第 2 周: 角色 + 任务核心 CRUD

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | Role 模型 + RoleRepository | `domain/role.py`, `role_repo.py` |
| Tue | RoleService + Roles API | `role_service.py`, `roles.py` handler |
| Wed | Task 模型 + TaskRepository | `domain/task.py`, `task_repo.py` |
| Thu | TaskService + Tasks API | `task_service.py`, `tasks.py` handler |
| Fri | 状态机 + 角色标签过滤 | `task_service.py` 状态流转逻辑 |

**验收标准**:
- [ ] CRUD API 测试全部通过
- [ ] 角色视角过滤正确 (SQL WHERE role_tags)
- [ ] 任务状态流转 (inbox→todo→in_progress→done) 正确
- [ ] OpenAPI docs 可用

### 第 3 周: AI Brain 集成

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | LLM Provider 抽象 + Registry | `llm/base.py`, `llm/registry.py` |
| Tue | MiniMax Provider 实现 | `llm/minimax.py` |
| Wed | OpenAI/Anthropic Provider | `llm/openai.py`, `llm/anthropic.py` |
| Thu | AI Brain 服务 (parse, summarize) | `ai_brain.py` |
| Fri | AI API 端点 + 测试 | `ai.py` handler, AI 测试 |

**验收标准**:
- [ ] Provider 可通过 registry 切换
- [ ] `POST /api/v1/ai/parse` 返回有效的 TaskIntent
- [ ] MiniMax 调用延迟 < 3s (p95)
- [ ] AI 响应缓存生效 (Redis)

### 第 4 周: 微信集成

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | 微信 Webhook 接收骨架 | `integrations/wechat/webhook.py` |
| Tue | 微信签名验证 + 消息解析 | `integrations/wechat/crypto.py` |
| Wed | 微信消息 → 任务创建流程 | `wechat_service.py` |
| Thu | 微信通知推送 | `integrations/wechat/pusher.py` |
| Fri | 微信端到端测试 | E2E 测试文档 |

**验收标准**:
- [ ] 微信消息 Webhook 签名验证通过
- [ ] 微信发消息 → 任务创建成功
- [ ] 任务状态变更 → 微信通知推送成功
- [ ] 错误处理 (签名失败/消息解析失败)

### 第 5 周: 任务规划

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | DailyPlan + TimeSlot 模型 | `domain/plan.py` |
| Tue | PlanRepository | `plan_repo.py` |
| Wed | Task Planner 生成算法 | `task_planner.py` |
| Thu | 规划 API 端点 | `plans.py` handler |
| Fri | 规划可行性评估 | `evaluate_plan_feasibility()` |

**验收标准**:
- [ ] `POST /api/v1/roles/{id}/plans/generate` 生成有效计划
- [ ] 规划包含精力匹配逻辑
- [ ] 硬截止任务优先安排
- [ ] 规划推送微信消息格式正确

### 第 6 周: 完善 + 集成

| Day | 任务 | 交付物 |
|-----|------|--------|
| Mon | Redis 集成 (缓存 + 队列) | `redis_client.py`, 缓存逻辑 |
| Tue | 通知队列 + Cron 定时任务 | `notifications.py`, `cron.py` |
| Wed | Linear 集成适配器 | `integrations/linear.py` |
| Thu | GitHub 集成适配器 | `integrations/github.py` |
| Fri | 前端 PWA 基础 + 集成测试 | `static/`, PWA 配置 |

**验收标准**:
- [ ] AI 响应缓存命中率 > 50%
- [ ] 每日早 8:30 定时推送成功
- [ ] Linear 同步延迟 < 5min
- [ ] PWA 可离线访问核心页面

### 3.2 Phase 边界修正

> **评审修正 (2026-05-20)**: 原技术计划将 Channel Adapter 抽象放在 Phase 3.x，不合理。以下是修正后的 Phase 边界。

**Phase 1 明确范围 (MVP，4周)**:
- 角色 CRUD + 任务 CRUD
- 微信消息接收 Webhook（个人测试号）
- AI 意图解析（MiniMax）
- 微信通知推送（基础版）
- Web 端任务列表

**Phase 2 明确范围 (4周)**:
- AI 每日规划（Task Planner）
- AI 角色自动推断
- 定时每日摘要推送
- Redis 缓存 + 队列

**Phase 3 明确范围 (6周)**:
- Linear/GitHub 集成
- PostgreSQL 迁移
- PWA 完善
- **Channel Adapter 抽象**（如需要多端消息接入）

**不做的功能（确认）**:
- 精力曲线/能量等级 — MVP 过于复杂，先用简单优先级
- 冲突检测 — Phase 2 后期按需引入
- 钉钉/Slack 接入 — Phase 3 之后

---

## 四、技术风险

### 4.1 微信接入风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|----------|
| 微信消息签名验证失败 | 高 | 高 | 使用测试公众号验证签名逻辑，参考微信官方 SDK |
| 企业微信需要公司主体 | 中 | 中 | MVP 使用个人微信测试号，正式版申请企业账号 |
| 微信消息 API 调用限制 | 高 | 中 | Redis 限流 + 消息队列缓冲 |
| 消息回调延迟/丢失 | 中 | 中 | 消息持久化到 `wechat_messages` 表，重试机制 |

**个人测试号申请流程**：微信公众平台 → 注册个人测试号 → 获取 appID/appsecret/encodingAESKey → Phase 1 第1天申请

**具体缓解措施**:

```python
# 微信签名验证 (integrations/wechat/crypto.py)
import hashlib
import time
from typing import Optional

class WeChatCrypto:
    def __init__(self, token: str, encoding_aes_key: str, app_id: str):
        self.token = token
        self.encoding_aes_key = encoding_aes_key
        self.app_id = app_id

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        echostr: Optional[str] = None
    ) -> bool:
        """验证微信服务器签名"""
        # 1. 将 token、timestamp、nonce 按字典序排序
        # 2. 拼接字符串进行 SHA1 哈希
        # 3. 与 signature 比对
        ...

    def decrypt_message(self, encrypt_str: str) -> str:
        """解密微信消息（安全模式）"""
        ...
```

### 4.2 AI 解析质量风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|----------|
| LLM 解析结果不稳定 | 中 | 高 | 提供手动修正机制，允许用户覆盖 AI 判断 |
| 角色推断错误 | 中 | 中 | AI 推断作为建议，用户确认后生效 |
| 响应超时 | 中 | 中 | 异步处理 + 10s 超时 + 降级规则 |
| Token 成本超支 | 低 | 中 | Redis 缓存 + daily token 用量监控 |

**降级策略**:

```python
# ai_brain.py - AI 解析降级
class AIBrain:
    async def parse_natural_input(self, text: str) -> TaskIntent:
        # 尝试 AI 解析
        try:
            return await self._ai_parse(text)
        except TimeoutError:
            # 超时降级：使用规则解析
            return self._rule_based_parse(text)
        except Exception as e:
            # 其他错误降级：返回默认意图
            return TaskIntent(
                action="unknown",
                confidence=0.0,
                suggested_priority=2
            )

    def _rule_based_parse(self, text: str) -> TaskIntent:
        """基于规则的简单解析作为降级"""
        # 检测截止日期
        due_date = self._extract_date(text)
        # 检测优先级关键词
        priority = self._extract_priority(text)
        # 检测动作
        action = self._extract_action(text)
        return TaskIntent(
            action=action or "general",
            estimated_hours=None,
            suggested_priority=priority or 2,
            confidence=0.3  # 低置信度，提示用户确认
        )
```

### 4.3 性能瓶颈预估

| 场景 | 瓶颈点 | 预估 QPS | 缓解方案 |
|------|--------|----------|----------|
| 任务列表查询 | SQLite 并发写入 | ~50 QPS | PostgreSQL 迁移 (Phase 3) |
| AI 解析 | MiniMax API 限流 | ~20 QPS | Redis 缓存 + 队列缓冲 |
| 微信消息推送 | 企业微信 API 限制 | ~1000/分钟 | Redis 限流 + 异步队列 |
| 每日规划生成 | AI 调用延迟 | ~5s/次 | 异步生成 + 预生成 |

**SQLite → PostgreSQL 迁移时机**:
- 当并发用户 > 1 (多设备同步)
- 当 AI 缓存命中率 > 70% 但响应仍慢
- 当 Redis 队列堆积 > 1000 条

---

## 五、环境准备清单

### 5.1 依赖安装

**Python 版本**: `>= 3.11`

**核心依赖** (`pyproject.toml`):

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
    "redis>=5.0.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.2.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "httpx>=0.27.0",
    "python-multipart>=0.0.9",
    "aiocron>=1.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.3.0",
    "mypy>=1.9.0",
]

[project.optional-dependencies]
ai = [
    "openai>=1.12.0",
    "anthropic>=0.18.0",
]
```

**Node.js 依赖** (前端 PWA):

```json
{
  "devDependencies": {
    "vite": "^5.2.0",
    "typescript": "^5.4.0",
    "vue": "^3.4.0",
    "@vitejs/plugin-vue": "^5.0.0",
    "vite-plugin-pwa": "^0.19.0",
    "pinia": "^2.1.0",
    "tailwindcss": "^3.4.0"
  }
}
```

**MVP 单测覆盖率目标 >70%（整体，核心模块 P0 100%）**

### 5.2 API Key 申请

| 服务 | Key 类型 | 申请地址 | 用途 |
|------|----------|----------|------|
| MiniMax | API Key | https://platform.minimax.chat/ | 默认 AI Provider |
| OpenAI | API Key | https://platform.openai.com/ | 备选 AI Provider |
| Anthropic | API Key | https://console.anthropic.com/ | 备选 AI Provider |
| 企业微信 | CorpID + AgentID + Secret | https://work.weixin.qq.com/ | 微信消息推送 |
| 个人微信测试号 | appID + appsecret + encodingAESKey | https://mp.weixin.qq.com/ | MVP 测试阶段微信消息推送 |
| Linear | API Key | https://linear.app/settings/api | Linear 集成 |
| GitHub | Personal Access Token | https://github.com/settings/tokens | GitHub 集成 |

### 5.3 配置文件准备

**开发环境** `config.json`:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8765,
    "debug": true,
    "cors_origins": ["http://localhost:5173"]
  },
  "database": {
    "url": "sqlite+aiosqlite:///./data/agent.db",
    "echo": false
  },
  "redis": {
    "url": "redis://localhost:6379/0",
    "enabled": true
  },
  "auth": {
    "jwt_secret": "dev-secret-change-in-production",
    "jwt_algorithm": "HS256",
    "token_expire_hours": 720
  },
  "ai": {
    "default_provider": "minimax",
    "providers": {
      "minimax": {
        "api_key": "${MINIMAX_API_KEY}",
        "model": "MiniMax-M2.7",
        "base_url": "https://api.minimax.chat/v1"
      },
      "openai": {
        "api_key": "${OPENAI_API_KEY}",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1"
      }
    },
    "cache_ttl_seconds": 3600
  },
  "wechat": {
    "enabled": true,
    "token": "${WECHAT_TOKEN}",
    "encoding_aes_key": "${WECHAT_AES_KEY}",
    "corp_id": "${WECHAT_CORP_ID}",
    "agent_id": "${WECHAT_AGENT_ID}",
    "corp_secret": "${WECHAT_CORP_SECRET}"
  },
  "integrations": {
    "linear": {
      "enabled": false,
      "api_key": "${LINEAR_API_KEY}"
    },
    "github": {
      "enabled": false,
      "token": "${GITHUB_TOKEN}"
    }
  }
}
```

### 5.4 开发环境启动

```bash
# 1. 克隆项目
git clone <repo>
cd python-agent

# 2. 安装 uv (如果未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 安装依赖
uv sync

# 4. 创建数据目录
mkdir -p data

# 5. 配置环境变量或 config.json
cp config.json.example config.json
# 编辑 config.json 填入 API Keys

# 6. 运行数据库迁移
uv run python -m src.storage.migrations.run

# 7. 启动开发服务器
uv run fastapi dev src/main.py

# 8. 访问 API 文档
open http://localhost:8765/docs
```

### 5.5 Docker 环境 (可选)

```bash
# 使用 Docker Compose 启动完整环境
cd docker
docker-compose -f docker-compose.yml up -d

# 启动开发模式 (带热重载)
cd docker
docker-compose -f docker-compose.dev.yml up -d
```

---

## 六、附录

### 6.1 技术选型理由汇总

| 选型 | 决策 | 理由 |
|------|------|------|
| FastAPI | ✅ 采用 | 异步原生 + Pydantic v2 + 自动 OpenAPI |
| SQLAlchemy 2.0 | ✅ 采用 | asyncio 支持 + 静态类型 + 成熟稳定 |
| SQLite MVP | ✅ 采用 | 零部署 + 单文件 + 开发效率 |
| PostgreSQL 正式版 | ⏸ 规划 | 并发 + JSON/向量支持 |
| Redis | ✅ 采用 | AI 缓存 + 任务队列 + 会话存储 |
| MiniMax | ✅ 默认 | 成本低 + 支持 Agent + 国内合规 |
| Vue 3 + TS | ✅ 采用 | 高开发效率 + 微信浏览器兼容 |
| PWA | ✅ 采用 | 离线支持 + 微信内嵌兼容 |
| 企业微信 | ✅ 正式 | 消息推送稳定 + 官方支持 |

### 6.2 开放问题 (待讨论)

1. **微信方案**: 企业微信(需公司主体) vs 个人测试号? 当前决策: MVP 用测试号，正式版申请企业账号
2. **多用户支持**: MVP 单用户，未来是否需要多用户? 当前决策: MVP 单用户，架构预留多用户扩展
3. **向量数据库**: RAG 能力是否真的需要? 当前决策: 暂时不需要，Phase 3 按需引入
4. **开源协议**: 当前决策: 待定 (建议 Apache 2.0)
