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
  /** 行级门控（features.ts key；无＝免费可用/读类） */
  feature?: FeatureKey;
  /** 前置条件不满足置灰＋hint（由宿主按页面状态计算） */
  disabled?: boolean;
  hint?: string;
}

export interface ChatPageScope {
  view: "workbench" | "advanced-settings" | "archives";
  chapterRef: string | null;
  volumeSelId: string | null;
  /** 空书（零卷零章）判定——开场白据此换口吻 */
  emptyBook: boolean;
  /** 设定面板名（SettingsView 当前面板；advanced-settings 时有值） */
  settingPanel?: string;
}

export interface ChatPageRegistration {
  id: string;
  label: string;
  match(s: ChatPageScope): boolean;
  /** 开场白（状态感知）；null＝不开口 */
  greeting(s: ChatPageScope): string | null;
  chips(): ChatChip[];
}

/** 一期 chips 白名单（与后端 TOOL_REGISTRY 对齐的对话入口子集；发散 MAX）。 */
const CHIP_KEYS = [
  "draft_volume_expand",
  "draft_chapter_split",
  "draft_chapter_plot",
  "draft_arc",
  "check_consistency",
  "draft_names",
  "diverge_character_group",
  "diverge_plot_branches",
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
    id: "settings.default",
    label: "初始设定",
    match: (s) => s.view === "advanced-settings",
    greeting: () => null, // 具体面板注册未覆盖时不主动开口（批F 逐面板补）
    chips: () => [
      { key: "draft_arc", label: "AI 填 · 起草主线", command: "帮我起草主线。" },
      { key: "check_consistency", label: "主线自检", command: "做一次主线自检。" },
    ],
  },
];

/** 取当前页注册（按序首个 match；无匹配返回 null——宿主回落旧面板）。 */
export function matchRegistration(scope: ChatPageScope): ChatPageRegistration | null {
  for (const r of REGISTRATIONS) {
    if (r.match(scope)) return r;
  }
  return null;
}

/** 启动校验（fail loud）：chips 的 key 必须在白名单内——注册了工具清单外的能力即报错。 */
export function validateRegistrations(): void {
  for (const r of REGISTRATIONS) {
    for (const chip of r.chips()) {
      if (!(CHIP_KEYS as readonly string[]).includes(chip.key)) {
        throw new Error(`[chatRegistry] 页面 ${r.id} 注册了未登记的能力：${chip.key}`);
      }
    }
  }
}

export function registrationsForTest(): readonly ChatPageRegistration[] {
  return REGISTRATIONS;
}
