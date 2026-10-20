# Develop Helper 上游来源与快照

## 来源

| 项目 | 记录 |
| --- | --- |
| 名称 | Develop Helper / SDD V7_2 |
| 本地源仓记录的远端 | `git@github.com:RiaHello/SDD.git` |
| 固定提交 | `ec75f8f113402be73a415282dd274a8e3513f291` |
| 提交日期 | 2026-09-12 |
| 收录方式 | 从该本地 Git 提交导出普通源码快照，保存在 `Develop_Helper/` |
| 收录文件 | 169 个，保留原字节与可执行标记 |
| 来源清单 | [逐文件 SHA-256、大小与模式](../upstream/develop-helper-source.json) |
| 中文指南 | 本地提供的 8 篇阅读指南，单独保存在 `Develop_Helper_reading-guide/`，逐文件摘要也在清单中 |

上游地址来自本地 Git 配置。本次 GitHub API 未能读取该远端，不能确认其当前可访问性；本仓库已收录实际固定快照，阅读这部分不依赖 submodule 下载。

## 为什么采用普通快照

本批先交付能够直接阅读、检查的完整 SDD 来源。普通 clone 即包含源码和指南，已有相对路径保持有效；无需先配置上游凭据或初始化 submodule。

上游快照与 SA-mate 新增说明分开保存。当前没有重写上游 Router、Skill、Agent、Protocol 或模板，也没有把整个框架的入口复制到仓库根目录。

## 与本机工作树的区别

本机工作树有两项未提交变化：`project-registry.json` 和 `learning/technical-terms/index.md`。它们是个人项目登记与学习状态，本次不收录。

发布快照取这两个文件在固定提交中的空白版本。`active_project_id` 为 `null`，项目列表为空；业务项目目录只含 `.gitkeep`。

这份发布快照不等同于本机融合实验所用的全部工作树内容，也不声称匹配原融合层的 `upstream-lock.json`。将来接入融合工具时，需要对准确的发布来源另行核对，不自动更新旧锁文件。

## 校验与更新

来源清单记录每个上游文件的相对路径、SHA-256、字节大小和 Git 模式。校验可以从 `Develop_Helper/` 实际文件重算摘要后与清单逐项比较。

更新时选择明确的新上游提交，审查方法、角色、模板和脚本差异，检查阅读指南是否仍适用，运行对应离线检查，再同步来源清单及受影响的说明。个人项目状态不作为来源升级内容上传。

本次正文中提及的外部产品、工具和历史记录，按其原有语境理解；固定快照不代表其中全部外部接口或命令在所有环境仍然有效。

## 许可状态

本次本地固定快照未发现 LICENSE、COPYING 或 NOTICE 文件。保留来源及作者原有内容，不为上游补造许可，也不为整个组合仓库新增一个覆盖上游的统一许可证。详见 [第三方来源说明](../THIRD_PARTY_NOTICES.md)。

返回 [SDD 阅读入口](sdd-foundation.md) · [SA-mate 首页](../README.md)。
