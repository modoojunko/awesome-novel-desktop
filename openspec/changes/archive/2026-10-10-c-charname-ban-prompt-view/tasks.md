# tasks — c-charname-ban-prompt-view

## 1. 提示词模板（提示词仓 awesome-novel-prompts#3，合 main＝b935440）

- [x] 1.1 立主角／一键立卡／盘点抽卡三模板同钉【新拟名禁令】：16 禁字表＋同音同算
  （同音不同字、连声调不同都算违规）＋禁烂俗文学腔；作者已写名字豁免照抄
- [x] 1.2 示例名自证合规：cast_draw 孟舟白（含禁字「舟」）→ 郑铁栓，CURATED 同步
- [x] 1.3 产出字段说明＋JSON 骨架从 user 段挪 system【输出契约】（立主角／一键立卡
  两模板；系统段不经 format，骨架单花括号）；user 段留【空格键位】＋口径＋禁令
- [x] 1.4 CURATED layer/desc 同步＋sync.py render/lint/index；pin＝test_charname_ban.py
  （三模板禁字表同串、产名条款 system 层回指、user 段无「只输出 JSON」、示例名合规）

## 2. C端编辑流（desktop#795，合 main＝29703ee7）

- [x] 2.1 端点：`preview:true` 只渲染即回（不调模型不计费）；`body.prompt` 编辑稿
  逐字下发（空白回落渲染稿）；响应 `prompt` 回显＝实发用户段
- [x] 2.2 弹窗两段式：编辑段（textarea＋生成钮，无换一个/无版数）→ 结果段（换一个
  沿编辑稿重跑＋采纳＋查看本次提示词回显）；失败留编辑段；runningText 措辞
- [x] 2.3 系统段保密：不进响应、不进页面（泄漏守卫钉：断言实发 system 不在响应任何位置）
- [x] 2.4 D9 缓存保留；换卡/清 AI 清编辑稿；迟到稿守卫 selectedIdRef
- [x] 2.5 测试：bootstrap/cardDraft 两套重写两段式流（29 用例）；后端 28/28
  （preview 不调 AI／编辑稿逐字下发／空白回落／泄漏守卫/主角模板守卫钉改读 system）；
  e2e 一键立卡桩分叉 preview/生成
- [x] 2.6 演示栈真机验证：编辑额外要求→生成按新要求改写（陈秤子）；curl 全链路
  （2071 字无格式说明→雨生/白手套零禁字 19 格解析）
