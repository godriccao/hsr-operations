# 性能复测

## 历史实机证据（项目记录原文汇总，2026-11-19）

| 样本 | 起止口径 | 样本量 | 中位秒数 | 已知限制 |
|---|---|---:|---:|---|
| CUA 基线 | 首张观察帧返回至桥首派 | 16 | 4.868 | 10/16 <5s，0/16 <3s，尚未逐帧排除不可操作片段 |
| 同批末帧口径 | 末帧返回至桥首派 | 16 | 4.484 | 12/16 <5s，16 段全部配到 ACK |
| 同批菜单 | 末帧返回至桥首派 | 9 | 4.290 | 7/9 <5s |
| 同批首条 WASD | 末帧返回至桥首派 | 7 | 4.841 | 5/7 <5s |
| 海原市三段纯走位 | 画面返回至首派 | 3 | 5.910 | 三段为 5.268、6.792、5.910 秒；首查一次 ready 约 4–5ms |
| 海原市市长府邸实战 | 首帧返回至首派 | 36 | 7.671 | 0/36 <3s，104 条派发均配回执；混合走位、交互和菜单 |

16 段内两段补图，从末帧计为 4.018、4.204 秒，从第一帧计为 24.880、18.279 秒。补图不能重置决策时钟。海原市 36 段窗中两只目标实收合计 80 星琼，两个检查点间约 12 分钟；该窗含查路、走位、战斗和对白，约 400 星琼/小时只适用于该样本。

首帧组与末帧菜单/走位组不是同一个起点，不能直接比较提速。首帧的类别细分未留足可公开的逐段证据，不能由末帧分组反推。低于 3 秒仍是目标，环境、模型调度、地图判断、窗口恢复和工具版本均可改变结果。

## 截图与控制占用

本机已核 Windows MCP 0.8.8 源码：工具中间件仅 ControlStatus 免申请控制租约，其他调用结束走 `end_call`，最后一次调用后保留约 15 秒。区域/整屏及注释设置只改变捕图。实测区域约 182ms、整屏无注释约 227ms，两者从 ready 转 ai，区域截图约 15.158 秒后 ready。截图快不等于输入能立即开始。

原生 CUA 窗口截图后，正常 ControlStatus 仍可就绪，再由原桥输入，项目已有连续菜单与走位实测。不能把 Windows MCP 截图与 CUA 截图混到一个样本。版本升级后重新核源码和正常表现；保持控制归属与用户优先，不修改租约实现。

## OBS 连续取图

2026-11-19，OBS 33.0.0 经 WGC 和虚拟摄像机向本地 FFmpeg 供图，常驻 reader 输出 960×540 JPEG。龙骸古城 2F 实机测得首次取帧调用 567 毫秒，随后一次常驻取帧调用 43 毫秒。另一次常驻读取并返回 JPEG 为 62 毫秒，门徽和寻宝标记均可辨。这些是单次取帧样本。同一轮用首张 OBS 图成功走到预定栏杆，从宿主确认图到桥首派仍为 9.384 秒。比较 OBS 与 CUA 时，在同一环境、模型及可比路段分别统计取图和首派耗时。

## 可比计时协议

同一 sender 单调时钟记录：第一张可操作帧返回、补图返回、控制就绪、动作准备好、命令调用启动、实际首派、各 ACK。公开 schema 以相对毫秒存储，避免账号和绝对时间；原始工具日志可本地用 codex_timing.py 分析。

- `first_frame_ms`：本观察批第一张已现场确认可操作画面的返回时点。若只能从工具返回时点起算，明确 capture-return 口径；画面生成至宿主返回的时间不在其中。
- `frames_ms`：同一观察批所有帧，连续补图保留第一帧；补图间另有输入或切界面时重新定义实际批次。
- `dispatch_ms`：命令真正提交给桥的时点，不能替换为 shell 启动时间。
- `events`：顺序配对的 dispatch/ack，包含 command 和 t_ms。ACK 匹配不等于位移命中。
- `category`：menu、movement、interaction 分组；类别不能只由按键推断，WASD 也可能操作菜单。
- `operable`：true / false / null；null 表示未确认。不可操作或未知样本单列，不悄悄进入净指标。
- `target_hit`：true / false / null；命中率分母为已执行且有明确目标的批次，未验收数另列。

等待强制加载、动画、自动战斗和用户接管分别记录，整批墙钟保留。有效输入按实际裁限后的时长估算，ACK 不能证明全部按住时间。空闲占比 = 空闲秒数 / (空闲秒数 + 有效操作秒数)，两个时段必须互斥，不把模型等待移出墙钟。缺标签时仅报告原始合计。每种可比类别积累至少十段，再比较中位数、首段命中率和返工，不只挑快段。

## 离线运行

```powershell
python tools/benchmark.py examples/timing.synthetic.jsonl
python -m unittest discover -s tests -v
python tools/codex_timing.py examples/session.synthetic.jsonl --capture CuaScreenshot --bridge-only
python tools/codex_timing.py examples/session.synthetic.jsonl --capture ObsScreenshot --bridge-only
```

合成样例专门测试首帧、多帧、分组、未知状态、重复命令和回执异常；其数值不是 16 段实机原始值。benchmark 遇不匹配 ACK 会把该段列为无效而不计入中位数。请在本地单独保存实际样本，按 schema 记录后复算。

本地原始 Codex 日志可用 `python tools/codex_timing.py <本地日志> --since <带时区时间> --until <带时区时间> --capture CuaScreenshot --bridge-only`。OBS 同口径用 `--capture ObsScreenshot`。每批用同一来源取帧，以便比较。解析器只识别项目已知的独立 CUA 和 OBS 调用形态；其他宿主/新调用写法需适配，零样本不代表零延迟。它不判断画面是否可操作，也不自动分组。始终复核 `observation_frames`、`first_frame_to_first_bridge_dispatch_ms`、`bridge_dispatches`、`bridge_acknowledgements`。原始日志不可上传公开仓库。

需从独立 OBS 取帧调用自动统计时，可在支持 `nodeRepl.emitImage` 的本地 REPL 先导入模块并在单独调用中建立 `reader`（`const reader = openObsFrames()`）和可重复赋值的 `frame`（`let frame`），再用下面的调用。日志按宿主工具完成时间计。

```javascript
frame=await reader.nextFrame(); nodeRepl.write(Date.now()); await nodeRepl.emitImage({bytes:frame.bytes,mimeType:"image/jpeg"});
```
