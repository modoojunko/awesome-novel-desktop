// 设定视图（book.html #viewSettings 复刻，PR4）：
//   two-col = 左栏（tree-head 设定·7 项 + settings-progress n/7 进度条
//   + 8 导航项 done/empty 两态徽标 + 可后补 tag + tree-foot 口径注）
//   + 右面板（panel-head/badge/desc/panelBody + panel-foot 确认完成）。
// 七项计数与后端 READINESS_KEYS 同源（synopsis=简介 / hooks=伏笔）；
// 模型设定为**第 00 项工具项**（用户 2026-09-10 指定排在最前）：恒 done、无确认按钮、
// 不参与进度（ADJUSTMENTS #4）。
// 产品扩展（ADJUSTMENTS #9）：已确认面板的按钮转「保存修改」——设计稿 done 态
// 无落库入口，保留产品「改完随时存」能力；确认流程沿 gap3（先 save 再 confirm）。
// 例外（c-chars-confirm-scope）：自动保存制面板（角色/伏笔）的改动即时落库，已确认态
// 按钮与回执走「重新确认 / 已重新确认」；角色页脚提示＝整项口径的缺口摘要（按档位），
// 数据由 CharacterManager 经 onGateHintChange 上抛（列表载入前报 null → 回落通用 note）。
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { useDirtyState } from "@/hooks/useDirtyState";
import { type SettingSaveHandle } from "@/components/novel/settings/FormField";
import WorldSettingPanel from "@/components/novel/settings/world/WorldSettingPanel";
import type { WorldPanelHandle } from "@/components/novel/settings/world/WorldSettingPanel";
import StyleSettingForm, { type StylePanelHandle } from "@/components/novel/settings/StyleSettingForm";
import HooksSettingForm, { type HookSaveState, type HooksPanelHandle } from "@/components/novel/settings/HooksSettingForm";
import CharacterManager, { type CharGateHint } from "@/components/novel/settings/CharacterManager";
import { type CharAiCtx } from "@/lib/characterModel";
import { charactersApi } from "@/lib/charactersApi";
import ModelSettingForm from "@/components/novel/settings/ModelSettingForm";
import StoryArcForm, { type ArcFormHandle, type ArcAiAction } from "@/components/novel/settings/StoryArcForm";
import { useStoryArc } from "@/components/novel/settings/useStoryArc";
import GenreSettingForm, {
  type GenreHandle,
  type GenreAiField,
} from "@/components/novel/settings/GenreSettingForm";
import { INTRO_SEGMENTS, INTRO_FORMULA, DONT_DO, INTRO_MAX_LEN, TABOO_RULES } from "@/lib/introTemplate";
import { GENRE_DEFINITION } from "@/lib/genreVocab";
import { useModelStatus } from "@/hooks/useModelStatus";
import { useFeature } from "@/hooks/useTier";
import { upgradeHintOf } from "@/lib/features";
import type { AiState } from "@/types/api-config";
import AiWriterAssistant, {
  CharsAiRail,
  type AiCapabilityRow,
} from "@/components/novel/AiWriterAssistant";
import AiCardModal, { type AiCardState } from "@/components/novel/settings/AiCardModal";
import {
  ChangeReceiptBar,
  RestoreHint,
  useChangeReceipt,
  type ChangeReceiptState,
} from "@/components/novel/settings/ChangeReceipt";
import { introAi, aiBlockReason, type IntroAiAction } from "@/lib/ai";

// ── 面板注册表（顺序/命名与原型 navItems 一致；settingsKey 对后端口径）──
// 顺序＝用户 2026-09-10 拍板：00 模型设定（工具项，见下方树内单列）→ 01 简介 →
// 02 题材 → 03 世界 → 04 角色 → 05 主线 → 06 文风 → 07 伏笔。
// 这一序同时决定「确认即前进」的推进顺序（nextPanel 按本数组取下一项）；
// banned-words-into-style：08 禁用词句退役——禁用词/句式规则并入文风硬约束区。
const SETTINGS_ITEMS = [
  { k: "intro", name: "简介", settingsKey: "synopsis", canDefer: false },
  { k: "genre", name: "题材", settingsKey: "genre", canDefer: false },
  { k: "world", name: "世界", settingsKey: "world", canDefer: true },
  { k: "chars", name: "角色", settingsKey: "characters", canDefer: true },
  { k: "arc", name: "主线", settingsKey: "story-arc", canDefer: true },
  { k: "style", name: "文风", settingsKey: "style", canDefer: false },
  { k: "foreshadow", name: "伏笔", settingsKey: "hooks", canDefer: true },
] as const;

const DESCS: Record<string, string> = {
  genre: GENRE_DEFINITION,
  intro: "让读者（和 AI）知道这是一个怎样的故事。",
  arc: "比简介更全地说清这本书从头到尾讲什么、结局是什么——不填也不拦写作，直接开写都行。",
  world: "世界是 AI 写章时的物理法则——能做什么、不能做什么、付什么代价，都从这里读。",
  style: "文字文风管身份与红线（免费，继承题材），量化参数管数字手感（会员·蒸馏）。",
  foreshadow:
    "先埋下的，后面要还（「收束」＝把坑填了）。每条伏笔记三件事：在哪埋、打算哪章还、还了没——章节从卷章树里选，AI 写到那章会照着还。改动即自动保存；设定期想到就记一条，写正文时回来埋也一样。",
  chars:
    "AI 写每一章，都要靠这里知道「谁在场、谁想干什么」。主角必立——从称呼和一句话人设写起；配角、反派把认知内核填全，路人只留基础档案。人物关系只记「他怎么看别人」：一段一句，同一对方一条。",
};

const BADGE_DONE = "ok";
const BADGE_EMPTY = "empty";
const CHECK_PATH = "M5 13l4 4L19 7";
/** 自动保存制面板（c-chars-confirm-scope）：字段改动即时落库，「保存」对它名不副实——
 *  已确认态的主按钮做的是重新跑门禁/前移指纹基线，故文案走「重新确认」；表单制面板不变。 */
const AUTO_SAVE_PANELS = new Set(["chars", "foreshadow"]);

function BadgeIcon({ ok }: { ok?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      {ok ? <path d={CHECK_PATH} /> : <circle cx="12" cy="12" r="5" />}
    </svg>
  );
}

export interface SettingsViewProps {
  projectId: string;
  initialPanel?: string;
  /** 页签回默认主页：值变化＝把面板拨回默认项（第一项「简介」）；脏表单由外壳先确认 */
  homeSeq?: number;
  settingsStatus: Record<string, boolean> | null;
  /** 角色项"内容有变"（character-settings-v2）：确认存档与当前内容指纹不一致 */
  charStale?: boolean;
  /** 重取确认存档状态（c-chars-stale-reconfirm）：角色面板数据刷新后与重新确认成功后调用，
   *  让徽标/页脚当场说真话（不再要求刷新页面） */
  onRefreshConfirmState?: () => void;
  confirmedStatus?: Record<string, boolean> | null;
  confirmSetting: (type: string) => Promise<boolean>;
  onDirtyChange?: (dirty: boolean) => void;
  /** 设定全部完成后「去写作」出口（切工作台写作视图）。 */
  onGoWrite?: () => void;
  /** 本书书名——简介 AI 入参 title 的来源（tasks 3.5 钉死）。 */
  novelName?: string;
}

/** 旧面板键 → 新面板键（外部 jump 载荷兼容） */
function normalizePanel(v: string | undefined): string {
  const map: Record<string, string> = {
    genre: "genre", synopsis: "intro", intro: "intro", "story-arc": "arc", arc: "arc",
    world: "world", style: "style", "anti-ai": "style",
    hooks: "foreshadow", characters: "chars", "ai-model": "aiModel",
  };
  return (v && map[v]) || "intro";
}

