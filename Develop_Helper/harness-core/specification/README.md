# specification — 规范集库

规范以「规范集」为单位组织，供项目在创建时明确选用。agents / skills 只引用路径，规范内容永不复制进 agent 定义。

## 一级结构

```text
specification/
├── default/          # React + TypeScript + Vite / Python + FastAPI + PyCore
│   ├── frontend/     # tech-stack / api-client / mock / style / acceptance
│   ├── backend/      # tech-stack / workflow / layers / api-design / error-handling / plugin
│   └── shared/       # env-policy / naming / security
└── <自建规范集>/      # 学生可自建，如 my-standards/，结构参照 default（件数可少）
```

default 三组语义：`frontend/`、`backend/` 是栈绑定件（换集即整组替换）；`shared/` 提供本集的共用纪律。自建集可参考这些条款，但执行时不得隐式继承 default。

## 规范集选择机制（四条）

1. **选择**：创建项目时结合用户技术栈确认 `default`、实际存在的自建规范集名称，或明确不用规范集的 JSON `null`；用户未回答不表示选择 default。已有确认直接沿用。
2. **记录**：项目 `.sdd/project.json` 的 `specification` 是唯一权威来源，必须保存字符串或 JSON `null`。缺字段表示尚未确认，不能当作 null 或 default；方案中的声明仅继承，不成为第二来源。
3. **传递**：Planner 从项目元信息继承到 tasks.json；非 null 时，任务 `rules_files` 只列需要的规范，并在生成时写实际路径，如 `specification/default/backend/tech-stack.md`，不用集名占位符。设计文件的章节引用放入 `context_files`。
4. **按需读取**：以项目元信息为准，规范路径相对 `harness_root/harness-core/` 解析，必须位于所选规范集内。null 时整个设计与开发过程不加载规范集，`rules_files=[]`，不回退 default；字段、选择或路径冲突交回主 Agent。自建集放在 `harness-core/specification/<集名>/`，按任务读取所需文件。

项目类型使用 web/mobile/api/cli。纯 API 只选取适用的后端/共享规则，CLI 不隐式继承 Web 服务层；缺少匹配规则时选择自建集或明确 null，不强制生成界面、前端目录或 HTTP 服务。

## 自建规范集

按实际技术栈创建规范集，说明适用范围并按需拆分文件。同一要求只维护一处，给出能验证的标准；不必复制 default 的全部目录或条款。具体接口字段与产品行为由项目方案决定。

## default 规范集索引（正反向：内容 + 谁消费）

| 文件 | 内容 | 消费方 |
|------|------|--------|
| frontend/tech-stack.md | React+TS+Vite+React Router 白名单 / Hooks 与 Context / 目录结构 | Planner（rules_files 分配）/ Developer / Tester |
| frontend/api-client.md | axios 封装 / React 受保护路由 / Vite React 插件与代理配置 / 常见错误对照 | Developer / Tester |
| frontend/mock.md | Mock 集中管理 / 格式对齐 tech-spec §二 / Endpoint DTO 收敛 | Developer（前端任务）/ Tester（Mock 阶段验证） |
| frontend/style.md | 原型参考（有原型时）+ 设计底线 + 交互五态 + 布局易错点 | Developer（写码）/ Tester（样式对齐校验）；原型环节不消费五态条 |
| frontend/acceptance.md | 任务范围与自动验收清单 | Developer / Tester |
| backend/tech-stack.md | Python/FastAPI/pycore 白名单 + 值单一权威源 + Python 环境 + 环境与工具链硬性禁止 + PyCore 核心配置 | Planner / Developer / Tester |
| backend/workflow.md | 任务上下文 + 环境与分层实现 + 真实联调 + 测试纪律 | Planner / Developer / Tester |
| backend/layers.md | 模型层 / 数据访问层 / Service 层规范 + 易错点 | Developer / Tester（分层检查） |
| backend/api-design.md | 接口定义即代码 + 统一信封 + 错误码 + 路由落位与资源词推导 + 认证依赖 | 产品设计阶段（tech-spec §二接口契约）/ Developer / Tester |
| backend/error-handling.md | 错误处理链路 + 异常使用速查 + 四类错误分类审核 | Developer / Tester |
| backend/plugin.md | PyCore Plugin 层（仅 AI Agent 应用） | Developer（Agent 任务）/ Tester |
| shared/env-policy.md | .env 策略 + 端口唯一权威表 + 存储落点唯一权威表 | 前后端全部任务 + 产品设计阶段 |
| shared/naming.md | 前后端命名规范归一 | Developer / Tester |
| shared/security.md | 密钥红线 + 外部服务调用红线（最高优先级，违反即停） | 全部（Planner / Developer / Tester / 产品设计阶段） |
