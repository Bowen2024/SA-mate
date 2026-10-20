# SDD V7_2 Student Framework

这是从 `SDD_V7` 继续优化出的学生版框架，重点补齐 Codex 适配层。

## 已清理内容

- 已移除示例业务项目 `Projects_Repo/customer_service/`
- 已重置 `project-registry.json`，当前没有 active project
- 已移除 `.env`、`.env.*`、数据库、缓存、虚拟环境、构建产物和本机 MCP 配置
- 已保留 `harness-core/`、`.cursor/`、`.claude/`、`.codex/`、`pycore/`、`templates/`、`scripts/`
- 已补齐 `.codex/commands/`、`.codex/README.md` 和 `harness-core/protocols/codex-subagents.md`

## 学生使用方式

### 方式一：创建新项目

```bash
python3 scripts/sdd_project.py new <project-id> --name "<项目名>" --type web
```

示例：

```bash
python3 scripts/sdd_project.py new customer-service --name "智能客服系统" --type web
```

### 方式二：查看当前项目

```bash
python3 scripts/sdd_project.py current
```

### 方式三：切换项目

```bash
python3 scripts/sdd_project.py list
python3 scripts/sdd_project.py use <project-id>
```

## 安全规则

真实 API Key、Token、Secret、密码只能写入 `.env` / `.env.local` / 用户指定 secret 配置文件；不得写入 `docs/**`、`.sdd/**`、报告、日志、README、JSON 或任何 Markdown 可读产物。
