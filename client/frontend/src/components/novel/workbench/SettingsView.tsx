// 设定视图（book.html #viewSettings 复刻，PR4）：
//   two-col = 左栏（tree-head 设定·7 项 + settings-progress n/7 进度条
//   + 8 导航项 done/empty 两态徽标 + 可后补 tag + tree-foot 口径注）
//   + 右面板（panel-head/badge/desc/panelBody + panel-foot 确认完成）。
// 七项计数与后端 READINESS_KEYS 同源（synopsis=简介 / hooks=伏笔）；
// 模型设定为**第 00 项工具项**（用户 2026-09-10 指定排在最前）：恒 done、无确认按钮、
// 不参与进度（ADJUSTMENTS #4）。
// 产品扩展（ADJUSTMENTS #9）：已确认面板的按钮转「保存修改」——设计稿 done 态
// 无落库入口，保留产品「改完随时存」能力；确认流程沿 gap3（先 save 再 confirm）。
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { useDirtyState } from "@/hooks/useDirtyState";
import { type SettingSaveHandle } from "@/components/novel/settings/FormField";
import WorldSettingForm from "@/components/novel/settings/WorldSettingForm";
import StyleSettingForm from "@/components/novel/settings/StyleSettingForm";
import AntiAiSettingForm from "@/components/novel/settings/AntiAiSettingForm";
import HooksSettingForm from "@/components/novel/settings/HooksSettingForm";
import CharacterManager from "@/components/novel/settings/CharacterManager";
import ModelSettingForm from "@/components/novel/settings/ModelSettingForm";
import StoryArcForm from "@/components/novel/settings/StoryArcForm";
import ArcWizard from "@/components/novel/settings/ArcWizard";
import { useStoryArc } from "@/components/novel/settings/useStoryArc";
import GenreSettingForm, {
  type GenreHandle,
  type GenreAiField,
} from "@/components/novel/settings/GenreSettingForm";
import { INTRO_SEGMENTS, INTRO_FORMULA, DONT_DO, INTRO_MAX_LEN, TABOO_RULES } from "@/lib/introTemplate";
import { GENRE_DEFINITION } from "@/lib/genreVocab";
import { useModelStatus } from "@/hooks/useModelStatus";
import type { AiState } from "@/types/api-config";
import AiWriterAssistant, { type AiCapabilityRow } from "@/components/novel/settings/AiWriterAssistant";
import AiSink from "@/components/novel/settings/AiSink";
import {
  ChangeReceiptBar,
  RestoreHint,
  useChangeReceipt,
  type ChangeReceiptState,
} from "@/components/novel/settings/ChangeReceipt";
import { introAi, aiBlockReason, type IntroAiAction } from "@/lib/ai";

// ── 面板注册表（顺序/命名与原型 navItems 一致；settingsKey 对后端口径）──
// 顺序＝用户 2026-09-10 拍板：00 模型设定（工具项，见下方树内单列）→ 01 简介 →
// 02 题材 → 03 世界 → 04 角色 → 05 主线 → 06 文风 → 07 伏笔 → 08 禁用词句。
// 这一序同时决定「确认即前进」的推进顺序（nextPanel 按本数组取下一项）。
const SETTINGS_ITEMS = [
  { k: "intro", name: "简介", settingsKey: "synopsis", canDefer: false },
  { k: "genre", name: "题材", settingsKey: "genre", canDefer: false },
  { k: "world", name: "世界", settingsKey: "world", canDefer: true },
  { k: "chars", name: "角色", settingsKey: "characters", canDefer: true },
  { k: "arc", name: "主线", settingsKey: "story-arc", canDefer: true },
  { k: "style", name: "文风", settingsKey: "style", canDefer: false },
  { k: "foreshadow", name: "伏笔", settingsKey: "hooks", canDefer: true },
  { k: "antiAI", name: "禁用词句", settingsKey: "anti-ai", canDefer: true },
] as const;

