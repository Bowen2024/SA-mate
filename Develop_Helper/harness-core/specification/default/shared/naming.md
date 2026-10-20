# 命名规范（default）

本件是前后端命名的单一权威源；前端示例使用 React + TypeScript，后端命名按本集工程约定。

## 前端

**规范说明**

- 页面组件：`PascalCase` + `Page` 后缀。
- 通用组件：`PascalCase`，可加功能前缀（如 `App*`）。
- 含 JSX 的组件 / Provider 文件使用 `.tsx`；普通状态逻辑 / Service / 类型文件使用 `camelCase` 文件名与 `.ts`。
- 自定义 Hook 使用 `use` 开头的 `camelCase`；Context / Provider 组件使用 `PascalCase`。
- 环境变量：`VITE_` 前缀大写下划线（如 `VITE_API_BASE_URL`）。

**示例（对照表）**

| 类型     | 规则                    | 示例                          |
|----------|-------------------------|-------------------------------|
| 页面组件 | PascalCase + Page 后缀  | `LoginPage.tsx`, `ItemListPage.tsx` |
| 通用组件 | PascalCase + 功能前缀   | `AppHeader.tsx`, `UserAvatar.tsx`   |
| Hook     | use + camelCase         | `useAuth.ts`, `useItems.ts`          |
| Provider | PascalCase              | `AuthProvider.tsx`                  |
| 状态逻辑 | camelCase               | `authReducer.ts`, `itemReducer.ts`  |
| Service  | camelCase               | `authService.ts`, `itemService.ts`   |
| 类型文件 | camelCase               | `auth.ts`, `item.ts`                 |

## 后端

- 模块/文件：snake_case（`user_service.py`）；数据访问层目录统一 `repositories/`（见 `backend/tech-stack.md`）
- 类：PascalCase（`UserService`）；函数/变量：snake_case
- Pydantic 模型后缀：`*Create` / `*Update`（写操作入参）、`*Read` / `*Response` / `*Public`（读操作出参），密码与内部字段不进 `*Response`（见 `backend/layers.md` 层 1）
- ORM 表名：复数 snake_case（`__tablename__ = "users"`）
- 路由文件与 URL 资源词：一资源一文件、复数 snake_case、`/api/<资源复数>`（推导规则见 `backend/api-design.md`「路由文件位置与命名」）

## 通用

- 数据库字段 / 接口字段：snake_case；接口 DTO 字段以 `docs/tech-spec.md` §二契约为准，前后端同名字段不做驼峰转换
- 分支名：`feat/<功能>`、`fix/<问题>` 小写短横线；commit message 一句话说清本次改动，一个功能一次 commit（git 流程见 `harness-core/skills/git-workflow/`）
- 项目 id：小写英文 + 短横线（如 `kefu-bot`）
