/**
 * 题材候选源与口味联动（genre-signup-redesign tasks 4.1 / 6.4）。
 *
 * 单一事实源＝后端 `genres/vocab_presets.py` + `GET /api/genres/candidates`；
 * 本文件是**前端镜像**，id 必须逐字一致（parity 测试对拍），否则采纳写回的
 * tagId 在后端查不到 label，注入会退化成裸 slug。
 *
 * - `GENRE_VOCAB`：候选源（promise / forbidden / battlefield），与后端种子同 id。
 * - `GENRE_FLAVORS`：01 口味胶囊的预置联动（选中后预填 02-06），**不落库、不计入判据**。
 * - `COST_SENTENCES` / `costAnchor`：04 吃苦指数的浮例句。
 */

export type VocabKind = "promise" | "forbidden" | "battlefield";

export interface VocabEntry {
  id: string;
  kind: VocabKind;
  label: string;
  sort: number;
}

function v(kind: VocabKind, slug: string, label: string, sort: number): VocabEntry {
  return { id: `${kind}:${slug}`, kind, label, sort };
}

/** 候选源（镜像后端 genres/vocab_presets.py::VOCAB_PRESETS）。 */
export const GENRE_VOCAB: VocabEntry[] = [
  v("promise", "comeback", "以弱破强的痛快", 10),
  v("promise", "mind-game", "层层反转的智力快感", 20),
  v("promise", "sweet", "甜到齁的情感满足", 30),
  v("promise", "survival", "绝处逢生的紧张", 40),
  v("promise", "scheme", "算无遗策的掌控感", 50),
  v("forbidden", "no-deus-ex-machina", "禁天降外援", 10),
  v("forbidden", "no-free-powerup", "禁白捡神器", 20),
  v("forbidden", "no-villain-idiot", "禁反派降智", 30),
  v("forbidden", "no-foresight", "禁预知破局", 40),
  v("forbidden", "no-gratuitous-angst", "禁无端虐主", 50),
  v("forbidden", "no-third-wheel", "禁第三者搅局", 60),
  v("battlefield", "resources", "抢资源", 10),
  v("battlefield", "status", "爬地位", 20),
  v("battlefield", "truth", "查真相", 30),
  v("battlefield", "affection", "争感情", 40),
  v("battlefield", "infrastructure", "搞基建", 50),
  v("battlefield", "external-enemy", "抗外敌", 60),
];

export function vocabOf(kind: VocabKind): VocabEntry[] {
  return GENRE_VOCAB.filter((e) => e.kind === kind);
}

/** id → label（注入/展示用；未知 id 原样返回，不静默吞掉）。 */
export const VOCAB_LABEL: Record<string, string> = Object.fromEntries(
  GENRE_VOCAB.map((e) => [e.id, e.label]),
);

export function vocabLabel(id: string): string {
  return VOCAB_LABEL[id] ?? id;
}

// ── 01 口味胶囊（预置联动；不落库、不计入确认判据）────────────────────────

export interface GenreFlavor {
  /** 胶囊标识（data-g，e2e 定位用）。 */
  key: string;
  /** 胶囊文案。 */
  label: string;
  /** 预填 02 主要看什么（core_promise）。 */
  corePromise: string;
  /** 预填 03 绝对禁止（tagId 列表）。 */
  forbidden: string[];
  /** 预填 04 吃苦指数。 */
  costRatio: number;
  /** 预填 05 主线战场（tagId 列表）。 */
  battlefield: string[];
}

export const GENRE_FLAVORS: GenreFlavor[] = [
  {
    key: "comeback",
    label: "逆袭打脸",
    corePromise: "以弱破强的痛快",
    forbidden: [
      "forbidden:no-deus-ex-machina",
      "forbidden:no-free-powerup",
      "forbidden:no-villain-idiot",
    ],
    costRatio: 8,
    battlefield: ["battlefield:resources", "battlefield:status"],
  },
  {
    key: "mind",
    label: "烧脑博弈",
    corePromise: "层层反转的智力快感",
    forbidden: ["forbidden:no-foresight", "forbidden:no-villain-idiot"],
    costRatio: 5,
    battlefield: ["battlefield:status", "battlefield:truth"],
  },
  {
    key: "sweet",
    label: "独宠撒糖",
    corePromise: "甜到齁的情感满足",
    forbidden: ["forbidden:no-gratuitous-angst", "forbidden:no-third-wheel"],
    costRatio: 3,
    battlefield: ["battlefield:affection", "battlefield:infrastructure"],
  },
  {
    key: "survival",
    label: "绝境求生",
    corePromise: "绝处逢生的紧张",
    forbidden: ["forbidden:no-deus-ex-machina", "forbidden:no-foresight"],
    costRatio: 7,
    battlefield: ["battlefield:external-enemy", "battlefield:resources"],
  },
  {
    key: "scheme",
    label: "权谋布局",
    corePromise: "算无遗策的掌控感",
    forbidden: ["forbidden:no-villain-idiot", "forbidden:no-foresight"],
    costRatio: 5,
    battlefield: ["battlefield:status", "battlefield:truth"],
  },
];

// ── 04 吃苦指数浮例句 ────────────────────────────────────────────────────

export const COST_SENTENCES: Record<number, string> = {
  1: "他顺手捡了秘境，没人知道",
  3: "断了三根肋骨，换回一条命",
  5: "当众断骨毁名，才拿到入场券",
  7: "折寿十年，换一次出手",
  9: "以命作祭，才封得住那扇门",
  10: "命抵江山",
};

/** 把 1-10 的任意取值吸附到最近的例句锚点。 */
export function costAnchor(value: number): number {
  if (value <= 1) return 1;
  if (value <= 3) return 3;
  if (value <= 5) return 5;
  if (value <= 7) return 7;
  if (value <= 9) return 9;
  return 10;
}

/** 滑块浮例句文案（如「8 分 → 折寿十年，换一次出手」）。 */
export function costSentence(value: number): string {
  return `${value} 分 → ${COST_SENTENCES[costAnchor(value)]}`;
}

// ── 字段契约上限（镜像后端 D18）─────────────────────────────────────────

export const GENRE_LIMITS = {
  corePromise: 60,
  promiseNote: 200,
  track: 300,
  forbiddenMax: 50,
  battlefieldMax: 10,
  battlefieldTextMax: 20,
} as const;

/** 06 剧情轨道为唯一自由填空，可不填。 */
export const GENRE_DEFINITION =
  "题材 = 读者预期 + 作者轨道 + 核心冲突的类型锁——定了它，百万字不跑偏；随时能改。";

// ── 题材展示（书卡胶囊 / 书内标签）───────────────────────────────────────

/**
 * 题材未设定时的占位文案（用户 2026-09-10 拍板）。
 *
 * 展示位恒在：书架卡片胶囊与书内标签都读后端下发的题材展示名（新契约核心承诺 →
 * 老书 story.yaml.genre / KV 题材名），空值即「题材还没定」——用本占位而非空缺。
 */
export const GENRE_PENDING_LABEL = "待定题材";
