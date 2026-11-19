# 合成样例

`timing.synthetic.jsonl` 是公开计时 schema 的最小样例。所有时间以同一观察批的相对毫秒给出，第一条菜单 4000ms，多帧走位 18000ms，另有不可操作与未知状态各一条。有效两段的中位数为 11000ms，三条派发均有对应 ACK。它们用于检验计算规则，不代表历史实机分布。

`session.synthetic.jsonl` 是 codex_timing.py 已知格式的合成工具事件。两帧后两条重复 W 命令，首帧至首派 18000ms，末帧至首派 3000ms，两条派发均配到新 ACK。没有聊天、真实路径、账号或截图。

实际归一化记录须将 `data_kind` 设为 `observed`，`operable` 按现场确认填 true / false / null。`target_hit` 未验收时填 null。可选增加地图、窗口尺寸、工具版本、模型和强制等待分类等不含个人信息的环境说明。实际样本留本地，不覆盖合成文件。
