# 后端接口设计规范（default）

> 来源：原 dev-standards/backend-layers.md 层 4（API 路由层）+ 易错点 API 2 行 + backend-dev 错误码表 + 认证行为约束 + V8 backend/api-design 与 shared/naming 条款（分层名按本集 repositories/ 改造，产物名对齐本集 docs 体系）。

## 接口定义即代码

- 接口文档 = FastAPI 自动生成的 Swagger（`/docs`）；路由函数 + Pydantic 请求/响应模型写在代码里，代码即文档。`docs/tech-spec.md` §二是已确认的接口契约，接口实现必须与其一致
- 每个路由必须声明完整的 Pydantic 请求模型与响应模型（含字段名、类型、必填性、默认值），禁止只写接口名+一句话描述或用裸 dict 作注解
  - 正例：`POST /api/tasks` 路由声明 `TaskCreate`（`title: str`、`priority: Literal["low","mid","high"]`）与 `TaskOut` 响应模型，`/docs` 自动展示完整结构
  - 反例：路由参数用 `data: dict`、返回不注解——Swagger 里看不到字段结构
- curl 验证命令的请求体/预期返回必须与 `/docs` 及 `docs/tech-spec.md` §二中展示的模型结构一致
  - 验收：任取一个接口，`/docs` 中可见完整请求/响应结构，前端能仅凭契约写出 Mock，后端实现与契约一致并通过 curl 对照

## 统一响应信封

- 普通 JSON 接口（含错误）统一使用 PyCore 信封：`success`、`data`、`error`、`error_code`、`message`；由 `pycore.api.responses` 的 `success_response` / `error_response` / `paginated_response` 实现，不另设 `code` 字段。SSE、文件等非 JSON 响应按技术方案的实际传输契约验证。
- HTTP 状态码与 `success` / `error_code` 必须一致；错误函数返回 `(响应模型, HTTP 状态码)`，路由必须应用该状态码，不能只返回模型导致错误变成 HTTP 200。
- 前端解析只认信封结构，禁止对裸 JSON / 裸数组做特判
  - 业务字段示例：成功 `{"success": true, "data": {"id": 1}, "error": null, "error_code": null, "message": "ok"}`；失败 `{"success": false, "data": null, "error": "参数验证失败", "error_code": "VALIDATION_ERROR", "message": null}`。实际 PyCore 还提供 `timestamp`、`request_id`、`metadata`；分页响应另含 `pagination`（page、page_size、total_items、total_pages、has_next、has_prev）。
  - 反例：成功直接返回 `{"id": 1}`，失败直接返回 FastAPI 默认 422 结构——前端被迫写两套解析逻辑

## 错误码规范

| 错误码 | HTTP | 含义 |
|--------|------|------|
| `VALIDATION_ERROR` | 400 | 参数验证失败 |
| `UNAUTHORIZED` | 401 | 未认证 |
| `FORBIDDEN` | 403 | 无权限 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 资源冲突 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

## 响应模型速查

```python
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pycore.api import success_response, error_response, paginated_response
return success_response(data=user_data, message="User created")
resp, status = error_response(error="Not found", error_code="NOT_FOUND", status_code=404)
return JSONResponse(status_code=status, content=jsonable_encoder(resp))
return paginated_response(data=items, page=1, page_size=20, total_items=100)
```

## 路由速查

```python
from pycore.api import APIRouter
from pycore.api.routes import Pagination, handle_errors
from fastapi import Depends

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/{user_id}")
@handle_errors
async def get_user(user_id: int):
    ...
```

**注册路由**：
```python
server.include_router(router)          # APIServer 自动处理
app.include_router(router.router)      # 直接用 FastAPI app 时需要 .router
```

## 参数来源速查

| 来源 | 装饰器 |
|------|--------|
| URL 路径 | 自动 / `Path()` |
| 查询字符串 | `Query()` |
| 请求头 | `Header()` |
| Cookie | `Cookie()` |
| 请求体 | Pydantic Model |
| 依赖注入 | `Depends()` |

