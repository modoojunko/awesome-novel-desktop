# Tasks

## 1. 后端（reconcile.py）

- [x] hooks prompt 对账制：台账块带编号＋计划收束章；三段产出指令（resolved/advanced 各 ≤3 按 ref；planted ≤3 空则空）；e2e 桩短语保留
- [x] accept hooks：ref→seq 精确解析（失败跳过）；resolved 命中→patch resolved＋收束章＋payoff_note；advanced 命中→mentioned_chapter_id=本章；旧格式（无 ref description）兼容
- [x] 测试：pytest（advanced 回填＋幂等／ref 解析失败跳过／旧格式兼容／prompt 带编号与三段指令／无台账无对账块）

## 2. 前端

- [x] HooksSettingForm：台账行 meta「最近推进 · 第 N 章」「计划收 · 第 N 章」「该收了」小标；伏笔卡同步；主线最新章号解析
- [x] HooksPane：投影行「最近推进 · 第 N 章」（晚于埋点才显）＋「该收了」（≤当前章／卷末章）
- [x] vitest：storylineHooksAndLore 补推进/该收了例

## 3. 门禁与交付

- [x] pytest 全量＋vitest 全量＋tsc＋design:lint＋openspec validate
- [x] 隔离栈 e2e reconcile（桩补 advanced 断言）
- [x] PR＋合入＋演示栈前后端换装＋归档
