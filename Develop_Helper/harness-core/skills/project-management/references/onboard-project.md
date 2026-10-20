# 纳管已有项目

目标是保留已有成果并接入当前 SDD，不套用新建项目的空白设计流程。继承已确认信息，仅补齐缺口。

## 确定来源与接入方式

- 确定来源绝对路径、项目名称/ID、类型（web/mobile/api/cli）、规范名称或 null，以及已存在的 Git origin。规范不匹配时不默认选 default；不读取真实 .env 来判断技术栈。
- 用 read 读取注册表（路径：`<harness_root>/project-registry.json`），定向检查目标目录（路径：`<harness_root>/Projects_Repo/<project-id>/`）。已登记则核对身份并进入修改/继续，不重复纳管。
- 来源在框架外：默认建议复制一份到目标路径、保留原目录，由用户选择；已有明确复制授权直接执行。只给远程 URL 时，明确本地目标后按已有授权克隆到框架外临时目录，再复制纳管；不能将克隆误说成创建远程仓库或推送。
- 来源已经位于目标目录但未登记：使用 register 模式，仅补元信息，不复制业务代码。框架只纳管 Projects_Repo 的直接子目录，不支持将任意外部路径直接登记。
- 用户要求移动原项目时，先完成复制和核对，再按用户明确授权移走原目录；不默认删除原件。若存在旧 .sdd 信息，先核对来源、ID、状态和证据，保留原件；脚本拒绝覆盖。需要迁移时，在副本中将旧 .sdd 原样移到已告知的历史归档目录（路径：`<active_project_path>/docs/import-history/<实际时间>/sdd/`），再 register；不把旧 PASS 自动当成当前验收。

## 执行与核对

在 harness_root 使用可用 Python 执行 [项目脚本](../../../../scripts/sdd_project.py)。参数替换为实际值；规范参数必须二选一。

```bash
python3 scripts/sdd_project.py onboard "<project-id>" --name "<名称>" --type api --from-path "<来源绝对路径>" --mode copy --no-specification
```

原目录就是目标目录时改用 `--mode register`。选规范集时将 `--no-specification` 替换为 `--specification "<规范集名称>"`。脚本继承来源根仓库的 origin；仅在用户明确要配置且来源无 origin 时传 `--repo-url`，冲突时先由用户确定，不自动覆盖。

脚本复制时排除 node_modules、.venv、venv、__pycache__、常见检查缓存和 .DS_Store；保留代码、文档、普通独立 Git 仓库及其他文件，不读取或展示密钥。符号链接保留为链接、不追读；复制后的链接可能仍指向原位置，应按实际使用核对。Git worktree 的 .git 文件不适合直接复制，先在明确位置准备独立 clone。纳管不复制默认 PyCore，不改原有 AGENTS.md/README 或平台规则。

检查退出结果、目标目录、项目元信息（路径：`<active_project_path>/.sdd/project.json`）及注册记录一致；核对来源业务文件仍在、目标入口可定位。失败时报告实际残留和未完成步骤，先核对再恢复，不反复覆盖重跑。保留原有规则但检查其与 Harness 的冲突，只处理必要冲突并说明文件改动。

## 接上当前阶段

只读已有 README、需求、接口方案、界面与任务的相关部分。能沿用的成果继续沿用；设计缺口补到 PRD/tech-spec 的对应章节，缺少当前格式不等于全部重写。将沿用依据和待核对项记入工作日志（路径：`<active_project_path>/.sdd/work-log.md`），不伪造 Confirmed 或验收通过。

由 [修改与继续项目](modify-project.md) 判断进入需求、方案、界面、规划还是修复。技术栈无关的纳管不安装依赖或运行服务；只有下一步任务需要且在授权范围内才执行。
