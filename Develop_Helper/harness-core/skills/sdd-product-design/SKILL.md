---
name: sdd-product-design
description: 仅承接已确定的新建项目意图。先确认项目基础信息与规范并创建项目，再完成需求与验收、按需原型和七层技术方案，交接任务规划与开发。
---

# 新建项目与产品设计

仅在 project-management 已确定用户要创建新项目时进入本 Skill。由本 Skill 统一确认基础信息、检查 ID 与目录占用并创建项目；沿用用户和上游已确认的信息，不重复判断新建意图。

## 一、确认开发规范与项目基础信息

### 先选择开发规范

1. 用户已明确选择规范时直接沿用；尚未选择时，引导选择 `default`、自定义规范集或不使用规范集。创建阶段只核对所选规范集目录是否存在及适用范围，必要时读取规范集说明的相关部分；不预读前后端技术栈全文，详细规范留到技术方案或开发阶段按需读取。
2. 向用户说明 `default` 的适用范围：Web 前端为 React + TypeScript + Vite，路由使用 React Router，状态优先使用 React Hooks / Context；后端为 Python 3.11+ + FastAPI + PyCore。纯 API 项目只使用相关后端/共享规范，不创建前端；CLI 项目不自动套用 Web 服务栈，可选匹配的自定义规范或 null。只有用户认可适用部分时，才选择 `default`。
3. 用户要用其他语言、框架或 APP 技术栈时，可以选择匹配的自定义规范集，也可以明确不使用规范集。只有用户选择使用自定义规范但尚未提供时，才需要准备对应规范；不强制要求创建规范集。
4. 使用规范集时，确认其名称和绝对路径 `harness_root/harness-core/specification/<集名>/`；不使用时，`specification` 记为 JSON 的 `null`，不解析规范路径。用户未回答仍属待确认，不自动选择 `default` 或 `null`。

### 确认项目基础信息

- **项目名称**：面向用户的名称，明确这个项目要做什么。
- **项目 ID**：沿用用户提供的 ID；未提供时，根据项目名称建议一个简短 ID，供用户确认，无须让用户自行编写。ID 是单个目录名，不能包含路径分隔符或使用 `.`、`..`；占用检查按下文执行。
- **项目路径**：根据项目 ID 推导 `harness_root/Projects_Repo/<project-id>/` 的绝对路径并告知用户，无须单独确认框架规则推导的路径。上游已提供路径时核对其与 ID 一致，解析后仍是 `Projects_Repo/` 的直接子目录，且未被占用。将核对后的路径作为 `active_project_path`。
- **远程仓库**：确认用户提供的 Git 仓库地址 `repo_url`；尚未准备好时允许明确暂不配置，记录为 `null`，不把未提供地址理解为要求新建或克隆远程仓库。
- **项目类型**：按已明确用途记录 Web、APP、纯 API 或 CLI，项目元信息分别为 `web`、`mobile`、`api`、`cli`。已有表述明确时不再询问；APP 同时明确目标平台。使用规范集时核对其是否覆盖实际开发方式；api/cli 跳过界面设计，不生成空前端。
- **规范集选型**：沿用前面的规范选择，不单独再问一次。`specification` 为规范集名称或 `null`。`"default"` 表示默认规范集，其他非空名称表示对应的自定义规范集，`null` 表示整个项目不使用规范集。

仅在信息缺失时提问，将规范选择与缺失的基础信息合并成一条简短消息：规范只问一次，名称与项目用途一起问，类型按已有描述提出建议，远程仓库允许暂不配置。尚不知道项目名称或用途时，先补问，不编造名称、ID 或项目需求；不提前进入详细需求访谈。

用户明确要求创建项目，即已授权执行本地创建流程。名称、ID、路径、远程仓库（可明确暂不配置）、类型和规范集齐备，且检查通过后，直接调用脚本，不再要求“确认全部信息并授权创建”。只补问缺失项或确认 AI 新提出的 ID 等未定选项；用户明确要求仅讨论方案时不创建。覆盖已有内容、改变用户指定路径等冲突需另行说明并由用户决定。

### 创建前的占用检查

只做以下两项定向检查，不查其他业务项目文件：

1. 使用 `read` 或等价文件读取工具，直接读取 `<harness_root>/project-registry.json`，核对 `projects` 中是否已登记目标 ID。
2. 直接检查 `<harness_root>/Projects_Repo/<project-id>` 是否存在，确认 `Projects_Repo` 下没有同名文件夹；同名文件或符号链接也视为占用。使用路径存在性检查即可，不读取目录内容，不使用 `Searched files`、递归搜索或 `**` 遍历查找同名目录。

ID 已登记或路径被占用时，说明冲突，不覆盖。注册表无法读取或解析时停止创建；其他记录异常只判断是否影响本次创建，不扩展为全仓核查，不顺手修复无关记录。

创建脚本将项目信息及 `specification` 写入对应项目的 `.sdd/project.json`（路径：`<active_project_path>/.sdd/project.json`）和项目注册表 `project-registry.json`（路径：`<harness_root>/project-registry.json`）。字段类型为字符串或 `null`；用户明确选择空值、不使用规范集时，统一保存为 JSON 的 `null`，不保存空字符串或字符串 `"null"`。字段缺失表示尚未记录选择，不能等同于不使用规范集。

例如，不使用规范集时，该字段保存为（此示例仅展示该字段）：

```json
{
  "specification": null
}
```

