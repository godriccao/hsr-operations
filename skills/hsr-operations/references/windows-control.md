# Windows 控制

按本机登记的 REPO_ROOT 读 `docs/INSTALL.md` 与 `docs/BRIDGE.md`。公开包只使用后期单槽 `keys|...` / `click|...` 协议；早期 Sequence sender 不属于本包依赖。

原生 CUA 窗口取图后正常查 ControlStatus，仅在 ready、游戏前台、用户交回控制和当前宿主允许此输入通道时执行。user 时立即让出，ai 时等待正常就绪，超时停止。桥无法代查宿主归属，不可脱离操作者守卫无人运行。只允许 CUA 的宿主遵守该限制。

坐标区分 screenshot、screen 与 client。窗口移动、DPI 或分辨率改变后重新校准。帮派迷钟的历史比例只适用于该次记录，不能当全局常数。

每条命令等新增 ACK，回执未知停余下指令，不能覆盖槽或重放整批。ACK 不能证明游戏动作或奖励成功。用户接管、失焦、窗口几何改变后丢弃旧计划，新画面再规划。

AHK 新脚本先普通权限 `/Validate /ErrorStdOut=UTF-8`，通过后才按正常授权现场验收。错误弹窗不点 Continue。控制桥遇状态文件短暂共享冲突会重试写入，持续冲突会退出。短读日志及时关句柄。ACK 缺失时重新取图核实实际位移，处理步骤见 `docs/BRIDGE.md`。

## 胶囊采样辅助与 stdout Error (6)

回溯辅助 `tools/rewind-cue.ahk` 接口、配置、预算与退出码见 BRIDGE。先实见针盘，在当前客户区校准独立胶囊中心，初始必须非青。总预算 12 秒，失焦或窗口几何变化即停，finally/退出回调释放 Space。edges 和退出码不能替代挑战成功及奖励画面。历史 stdout 错误修版改为先释放按键再写独立结果文件；公开版写本地运行目录。

原生 CUA 多帧和 Windows MCP 截图有不同控制开销，计时遵守 `docs/PERFORMANCE.md`，从第一张可操作帧至实际首派，菜单和走位分开。

## 锁屏期间只读画面

需要在锁屏期间观察时，先在解锁状态为 OBS 新建场景集合，添加「窗口采集」，选中 `StarRail.exe`，将采集方法设为 Windows Graphics Capture（WGC）。只采游戏画面，关闭麦克风、桌面音频和应用音频。需要本地程序读取画面时，启动 OBS 虚拟摄像机，以 FFmpeg 的 `-f dshow -i "video=OBS Virtual Camera"` 读取，完成后关闭虚拟摄像机。[OBS 窗口采集](https://obsproject.com/kb/window-capture-sources)

用 `WTSQuerySessionInformationW` 的 `WTSSessionInfoEx` 会话标志确认锁屏及解锁。在锁屏期间间隔抽取数帧，比较像素并观察角色待机动作，排除重复的最后一帧。锁屏期间停发游戏键鼠。解锁后重新取图，确认游戏前台及控制归属，再按正常流程派发。[Windows 会话状态](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)

2026-11-19，Windows 上用 OBS 33.0.0 在龙骸古城 2F 瓦砾阶验证。约 86.5 秒锁屏期间以每秒 4 帧抽样，347 帧的像素哈希均不同，解锁后继续出图。同机普通权限的 OBS「游戏采集」报 `could not open process: StarRail.exe`，切到 WGC 窗口采集后成功。
