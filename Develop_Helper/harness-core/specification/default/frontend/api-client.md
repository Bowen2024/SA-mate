# 前端 API 调用与联调（default）

> 来源：原 dev-standards/frontend.md §6/§7/§13 + §5 的 vite.config.ts 代理示例与启动命令。端口 / .env / CORS 策略的权威表在 `shared/env-policy.md`，本件只放实操配置与代码。

## API 调用封装

**规范说明**

- 使用 **单一 axios 实例**（如 `services/api.ts`），统一 `baseURL`、`timeout`。
- 在 **请求拦截器** 中附加 Token（若有）。
- 在 **响应拦截器** 中统一处理 401 等；禁止在每个页面重复写一套错误处理。
- 业务接口方法写在 `services/*.ts` 中，**禁止在组件内直接** `axios.get('/...')`。
- `baseURL` **禁止**硬编码 `http://localhost:8000`，须来自 `import.meta.env`。
- 拦截器在模块层注册一次，不在 React 组件渲染时反复注册；普通 service 模块不能调用 React Hooks。认证处理仅适用于项目确有登录需求时，凭据存储方式按项目技术方案确定。

**示例（`services/api.ts`）**

```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default api
```

---

## React 路由与访问控制

**规范说明**

- 需要页面路由时，在应用入口包裹 `BrowserRouter`，在 `router/index.tsx` 中声明 `Routes` / `Route`。
- 有登录需求时，通过 `RequireAuth` 包裹受保护页面；登录状态来自 React state / Context，登录、退出与凭据失效后同步更新。异步恢复状态时先展示加载反馈，再决定是否跳转。
- 前端控制页面访问体验；接口权限仍由后端校验。无登录需求时不增加认证路由。

**示例（`frontend/src/router/index.tsx`，路径：`<active_project_path>/frontend/src/router/index.tsx`）**

```tsx
import { Navigate, Outlet, Route, Routes } from 'react-router'
import LoginPage from '../pages/LoginPage'
import DashboardPage from '../pages/DashboardPage'

type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

function RequireAuth({ status }: { status: AuthStatus }) {
  if (status === 'loading') return <p role="status">正在恢复登录状态…</p>
  return status === 'authenticated' ? <Outlet /> : <Navigate to="/login" replace />
}

export function AppRoutes({ authStatus }: { authStatus: AuthStatus }) {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth status={authStatus} />}>
        <Route path="/" element={<DashboardPage />} />
      </Route>
    </Routes>
  )
}
```

`authStatus` 由应用的认证 state / Context 传入，不用一次性的存储读取代替可更新状态。上述 Axios 示例以清除本地 token 后整页跳转处理失效；若项目改为站内导航，则同时清理认证 Context。路由用法见 [React Router 官方文档](https://reactrouter.com/start/declarative/routing)。

---

## Vite 代理配置

任何需要对接后端 API 的前端项目，**必须**在 `vite.config.ts` 中配置 `/api` 代理（端口取值见 `shared/env-policy.md` 端口表）。

**示例（`vite.config.ts` 必须配置开发代理）**

```typescript
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8099'
  const wsTarget = backendTarget.replace(/^http/, 'ws')

  return {
    plugins: [react()],
    server: {
      port: 5199,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    }
  }
})
```

**规则**：
- 项目开发依赖包含 `@vitejs/plugin-react`，配置保留 `plugins: [react()]`，见 [Vite 官方插件说明](https://vite.dev/plugins/)。
- WebSocket 路径 `/ws` 必须单独配置 `ws: true` 代理，禁止前端代码直接写 `ws://localhost:<port>`
- 修改 `vite.config.ts` 或 `.env` 后**必须重启 Vite 开发服务器**才能生效
- Agent / Tester 启动前端时默认使用：`cd frontend && npm run dev -- --host 127.0.0.1 --port 5199`
- 给用户门禁验收时使用：`cd frontend && VITE_BACKEND_PROXY_TARGET=http://localhost:8003 npm run dev -- --host 127.0.0.1 --port 5175`

**示例（代码中读取）**

```typescript
const baseURL = import.meta.env.VITE_API_BASE_URL
```

---

## 常见错误对照

**规范说明**

下列为高频错误，编码与 Review 时对照检查（端口与 .env 策略权威表见 `shared/env-policy.md`）。

**示例（错误 → 正确）**

| 错误写法                         | 正确写法                                       |
|----------------------------------|------------------------------------------------|
| `import.meta.env.API_URL`        | `import.meta.env.VITE_API_URL`（必须 `VITE_` 前缀） |
| 前后端共用同一个 `.env`          | 前后端各自独立 `.env`                          |
| 组件内直接 `axios.get(...)`      | 统一经 `services/` 封装调用                    |
| `baseURL` 写死 `localhost:<port>` | 从 `import.meta.env` 读取                      |
| 每页单独处理 401                 | 在 axios 响应拦截器中统一处理                  |
| `.env` 写完整后端 URL 触发 CORS  | `VITE_API_BASE_URL=/api` + Vite 代理配置       |
| 未配 Vite `/api` 代理            | 必配 `server.proxy['/api']` 指向后端端口       |
| WebSocket 直连 `localhost:<port>` | 配置 `/ws` 代理 + 前端用相对路径               |