export default function SettingsView({
  projectId, initialPanel, homeSeq, settingsStatus, confirmedStatus, charStale, confirmSetting,
  onRefreshConfirmState, onDirtyChange, onGoWrite, novelName,
}: SettingsViewProps) {
  const [panel, setPanel] = useState(() => normalizePanel(initialPanel));
  /** 改动回执（用户 2026-09-10）：三面板里"一键改变内容"的动作在脚部留一条 + 一步撤销。 */
  const [receipt, setReceipt] = useState<ChangeReceiptState | null>(null);
  const handleReceiptChange = useCallback((r: ChangeReceiptState | null) => setReceipt(r), []);
  // 回执只属于「当前面板的那一次改动」：撤销闭包握的是该面板表单的 setData，
  // 切走后留着就是点了没反应的死撤销（值已确认落库的更糟）。切面板有四条路径
  // （点左栏 / 确认即前进 / 缺模型跳转 / 外部 initialPanel），统一由这条兜住，
  // 不在各调用点各自清。
  useEffect(() => setReceipt(null), [panel]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  const formRef = useRef<SettingSaveHandle>(null);
  /** 主线面板句柄（save 走 formRef 同一 ref；runAi 为 arc 面板专属能力） */
  const arcFormRef = useRef<ArcFormHandle>(null);
  const genreRef = useRef<GenreHandle>(null);
  const introRef = useRef<IntroHandle>(null);
  /** 世界面板句柄：save 落库；runAi 由右栏 AI 卡/格头快捷钮调用（world-setting-v2）。 */
// D13：AI 行的门控只读后端 ai_state 一次分派（不再 useFeature + 本地推导两处判）
  const { aiState, aiMessage, refresh: refreshAiState } = useModelStatus(projectId);
  /** AI 行运行态（受控下发给卡片）：点即置位、promise 落地即清，用户看得见后台在跑。 */
  const [aiRunningKey, setAiRunningKey] = useState<string | null>(null);
  const aiRowBusyRef = useRef(false);
  const runIntroAi = useCallback(async (key: string, action: IntroAiAction) => {
    if (aiRowBusyRef.current) return;
    aiRowBusyRef.current = true;
    setAiRunningKey(key);
    try {
      await introRef.current?.runAi(action);
    } finally {
      aiRowBusyRef.current = false;
      setAiRunningKey(null);
    }
    },
    [],
  );
  const runGenreAi = useCallback(
    async (key: string, field: GenreAiField, opts?: { multi?: boolean }) => {
    if (aiRowBusyRef.current) return;
    aiRowBusyRef.current = true;
    setAiRunningKey(key);
    try {
      await genreRef.current?.runAi(field, opts);
    } finally {
      aiRowBusyRef.current = false;
      setAiRunningKey(null);
    }
  }, []);
  const worldRef = useRef<WorldPanelHandle>(null);
  const runWorldAi = useCallback(
    async (key: string) => {
      if (aiRowBusyRef.current) return;
      aiRowBusyRef.current = true;
      setAiRunningKey(key);
      try {
        await worldRef.current?.runAi(key);
      } finally {
        aiRowBusyRef.current = false;
        setAiRunningKey(null);
      }
    },
    [],
  );
  const charsRef = formRef;
  const runCharsAi = useCallback(
    async (key: string) => {
      if (aiRowBusyRef.current) return;
      aiRowBusyRef.current = true;
      setAiRunningKey(key);
      try {
        await (charsRef.current as { runAi?: (k: string) => Promise<void> } | null)?.runAi?.(
          key,
        );
      } finally {
        aiRowBusyRef.current = false;
        setAiRunningKey(null);
      }
    },
    [charsRef],
  );
  /** 伏笔面板句柄：save/confirm 走 formRef；runAi 为伏笔右栏专属分发（批2） */
  const hooksRef = useRef<HooksPanelHandle>(null);
  const runHooksAi = useCallback(async (key: string) => {
    if (aiRowBusyRef.current) return;
    aiRowBusyRef.current = true;
    setAiRunningKey(key);
    try {
      await hooksRef.current?.runAi?.(key);
    } finally {
      aiRowBusyRef.current = false;
      setAiRunningKey(null);
    }
  }, []);
  /** 文风面板句柄（style-settings-v2）：save/confirm 走 formRef；runAi 为文风右栏分发 */
  const styleRef = useRef<StylePanelHandle>(null);
  const runStyleAi = useCallback(async (key: string) => {
    if (aiRowBusyRef.current) return;
    aiRowBusyRef.current = true;
    setAiRunningKey(key);
    try {
      await styleRef.current?.runAi?.(key);
    } finally {
      aiRowBusyRef.current = false;
      setAiRunningKey(null);
    }
  }, []);
  const [charCtx, setCharCtx] = useState<CharAiCtx | null>(null);
  /** 角色整项确认缺口（c-chars-confirm-scope）：CharacterManager 上抛，页脚提示按档位取用 */
  const [charGateHint, setCharGateHint] = useState<CharGateHint | null>(null);
  // 伏笔面板（foreshadow-settings-v2）：徽标五态 / 保存四态 / 选中条目 ctx 的上报落点。
  // 不在 [panel] 变化时重置——伏笔面板挂载即重新上报（挂载 effect 先于父层 effect 跑，
  // 任何「先清后报」的时序都会把刚上报的状态抹掉）；徽标按 isForeshadow 取用，天然隔离。
  const [hookPanelState, setHookPanelState] = useState<{
    cls: string;
    label: string;
    ok: boolean;
    empty: boolean;
    /** 内容有变（c-chars-stale-reconfirm）：页脚让位判据的第二来源 */
    stale: boolean;
  } | null>(null);
  const [hookSaveState, setHookSaveState] = useState<HookSaveState>("saved");
  const [hookCtx, setHookCtx] = useState<{ id: string; code: string; desc: string } | null>(null);
  const handleAiBlocked = useCallback((reason: AiState) => {
    if (reason === "no_key") {
      window.location.hash = "/config";
      return;
    }
    if (reason === "missing_model" || reason === "invalid") {
      setPanel("aiModel");
      return;
    }
    toast.info("这是会员功能——开通后可用；免费版写作能力完整");
  }, []);
  // 简介右栏 AI 三能力（并列，非先后流程）——onClick 经 introRef 调面板内 runAi
  // 前置守卫（D14/O-3）：补缺失未体检 → 置灰 + 「先体检」
  const [introspected, setIntrospected] = useState(false);
  const introAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "check",
        name: "体检",
        desc: "六段逐项查达标 / 缺失 + 扫禁忌，只提醒不拦确认",
        onClick: () => {
          setIntrospected(true);
          return runIntroAi("check", "introspect");
        },
      },
      {
        key: "fill",
        name: "补缺失",
        desc: "只补缺的段，候选采纳才插入",
        disabled: !introspected,
        hint: introspected ? undefined : "先体检",
        onClick: () => runIntroAi("fill", "fill"),
      },
      {
        key: "polish",
        name: "润色",
        desc: "保你原意压 AI 味，前后对照采纳才替换",
        onClick: () => runIntroAi("polish", "polish"),
      },
    ],
    [introspected, runIntroAi],
  );

  // 现实向开关（世界面板上报）：右栏力量两行随之退场，原位一行灰字占位
  const [worldNoPower, setWorldNoPower] = useState(false);

  // 世界右栏五行（world-setting-v2）：四问生成 + 一致性体检（答案落对应格下）
  const worldAiRows = useMemo<AiCapabilityRow[]>(() => {
    const rows: AiCapabilityRow[] = [
      { key: "stage", name: "世界舞台", desc: "这是个什么世界，故事发生在哪 · 输入：书名+简介+题材", onClick: () => runWorldAi("stage") },
      { key: "factions", name: "势力", desc: "谁在和谁争、各自想要什么 · 输入：简介+历史旧账（若已写）", onClick: () => runWorldAi("factions") },
      { key: "constraints", name: "世界铁律", desc: "为这个世界立几条不许破的硬边界 · 输入：01-05 已填内容", onClick: () => runWorldAi("constraints") },
      { key: "check", name: "一致性体检", desc: "简介、题材、世界三方对照，扫矛盾与漏洞 · 只提醒不拦确认", onClick: () => runWorldAi("check") },
    ];
    if (!worldNoPower) {
      rows.splice(1, 0,
        { key: "power", name: "力量体系", desc: "力量叫什么、分几级、上限在哪 · 输入：01+题材+简介", onClick: () => runWorldAi("power") },
        { key: "cost", name: "力量的代价", desc: "用它要付什么代价 · 输入：02+简介", onClick: () => runWorldAi("cost") },
      );
    }
    return rows;
  }, [runWorldAi, worldNoPower]);

  // 主线右栏三行（storyline-settings-v2）：全部聚焦主线——他项设定只作输入，
  // 结论只落主线面板字段；runAi 经 formRef（ArcFormHandle）分发，面板内自带在途互斥
  const runArcAiRow = useCallback(
    async (key: string, action: ArcAiAction) => {
      if (aiRowBusyRef.current) return;
      aiRowBusyRef.current = true;
      setAiRunningKey(key);
      try {
        await arcFormRef.current?.runAi(action);
      } finally {
        aiRowBusyRef.current = false;
        setAiRunningKey(null);
      }
    },
    [],
  );
  const arcAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "draft",
        name: "起草主线",
        desc: "把你的简介扩写成从头到尾的完整故事，顺带把结局三问答了；散着说想法也行",
        onClick: () => runArcAiRow("draft", "draft"),
      },
      {
        key: "ending",
        name: "结局校准",
        desc: "帮你把结局三问捋顺，和你的题材对味",
        onClick: () => runArcAiRow("ending", "calibrate"),
      },
      {
        key: "check",
        name: "主线体检",
        desc: "看看故事讲不讲得通、结尾接不接得上开头——只提醒，不拦你确认",
        onClick: () => runArcAiRow("check", "check"),
      },
    ],
    [runArcAiRow],
  );

  // 题材右栏四行（02-05 各答各题；01 题材目录不走 AI；06 剧情轨道已退役——归主线规划）
  const genreAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "m1",
        name: "主要看什么",
        desc: "直接给几个看点，你**勾选**采纳（可多选/单选，也可以都别勾、自己写）。输入：题材 + 书名 + 简介 + 你已写的那句话",
        onClick: () => runGenreAi("m1", "core_promise", { multi: true }),
      },
      {
        key: "m2",
        name: "绝对禁止",
        desc: "本格问题：这本书绝不出现什么？输入：题材 + 02 的承诺 + 简介",
        onClick: () => runGenreAi("m2", "forbidden_list"),
      },
      {
        key: "m3",
        name: "吃苦指数",
        desc: "本格问题：主角得到好处，要付多大代价？输入：题材 + 02 的承诺 + 03 的禁项",
        onClick: () => runGenreAi("m3", "cost_ratio"),
      },
      {
        key: "m4",
        name: "本小说斗什么",
        desc: "本格问题：全书主要斗的是什么？输入：题材 + 02 的承诺 + 简介",
        onClick: () => runGenreAi("m4", "battlefield"),
      },
    ],
    [runGenreAi],
  );

  // 伏笔右栏四行（foreshadow-settings-v2；data-aiact h1-h4）：h2/h4 无选中置灰＋hint；
  // 行点击经 hooksRef 分发（伏笔面板 runAi；批2 起草/体检为真能力，h2/h4 留批3）
  const foreshadowAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "h1",
        name: "起草伏笔",
        desc: "按你的简介＋题材＋世界＋主线给 3 条候选，勾选采纳 · 输入：简介＋题材＋世界＋主线",
        onClick: () => runHooksAi("h1"),
      },
      {
        key: "h2",
        name: "拟收束方案",
        desc: "对当前选中的伏笔给收束方案 · 采纳后写入收束记录并移入已收束 · 输入：当前伏笔＋主线＋已写章纲",
        disabled: !hookCtx,
        hint: hookCtx ? undefined : "先选一条伏笔",
        onClick: () => runHooksAi("h2"),
      },
      {
        key: "h3",
        name: "埋坑体检",
        desc: "扫全部活跃伏笔 × 已写章纲：埋了没还的点名，给出建议收束章 · 只提醒不拦确认；章纲未建时降级为纯台账自检",
        onClick: () => runHooksAi("h3"),
      },
      {
        key: "h4",
        name: "查一致性",
        desc: "只查当前选中伏笔 × 简介/题材/世界：钩子是否与设定矛盾、代价是否对得上 · 只提醒不拦确认",
        disabled: !hookCtx,
        hint: hookCtx ? undefined : "先选一条伏笔",
        onClick: () => runHooksAi("h4"),
      },
    ],
    [hookCtx, runHooksAi],
  );

  // 文风右栏四行（style-settings-v2；data-aiact s1-s4）：蒸馏跳量化页签并打开样本面板。
  // 蒸馏＝style-quant（MAX 专属，四档拆 key）——maxlk 锁视觉但保持可点，非 MAX 点击
  // 端内直出升级口（member-block），不发请求；前端快照误放行时后端 style-quant 门
  // 403 兜底。（AiWriterAssistant 行契约：锁定行 SHALL NOT disabled——吞 click 即无出口）
  const styleQuant = useFeature("style-quant");
  const styleAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "distill",
        name: "蒸馏我的文风",
        desc: "交 3,000–10,000 字你认可的案例 → 出「作者画像」给你确认 → 六行基线落卡 · 输入：粘贴文本、novel-samples 或已归档章节",
        badge: styleQuant ? undefined : <span className="pill pill-warn">{upgradeHintOf("style-quant")}</span>,
        variant: styleQuant ? undefined : "maxlk",
        onClick: () => {
          if (!styleQuant) {
            // 端内直出升级口（zhuque 行先例）；后端 style-quant 门仍是权威兜底
            window.dispatchEvent(
              new CustomEvent("member-block", { detail: { message: "文风蒸馏为 MAX 专属——升级后解锁" } }),
            );
            return;
          }
          runStyleAi("distill");
        },
      },
      {
        key: "polish",
        name: "润色文字文风",
        desc: "按题材文字文风＋简介起草或润色三区，采纳才写回 · 输入：题材＋简介",
        onClick: () => runStyleAi("polish"),
      },
      {
        key: "check",
        name: "锚定体检",
        desc: "文字文风三区锚定自检：身份/红线/手法是否自洽，并与禁用词/句式规则同源对齐 · 只提醒不拦确认",
        onClick: () => runStyleAi("check"),
      },
      {
        key: "fewshot",
        name: "例句提炼",
        desc: "从已归档正文里挑 1–3 条最能代表文风的句子 · 输入：已归档章节",
        onClick: () => runStyleAi("fewshot"),
      },
    ],
    [runStyleAi, styleQuant],
  );

  useEffect(() => {
    if (initialPanel) setPanel(normalizePanel(initialPanel));
  }, [initialPanel]);

  // 页签回默认主页（c-write-home-rail-anchor）：重复点「设定」→ 面板拨回默认项。
  // 只认值变化（首帧的 0 不算），回执由既有 [panel] effect 一并清。
  const firstHomeSeq = useRef(homeSeq ?? 0);
  useEffect(() => {
    if (homeSeq === undefined || homeSeq === firstHomeSeq.current) return;
    firstHomeSeq.current = homeSeq;
    setPanel(normalizePanel(undefined));
  }, [homeSeq]);

  const handleDirtyChange = useCallback(
    (v: boolean) => {
      setDirty(v);
      onDirtyChange?.(v);
    },
    [onDirtyChange],
  );

  const handleSelect = useCallback(
    (k: string) => {
      if (k === panel) return;
      if (dirty) {
        const ok = window.confirm(
          "当前设定面板有未保存的修改，切换面板将丢失这些修改。确定继续吗？",
        );
        if (!ok) return;
      }
      handleDirtyChange(false);
      setPanel(k); // 回执由 [panel] 的 effect 统一清（见 receipt 声明处）
    },
    [panel, dirty, handleDirtyChange],
  );

  // 主线卡共享状态（settings-three-col）：表单与右栏 AI 向导同源，向导落卡不覆盖表单编辑
  const arcCtl = useStoryArc(projectId, panel === "arc", handleDirtyChange);

  const item = SETTINGS_ITEMS.find((i) => i.k === panel);
  const isModel = panel === "aiModel";
  // §5.1 三态：已确认（/settings/status 的确认标记）> 已填（/readiness 内容判定）> 未填。
  // 已确认 ONLY 来自确认标记存档——存草稿/内容就绪（readiness）不得误标「已确认」。
  const confirmed = item ? !!confirmedStatus?.[item.settingsKey] : false;
  const filled = item ? !!settingsStatus?.[item.settingsKey] : false;

  // ── 进度（两态口径：done/empty；readiness 拉取失败按 0 计，与 modnav 一致）──
  const total = SETTINGS_ITEMS.length;
  // 设定完成入口（settings-done-entry 用户拍板）：N/7 数的是「已确认」——
  // 内容齐了但没点确认不算完成；已填与否仍看 settingsStatus（每项徽标）
  const done = confirmedStatus
    ? SETTINGS_ITEMS.filter((i) => confirmedStatus[i.settingsKey]).length
    : 0;
  const progNote =
    done === total
      ? "设定项全部确认"
      : `${total - done} 项未填 · 均可后补`;

  // ── 确认完成 / 保存修改（gap3：先 save 后 confirm；已确认态只 save）────
  /** 当前面板的保存句柄（简介/题材各自挂 ref，其余走 formRef）。 */
  const currentHandle = useCallback(
    (): SettingSaveHandle | null =>
      panel === "genre"
        ? genreRef.current
        : panel === "intro"
          ? introRef.current
          : panel === "world"
            ? worldRef.current
            : formRef.current,
    [panel],
  );

  /** 存草稿：只落库、不确认、不前进（§5.1 草稿＝进行中）。 */
  const handleSaveDraft = useCallback(async () => {
    if (!item || busy) return;
    setBusy(true);
    try {
      const saved = await currentHandle()?.save();
      if (saved === true) {
        setReceipt(null); // 同上：落库后回执的撤销不再成立
        toast.success(`「${item.name}」已存草稿`);
      }
    } finally {
      setBusy(false);
    }
  }, [item, busy, currentHandle]);

  const handleFootAction = useCallback(async () => {
    if (!item || busy) return;
    // tasks 2.4：移除前端「空内容阻断」gate——全页无必填、确认永远可点；
    // 内容为空时由后端 400 提示（confirmSetting 的 catch 已承接「还未填写内容」），
    // 「跳过」＝直接切到下一个 tab（顺序是引导不是锁）。
    setBusy(true);
    try {
      // 简介（IntroPanel）挂的是 introRef —— 漏分发会拿到 undefined 并带空数据
      // 去 confirm（后端 400）；改为严格 true 才继续，false/undefined 一律中止。
      const handle = currentHandle();
      const saved = await handle?.save();
      if (saved !== true) return;
      // 伏笔确认门禁（提示性预检）：≥1 条描述非空（任意状态）——按钮恒可点不 disable，
      // 这里只提示性拦下；后端 confirm 400 兜底（同「伏笔不能为空…先跳过」口径）
      if (panel === "foreshadow" && handle?.canConfirm?.() === false) {
        toast.info("伏笔不能为空：先埋一条——写一句描述就行；或先跳过，写作期回来补");
        return;
      }
      if (panel === "style" && handle?.canConfirm?.() === false) {
        toast.info("先写叙事身份：一句话说清镜头多近、什么态度——这是每一章的地基");
        return;
      }
      // 保存成功＝这次改动已落库，回执里的撤销只能改回内存（与库不一致）→ 清掉
      setReceipt(null);
      // 角色确认走两档门禁端点（review P1：此前只 PUT status，门禁从未生效，
      // 新书更是永远 400）：首次档只查主角卡，此后档全量六项
      if (panel === "chars") {
        try {
          await charactersApi.confirm(projectId, !confirmed);
        } catch (e) {
          toast.error((e as Error).message || "确认未通过");
          handle?.markDirty?.();
          return;
        }
      }
      if (confirmed) {
        handle?.clearAi?.();
        // 已确认态再点＝重新确认：内容指纹基线随之前移（伏笔徽标恢复「已确认」系）
        handle?.markConfirmed?.();
        // 角色：存档被重盖过 → 立刻重取确认存档状态，徽标与页脚当场从「内容有变」恢复
        // （伏笔的基线在面板本地，markConfirmed 已即时生效，不需要重取）
        if (panel === "chars") onRefreshConfirmState?.();
        toast.success(
          AUTO_SAVE_PANELS.has(panel) ? `「${item.name}」已重新确认` : `「${item.name}」已保存`,
        );
      } else {
        const ok = await confirmSetting(item.settingsKey);
        if (ok) {
          handle?.clearAi?.();
          // 伏笔：确认成功＝快照内容指纹（之后内容有变→徽标降级「内容有变 · 待重新确认」）
          handle?.markConfirmed?.();
          toast.success(`「${item.name}」已确认`);
          // 确认即前进：切到 SETTINGS_ITEMS 的数组顺序下一项（末项不动；
          // 模型窗（aiModel）不在 SETTINGS_ITEMS，天然被跳过）
          const idx = SETTINGS_ITEMS.findIndex((i) => i.k === panel);
          const next = idx >= 0 ? SETTINGS_ITEMS[idx + 1] : undefined;
          if (next) setPanel(next.k);
          else if (done + 1 >= total) toast.success("设定全部完成，可以开写了");
        } else {
          // O-4：save 成功但 confirm 400（服务端读到的不一致）→ 保留 dirty，不假装已确认
          handle?.markDirty?.();
        }
      }
    } finally {
      setBusy(false);
    }
  }, [item, panel, confirmed, busy, confirmSetting, done, total, currentHandle, projectId, onRefreshConfirmState]);

  const panelTitle = isModel ? "模型设定" : (item?.name ?? "");
  // 模型窗不是设定完成度项 → 徽标改为**真实就绪态**（与面板内「当前状态」同源，D13）
  const MODEL_BADGE: Record<string, { cls: string; label: string; ok: boolean }> = {
    ready: { cls: BADGE_DONE, label: "可用", ok: true },
    missing_model: { cls: BADGE_EMPTY, label: "未选择", ok: false },
    no_key: { cls: BADGE_EMPTY, label: "未配置", ok: false },
    member_required: { cls: BADGE_EMPTY, label: "需会员", ok: false },
    invalid: { cls: "err", label: "配置失效", ok: false },
  };
  const modelBadge = MODEL_BADGE[aiState] ?? MODEL_BADGE.no_key;
  const isChars = panel === "chars";
  const isForeshadow = panel === "foreshadow";
  // 角色第三态（character-settings-v2）：确认过但内容指纹变了 → 「内容有变 · 待重新确认」
  // （文案刻意不含「已确认」，守 §5「已确认→ok 绿」硬规则）
  const charsStaleBadge = isChars && confirmed && charStale;
  // 伏笔徽标五态（foreshadow-settings-v2）：由 HooksSettingForm 按台账内容＋确认态上报——
  // 还没有伏笔=empty／N 条待收束=warn／已确认 · N 条待收束=done／全部收束=ok／内容有变=warn（最高优先）
  const hookBadge = isForeshadow ? hookPanelState : null;
  const badgeCls = isModel
    ? modelBadge.cls
    : hookBadge
      ? hookBadge.cls
      : charsStaleBadge
        ? "warn"
        : confirmed
          ? BADGE_DONE
          : filled
            ? "warn"
            : BADGE_EMPTY;
  const badgeLabel = isModel
    ? modelBadge.label
    : hookBadge
      ? hookBadge.label
      : charsStaleBadge
        ? "内容有变 · 待重新确认"
        : confirmed
          ? "已确认"
          : filled
            ? "已填"
            : "未填";
  const badgeOk = isModel ? modelBadge.ok : hookBadge ? hookBadge.ok : badgeCls === BADGE_DONE;
  const hookEmpty = isForeshadow && !!hookPanelState?.empty;
  // 内容有变（c-chars-stale-reconfirm）：角色＝服务端确认存档过期；伏笔＝面板本地指纹快照。
  // 让位口径——stale 期间页脚不以「已确认」表述、不渲染绿色已确认标注（warn 只由徽标给一次）。
  const panelStale = (isChars && !!charStale) || (isForeshadow && !!hookPanelState?.stale);
  // 角色面板页脚提示（c-chars-confirm-scope）：讲的是**整项**（书内所有角色卡）而不是当前选中卡，
  // 且按这次点击将要适用的档位出摘要——未确认＝第一次确认档只查主角，已确认＝此后档点名首卡。
  // 缺口来自列表响应（CharacterManager 上抛），此处只负责措辞与语气。
  const charsGateNote = useMemo((): { text: string; warn: boolean } | null => {
    if (!isChars || !charGateHint) return null; // 列表未就绪：退回通用 note，不喊不存在的缺口
    const h = charGateHint;
    if (h.noProtagonist) {
      return { text: "确认「角色」要先有一位主角——在人物卡上把谁点成主角", warn: true };
    }
    if (!confirmed) {
      if (h.protagonistMissing.length) {
        return {
          text: `还差：主角《${h.protagonistName || "未命名"}》缺 ${h.protagonistMissing.join("、")}（第一次确认只看主角）`,
          warn: true,
        };
      }
      return {
        text: "主角写全了——第一次确认只看主角；配角、反派后补也行，改动会自动保存",
        warn: false,
      };
    }
    if (h.gapCards.length) {
      const first = h.gapCards[0];
      const fields =
        first.fields.slice(0, 3).join("、") + (first.fields.length > 3 ? " 等" : "");
      const more = h.gapCards.length > 1 ? `（共 ${h.gapCards.length} 张卡）` : "";
      return {
        text: `还差：${first.role}《${first.name || "未命名"}》缺 ${fields}${more}`,
        warn: true,
      };
    }
    // 缺口优先（上面那条）；无缺口但内容有变 → 让位文案，不出现「已确认」
    if (panelStale) {
      return { text: "内容改过了——点「重新确认」即可，改动已自动保存", warn: false };
    }
    return { text: "已确认 · 改动自动保存，可随时重新确认", warn: false };
  }, [isChars, charGateHint, confirmed, panelStale]);
  const panelDesc = isModel
    ? "本书写作所用的模型、变更历史与用量。"
    : (DESCS[panel] ?? "");
  const panelNote = isModel
    ? "工具项 · 不参与设定进度"
    : isForeshadow
      ? hookPanelState?.stale
        ? "内容改过了——点「重新确认」即可，改动已自动保存"
        : confirmed
          ? "已确认 · 可随时回来修改并重新确认"
          : "改动自动保存 · 确认后停留本格（已是最后一项）"
      : confirmed
        ? "已确认 · 可随时回来修改并重新确认"
        : item?.canDefer
          ? "高级项可后补 · 确认即计入进度"
          : "确认后计入设定进度";

  return (
    <div className="view three-col on settings-v">
      <aside className="col-tree">
        <div className="tree-head">
          <span className="t">
            设定 · <b>{SETTINGS_ITEMS.length}</b> 项 + 1 工具
          </span>
        </div>
        <div className="settings-progress">
          <span className={`pl num${done === total ? " done" : ""}`}>
            设定 <b>{done}</b>/{total}
          </span>
          <div className={`pbar${done === total ? " done" : ""}`}>
                <i style={{ width: `${(done / total) * 100}%` }} />
          </div>
        </div>
        {done === total && onGoWrite && (
          // 设定完成入口（settings-done-entry）：进度行本体升级为完成卡——
          // 对勾＋「设定完成 N/N」＋「全部就绪」＋满格绿条＋「去写作」CTA。
          // 旧全宽普通主按钮退役（评审：完成态不该长得和「保存」一样）。
          <div className="settings-progress done" data-od-id="settings-done-card">
            <span className="pb-check" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="15" height="15">
                <circle cx="12" cy="12" r="9" strokeWidth="1.8" />
                <path d={CHECK_PATH} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className="pl num">
              设定完成 <b>{total}/{total}</b>
            </span>
            <span className="pb-badge">全部就绪</span>
            <div className="pbar">
              <i style={{ width: "100%" }} />
            </div>
            <button
              className="btn btn-primary done-btn"
              type="button"
              data-od-id="btn-go-write"
              onClick={onGoWrite}
            >
              去写作
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14" aria-hidden="true">
                <path d="M5 12h14m-6-6 6 6-6 6" />
              </svg>
            </button>
            <p className="done-foot">写作时也能回来改设定，不冲突</p>
          </div>
        )}
        <div className="settings-nav-wrap">
          {/* 00 模型设定：工具项，排在最前（用户 2026-09-10 指定） */}
          <div
            className={`s-item${panel === "aiModel" ? " on" : ""}`}
            onClick={() => handleSelect("aiModel")}
            data-od-id="nav-model"
          >
            <span className="nm">模型设定</span>
            <span className="defer-tag">工具</span>
            <span className="spacer" />
            {/* 工具项无「确认」语义（D15/O-18 已移除 ai-model 可确认）→ 不挂确认徽标 */}
            <span className="badge empty">不参与进度</span>
          </div>
          {SETTINGS_ITEMS.map((i) => {
            const done_ = !!settingsStatus?.[i.settingsKey];
            // 5.4 三级阶梯：确认 > 已填 > 未填——已填不再冒充已确认（中间徽标同源）
            const confirmed = !!confirmedStatus?.[i.settingsKey];
            const badgeCls = confirmed ? BADGE_DONE : done_ ? "warn" : BADGE_EMPTY;
            const badgeLabel = confirmed ? "已确认" : done_ ? "已填" : "未填";
            return (
              <div
                key={i.k}
                className={`s-item${panel === i.k ? " on" : ""}`}
                onClick={() => handleSelect(i.k)}
              >
                <span className="nm">{i.name}</span>
                {i.canDefer && !done_ && <span className="defer-tag">可后补</span>}
                <span className="spacer" />
                <span className={`badge ${badgeCls}`}>
                  <BadgeIcon ok={confirmed} />
                  {badgeLabel}
                </span>
              </div>
            );
          })}
        </div>
        <div className="tree-foot">
          <span style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7 }}>
            {progNote}
          </span>
        </div>
      </aside>

      <main className="col-middle">
        <div className="col-panel">
        <div
          className={`panel${panel === "chars" || panel === "foreshadow" ? " sub-fill" : ""}`}
        >
          <div className="panel-head">
            <h2>{panelTitle}</h2>
            <span className={`badge ${badgeCls}`}>
              <BadgeIcon ok={badgeOk} />
              {badgeLabel}
            </span>
          </div>
          <p className="desc">{panelDesc}</p>

          <div
            className={panel === "chars" || panel === "foreshadow" ? "sub-wrap" : undefined}
          >
            {panel === "genre" && (
              <GenreSettingForm
                ref={genreRef}
                projectId={projectId}
                settingKey="genre"
                onDirtyChange={handleDirtyChange}
                onReceiptChange={handleReceiptChange}
                novelName={novelName}
              />
            )}
            {panel === "intro" && (
              <IntroPanel
                ref={introRef}
                novelName={novelName}
                projectId={projectId}
                onDirtyChange={handleDirtyChange}
                onReceiptChange={handleReceiptChange}
              />
            )}
            {panel === "arc" && (
              <StoryArcForm
                ref={(h) => {
                  // 双 ref：formRef 供 panel-foot save/confirm；arcFormRef 供右栏 runAi 分发
                  (formRef as React.MutableRefObject<SettingSaveHandle | null>).current = h;
                  arcFormRef.current = h;
                }}
                projectId={projectId}
                ctl={arcCtl}
                onReceiptChange={handleReceiptChange}
              />
            )}
            {panel === "world" && (
              <WorldSettingPanel
                ref={worldRef}
                projectId={projectId}
                onDirtyChange={handleDirtyChange}
                onReceiptChange={handleReceiptChange}
                onGotoPanel={(k) => handleSelect(k)}
                onNoPowerChange={setWorldNoPower}
              />
            )}
            {panel === "style" && (
              <StyleSettingForm
                ref={(h) => {
                  // 双 ref：formRef 供 panel-foot save/confirm；styleRef 供右栏 runAi 分发
                  (formRef as React.MutableRefObject<SettingSaveHandle | null>).current = h;
                  styleRef.current = h;
                }}
                projectId={projectId}
                settingKey="style"
                onDirtyChange={handleDirtyChange}
                onReceiptChange={handleReceiptChange}
              />
            )}
            {panel === "foreshadow" && (
              <HooksSettingForm
                ref={(h) => {
                  // 双 ref：formRef 供 panel-foot save/confirm；hooksRef 供右栏 runAi 分发
                  (formRef as React.MutableRefObject<SettingSaveHandle | null>).current = h;
                  hooksRef.current = h;
                }}
                projectId={projectId}
                settingKey="hooks"
                onDirtyChange={handleDirtyChange}
                onSaveStateChange={setHookSaveState}
                onPanelState={setHookPanelState}
                onCtxChange={setHookCtx}
                aiState={aiState}
                onBlocked={handleAiBlocked}
                confirmed={!!confirmedStatus?.hooks}
              />
            )}
            {panel === "chars" && (
              <CharacterManager
                ref={formRef}
                projectId={projectId}
                onDirtyChange={handleDirtyChange}
                onCtxChange={setCharCtx}
                onGateHintChange={setCharGateHint}
                onRefreshConfirmState={onRefreshConfirmState}
                introReady={!!settingsStatus?.synopsis}
                aiState={aiState}
                onBlocked={handleAiBlocked}
              />
            )}
            {panel === "aiModel" && (
              <ModelSettingForm
                projectId={projectId}
                settingKey="ai-model"
                onDirtyChange={handleDirtyChange}
                onModelChanged={refreshAiState}
                onReceiptChange={handleReceiptChange}
              />
            )}
          </div>

          <div className="panel-foot">
            {/* 伏笔空表：warnline 取代 note（常驻信号，非 toast；门禁的提示性预检口径） */}
            {hookEmpty && (
              <span className="warnline" data-od-id="hook-hint" style={{ marginRight: "auto" }}>
                确认「伏笔」至少要埋一条——写一句描述就行；也可以先跳过，写作期回来补
              </span>
            )}
            {!hookEmpty && charsGateNote?.warn && (
              <span className="warnline" data-od-id="chars-gate-hint" style={{ marginRight: "auto" }}>
                {charsGateNote.text}
              </span>
            )}
            {!hookEmpty && !charsGateNote?.warn && (
              <span className="note" style={{ marginRight: "auto" }}>
                {charsGateNote ? charsGateNote.text : panelNote}
              </span>
            )}
            {/* 改动回执（在模型设定/简介/题材/世界四面板发声；其余面板恒 null） */}
            <ChangeReceiptBar receipt={receipt} />
            {confirmed && !isModel && !panelStale && (
              <span className="done-note">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d={CHECK_PATH} />
                </svg>
                已确认
              </span>
            )}
            {/* 「存草稿」对伏笔隐藏（自动保存制——草稿态＝已落库未确认，foreshadow-settings-v2） */}
            {!isModel && !confirmed && panel !== "chars" && panel !== "foreshadow" && (
              <button
                className="btn btn-secondary"
                onClick={() => void handleSaveDraft()}
                disabled={busy}
                data-od-id="btn-save-draft"
              >
                存草稿
              </button>
            )}
            {/* 伏笔面板脚保存态（自动保存制；「存草稿」对伏笔隐藏——草稿态＝已落库未确认） */}
            {isForeshadow && (
              <span className={`save-state ${hookSaveState}`} data-od-id="save-state">
                {hookSaveState === "saving" && "保存中…"}
                {hookSaveState === "saved" && "已自动保存"}
                {hookSaveState === "dirty" && "有未保存修改"}
                {hookSaveState === "failed" && "保存失败 · 请重试"}
              </span>
            )}
            {!isModel && (
              <button
                className="btn btn-primary"
                onClick={() => void handleFootAction()}
                disabled={busy}
              >
                {/* 自动保存制面板的已确认态＝重新确认（改动早已落库，按钮不再叫「保存修改」） */}
                {confirmed ? (AUTO_SAVE_PANELS.has(panel) ? "重新确认" : "保存修改") : "确认完成"}
              </button>
            )}
          </div>
        </div>
        </div>
      </main>

      {/* 右侧 AI 栏（settings-three-col）：与写作页右栏同构；主线时为四步向导 */}
      <aside className="col-ai">
        {panel === "intro" ? (
          <AiWriterAssistant
            rows={introAiRows}
            footNote="输入：书名 + 简介本文（题材可后补）。结果在弹窗里过目，确认才写回；重开同一行先看上次结果，「换一个」才重新生成。"
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
          />
        ) : panel === "genre" ? (
          <AiWriterAssistant
            rows={genreAiRows}
            footNote="点某行，AI 建议在弹窗里过目，确认才写回对应格；关闭即弃，可换一个重生成。"
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-genre"
          />
        ) : panel === "arc" ? (
          <AiWriterAssistant
            rows={arcAiRows}
            footNote="建议在弹窗里过目，点「采纳 · 覆盖」才写入，面板底部可一步撤销；重开同一行先看上次结果，「换一个」才重新生成。"
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-arc"
          />
        ) : panel === "world" ? (
          <AiWriterAssistant
            rows={worldAiRows}
            footNote={
              worldNoPower
                ? "本书开了现实向：力量两行已退场，物理与法律规则在「更多世界细节」里补。"
                : "答案在弹窗里过目，采纳 · 覆盖才写回，脚部有回执可一步撤销；体检报告可点「AI 补」逐项补，补完自动回报告。体检缺输入走降级，不拦确认。"
            }
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-world"
          />
        ) : panel === "chars" ? (
          <CharsAiRail
            ctx={charCtx}
            aiState={aiState}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            onRun={runCharsAi}
          />
        ) : panel === "foreshadow" ? (
          <AiWriterAssistant
            rows={foreshadowAiRows}
            footNote="答案在弹窗里过目，采纳 · 覆盖才写回（覆盖已有收束记录时按钮明示「覆盖并收束」，采纳仍可一步撤销）；回执只留最近一条、8 秒内可点撤销；埋坑体检报告行可点跳转对应伏笔。所有 AI 辅助功能都在本栏，伏笔卡编辑区不放 AI 按钮；免费版四行可见＋锁定，点击走统一升级提示。"
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-foreshadow"
          />
        ) : panel === "style" ? (
          <AiWriterAssistant
            rows={styleAiRows}
            footNote="蒸馏学到的禁用词会自动并入硬约束区下方的「禁用词」组并去重；机器写的章永不回写文风卡——重蒸馏只由你触发，每次蒸馏都有版本快照；要保住的基线行锁定即可，重蒸馏跳过。所有 AI 辅助功能都在本栏，编辑区不放 AI 按钮；免费版四行可见＋锁定，点击走统一升级提示。"
            aiState={aiState}
            aiStateMessage={aiMessage}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-style"
          />
        ) : (
          <div className="rail-card">
            <b>当前设定项暂无 AI 功能</b>
            <p className="opt" style={{ fontSize: 12 }}>
              「主线」面板的右栏是 AI 拆主线四步向导；世界/风格的字段旁有「AI 帮我填」。
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

// ── 简介面板（SynopsisCard 收编为第 2 项：x/500 计数为 spec#3 顺手修）──────
export interface IntroHandle extends SettingSaveHandle {
  isEmpty: () => boolean;
  focus: () => void;
  /** 运行 AI 能力（体检/补缺失/润色）——结果进弹窗出卡（c-settings-ai-confirm-modal）。 */
  runAi: (action: IntroAiAction) => Promise<void>;
  /** 是否已体检（补缺失的前置守卫，D14/O-3）。 */
  hasIntrospected: () => boolean;
}

/** 标题对照三态的展示文案（只提示，不代改书名）。 */
const TITLE_FIT_LABEL: Record<"ok" | "mismatch" | "generic", string> = {
  ok: "标题对照：一致",
  mismatch: "标题对照：与简介不符",
  generic: "标题对照：标题无信息",
};

const IntroPanel = forwardRef<
  IntroHandle,
  {
    projectId: string;
    novelName?: string;
    onDirtyChange?: (dirty: boolean) => void;
    onReceiptChange?: (r: ChangeReceiptState | null) => void;
  }
>(function IntroPanel({ projectId, novelName, onDirtyChange, onReceiptChange }, ref) {
    const [synopsis, setSynopsis] = useState("");
    const [saving, setSaving] = useState(false);
    const taRef = useRef<HTMLTextAreaElement>(null);
    // P3-4：用户已手动输入时，晚到的挂载 fetch 不得覆盖输入
    const editedRef = useRef(false);
    const { snapshotLoaded, markSaved, markDirty } = useDirtyState(synopsis, onDirtyChange);
    // 改动回执（用户 2026-09-10）：AI 采纳＝一键覆盖整段 → 脚部回执 + 一步撤销
    const { record: recordChange } = useChangeReceipt(onReceiptChange);
    /** 简介的「打开时原值」：自己敲的字 → 失焦后给「恢复到打开时的原文」。 */
    const baseTextRef = useRef("");
    const [textHint, setTextHint] = useState(false);
    /** 采纳时刻的真实「改前值」（sink 是结果到达时创建的，闭包里的 synopsis 会过期）。 */
    const synopsisRef = useRef("");
    useLayoutEffect(() => {
      synopsisRef.current = synopsis;
    });
    // 前置守卫（O-3）：补缺失必须先体检拿到缺失段
    const introspectedRef = useRef(false);

    useEffect(() => {
      let cancelled = false;
      api
        .fetchStory(projectId)
        .then((r) => {
          if (!cancelled && !editedRef.current) {
            setSynopsis(r.synopsis ?? "");
            baseRef.current = r.synopsis ?? "";
            baseTextRef.current = r.synopsis ?? "";
            snapshotLoaded(r.synopsis ?? "");
          }
        })
        .catch(() => {});
      return () => {
        cancelled = true;
      };
      // snapshotLoaded 引用稳定（useDirtyState useCallback）；仅项目切换重拉
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [projectId]);

    const save = useCallback(async (): Promise<boolean> => {
      if (saving) return false;
      setSaving(true);
      try {
        const r = await api.updateStory(projectId, synopsis);
        setSynopsis(r.synopsis);
        markSaved();
        // 保存＝新的「原文」：基线前移 + 撤下提示（否则一键恢复会把刚保存的内容改回旧版）
        baseTextRef.current = r.synopsis ?? "";
        setTextHint(false);
        return true;
      } catch {
        toast.error("简介保存失败");
        return false;
      } finally {
        setSaving(false);
      }
    }, [projectId, synopsis, saving, markSaved]);


    const [guideOpen, setGuideOpen] = useState(false);
    // AI 出卡确认弹窗（c-settings-ai-confirm-modal）：每个能力缓存最近一版结果，
    // 重开同一行直接展示缓存不再发请求，「换一个」才重新生成（D9）；采纳＝确认后整段替换输入框。
    const [cards, setCards] = useState<Partial<Record<IntroAiAction, AiCardState>>>({});
    const [versions, setVersions] = useState<Partial<Record<IntroAiAction, number>>>({});
    const [cardAction, setCardAction] = useState<IntroAiAction | null>(null);
    const [cardOpen, setCardOpen] = useState(false);
    const [cardError, setCardError] = useState("");
    /** 运行态：点完立刻开弹窗给「生成中」占位，避免用户以为没反应（D14）。 */
    const [aiRunning, setAiRunning] = useState<IntroAiAction | null>(null);
    /** 面板级在途锁（ref 同步判定）：无论调用方点几次，同时在飞的只有一个请求。 */
    const aiBusyRef = useRef(false);

    /** 手写内容＝合成基准：手动编辑时更新；采纳结果不回写基准（防多次采纳叠加）。 */
    const baseRef = useRef("");

    /** 采纳成功后收尾：关弹窗（确认写回＝弹窗自动关）。 */
    const closeCard = useCallback(() => setCardOpen(false), []);

    /** 缓存命中：只开弹窗展示既有结果，不发请求（D9）。 */
    const openCached = useCallback((action: IntroAiAction) => {
      setCards((prev) => (prev[action] ? { ...prev, [action]: { ...prev[action]!, cached: true } } : prev));
      setCardError("");
      setCardAction(action);
      setCardOpen(true);
    }, []);

    const runRequest = useCallback(
      async (action: IntroAiAction, content: string) => {
        aiBusyRef.current = true;
        setAiRunning(action);
        setCardError("");
        setCardAction(action);
        setCardOpen(true);
        try {
          const r = await introAi(action, { title: novelName ?? "", content }, projectId);
          if (action === "introspect") {
            introspectedRef.current = true;
            const segs = r.six_segments ?? [];
            const hits = r.taboo?.hits ?? [];
            setCards((prev) => ({
              ...prev,
              [action]: {
                label: "AI 体检 · 六段逐项",
                kind: "report",
                cached: false,
                node: (
                  <>
                    {/* 行名按模板单源顺序渲染（后端只提供 status/note），保证与六段模板逐字一致 */}
                    <div className="chk-grid">
                    {INTRO_SEGMENTS.map((seg) => {
                      const s = segs.find((x) => x.name === seg.name);
                      return (
                        <div className="chk-line" key={seg.name}>
                          <span className="chk-name">{seg.name}</span>
                          <span className={`chk-res ${s?.status === "ok" ? "ok" : "miss"}`}>
                            {s?.status === "ok" ? "达标" : "缺失"}
                          </span>
                          <span className="chk-note">{s?.note ?? s?.excerpt ?? ""}</span>
                        </div>
                      );
                    })}
                    </div>
                    <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
                      禁忌扫描：
                      {hits.length
                        ? hits.map((h) => h.rule).join(" / ")
                        : `无 ${TABOO_RULES.join(" / ")}`}
                      {r.verdict ? ` · 结论：${r.verdict}` : ""}
                    </p>
                    {/* 标题对照（D21）：只提示、不提供改书名入口——改不改由作者自己决定 */}
                    {r.title_check && (
                      <div className="title-check" data-od-id="intro-title-check">
                        <span className={`tc-res ${r.title_check.fit === "ok" ? "ok" : "warn"}`}>
                          {TITLE_FIT_LABEL[r.title_check.fit]}
                        </span>
                        {r.title_check.note && <span className="tc-note">{r.title_check.note}</span>}
                        {r.title_check.suggestions.length > 0 && (
                          <span className="tc-sug">
                            可考虑：
                            {r.title_check.suggestions.map((s) => (
                              <span className="tc-chip" key={s}>
                                {s}
                              </span>
                            ))}
                            <span className="tc-tip">（仅供参考，改不改由你定）</span>
                          </span>
                        )}
                      </div>
                    )}
                  </>
                ),
              },
            }));
          } else if (action === "fill") {
            const miss = r.missing ?? [];
            setCards((prev) => ({
              ...prev,
              [action]: {
                label: "补全缺失 · 候选如下，采纳才插入",
                kind: "text",
                adoptText: "采纳 · 替换为补全后的简介",
                cached: false,
                node: (
                  <div>
                    {miss.length ? (
                      miss.map((m) => (
                        <p key={m.name} style={{ margin: "4px 0" }}>
                          <b>{m.name}</b>：{m.candidate}
                        </p>
                      ))
                    ) : (
                      <p style={{ margin: 0 }}>无需补，六段都齐了。</p>
                    )}
                  </div>
                ),
                adopt: miss.length
                  ? () => {
                      const prevValue = synopsisRef.current;
                      const prevBase = baseRef.current;
                      // 采纳＝**清空原输入、用「手写基准 + 本次候选」整段重写**：
                      // 基准只在手动编辑时更新，故连续采纳不同候选不会层层叠加
                      const base = baseRef.current.trim();
                      const add = miss
                        .map((m) => m.candidate)
                        .join("")
                        .trim();
                      const next = (base ? `${base}。${add}` : add).slice(0, INTRO_MAX_LEN);
                      editedRef.current = true;
                      recordChange(
                        `已采纳「补全缺失」，简介 ${synopsisRef.current.length} 字 → ${next.length} 字`,
                        () => {
                          /* 值在下面落地 */
                        },
                        () => {
                          setSynopsis(prevValue);
                          baseRef.current = prevBase;
                          setTextHint(false);
                        },
                      );
                      setSynopsis(next);
                      closeCard();
                      toast.success(
                        next.length >= INTRO_MAX_LEN
                          ? "已采纳（到 500 字上限，尾部截断）"
                          : "已采纳，整段已替换为「你的原文 + 补全段」，可继续改",
                      );
                    }
                  : undefined,
              },
            }));
          } else {
            const polished = r.polished ?? "";
            setCards((prev) => ({
              ...prev,
              [action]: {
                label: "润色 · 前后对照，采纳才替换",
                kind: "text",
                adoptText: "采纳 · 替换简介",
                cached: false,
                node: (
                  <div>
                    <p style={{ margin: "4px 0", color: "var(--muted)" }}>原句：{r.original ?? ""}</p>
                    <p style={{ margin: "4px 0" }}>
                      <b>润后</b>：{polished}
                    </p>
                  </div>
                ),
                adopt: polished
                  ? () => {
                      const prevValue = synopsisRef.current;
                      const prevBase = baseRef.current;
                      const next = polished.slice(0, INTRO_MAX_LEN);
                      editedRef.current = true;
                      recordChange(
                        `已采纳「润色」，简介 ${synopsisRef.current.length} 字 → ${next.length} 字`,
                        () => {
                          /* 值在下面落地 */
                        },
                        () => {
                          setSynopsis(prevValue);
                          baseRef.current = prevBase;
                          setTextHint(false);
                        },
                      );
                      setSynopsis(next);
                      closeCard();
                      toast.success("已替换，原句可随时改回");
                    }
                  : undefined,
              },
            }));
          }
          setVersions((prev) => ({ ...prev, [action]: (prev[action] ?? 0) + 1 }));
        } catch (e: unknown) {
          const reason = aiBlockReason(e);
          const msg =
            reason === "member_required"
              ? "AI 是会员功能，开通套餐后解锁"
              : reason === "no_key"
                ? (e as Error).message || "先去「模型配置」添加 API Key"
                : reason === "missing_model" || reason === "invalid"
                  ? "先在本书选择模型"
                  : (e as Error).message || "暂不可用，请重试";
          if (cards[action]) {
            setCardError(msg); // 有缓存：错误体进弹窗，旧版仍在
          } else if (reason === "member_required" || reason === "no_key" || reason === "missing_model" || reason === "invalid") {
            setCardOpen(false); // 无缓存＋门控类：关弹窗走 toast 分流
            toast.info(msg);
          } else {
            setCardError(msg); // 其余失败：弹窗滞留展示错误体（可换一个重试）
          }
        } finally {
          aiBusyRef.current = false;
          setAiRunning(null);
        }
      },
      [novelName, projectId, recordChange, closeCard, cards],
    );

    const runAi = useCallback(
      async (action: IntroAiAction) => {
        if (aiBusyRef.current) return; // 已有在途请求：忽略重复触发
        const content = synopsis;
        if (action === "introspect" && !content.trim()) {
          toast.info("先写两句简介，体检才有东西可查");
          return;
        }
        if (action === "fill" && !introspectedRef.current) {
          toast.info("先点「体检」，AI 才知道缺哪段");
          return;
        }
        if (cards[action]) {
          openCached(action); // 重开＝展示缓存，不重复生成（D9）
          return;
        }
        await runRequest(action, content);
      },
      [synopsis, cards, openCached, runRequest],
    );

    useImperativeHandle(
      ref,
      () => ({
        save,
        isEmpty: () => !synopsis.trim(),
        focus: () => taRef.current?.focus(),
        runAi,
        markDirty,
        clearAi: () => {
          setCards({});
          setVersions({});
          setCardAction(null);
          setCardOpen(false);
          setCardError("");
        },
        hasIntrospected: () => introspectedRef.current,
      }),
      [save, synopsis, runAi, markDirty],
    );

    return (
      <>
        <div className="field">
          <label>
            故事简介 <span className="opt">≤{INTRO_MAX_LEN} 字</span>
            {/* 计数紧邻上限说明（原 margin-left:auto 在宽面板下被推到最右，与文案脱节） */}
            <span className="cnt">
              {synopsis.length}/{INTRO_MAX_LEN}
            </span>
          </label>
          <textarea
            ref={taRef}
            className="textarea intro-ta"
            rows={4}
            maxLength={INTRO_MAX_LEN}
            placeholder="用几句话讲讲这个故事是关于什么的（主角、世界、核心冲突）"
            value={synopsis}
            disabled={saving}
            onChange={(e) => {
              editedRef.current = true;
              baseRef.current = e.target.value; // 手动编辑＝新的合成基准
              setSynopsis(e.target.value);
            }}
            onBlur={() => setTextHint(synopsis !== baseTextRef.current)}
          />
          <RestoreHint
            show={textHint}
            onRestore={() => {
              editedRef.current = true;
              baseRef.current = baseTextRef.current;
              setSynopsis(baseTextRef.current);
              setTextHint(false);
            }}
          />
        </div>
        {/* 「怎么写」六段模板——默认收起，点开才展开（tasks 3.1 / D2） */}
        <div className="guide" data-od-id="intro-guide">
          <button
            className="guide-toggle"
            type="button"
            aria-expanded={guideOpen}
            onClick={() => setGuideOpen((v) => !v)}
          >
            <span className="gt-b">「怎么写」六段模板</span>
            <span className="gt-s">
              {INTRO_SEGMENTS.map((s) => s.name).join(" → ")} · 点开看每段怎么写
            </span>
            <span className="gt-c" aria-hidden="true">
              {guideOpen ? "收起" : "展开"}
            </span>
          </button>
          {guideOpen && (
            <div className="guide-body">
              {INTRO_SEGMENTS.map((s) => (
                <div className="g-row" key={s.name}>
                  <span className="g-name">{s.name}</span>
                  <span className="g-body">
                    <em>例：{s.example}</em>
                    {s.why}
                  </span>
                </div>
              ))}
              <span className="g-formula">
                六段公式：<b>{INTRO_FORMULA}</b>
              </span>
              <p className="g-dont">别踩：{DONT_DO.join("；")}。</p>
            </div>
          )}
        </div>

        {/* AI 出卡确认弹窗：三能力共用（关闭即弃；缓存重开免请求） */}
        <AiCardModal
          open={cardOpen && cardAction !== null}
          card={cardAction ? cards[cardAction] ?? null : null}
          running={cardAction !== null && aiRunning === cardAction}
          error={cardAction !== null && aiRunning !== cardAction ? cardError : undefined}
          version={cardAction ? versions[cardAction] : undefined}
          onClose={() => setCardOpen(false)}
          onRegenerate={
            cardAction
              ? () => {
                  const content = synopsis;
                  if (cardAction === "introspect" && !content.trim()) {
                    toast.info("先写两句简介，体检才有东西可查");
                    return;
                  }
                  void runRequest(cardAction, content);
                }
              : undefined
          }
          data-testid="intro-ai-card"
        />

        <p className="opt" style={{ fontSize: 12, margin: "-6px 0 16px" }}>
          简介会作为后续设定和写作的依据。
        </p>
      </>
    );
  },
);