const DESCS: Record<string, string> = {
  genre: GENRE_DEFINITION,
  intro: "让读者（和 AI）知道这是一个怎样的故事。",
  arc: "这本书讲什么、结局想怎样、分几卷——定总方向盘，不拦写作。",
  world: "地理、政治与规则——故事发生的世界如何运转。",
  style: "用谁的视角讲，用什么语气讲（叙事身份 + 核心原则）。",
  antiAI: "这些词句一出现就拦掉——AI 味最重的那批。",
  foreshadow: "先埋下的，后面要还。",
  chars: "核心角色是谁，他们想要什么。",
};

const BADGE_DONE = "ok";
const BADGE_EMPTY = "empty";
const CHECK_PATH = "M5 13l4 4L19 7";

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
  settingsStatus: Record<string, boolean> | null;
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
    world: "world", style: "style", "anti-ai": "antiAI",
    hooks: "foreshadow", characters: "chars", "ai-model": "aiModel",
  };
  return (v && map[v]) || "intro";
}

export default function SettingsView({
  projectId, initialPanel, settingsStatus, confirmedStatus, confirmSetting, onDirtyChange, onGoWrite, novelName,
}: SettingsViewProps) {
  const [panel, setPanel] = useState(() => normalizePanel(initialPanel));
  /** 改动回执（用户 2026-09-10）：三面板里"一键改变内容"的动作在脚部留一条 + 一步撤销。 */
  const [receipt, setReceipt] = useState<ChangeReceiptState | null>(null);
  const handleReceiptChange = useCallback((r: ChangeReceiptState | null) => setReceipt(r), []);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  const formRef = useRef<SettingSaveHandle>(null);
  const genreRef = useRef<GenreHandle>(null);
  const introRef = useRef<IntroHandle>(null);
  // D13：AI 行的门控只读后端 ai_state 一次分派（不再 useFeature + 本地推导两处判）
  const { aiState, refresh: refreshAiState } = useModelStatus(projectId);
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
  const handleAiBlocked = useCallback((reason: AiState) => {
    if (reason === "no_key") {
      window.location.hash = "/config";
      return;
    }
    if (reason === "missing_model" || reason === "invalid") {
      setPanel("aiModel");
      return;
    }
    toast.info("这是会员功能，升级 PRO 后解锁——免费版写作能力完整");
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

  useEffect(() => {
    if (initialPanel) setPanel(normalizePanel(initialPanel));
  }, [initialPanel]);

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
      setReceipt(null); // 换面板不留上一页的回执
      setPanel(k);
    },
    [panel, dirty, handleDirtyChange],
  );

  // 主线卡共享状态（settings-three-col）：表单与右栏 AI 向导同源，向导落卡不覆盖表单编辑
  const arcCtl = useStoryArc(projectId, panel === "arc", handleDirtyChange);

  const item = SETTINGS_ITEMS.find((i) => i.k === panel);
  const isModel = panel === "aiModel";
  // §5.1 三态：confirmed（已确认，来自 /settings/status）> filled（已填，来自 /readiness）> 未填
  // confirmedStatus 拉取失败（null）时回退 settingsStatus，避免已确认项被误标「已填」
  const confirmed = item
    ? !!(confirmedStatus?.[item.settingsKey] ?? settingsStatus?.[item.settingsKey])
    : false;
  const filled = item ? !!settingsStatus?.[item.settingsKey] : false;

  // ── 进度（两态口径：done/empty；readiness 拉取失败按 0 计，与 modnav 一致）──
  const total = SETTINGS_ITEMS.length;
  const done = settingsStatus
    ? SETTINGS_ITEMS.filter((i) => settingsStatus[i.settingsKey]).length
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
          : formRef.current,
    [panel],
  );

  /** 存草稿：只落库、不确认、不前进（§5.1 草稿＝进行中）。 */
  const handleSaveDraft = useCallback(async () => {
    if (!item || busy) return;
    setBusy(true);
    try {
      const saved = await currentHandle()?.save();
      if (saved === true) toast.success(`「${item.name}」已存草稿`);
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
      if (confirmed) {
        handle?.clearAi?.();
        toast.success(`「${item.name}」已保存`);
      } else {
        const ok = await confirmSetting(item.settingsKey);
        if (ok) {
          handle?.clearAi?.();
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
  }, [item, panel, confirmed, busy, confirmSetting, done, total, currentHandle]);

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
  const badgeCls = isModel ? modelBadge.cls : confirmed ? BADGE_DONE : filled ? "warn" : BADGE_EMPTY;
  const badgeLabel = isModel ? modelBadge.label : confirmed ? "已确认" : filled ? "已填" : "未填";
  const badgeOk = isModel ? modelBadge.ok : badgeCls === BADGE_DONE;
  const panelDesc = isModel
    ? "本书写作所用的模型、变更历史与用量。"
    : (DESCS[panel] ?? "");
  const panelNote = isModel
    ? "工具项 · 不参与设定进度"
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
          <button
            className="btn btn-primary"
            type="button"
            style={{ width: "100%", marginTop: 10 }}
            onClick={onGoWrite}
          >
            设定完成 · 去写作
          </button>
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
            return (
              <div
                key={i.k}
                className={`s-item${panel === i.k ? " on" : ""}`}
                onClick={() => handleSelect(i.k)}
              >
                <span className="nm">{i.name}</span>
                {i.canDefer && !done_ && <span className="defer-tag">可后补</span>}
                <span className="spacer" />
                <span className={`badge ${done_ ? BADGE_DONE : BADGE_EMPTY}`}>
                  <BadgeIcon ok={done_} />
                  {done_ ? "已确认" : "未填"}
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
                ref={formRef}
                projectId={projectId}
                ctl={arcCtl}
              />
            )}
            {panel === "world" && (
              <WorldSettingForm
                ref={formRef}
                projectId={projectId}
                settingKey="world"
                onDirtyChange={handleDirtyChange}
              />
            )}
            {panel === "style" && (
              <StyleSettingForm
                ref={formRef}
                projectId={projectId}
                settingKey="style"
                onDirtyChange={handleDirtyChange}
              />
            )}
            {panel === "antiAI" && (
              <AntiAiSettingForm
                ref={formRef}
                projectId={projectId}
                settingKey="anti-ai"
                onDirtyChange={handleDirtyChange}
              />
            )}
            {panel === "foreshadow" && (
              <HooksSettingForm
                ref={formRef}
                projectId={projectId}
                settingKey="hooks"
                onDirtyChange={handleDirtyChange}
              />
            )}
            {panel === "chars" && (
              <CharacterManager
                ref={formRef}
                projectId={projectId}
                onDirtyChange={handleDirtyChange}
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
            <span className="note" style={{ marginRight: "auto" }}>
              {panelNote}
            </span>
            {/* 改动回执（仅在模型设定/简介/题材三面板发声；其余面板恒 null） */}
            <ChangeReceiptBar receipt={receipt} />
            {confirmed && !isModel && (
              <span className="done-note">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d={CHECK_PATH} />
                </svg>
                已确认
              </span>
            )}
            {!isModel && !confirmed && (
              <button
                className="btn btn-secondary"
                onClick={() => void handleSaveDraft()}
                disabled={busy}
                data-od-id="btn-save-draft"
              >
                存草稿
              </button>
            )}
            {!isModel && (
              <button
                className="btn btn-primary"
                onClick={() => void handleFootAction()}
                disabled={busy}
              >
                {confirmed ? "保存修改" : "确认完成"}
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
            footNote="输入：书名 + 简介本文（题材可后补）。结果统一落在简介框下方结果区，采纳才写回。"
            aiState={aiState}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
          />
        ) : panel === "genre" ? (
          <AiWriterAssistant
            rows={genreAiRows}
            footNote="点某行，AI 建议落到左侧对应格下方；采纳才写回，随时可改可重试。"
            aiState={aiState}
            onBlocked={handleAiBlocked}
            runningKey={aiRunningKey}
            data-od-id="ai-assist-genre"
          />
        ) : panel === "arc" ? (
          <ArcWizard ctl={arcCtl} />
        ) : panel === "world" || panel === "style" || panel === "antiAI" ? (
          <div className="rail-card">
            <b>{item?.name} · AI 能力</b>
            <p className="opt" style={{ fontSize: 12 }}>
              各字段行内的「AI 帮我填」按钮随字段就地可用：点一下，AI 按已确认的题材与简介给建议，结果可采纳或重试。
            </p>
          </div>
        ) : (
          <div className="rail-card">
            <b>当前设定项暂无 AI 功能</b>
            <p className="opt" style={{ fontSize: 12 }}>
              「主线」面板的右栏是 AI 拆主线四步向导；世界/风格/AI痕迹控制的字段旁有「AI 帮我填」。
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
  /** 运行 AI 能力（体检/补缺失/润色）——结果落简介框下方 .ai-sink（tasks 3.4）。 */
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

/** 运行中各能力的操作名（与结果区标题同口径）。 */
const AI_RUNNING_LABEL: Record<IntroAiAction, string> = {
  introspect: "AI 体检 · 生成中…",
  fill: "补全缺失 · 生成中…",
  polish: "润色 · 生成中…",
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
    synopsisRef.current = synopsis;
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
        return true;
      } catch {
        toast.error("简介保存失败");
        return false;
      } finally {
        setSaving(false);
      }
    }, [projectId, synopsis, saving, markSaved]);


    const [guideOpen, setGuideOpen] = useState(false);
    // AI 结果区（tasks 3.3/3.4 + 生成历史）：每个能力保留**最近 5 次**结果，
    // 可切回任意一次再采纳（避免无限抽卡 / 反悔）；采纳＝用选中那次整段替换输入框。
    const [sinks, setSinks] = useState<
      Partial<
        Record<
          IntroAiAction,
          { list: Array<{ label: string; node: React.ReactNode; adopt?: () => void }>; idx: number }
        >
      >
    >({});
    /** 手写内容＝合成基准：手动编辑时更新；采纳结果不回写基准（防多次采纳叠加）。 */
    const baseRef = useRef("");
    /** 最近一次触发的能力（结果区展示对象）。 */
    const lastActionRef = useRef<IntroAiAction>("introspect");
    /** 运行态（D14）：点完立刻在输入框下方给「生成中」占位，避免用户以为没反应。 */
    const [aiRunning, setAiRunning] = useState<IntroAiAction | null>(null);
    /** 面板级在途锁（ref 同步判定）：无论调用方点几次，同时在飞的只有一个请求。 */
    const aiBusyRef = useRef(false);

    /** 生成历史上限：只保留最近 5 次（避免无限抽卡；要更早的版本就从这 5 条里选）。 */
    const SINK_MAX = 5;

    /** 追加一条生成结果并切到最新（超出上限丢最旧）。 */
    const pushSink = useCallback(
      (entry: { action: IntroAiAction; label: string; node: React.ReactNode; adopt?: () => void }) => {
        const { action, ...rest } = entry;
        setSinks((prev) => {
          const list = [...(prev[action]?.list ?? []), rest].slice(-SINK_MAX);
          return { ...prev, [action]: { list, idx: list.length - 1 } };
        });
      },
      [],
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
        aiBusyRef.current = true;
        lastActionRef.current = action;
        setAiRunning(action);
        await introAi(action, { title: novelName ?? "", content }, projectId)
          .then((r) => {
            if (action === "introspect") {
              introspectedRef.current = true;
              const segs = r.six_segments ?? [];
              const hits = r.taboo?.hits ?? [];
              pushSink({
                action,
                label: "AI 体检 · 六段逐项",
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
              });
            } else if (action === "fill") {
              const miss = r.missing ?? [];
              pushSink({
                action,
                label: "补全缺失 · 候选如下，采纳才插入",
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
                        `已采纳「补全缺失」，简介 ${synopsis.length} 字 → ${next.length} 字`,
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
                      toast.success(
                        next.length >= INTRO_MAX_LEN
                          ? "已采纳（到 500 字上限，尾部截断）"
                          : "已采纳，整段已替换为「你的原文 + 补全段」，可继续改",
                      );
                    }
                  : undefined,
              });
            } else {
              const polished = r.polished ?? "";
              pushSink({
                action,
                label: "润色 · 前后对照，采纳才替换",
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
                        `已采纳「润色」，简介 ${synopsis.length} 字 → ${next.length} 字`,
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
                      toast.success("已替换，原句可随时改回");
                    }
                  : undefined,
              });
            }
          })
          .catch((e: unknown) => {
            const reason = aiBlockReason(e);
            if (reason === "member_required") {
              toast.info("AI 是会员功能，升级 PRO 后解锁");
            } else if (reason === "no_key") {
              toast.info("先去「模型配置」添加 API Key");
            } else if (reason === "missing_model" || reason === "invalid") {
              toast.info("先在本书选择模型");
            } else {
              toast.error((e as Error).message || "暂不可用，请重试");
            }
          })
          .finally(() => {
            aiBusyRef.current = false;
            setAiRunning(null);
          });
      },
      [synopsis, novelName, projectId],
    );

    useImperativeHandle(
      ref,
      () => ({
        save,
        isEmpty: () => !synopsis.trim(),
        focus: () => taRef.current?.focus(),
        runAi,
        markDirty,
        clearAi: () => setSinks({}),
        hasIntrospected: () => introspectedRef.current,
      }),
      [save, synopsis, runAi, markDirty],
    );

    // 结果区展示哪个能力的历史：取最近一次生成过的（点过体检就显示体检的那条）
    const viewAction: IntroAiAction =
      (["introspect", "fill", "polish"] as IntroAiAction[])
        .filter((a) => (sinks[a]?.list.length ?? 0) > 0)
        .slice(-1)[0] ?? lastActionRef.current;

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

        {/* 运行态占位：点完立刻可见（否则用户不知道后台在跑，会连点） */}
        {aiRunning && (
          <div className="ai-sink" data-od-id="intro-ai-running" aria-busy="true">
            <div className="aiz-head">{AI_RUNNING_LABEL[aiRunning]}</div>
            <span className="opt" style={{ fontSize: 12 }}>
              AI 正在生成，请稍候…（完成后结果会出现在这里）
            </span>
          </div>
        )}

        {/* AI 结果区：落编辑框下方（tasks 3.3/3.4，采纳后保留、重新请求覆盖） */}
        {(() => {
          const st = sinks[viewAction];
          const entry = st?.list[st.idx];
          if (!entry || !st) return null;
          const { list, idx: active } = st;
          return (
            <AiSink
              label={entry.label}
              history={{
                total: list.length,
                active,
                max: SINK_MAX,
                onSelect: (i) =>
                  setSinks((prev) => {
                    const cur = prev[viewAction];
                    return cur ? { ...prev, [viewAction]: { ...cur, idx: i } } : prev;
                  }),
              }}
              adoptText={
                viewAction === "fill"
                  ? "采纳 · 替换为补全后的简介"
                  : viewAction === "polish"
                    ? "采纳 · 替换简介"
                    : undefined
              }
              onAdopt={entry.adopt}
              onRetry={() => void runAi(viewAction)}
              data-od-id="intro-ai-sink"
            >
              {entry.node}
            </AiSink>
          );
        })()}

        <p className="opt" style={{ fontSize: 12, margin: "-6px 0 16px" }}>
          简介会作为后续设定和写作的依据。
        </p>
      </>
    );
  },
);
