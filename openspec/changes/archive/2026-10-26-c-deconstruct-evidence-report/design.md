# 设计：拆书证据报告

## 证据键清单（单源）

```
EVIDENCE_KEYS = ("evidence_ch", "confidence", "note", "quote", "raw")
```

- `evidence_ch` 证据章节、`confidence` 可信度、`note` 说明（分歧/原文未明确/理由）、
  `quote` 原文佐证、`raw` 原文措辞——五键在全部十维契约里只承担「证明这条结论」的职责
  （文风模板三铁律＋证据/指令分离；settings_map 同口径视其为分析尾巴）。
- 作家内容键不动：`need`/`how`/`transferable`（读者需求与迁移边界）、`repro_steps`/
  `emotion_chain`/`swappable`/`no_copy`（技法本体）、`example`（原文短例＝示例非存证）、
  `plant_ch`/`payoff_ch`（伏笔台账的埋设/回收章是内容不是存证）。
- 提示词仓不改：模型继续产出证据字段，任务资料里全量保留——报告才有得看、settings_map
  投影口径不变。

## md 读取侧现渲染（存量任务零迁移的关键）

产物 md 的读取方恰有三处：预览端点、导出（`apply._md_map`）、结果目录字符数
（`task_view`）。三处统一改为 `mdrender.md_map_from_products(products_raw)`：
`data` 在则现渲染，`data` 缺失（理论外）回退存量 `md`。管线不再写 `md` 键。

为什么不选「读取时打补丁/迁移旧 md」：存储 md 一旦不再是事实源，就不存在新旧口径
对账问题；渲染是纯函数（同 data 同字节），三个读取方天然一致。

## 渲染器独立成模块

`_render_md` 及标签表从 `pipeline.py`（1649 行）迁出到 `deconstruct/mdrender.py`：
service/apply/router 都要读渲染器，挂 在 pipeline 下会让轻量入口背上管线的重依赖
（提示词包加载等）。`render.py` 名字已被图谱渲染占用，新模块取名 `mdrender`。

## 证据报告 API

`GET /api/deconstruct/tasks/{task_id}/evidence`（鉴权同预览端点，产物查看不设档位门）：

```json
{"task_id": "...", "dims": [
  {"dim": "techniques", "name": "写作技法", "file": "写作技法.md", "confidence": "high",
   "sections": [{"title": "可复现模块卡",
     "items": [{"head": "章末炸点收束",
       "cells": [{"label": "证据章节", "value": "第3、8、118章"},
                 {"label": "可信度", "value": "高"}]}]}]}]}
```

- 非完成态/无产物 → `dims: []`（前端只在完成态出入口，空数组天然兜底）。
- 只收「有证据单元格」的条目与节；维度级只收顶层 `confidence`。
- head 取 `("name","title","desc","item","need")` 首个非空；`from`/`to` 条目（关系边）
  head 为「from → to」；其余取首个内容字段截 40 字。

## 前端呈现

- 完成态按钮行追加「证据报告」（`btn-secondary`），弹窗复用预览弹窗的
  scrim/modal/mcard/rd-style 骨架；加载失败 toast＋收起（同预览口径，含过期响应序号守卫）。
- 内容按维度分组：组头「维度名 · 可信度：高」（无顶层可信度只给维度名），条目行
  head 加粗＋证据单元格「标签：值」串联。空态「本任务产物没有证据类信息」。
- 提示文案同步：结果目录头与页脚 hint 注明证据在「证据报告」查看。
