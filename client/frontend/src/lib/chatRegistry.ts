// chatRegistry——每页注册制单一事实源（c-writing-agent 批E）。
// 每页注册三要素：状态感知开场白（会话内首见该页投递一次）＋默认能力 chips＋
// 上下文注入。启动时校验：注册引用的能力 id 必须在 CHIPS 白名单内（fail loud——
// spec §每页注册制能力盘）。actions 映射由宿主（NovelWorkspace）注入既有写回链，
// 禁止新增写回路径（spec §生成类工具只产卡）。

import type { FeatureKey } from "@/lib/features";

export interface ChatChip {
  key: string;
  label: string;
  /** 点 chip 发进对话的指令（带上下文的指令进对话，不是直接执行） */
  command: string;
  /** 富交互入口（AiModal/抽卡/推演等既有弹窗）：点 chip 由宿主开弹窗，不发指令 */
  open?: string;
  /** 行级门控（features.ts key；无＝免费可用/读类） */
  feature?: FeatureKey;
  /** 前置条件不满足置灰＋hint（由宿主按页面状态计算） */
  disabled?: boolean;
  hint?: string;
}

export interface ChatPageScope {
  /** 与 novelStage.LandingView 同构（从宿主直接传） */
  view: import("@/lib/novelStage").LandingView;
  chapterRef: string | null;
  volumeSelId: string | null;
  /** 空书（零卷零章）判定——开场白据此换口吻 */
  emptyBook: boolean;
  /** 设定面板名（SettingsView 当前面板；advanced-settings 时有值） */
  settingPanel?: string;
  /** 章内页签键（ChapterWorkspace chTab：og|prose|settings|relations|hooks|actions|style；
   *  railData.tab 上抛——章级 chips 据此换装，原型 PAGES 每页一套的口径） */
  chapterTab?: string;
}

export interface ChatPageRegistration {
  id: string;
  label: string;
  match(s: ChatPageScope): boolean;
  /** 开场白（状态感知）；null＝不开口 */
  greeting(s: ChatPageScope): string | null;
  chips(s: ChatPageScope): ChatChip[];
}

/** 一期 chips 白名单（与后端 TOOL_REGISTRY 对齐的对话入口子集；发散 MAX）。 */
// open 型 chip（宿主开既有弹窗/入口）与 command 型（agent 工具）同单源
const CHIP_KEYS = [
  "draft_volume_expand",
  "draft_chapter_split",
  "draft_chapter_plot",
  "draft_arc",
  "check_consistency",
  "draft_names",
  "diverge_character_group",
  "diverge_plot_branches",
  "ai_write",
  "kb_search",
  "plot_draw",
  "cast_review",
  "simulate",
  "fill_gaps",
  "conflict_check",
  "renwei",
  "seam",
  "zhuque",
  "settings_og_fill",
  "simulate_plot",
  "draw_plot_cards",
  "review_cast",
] as const;

