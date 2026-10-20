# 后端错误处理规范（default）

> 来源：原 dev-standards/backend-layers.md 层 2「错误处理链路」+ backend-dev「异常使用速查」+ V8 error-handling 四类错误分类审核条（异常体系按本集 pycore 改造）。

## 错误处理链路

```
Repository: IntegrityError → ValueError（数据冲突）
Service:    ValueError / 业务异常（产生或透传）
路由:       @handle_errors 捕获 ValueError→400, PermissionError→403
全兜底:     ErrorHandlerMiddleware → 500
```

## 异常使用速查

| 场景 | 使用方式 |
|------|---------|
| Plugin 业务错误 | `return self.fail("msg")` |
| 系统级错误 | `raise ConfigurationError("msg")` |
| 路由层返回 | `error_response("msg", "CODE", 404)` |

## 四类错误分类审核（强制）

- 新增错误处理必须先过分类审核：报错信息先归类（参数校验 / 业务规则 / 外部依赖 / 系统内部），归类决定处理路径（Pydantic 校验转统一响应 / 抛业务异常带错误码 / 重试+降级 / 500+日志留痕）；归类不清时停下问，**禁止遇到报错用 try/except 吞掉**
  - 正例：学生提交作业已截止 → 业务规则类，Service 抛 `ValueError("作业已截止，无法提交")`，经 `@handle_errors` 转成 409/400 统一信封，返回中文可读信息
  - 反例：LLM 接口超时被 `except Exception` 吞掉返回 `{"code": 200}`——外部依赖类错误被伪装成成功，日志里也找不到痕迹
  - 验收：review 时任挑一个异常处理点，能说出它的分类及对应处理路径；全局搜索禁止出现无日志的裸 `except Exception: pass`

## 规则

- 错误响应统一走 `@handle_errors` / 全局异常处理 + `pycore.api.responses` 统一信封，禁止各路由拼写错误 JSON（见 api-design.md）
- 面向前端的错误信息可读（中文场景给用户能懂的话），日志里保留技术细节；两者分离
- 测试或联调失败时先自行修复再汇报，禁止直接把错误甩给用户（流程见 workflow.md「每个功能完成后」）
