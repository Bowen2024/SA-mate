# 使用与接入

更新日期：2026-11-03。需求、方案、UI 的角色规则、MCP 服务、共享基础、必要模板与隔离测试已发布。以下从仓库根目录执行，使用 Python 3.11 或以上；保留 Git 克隆产生的相对软链布局。

## 1. 读取角色

| 目标 | 角色主文档 |
| --- | --- |
| 澄清需求、保存需求或 PRD | [requirements.md](../fusion-runtime/workflows/requirements/requirements.md) |
| 讨论工程方案 | [solution-design.md](../fusion-runtime/workflows/Solution%20Designer/solution-design.md) |
| 制作独立 UI 演示 | [ui-design.md](../fusion-runtime/workflows/UI/ui-design.md) |

在实际 Agent 环境中显式要求读取相应主文档；Agent 再按引用读取方法和文件约定。仅工具连接成功不能证明角色规则已经读取。

## 2. 在未配置的发布副本运行离线测试

```sh
python3 -B -m unittest discover -s fusion-runtime/tests
```

测试在临时项目进行。部分发布完整性检查要求源码树尚未生成 `config/local.json` 或迁移备份，因此在配置前运行本命令；已有安装可在干净克隆中复跑，不删除已有本机配置来迁就检查。

测试覆盖文件工具、保存冲突、历史、UI 候选及恢复、进程隔离和 stdio 调用。不要求真实客户端或模型，准确结果见[发布验证](independent-roles-publication.md)。

## 3. 生成本机配置并核对来源

三个服务共用 `fusion-runtime/workflows/requirements/config/local.json`。该文件不入版本跟踪。下例默认在用户目录下使用 `sa-mate-projects` 作为业务父目录，可按实际情况修改 `projects`；业务父目录应与本仓库、上游及其他 Git 仓库分开。

```sh
python3 -B - <<'PYCONFIG'
from pathlib import Path
import json
root = Path.cwd().resolve()
assert (root / 'fusion-runtime/workflows/requirements').is_dir(), '请从 SA-mate 仓库根目录执行'
projects = Path.home() / 'sa-mate-projects'
projects.mkdir(exist_ok=True)
foundation = root / 'fusion-runtime/workflows/requirements'
config = {'schema_version': 1, 'upstream_root': str(root / 'Develop_Helper'),
          'projects_root': str(projects.resolve()), 'project_directories': {}}
target = foundation / 'config/local.json'
with target.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
print(target)
PYCONFIG
```

配置已存在时命令停止，不覆盖。若后续检查失败，核对该文件和目录后修正配置，不刷新来源锁绕过检查。

当前 `project_path` 是项目完整目录，但项目仍须为 `projects_root` 的直接子目录。例如父目录为 `sa-mate-projects`，项目可以是其下一层 `项目A`。切换项目只更换每次调用的路径，不逐项目注册服务。

生成配置后核对安装：

```sh
python3 -B fusion-runtime/workflows/requirements/file_tools/check_foundation.py check --foundation fusion-runtime/workflows/requirements
```

发布锁对应仓库固定上游快照，与开发机旧锁的差异已定向核对：两份个人项目登记／学习状态未发布，方法正文保持一致。无需重新计算锁。

## 4. 连接 MCP

将下面各命令中的仓库位置替换为本机克隆的绝对路径，配置在支持 stdio MCP 的 Agent 客户端中。进程从标准输入读取请求、向标准输出返回结果，因此手工运行后等待输入属于正常状态。

```sh
python3 -B /absolute/SA-mate/fusion-runtime/workflows/requirements/cursor_mcp.py --foundation /absolute/SA-mate/fusion-runtime/workflows/requirements
python3 -B '/absolute/SA-mate/fusion-runtime/workflows/Solution Designer/mcp_server.py' --foundation /absolute/SA-mate/fusion-runtime/workflows/requirements
python3 -B /absolute/SA-mate/fusion-runtime/workflows/UI/mcp_server.py --foundation /absolute/SA-mate/fusion-runtime/workflows/requirements
```

三条命令对应三个独立服务。默认只读；按所需能力在对应命令追加以下开关：

| 服务 | 开关 | 开放能力 |
| --- | --- | --- |
| 需求 | `--allow-initialize` | 明确请求的项目初始化 |
| 需求 | `--allow-save` | 需求／PRD 保存和项目选择补录 |
| 方案 | `--allow-save` | 满足 PRD 用途确认条件的方案 Draft 保存 |
| UI | `--allow-write` | 候选准备、受控接收和显式恢复 |
| UI | `--import-root /absolute/authorized-source` | 只读外部导入目录，按需要重复指定 |

客户端配置格式分别处理。需求的 `configure_cursor.py`、方案的 `configure_client.py` 提供 Cursor 预览／应用辅助；以各自 `--help` 和预览返回的准确命令为准。其他客户端按原生配置注册，不能直接套用 Cursor JSON。

## 5. 先检查和读取隔离项目

先验证工具发现、项目检查、读取，再按明确请求初始化或保存。每次调用传入本次项目路径；读取引用只用于对应项目。仅讨论无需初始化，结果未知时先读取核对。

方案工程保存仍核对正式 PRD 用途确认。独立环境的受信确认写入入口尚未补齐，不以普通回复、工具启动开关或测试夹具替代。UI 文件接收成功也不代表浏览器、视觉或业务验收通过。

返回[首页](../README.md) · [当前架构](architecture.md) · [角色目录](../fusion-runtime/README.md)