const REGISTRATIONS: ChatPageRegistration[] = [
  {
    id: "workbench.volume",
    label: "工作台 · 卷纲",
    match: (s) => s.view === "workbench" && !s.chapterRef,
    greeting: (s) =>
      s.emptyBook
        ? "第一卷还空着，说说你的目标，我来铺。"
        : "这一卷想从哪里开始、到哪里收住？给我一句话，我来铺结构。",
    chips: () => [
      { key: "draft_volume_expand", label: "铺这一卷", command: "帮我铺这一卷的卷纲。" },
      { key: "draft_chapter_split", label: "拆下一章", command: "照卷纲拆下一章。" },
      { key: "check_consistency", label: "卷纲体检", command: "给这一卷做个体检。" },
    ],
  },
  {
    id: "settings.chars",
    label: "初始设定 · 角色",
    match: (s) => s.view === "advanced-settings" && s.settingPanel === "chars",
    greeting: () =>
      "这本书记录里的主线还差一句「主角最终变成什么样」。补上后起草的角色会更贴；现在也可以先起草，要我试试吗。",
    chips: () => [
      { key: "draft_arc", label: "起草主线", command: "帮我起草主线。" },
      { key: "check_consistency", label: "一致性体检", command: "做一次一致性体检。" },
    ],
  },
  {
    id: "workbench.chapter",
    label: "工作台 · 章节",
    match: (s) => s.view === "workbench" && !!s.chapterRef,
    greeting: () => null, // 章级页签深 chips 批F-2b；此处保持安静不打断写作
    // 随章内页签换装（原型 PAGES 口径：每页一套；boss 指正 2026-11-15——曾 11 颗全堆一起）
    // og=章纲（规划/盘点类）｜prose=正文（写/检测类）｜其余页签按语义各取
    chips: (s) => {
      const byTab: Record<string, ChatChip[]> = {
        og: [
          { key: "draft_chapter_split", label: "拆下一章", command: "照卷纲拆下一章。" },
          { key: "draft_chapter_plot", label: "本章剧情", command: "给本章出三版剧情清单。" },
          { key: "check_consistency", label: "体检", command: "给本章做一次体检。" },
          { key: "simulate_plot", label: "剧情推演", command: "给我这一章做剧情推演。" },
          { key: "draw_plot_cards", label: "剧情抽卡", command: "给我抽三张剧情提案卡。" },
          { key: "review_cast", label: "人物盘点", command: "给本章做一次人物盘点。" },
          { key: "settings_og_fill", label: "补全缺失", command: "帮我补全这一章章纲缺失的字段。" },
        ],
        prose: [
          { key: "ai_write", label: "生成正文", command: "", open: "ai_write", feature: "ai-generate" },
          { key: "renwei", label: "人味检测", command: "", open: "renwei" },
          { key: "seam", label: "接上一章", command: "", open: "seam" },
          {
            key: "zhuque",
            label: "朱雀检测",
            command: "",
            open: "zhuque",
            feature: "ai-detect",
            hint: "整章送腾讯朱雀测 AI 味；Key 在「模型配置 → 朱雀」配置",
          },
        ],
        settings: [
          { key: "check_consistency", label: "体检", command: "给本章做一次体检。" },
          { key: "cast_review", label: "人物盘点", command: "", open: "cast_review" },
        ],
        style: [{ key: "renwei", label: "人味检测", command: "", open: "renwei" }],
        relations: [{ key: "cast_review", label: "人物盘点", command: "", open: "cast_review" }],
        hooks: [{ key: "check_consistency", label: "体检", command: "给本章做一次体检。" }],
        actions: [],
      };
      return byTab[s.chapterTab ?? "og"] ?? byTab.og;
    },
  },
  {
    id: "archives.preview",
    label: "预览",
    match: (s) => s.view === "archives",
    greeting: () => null,
    chips: () => [
      { key: "kb_search", label: "查知识库", command: "在知识库里查一下相关的条目。" },
    ],
  },
  {
    id: "settings.default",
    label: "初始设定",
    match: (s) => s.view === "advanced-settings",
    greeting: () => null,
    // 设定卡收编（boss 拍板 2026-11-15）：16 行 AI 能力走 agent——chips 发
    // 自然语言，agent 识别调对应工具，产物卡回对话过目（写回走前端采纳）
    chips: (s) => {
      const byPanel: Record<string, ChatChip[]> = {
        genre: [
          { key: "settings_genre_core_promise", label: "AI 填 · 主要看什么", command: "给我几个「主要看什么」的核心看点候选。" },
          { key: "settings_genre_forbidden_list", label: "AI 填 · 绝对禁止", command: "这本书绝不出现什么？给我红线清单候选。" },
          { key: "settings_genre_cost_ratio", label: "AI 填 · 吃苦指数", command: "主角得到好处要付多大代价？给吃苦指数建议。" },
          { key: "settings_genre_battlefield", label: "AI 填 · 本小说斗什么", command: "全书主要斗的是什么？给对抗物候选。" },
        ],
        intro: [
          { key: "settings_intro", label: "AI 起草简介", command: "按三问帮我起草简介，出三条候选。" },
        ],
        foreshadow: [
          { key: "settings_hooks_draft", label: "起草伏笔", command: "按我的简介＋题材＋世界，起草几条伏笔候选，配收束章。" },
          { key: "settings_hooks_check", label: "埋坑体检", command: "扫一遍活跃伏笔和已写章纲，埋了没还的点名。" },
        ],
        arc: [
          { key: "draft_arc", label: "AI 填 · 起草主线", command: "帮我起草主线。" },
          { key: "check_consistency", label: "主线自检", command: "做一次主线自检。" },
        ],
      };
      return byPanel[s.settingPanel ?? ""] ?? [
        { key: "draft_arc", label: "AI 填 · 起草主线", command: "帮我起草主线。" },
        { key: "check_consistency", label: "主线自检", command: "做一次主线自检。" },
      ];
    },
  },
];

/** 取当前页注册（按序首个 match；无匹配返回 null——宿主回落旧面板）。 */
export function matchRegistration(scope: ChatPageScope): ChatPageRegistration | null {
  for (const r of REGISTRATIONS) {
    if (r.match(scope)) return r;
  }
  return null;
}

/** 启动校验（fail loud）：chips 的 key 必须在白名单内——注册了工具清单外的能力即报错。
 *  章级注册按页签全组扫（chips 随章内页签换装，漏扫一签即漏检一签）。 */
const CHAPTER_TAB_SWEEP = ["og", "prose", "settings", "relations", "hooks", "actions", "style"];

export function validateRegistrations(
  regs: ChatPageRegistration[] = REGISTRATIONS,
  whitelist: readonly string[] = CHIP_KEYS,
): void {
  for (const r of regs) {
    const scopes = (
      r.id === "workbench.chapter" ? CHAPTER_TAB_SWEEP : [undefined]
    ).map((chapterTab) => ({
      view: "workbench" as const,
      chapterRef: "vol-1-ch-1",
      volumeSelId: null,
      emptyBook: false,
      chapterTab,
    }));
    for (const scope of scopes) {
    for (const chip of r.chips(scope)) {
      if (!(whitelist as readonly string[]).includes(chip.key)) {
        throw new Error(`[chatRegistry] 页面 ${r.id} 注册了未登记的能力：${chip.key}`);
      }
      }
    }
  }
}

export function registrationsForTest(): readonly ChatPageRegistration[] {
  return REGISTRATIONS;
}

/** 会话线程键（每页签一个对话——boss 拍板 2026-11-15）：章内页签各一线程、
 *  设定面板各一线程、卷纲/预览各一线程；服务端按 (user, book, thread) 存。 */
export function threadKeyOf(s: ChatPageScope): string {
  if (s.view === "workbench") {
    return s.chapterRef ? `ch:${s.chapterTab ?? "og"}` : "vol";
  }
  if (s.view === "advanced-settings") {
    return `set:${s.settingPanel ?? "default"}`;
  }
  if (s.view === "archives") return "preview";
  return `v:${s.view}`;
}
