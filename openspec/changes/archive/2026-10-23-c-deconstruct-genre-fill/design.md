# c-deconstruct-genre-fill · design

## 数据流

```
deconstruct products (genre/mainplot/world)
  → settings_map.genre_extras
  → intro_genre_body (五字段)
  → apply.import_book
  → put_novel_genre (novel_genre + forbidden/battlefield)
```

## 推断矩阵

- `core_promise`：解谜/真相/反转/推理/悬疑 → 层层反转的智力快感；求生/绝境 → 绝处逢生；恋爱/感情 → 甜；权谋/朝堂 → 掌控感；逆袭/成长 → 以弱破强；未知 → 绝处逢生的紧张。
- `forbidden`：悬疑/灵异 → 禁天降外援＋禁反派降智；言情 → 禁第三者搅局＋禁无端虐主；玄幻/仙侠 → 禁白捡神器＋禁反派降智；权谋/历史 → 禁反派降智＋禁预知破局。
- `cost_ratio`：world.cost 出现死亡/必死/即死/生命/牺牲/绑定/重伤 → 8；受伤/失去/别离/背叛/悲伤 → 6；其余 → 4。
- `battlefield`：追查/调查/查案/真相/旧案/悬疑 → 查真相；鬼/邪祟/妖/大患/敌人/对抗 → 抗外敌；爱情/恋爱/感情 → 争感情；资源/宝物 → 抢资源；地位/权力 → 爬地位；建设/重建/基建 → 搞基建；取前 2，无命中 → 查真相。

## 边界

- 产物显式字段优先；显式空数组按缺失处理（本 change 的目标是不留空）。
- 推断值只在 import warnings 标注；设定页可改。
- 关键词使用多字词，避免「查看/命令/村庄」类误判。
