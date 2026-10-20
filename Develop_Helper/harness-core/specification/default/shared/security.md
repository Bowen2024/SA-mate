# 安全红线（default）

> 来源：原 dev-standards/backend-dev.md 密钥两条 + backend-plugin.md 外部服务调用安全两节消双写 + V8 security `.env.example` 条。全部规范件与 agent 共同引用的最高优先级规范，违反即停；shared 件 = 换规范集仍适用的栈无关纪律。

## 密钥红线

- 真实 API Key、Token、JWT Secret、数据库密码等敏感值**只能写入** `.env`、`.env.local` 或用户明确指定的本地 secret 配置文件
- `docs/**`、`.sdd/**`、测试报告、完成报告、BUG 日志、经验记录、README、任务 JSON、接口契约中一律只能写字段名和配置状态，禁止写真实值、部分值或 `sk-...` / `Bearer ...` 片段
- `.env` 文件加入 `.gitignore`
- 项目必须提供 `.env.example`：列出全部必需配置项的字段名 + 占位值 + 一行用途注释，与 `.env` 实际键一一对应；新增配置项时同步更新
  - 验收：按 `.env.example` 逐项填入真实值即可启动项目；`.env` 中不存在 `.env.example` 没有的键

## 外部服务调用红线

### 百炼平台禁止使用官方 SDK

调用阿里云百炼（LLM/Embedding/Reranker）时，**禁止使用 `dashscope` 等官方 SDK**。必须使用 `httpx` / `aiohttp` 直接发送 HTTP 请求，手动构造请求体、解析响应 JSON。

**原因：**
- SDK 封装层隐藏真实响应结构，易导致假设错误（如 `response.output.usage` vs 实际 `response.usage`）
- 直接 HTTP 调用结构透明、可控、Mock 简单
- 测试无需依赖 SDK 安装和版本兼容性

**正确做法示例：**
```python
import httpx

async def call_llm(prompt: str) -> str:
    async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]}
        )
        data = response.json()
        # 直接操作 dict，结构透明
        return data["choices"][0]["message"]["content"]
```

**错误做法：**
```python
# 禁止使用 SDK
import dashscope
response = dashscope.Generation.call(...)
```

### 禁止继承环境变量

外部服务 HTTP 客户端永远不得继承本机环境变量。所有 `httpx.Client` / `httpx.AsyncClient` 必须显式设置 `trust_env=False`，避免本机代理、证书、系统环境变量污染百炼/OpenAI/第三方 API 调用。禁止使用裸 `httpx.get()` / `httpx.post()` 快捷调用。

## 相关指针

- 配置读取与进程环境（禁 `os.environ`，pycore `ConfigManager` 绑定）：单一权威源在 `backend/tech-stack.md` 硬性禁止
- 测试库物理隔离：单一权威源在 `backend/workflow.md` 测试纪律
