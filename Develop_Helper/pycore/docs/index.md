# PyCore 文档

PyCore 是一个模块化、异步优先的 Python 后端框架，从 OpenManus 项目提取并泛化而成。

## 文档目录

| 文档 | 描述 |
|------|------|
| [快速入门](getting-started.md) | 安装、配置、第一个应用 |
| [核心模块](core.md) | 配置系统、日志系统、异常体系、基础模型 |
| [插件系统](plugins.md) | 插件基类、注册表、生命周期 |
| [服务层](services.md) | 状态机、服务基类、步骤执行 |
| [执行层](execution.md) | 执行上下文、流程编排 |
| [API 层](api.md) | FastAPI 集成、路由、中间件、响应 |
| [LLM 集成](llm.md) | OpenAI/DeepSeek/Ollama、工具调用、Token 计数 |
| [示例应用](examples.md) | AI Agent 示例、Web API 示例 |

## 框架特性

| 模块 | 功能 | 特点 |
|------|------|------|
| **core** | 配置、日志、异常、基础模型 | 线程安全、类型安全 |
| **plugins** | 插件系统 | 注册表模式、标准化结果 |
| **services** | 服务层 | 状态机、步骤执行 |
| **execution** | 执行层 | 上下文管理、流程编排 |
| **api** | API 层 | FastAPI 集成、标准响应 |
| **integrations** | 外部集成 | LLM 抽象层 |

## 架构概览

```
pycore/
├── core/           # 核心组件（必需）
├── plugins/        # 插件系统
├── services/       # 服务层
├── execution/      # 执行层
├── api/            # API 层（可选）
└── integrations/   # 外部集成（可选）
```

## 设计原则

1. **模块化**：各模块独立，按需导入
2. **异步优先**：所有 I/O 操作使用 async/await
3. **类型安全**：Pydantic 模型 + 类型注解
4. **可扩展**：ABC 基类 + 注册表模式
5. **生产就绪**：日志、错误处理、配置管理

## 快速链接

- [安装指南](getting-started.md#安装)
- [5 分钟教程](getting-started.md#五分钟教程)
- [API 参考](api.md)
- [示例代码](examples.md)
