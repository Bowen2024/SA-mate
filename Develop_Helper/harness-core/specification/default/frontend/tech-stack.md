# 前端技术栈（default）

本件是 default 前端选型的单一权威源。组件与状态组织参考 [React 官方文档](https://react.dev/learn/managing-state)，工程使用 Vite 的 React TypeScript 模板。

## 总则

**规范说明**

- 视觉取值按已确认的 `docs/ui-style.md`，具体页面布局参考已有原型，功能和交互按 PRD 与任务 AC。未提供原型不阻塞；风格与原型冲突或需要改变已确认范围时交回设计主 Agent。
- 页面结构与信息架构以 PRD 及已有原型为准，**不可凭感觉改页面规范**。
- 技术栈以本项目规范集声明为准：default 集 = **React + TypeScript + Vite + React Router**，状态优先使用 React 内置 Hooks / Context（本集内不接受无确认替换）。

---

## 白名单（固定选型）

**规范说明**

- 框架：React（函数组件 + Hooks）
- 语言：TypeScript
- 构建：Vite，使用 `react-ts` 模板与 `@vitejs/plugin-react`
- 状态：局部状态用 `useState` / `useReducer`；跨组件共享按需使用 Context，不默认增加外部状态库
- 路由：React Router；有路由需求时使用声明式 SPA 模式，示例统一从 `react-router` 导入
- 请求库：Axios（单一实例经 `services/` 封装，见 api-client.md）

- 入口使用 `react-dom/client` 的 `createRoot`；包含 JSX 的文件用 `.tsx`，普通逻辑与类型文件用 `.ts`。
- React、React DOM、Router 与构建工具选择相互兼容的版本，写入项目依赖与锁文件；已有项目按确认的技术方案处理，不因规范变化自动迁移代码。

## 选型变更规则

- 白名单外技术（其他框架 / UI 库 / 状态库）= 技术方案偏航，停下报告等拍板。

---

## 目录结构

**规范说明**

- 页面放 `pages/`，可复用块放 `components/`，接口放 `services/`，共享 Context / Provider / reducer 放 `stores/`，自定义 Hooks 放 `hooks/`，路由放 `router/`，公共类型放 `types/`，工具放 `utils/`；按实际需要创建目录。

**示例（目录树）**

```
frontend/src/
├── main.tsx        # createRoot 挂载入口
├── App.tsx         # 应用根组件
├── components/     # 通用组件（AppHeader.tsx, UserAvatar.tsx）
├── pages/          # 页面级组件（LoginPage.tsx, DashboardPage.tsx）
├── stores/         # 按需共享 Context / Provider / reducer
├── hooks/          # 自定义 Hooks（useAuth.ts 等）
├── services/       # API 调用封装
├── router/         # 路由配置与受保护路由（index.tsx 等）
├── types/          # TypeScript 类型定义
└── utils/          # 工具函数
```