后续 `docs/tech-spec.md` 和 `.sdd/tasks.json` 的 `specification` 继承项目记录，明确保留 `null`，不省略或替换为 `default`。

## 二、调用脚本创建项目

在 `harness_root` 中执行 [项目管理脚本](../../../scripts/sdd_project.py)。将示例中的 `python3` 替换为已核对的可用解释器，替换项目 ID、名称和规范集名称；APP 使用 `--type mobile`，纯 API 使用 `--type api`，命令行使用 `--type cli`；`unknown` 仅供旧数据兼容，不替代选型。

使用规范集：

```bash
python3 scripts/sdd_project.py new "<project-id>" --name "<项目名称>" --type web --specification "<规范集名称>"
```

不使用规范集：

```bash
python3 scripts/sdd_project.py new "<project-id>" --name "<项目名称>" --type web --no-specification
```

两种规范参数必须且只能提供一种。用户提供远程仓库时，追加 `--repo-url "<仓库地址>"`；暂不配置时省略该参数。脚本仅配置本地 Git 的 `origin`，不会创建远程仓库或推送。

脚本创建项目目录、`.sdd/` 元信息及状态（路径：`<active_project_path>/.sdd/`）、`docs/`（路径：`<active_project_path>/docs/`）、轻量入口 `AGENTS.md`（路径：`<active_project_path>/AGENTS.md`）和项目说明 `README.md`（路径：`<active_project_path>/README.md`），登记项目并设为活动项目。只有选择 `default` 时复制 PyCore；自定义规范或 `null` 不复制默认运行时，后续按已确认的技术方案开发。

创建后检查脚本成功退出，实际目录与 `active_project_path` 一致，项目元信息和注册记录中的 ID、名称、类型、远程仓库及 `specification` 与确认结果一致。配置了远程仓库时，还要核对实际 `origin`，不能只看登记的 URL。

创建失败时说明已完成和未完成的步骤；若已有部分文件或登记，先核对再修复，不重复运行 `new` 覆盖。检查通过后才进入产品设计。

## 三、进入产品设计流程

项目已创建并通过检查后，读取 [phase-A.md](phase-A.md)，明确需求与验收。方向需要比较或用户要求调研时，才读取 [phase-R.md](phase-R.md)，调研后回到 A。继续当前项目时不重复创建。

主链为 A 对齐需求（按需调用 R 调研）→ [七层技术方案](../solution-design/SKILL.md) 对齐接口、数据、模型、算法、异常与目录 → [阶段 B](phase-B.md) 界面风格与按需原型 → Plan 划分 Feature 与任务。模糊需求先逐步澄清，核心流程及影响体验的关键取舍明确后才进入 B；纯 API / CLI 项目跳过 B。技术取舍只回写受影响需求；只加载当前步骤，不预读后续文件。

## 全局规则

- **产物路径**：每个阶段在产出文件名后用括号注明路径。执行时将 `<active_project_path>` 替换为目标项目绝对路径，将 `<harness_root>` 替换为 SDD 根目录绝对路径；有文件名占位符时替换为实际标识，不按占位符原文创建目录或文件。交付及派发时给出实际绝对路径；任务清单的 `source_files` / `context_files.path` 保留项目相对路径，Markdown 链接仍相对于链接所在文件解析。模板引用与规范路径继续遵守各自规则。
- **规范继承**：以 `.sdd/project.json` 的 `specification` 为准。字符串只加载所选集的相关规范；`null` 时全流程不加载规范集，任务 `rules_files=[]`，不回退 `default`，不要求补建规范。缺失选择时只补问该项。
- **产物职责**：`docs/PRD.md`（路径：`<active_project_path>/docs/PRD.md`）保存需求和验收，`docs/tech-spec.md`（路径：`<active_project_path>/docs/tech-spec.md`）保存七层方案；有重要体验取舍时，`docs/decisions.md`（路径：`<active_project_path>/docs/decisions.md`）保存选项、选择理由及确认依据。Plan 将 Feature 分组、任务和执行状态放入 `.sdd/tasks.json`（路径：`<active_project_path>/.sdd/tasks.json`）；设计界面时由 UI Skill 产出 `docs/ui-style.md`（路径：`<active_project_path>/docs/ui-style.md`），原型按需存入 `docs/prototypes/`（路径：`<active_project_path>/docs/prototypes/`）。不预建空文档或重复维护同一内容。
- **确认与恢复**：PRD、技术方案各在完成时整体确认一次；随后阶段 B 将风格文档与原型合并确认，已确认需求不整份重问。用文档头部的 `status: Draft/Confirmed` 记录，只有用户已明确认可才写 `Confirmed`；修改影响范围或契约时，受影响文档恢复 `Draft`。已有确认和执行授权直接沿用，沉默不算确认。
- **阅读与追踪**：新 PRD 使用 `REQ-001` / `AC-001` 追踪需求与验收，技术方案使用 `API-001` 关联这些编号；方案确认后，Planner 才生成 `F-001` Feature 分组与 `T-001` 任务。旧项目沿用原 ID，不强制迁移。下游按任务读取相关章节，不另建逐 Feature Spec/Plan。

## 完成与交接

技术方案及本轮需要的阶段 B 完成后，按 [开发循环](../../protocols/development-loop.md) 进入 Planner → Developer → Tester。说明当前产物、下一步和真正阻塞项；每次完成请求列出改动文件及验证结果。