> `Field()` 仅用于 Pydantic 模型内部，路由参数必须用以上 FastAPI 装饰器。

## 路由文件位置与命名

- 路由文件一律放 `backend/src/api/routes/` 下；`api/` 直属层只放 `deps.py` 等公共依赖文件，路由文件不裸放（这是分层链 `…→api/deps.py→api/routes/` 的落盘形态）
- 一个资源一个路由文件；文件名 = 资源名复数 snake_case（`routes/users.py`、`routes/documents.py`，snake_case 基线见 `shared/naming.md`，资源复数与落位规则归本条款）；`routes/__init__.py` 汇出各 router，`main.py` 的 `include_router` 只从 routes 导入
- URL 前缀与文件名同源：`/api/<资源复数>`，URL 里的资源词与文件名用同一个复数词
- **资源词从 PRD 功能中的名词实体推导**：读取本任务关联的 PRD 功能章节，圈出被创建/操作的业务对象（名词实体），一个名词实体一个资源词；`docs/tech-spec.md` §二接口清单、URL 前缀与路由文件名共用同一个词，任何一侧不得从功能措辞另抓同义词
  - 正例：PRD 功能「会话问答」→ 名词实体 = 会话 → 资源词 `conversations` → `/api/conversations` + `api/routes/conversations.py`
  - 反例：同一 PRD 功能，技术方案 §二写 `chat`、路由文件叫 `conversations`——两边各自从措辞抓词、无共同推导起点，属本条款违规（Tester 单列不一致项）
- **动作不进资源词**：动词性操作（transfer / login / upload / search 等）不单独成资源，归入其操作的资源作子操作（如 `POST /api/conversations/{id}/transfer` 是 conversations 资源上的动作路由，不产生 transfer 资源、不产生 `routes/transfer.py`）
- 判定：grep `backend/src/api/` 直属层无含 `APIRouter` 的文件；`routes/` 下文件名与技术方案 §二接口清单的资源一一对应；每个路由文件只承载一个资源；接口清单与路由文件两边的资源词并集逐个回指 PRD 名词实体，回指不到的即自造词，违规
- 消费方：产品设计阶段（技术方案 §二接口清单按 PRD 推导资源词，不另抓同义词）+ Developer（路由文件名与 URL 同源推导）+ Tester（审契约与路由路径/资源词一致性，不一致本身即 FAIL 项）

## 认证与依赖注入

- 认证/权限默认使用路由级依赖，不使用全局认证中间件：PyCore/FastAPI 项目的认证、鉴权、权限控制默认在 `backend/src/api/deps.py` 中实现为依赖函数（如 `get_current_user`、`require_admin`），受保护路由通过 `Depends(...)` 显式启用。CORS、日志、请求上下文、异常处理可以是全局中间件；认证/权限不得默认注册全局 AuthMiddleware，也不得要求 `app.user_middleware` 中出现认证中间件，除非任务明确要求“所有接口默认拦截 + 公开接口 allowlist”
- 认证依赖中的数据库会话必须从项目运行时代码导入（如 `from src.db.session import get_db`），禁止直接使用 `pycore.integrations.db.session.get_db` 连接模板默认数据库

## 外部服务规格写死

- 外部服务（LLM 如百炼、第三方 HTTP 服务）的请求/响应字段在 `docs/tech-spec.md` §二确认，URL、模型名等环境配置在 §七确认，并落为 config 常量与 Pydantic 模型
- 上述规格任何变更 = 技术方案偏航，停下报告等拍板
  - 验收：代码中外部服务的 URL/模型名/字段均来自 config 常量与契约文档，无运行时猜测拼接

## 易错点汇总（API 层）

| 层 | 错误 | 正确 |
|----|------|------|
| API | `return error_response(...)` | 解包为 `resp, status`，用 `JSONResponse(status_code=status, content=jsonable_encoder(resp))` 返回 |
| API | `app.include_router(router)` | `app.include_router(router.router)`（PyCore APIRouter） |
