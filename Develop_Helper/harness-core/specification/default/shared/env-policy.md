# 环境与端口策略（default）

> 来源：原 dev-standards/frontend.md §5 策略条款 + backend-dev 端口/CORS 硬性禁止条消双写（前后端合并为单一权威表）+ V8 env-policy 存储落点权威表（落点按本集 Projects_Repo 体系改造）。本件是 .env、端口、CORS、存储落点的唯一权威源。

## .env 策略

- 前后端**各自独立** `.env`，禁止混用同一文件
- 前端变量**必须 `VITE_` 前缀**，否则 Vite 不会注入到客户端
- 开发环境 `VITE_API_BASE_URL=/api`（相对路径），后端地址只允许出现在 `VITE_BACKEND_PROXY_TARGET` 与 Vite 代理配置中
- **禁止**：开发环境把 `VITE_API_BASE_URL` 写成完整后端 URL（如 `http://localhost:8003/api`），这会触发浏览器 CORS 预检，导致本地调试失败
- `.env` 加入 `.gitignore`；`.env.example` 的要求见 `shared/security.md` 密钥红线

## 端口约定（唯一权威表）

| 用途 | 前端 | 后端 |
|---|---|---|
| Agent 自动开发 / Tester 自动验证 | 5199 | 8099 |
| 用户门禁验收 | 5175 | 8003 |

- 不得默认占用常见端口 `8000` / `5173`
- 前端代码永远使用相对路径 `/api` / `/ws`，不得硬编码后端端口；后端目标端口只允许出现在 `vite.config.ts` 的代理配置或启动命令中
- Vite 代理必须支持通过环境变量切换后端目标，默认指向 Agent 端口 `8099`；用户门禁时通过 `VITE_BACKEND_PROXY_TARGET=http://localhost:8003` 临时切换
- 后端 CORS 必须同时允许 `http://localhost:5199`、`http://127.0.0.1:5199`、`http://localhost:5175`、`http://127.0.0.1:5175`，避免 Agent 验证和用户门禁验收端口不一致导致假失败
- 修改 `vite.config.ts` 或 `.env` 后必须重启 Vite 开发服务器才能生效

（vite.config.ts 代理代码示例与启动命令见 `frontend/api-client.md`。）

## 存储落点（唯一权威表）

- SQLite 数据库文件一律 `backend/data/<project-id>.db`（config 默认值写相对路径 `data/<project-id>.db`，从 `backend/` 目录解析；project-id 取项目注册表中的项目 ID）；文件名不另行起名，`app.db` / `db.sqlite3` 等自造名禁止
- 上传与持久化目录一律 `backend/data/uploads/`；PRD 指明专门数据域时用 `backend/data/<PRD 命名>/`，不在 `data/` 之外另造平级目录（如项目根裸建 `uploads/`）
- config 键引用上述路径作默认值（如 `DATABASE_PATH=data/<project-id>.db`、`UPLOAD_DIR=data/uploads`），不自造其他落点
- SQLite 路径为相对路径时，生成连接 URL 前必须解析为绝对路径并自动创建父目录（实现要求见 `backend/tech-stack.md` 硬性禁止）
- 判定：config 默认值与真实落盘的 db 文件、持久化目录均能回指本表；`data/` 之外出现 .db 文件或上传目录即违规
- 消费方：产品设计阶段（`docs/tech-spec.md` §七 config 键默认值照此落）+ Developer（config 默认值照此落）+ Tester（真实落盘验证照此查）
