# c-hooks-advance-ledger — 伏笔对账制收尾：兑现/推进按编号引用＋「该收了」标注

## Why

用户拍板（2026-09-29）：伏笔还是太多——「怎么看是否推进？是否兑现？而不是每章都创建一对」。
实勘三缺口：①收尾 AI 只被要求「判断埋下或收束」，台账注入只用于排重，模型不知道「这些是
挂着的、该考虑收的」，产出天然偏向新埋；②「推进」概念不存在（active/resolved 二元跳变，
埋与收之间空白）；③收束匹配靠描述包含，措辞变体即失配→又建新条。#589 治了产量（≤3），
本 change 治方向：**从「登记」转向「先对账、再登记」**。

## What Changes

- **收尾对账制（hooks 段重写）**：活跃台账带编号＋计划收束章注入；prompt 要求先判
  `resolved`（本章兑现，按编号 `#H-####` 引用＋证据＋怎么收的）与 `advanced`（本章推进
  ——部分揭示/强化未收，按编号＋一句推进说明，各 ≤3），再判 `planted`（真新伏笔 ≤3，
  **本章无新悬念 SHALL 输出空数组**）。
- **accept 编号精确匹配**：`resolved`/`advanced` 按 `ref`（#H-#### → seq）定位台账行，
  SHALL NOT 再依赖描述包含匹配；payload 无 ref 的旧格式行（存量 pending）兼容走旧匹配。
  resolved 命中→patch resolved＋payoff_note；advanced 命中→`mentioned_chapter_id` 回填
  本章（**复用归档留痕列，零 DDL**——模型注释预留的「归档 UI 归写作期 change」口子）。
- **「最近推进」可见**：设定页台账行与伏笔卡、工作台投影行显示「最近推进 · 第 N 章」
  （mentioned_chapter_id；埋点当章回填维持现状，两写并存语义＝最近一次被收尾认定相关）。
- **「该收了」一眼化**：`planned_chapter_id` 非空 ∧ active ∧ 计划章 ≤ 当前章（工作台
  投影按当前章、设定页按主线最新章）→ 台账行标「该收了」。
- 后端零 DDL、零接口形状破坏（payload 向后兼容）。

## Impact

- specs：archive-reconcile（收尾行生命周期＋采纳写回 MODIFIED）、foreshadow-settings
  （台账与伏笔卡 MODIFIED——最近推进/该收了/计划收束显示）、workbench（中栏伏笔页签
  MODIFIED——投影行推进与该收了标注）。
- 代码：reconcile.py（prompt＋accept）、hooks 前端两处；e2e reconcile 桩补 advanced。
- 非目标：体检「到期未收」检查扩展（另行立项）；mentioned 的独立推进记录表（本期单值
  「最近一次」够用）。
