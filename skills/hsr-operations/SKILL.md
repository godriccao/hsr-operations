---
name: hsr-operations
description: 在 Windows 上操作《崩坏：星穹铁道》，完成每日实训、历战余响、清图寻宝、探索谜题、成就盘点与规划，校准移动、鼠标和输入桥，并核实进度与奖励。
---

# 崩坏：星穹铁道操作

先确认任务范围、唯一操作者与输入归属。用户使用电脑或状态为 user 时停止键鼠；恢复后取新画面，重新校准窗口、朝向与断点。工具和历史成功记录不扩大当前宿主权限。

原生 CUA 负责窗口取图，随后按正常 Windows MCP ControlStatus 检查，仅在 ready、游戏前台、用户交还控制且当前宿主允许文件桥时派发。原生 CUA 与 Windows MCP 截图不是同一个计时与控制路径。读 [Windows 控制](references/windows-control.md)。

按任务读：

- 每日活跃度、批量提取和每周历战余响：[每日与每周](references/daily-weekly.md)。
- 成就逐页盘点与解锁规划：[成就盘点与规划](references/achievement-audit.md)。
- 寻宝、楼层、地标、多帧观察与批量移动：[清图与导航](references/exploration.md)。
- 迷钟：[操作](references/dream-ticker.md)、[帮派迷钟实测](references/gang-clock.md)。
- 黄金替罪羊、预言算碑、矩阵、ROTATE、JUMP、贼灵回溯：[探索谜题](references/exploration-puzzles.md)。

发布仓库的完整 checkout 根目录记为 REPO_ROOT，由操作者配置。安装后从本机登记的 REPO_ROOT 读 `docs/INSTALL.md`、`docs/BRIDGE.md`、`docs/PERFORMANCE.md`；这些不依赖作者电脑路径。使用工具前核实可用依赖与本机配置。未知 REPO_ROOT 时先定位 checkout；只有技能目录时先补齐发布仓库的 tools 和 docs。

维护源为公开仓库 https://github.com/godriccao/hsr-operations 。通用操作经验、技能参考和工具修改直接在该仓库完成；维护流程见根目录 `CONTRIBUTING.md`。本地账号进度、日志、截图、凭据和会话配置留在操作者本机。通过链接安装的技能仍只维护这一份源。

每批先核地图、楼层、位置、镜头和目标。已知通路或同阶段谜题可合批；在转角、变层、卡住、交互或结算时看画面，异常立即停余下动作。回执、实际位移、关卡成功、对白收尾与奖励到账分别验收。

性能从第一张可操作画面到实际首派计时，多帧观察保留同一时间起点，菜单与走位分组。低于 3 秒是优化目标。固定坐标、动作时长和历史账号完成状态只用于匹配前置条件后的复测。当前进度和奖励由本地记录维护，公开实例不是新账号状态。
