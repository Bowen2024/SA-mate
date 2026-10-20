# SDD V7_2

SDD 是一个多项目开发工作台，支持 Codex、Claude Code 和 Cursor。核心工作规则集中在 `harness-core/`，业务项目位于 `Projects_Repo/<project-id>/`。

## 从哪里开始

在编辑器中打开 Harness 根目录。三个平台入口统一读取 [Router](harness-core/router.md)，先区分技术讨论和项目工作。项目工作进入 [项目管理](harness-core/skills/project-management/SKILL.md)，定位项目后再处理新建、修改或接入请求。

## 新项目的阅读链

```text
平台入口 → Router → 项目管理 → 产品设计入口
  → 确认项目基础信息与规范集 → 脚本创建项目
  → A 需求与验收对齐（按需调用 R 调研）
  → 七层技术方案与体验对齐 → B 界面设计（有界面时）
  → Plan 划分 Feature / 任务
  → Developer 实现 → Tester 验证
```

只读取当前步骤需要的文件。后续修改从已有设计和任务继续，避免每次重跑完整设计流程；具体流程以相应 Skill 为准。

## 核心产物

| 文件 | 内容 |
| --- | --- |
| `docs/PRD.md` | 用户目标、需求范围、业务规则与验收标准；使用 REQ / AC 追踪 |
| `docs/tech-spec.md` | 技术选型、接口与数据、模型、算法、异常、项目结构 |
| `docs/decisions.md` | 有重要体验取舍时保存选项、用户影响、最终选择与确认依据 |
| `.sdd/tasks.json` | Plan 生成的 Feature 分组、需求映射、任务、依赖与执行状态 |
| `docs/ui-style.md` | UI Skill 产出的项目设计风格，供原型、前端开发和视觉验收引用 |
| `docs/prototypes/` | 用户需要时保存界面设计 |

接口契约和实施要点写进技术方案，重点分析每个接口的处理方式怎样影响用户体验；重要选择先讨论并留存依据，Plan 再按需引用相关章节。旧项目保留原编号与任务记录，不强制迁移。交付时将环境、配置与启动说明写入项目 README；按需产物没有内容时不预建空文件。

## 项目与规范集

项目基础信息保存在 `.sdd/project.json`，根 `project-registry.json` 保存项目登记与默认活动项目。`specification` 由用户明确选择：

- `"default"`：使用默认规范集及适配的技术栈。
- 自定义集合名称：使用 `harness-core/specification/` 中对应集合。
- `null`：不加载规范集，以当前项目确认的技术方案为准。

字段缺失表示尚未确定，不能自动当作 `default` 或 `null`。详见 [规范集说明](harness-core/specification/README.md)。新建脚本只在选择 `default` 时复制 PyCore。

## 目录

```text
harness-core/        Skills、角色、流程协议和可选规范集
.codex/             Codex 平台适配
.claude/            Claude Code 平台适配
.cursor/            Cursor 平台适配
scripts/            项目创建和一致性检查
templates/          初始化模板
Projects_Repo/      各项目代码、docs 和 .sdd
project-registry.json
```

平台适配方式见 [平台协议](harness-core/protocols/platform-adapters.md)。开发执行以 [开发循环](harness-core/protocols/development-loop.md) 为准。

## 检查 Harness

在根目录运行 `python3 scripts/check_harness_consistency.py`，检查入口与引用路径、模板 JSON 和任务依赖契约。已明确标注的待建设分支会提示警告；检查通过不代表业务项目已完成开发或验收。
