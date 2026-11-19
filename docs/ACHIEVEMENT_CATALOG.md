# 成就目录的本地增量更新

在仓库根目录运行同一条命令，首次建立目录，后续更新并列出变化。Python 3.10+，仅用标准库。

```text
python tools/achievement_catalog.py
```

命令先读取 Nanoka 正式服 `hsr.live`，再获取同版本中文目录。需要检查变化再写入时加 `--dry-run`。用 `--output` 可指定另一个本地缓存目录。默认使用 Git 忽略的 `runtime/achievement-catalog`。

- `current.json` 为当前完整目录。`versions/<版本>-<原始数据哈希>.json` 留存每次成功的不同版本或同版本修订。文件含来源、语言、版本、采集时间和原始数据 SHA-256。
- 按成就 ID 比对。首次 `added` 是建表时全部 ID。后续 `added`、`removed` 和 `changed` 是相邻快照差异。升级后字段相同的旧 ID 不进入 `changed`，同版修订可据前后 SHA-256 复查。`changed` 列出确实变化的字段，包括标题、条件、分类、显示类型和星琼等。
- 下载及全量校验通过后，先在 stderr 说明差异数量，再原子替换当前快照。stdout 的单条 JSON 报告可重定向留档，`saved` 表示写入成功，`unchanged` 表示同版字节未变，`preview` 表示本次只读。超时、限流、格式异常或替换失败时，已生效的快照保留。出错后查看 stderr，确认原因后再运行。

已保存原始 JSON 时可作为种子。`--input` 必须带 `--version`，来源标为本地输入。需要核验已知规模时可带 `--expect-count`。在线指定的正式版本必须仍在来源清单；以前的本地版本可用单独输出目录打开。

```text
python tools/achievement_catalog.py --input examples/achievement-catalog.synthetic.jsonl --version 0.1 --output runtime/achievement-catalog-demo
python tools/achievement_catalog.py --input examples/achievement-catalog.synthetic.jsonl --version 0.2 --output runtime/achievement-catalog-demo
```

这两个命令用同一份合成目录演示初建与升版，第二次保留旧版且报告零字段变化。用同一版号导入另一份修改过条件的合成 JSON，`changed` 会列对应 ID 和 `description` 字段。真实同版修订按相同规则处理。

## 数据字段与来源

`schema_version: 1` 的 `items` 以数值 `id` 排序。每行保留 `series_id`、`series_name`、显示标题 `name`、来源条件 `description` 及 `parameters`、`rarity`、换算星琼 `jade`、原始 `show_type`。同名 ID 各自保留；`VISIBLE` 为常显、`HiddenDesc` 为仅隐藏描述、`ShowAfterFinish` 为完成后才显示。账号已完成和未完成状态留在各自账号账本里，对表流程见[成就盘点](../skills/hsr-operations/references/achievement-audit.md)。

[已核来源清单](achievement-catalog-sources.jsonl)版本化记录来源 URL、正式版本、语言、字节数、ID 数与 SHA-256。4.7 实读九类、1,993 个独立 ID、1,989 个不同标题。清单的旧哈希用于复核对应历史快照，同一正式版有新字节时按常规差异流程更新本地。BWIKI 可辅助核首次上线和版本标签，攻略行与稳定 ID 的匹配仍需按实际来源核对。[Nanoka 版本清单](https://static.nanoka.cc/manifest.json) · [BWIKI 成就筛选](https://wiki.biligame.com/sr/%E6%88%90%E5%B0%B1%E7%AD%9B%E9%80%89)

公开仓库维护工具、来源清单和合成数据。目录正文及账号账本由使用者保存在本地。第三方许可范围见[第三方说明](../THIRD_PARTY.md)。
