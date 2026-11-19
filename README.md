# hsr-operations

在 Windows 上用 AI 操作《崩坏：星穹铁道》的技能、输入辅助和性能复测方法。覆盖寻宝、分层导航、多帧观察、批量移动、贼灵回溯、每日实训、历战余响和探索谜题。

已验证的组合是：**原生 CUA 窗口取图 → 正常 ControlStatus 就绪检查 → 游戏前台核验 → 既有文件桥输入 → 新画面验收**。需要带本地 Windows CUA 和控制状态工具的 agent 宿主；本仓库本身不提供模型、CUA 服务或无人值守游戏客户端。

## 安装和最小验收

```powershell
git clone https://github.com/godriccao/hsr-operations.git
cd hsr-operations
python tools/check_release.py
python -m unittest discover -s tests -v
python tools/benchmark.py examples/timing.synthetic.jsonl
```

以上命令只离线检查文件和合成计时，不取桌面画面、不发游戏输入。Python 3.10+，只用标准库。Windows 输入辅助另需 AutoHotkey v2；地图配准可选安装 `python -m pip install -r requirements-map.txt`。

将 `skills/hsr-operations` 整个目录原样复制到宿主支持的技能目录，或使用宿主的本地技能注册方式。保留 `references` 和 `agents`。工具位于仓库根目录的 `tools`，与技能一起保留本 checkout。验证复制可用 `git diff --no-index -- skills/hsr-operations <复制后的目录>`，无输出、退出码 0 表示一致。不要将示例路径当成本机配置。

现场部署按 [Windows 安装与接管](docs/INSTALL.md) 完成；首次仅做一次可逆菜单切换与短移。发布版的可配置工具已做离线验证，新的 checkout 仍需现场验收。

## 实测范围

2026-11-19 的项目记录中，16 段 CUA 首帧至桥首派中位 **4.868 秒**，10/16 低于 5 秒，0/16 低于 3 秒。海原市另一批 36 段为 **7.671 秒**，104 条派发均配到回执。低于 3 秒仍是目标，不能保证其他环境达到。两批尚未逐帧剔除不可操作时段；菜单和走位的分组及完整计时定义见 [性能复测](docs/PERFORMANCE.md)。

流程与已跑通范围见 [操作方法](docs/OPERATIONS.md)、[实测证据](docs/EVIDENCE.md) 和 [地点路段](docs/BATCHES.md)。技能入口为 [SKILL.md](skills/hsr-operations/SKILL.md)。回执证明输入链路，落点、机关成功和奖励分别由游戏画面确认。

## 权限和许可证

用户接管优先，一个操作者发键鼠；使用当前宿主允许的正常输入与授权入口。宿主只允许 CUA 时，不能调用 AHK 或 shell 代替受限制输入。工具无注入、内存读取或提权绕过功能。见 [控制协议](docs/BRIDGE.md)。

本仓库作者可授权的文档、技能和项目工具按 [MIT](LICENSE) 发布。游戏及第三方攻略、运行时、库与服务的权利和许可证分别见 [第三方说明](THIRD_PARTY.md)。
