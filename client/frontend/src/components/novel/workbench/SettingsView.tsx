// 设定视图（book.html #viewSettings 复刻，PR4）：
//   two-col = 左栏（tree-head 设定·7 项 + settings-progress n/7 进度条
//   + 8 导航项 done/empty 两态徽标 + 可后补 tag + tree-foot 口径注）
//   + 右面板（panel-head/badge/desc/panelBody + panel-foot 确认完成）。
// 七项计数与后端 READINESS_KEYS 同源（synopsis=简介 / hooks=伏笔）；
// AI 模型为第 8 项工具项：恒 done、无确认按钮、不参与进度（ADJUSTMENTS #4）。
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
import GenreSettingForm, { type GenreHandle } from "@/components/novel/settings/GenreSettingForm";
import { INTRO_SEGMENTS, INTRO_FORMULA, DONT_DO, INTRO_MAX_LEN, TABOO_RULES } from "@/lib/introTemplate";
import { GENRE_DEFINITION } from "@/lib/genreVocab";
import { useModelStatus } from "@/hooks/useModelStatus";
import type { AiState } from "@/types/api-config";
import AiWriterAssistant, { type AiCapabilityRow } from "@/components/novel/settings/AiWriterAssistant";
import AiSink from "@/components/novel/settings/AiSink";
import { introAi, aiBlockReason, type IntroAiAction } from "@/lib/ai";

// ── 面板注册表（顺序/命名与原型 navItems 一致；settingsKey 对后端口径）──
const SETTINGS_ITEMS = [
  { k: "intro", name: "简介", settingsKey: "synopsis", canDefer: false },
  { k: "genre", name: "题材", settingsKey: "genre", canDefer: false },
  { k: "arc", name: "主线", settingsKey: "story-arc", canDefer: true },
  { k: "world", name: "世界", settingsKey: "world", canDefer: true },
  { k: "style", name: "风格", settingsKey: "style", canDefer: false },
  { k: "antiAI", name: "AI痕迹控制", settingsKey: "anti-ai", canDefer: true },
  { k: "foreshadow", name: "伏笔", settingsKey: "hooks", canDefer: true },
  { k: "chars", name: "角色", settingsKey: "characters", canDefer: true },
] as const;

const DESCS: Record<string, string> = {
  genre: GENRE_DEFINITION,
  intro: "让读者（和 AI）知道这是一个怎样的故事。",
  arc: "这本书讲什么、结局想怎样、分几卷——定总方向盘，不拦写作。",
  world: "地理、政治与规则——故事发生的世界如何运转。",
  style: "用谁的视角讲，用什么语气讲。",
  antiAI: "控制生成正文的 AI 痕迹，让文字更像人写的。",
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
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  const formRef = useRef<SettingSaveHandle>(null);
  const genreRef = useRef<GenreHandle>(null);
  const introRef = useRef<IntroHandle>(null);
  // D13：AI 行的门控只读后端 ai_state 一次分派（不再 useFeature + 本地推导两处判）
  const { aiState } = useModelStatus(projectId);
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
          introRef.current?.runAi("introspect");
          setIntrospected(true);
        },
      },
      {
        key: "fill",
        name: "补缺失",
        desc: "只补缺的段，候选采纳才插入",
        disabled: !introspected,
        hint: introspected ? undefined : "先体检",
        onClick: () => introRef.current?.runAi("fill"),
      },
      {
        key: "polish",
        name: "润色",
        desc: "保你原意压 AI 味，前后对照采纳才替换",
        onClick: () => introRef.current?.runAi("polish"),
      },
    ],
    [introspected],
  );

  // 题材右栏五行（02-06 各答各题；01 口味胶囊不走 AI）
  const genreAiRows = useMemo<AiCapabilityRow[]>(
    () => [
      {
        key: "m1",
        name: "主要看什么",
        desc: "本格问题：读者翻开这本书，主要看什么？输入：书名 + 简介（第一步已填）",
        onClick: () => genreRef.current?.runAi("core_promise"),
      },
      {
        key: "m2",
        name: "绝对禁止",
        desc: "本格问题：这本书绝不出现什么？输入：02 的承诺 + 简介（第一步）",
        onClick: () => genreRef.current?.runAi("forbidden_list"),
      },
      {
        key: "m3",
        name: "吃苦指数",
        desc: "本格问题：主角得到好处，要付多大代价？输入：02 的承诺 + 03 的禁项",
        onClick: () => genreRef.current?.runAi("cost_ratio"),
      },
      {
        key: "m4",
        name: "主线战场",
        desc: "本格问题：整本书主要斗什么？输入：02 的承诺 + 简介（第一步）",
        onClick: () => genreRef.current?.runAi("battlefield"),
      },
      {
        key: "m5",
        name: "剧情轨道",
        desc: "本格问题：整本书怎么走？输入：02-05 已填的全部内容",
        onClick: () => genreRef.current?.runAi("track"),
      },
    ],
    [],
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
  const handleFootAction = useCallback(async () => {
    if (!item || busy) return;
    // tasks 2.4：移除前端「空内容阻断」gate——全页无必填、确认永远可点；
    // 内容为空时由后端 400 提示（confirmSetting 的 catch 已承接「还未填写内容」），
    // 「跳过」＝直接切到下一个 tab（顺序是引导不是锁）。
    setBusy(true);
    try {
      // 简介（IntroPanel）挂的是 introRef —— 漏分发会拿到 undefined 并带空数据
      // 去 confirm（后端 400）；改为严格 true 才继续，false/undefined 一律中止。
      const handle =
        panel === "genre"
          ? genreRef.current
          : panel === "intro"
            ? introRef.current
            : formRef.current;
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
  }, [item, panel, confirmed, busy, confirmSetting, done, total]);

  const panelTitle = isModel ? "AI 模型" : (item?.name ?? "");
  const badgeCls = isModel || confirmed ? BADGE_DONE : filled ? "warn" : BADGE_EMPTY;
  const badgeLabel = isModel || confirmed ? "已确认" : filled ? "已填" : "未填";
  const panelDesc = isModel
    ? "本书写作所用的模型、变更历史与用量。"
    : (DESCS[panel] ?? "");
  const panelNote = isModel
    ? "工具项 · 恒可用，不参与设定进度"
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
            设定 · <b>{SETTINGS_ITEMS.length}</b> 项
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
          <div
            className={`s-item${panel === "aiModel" ? " on" : ""}`}
            onClick={() => handleSelect("aiModel")}
          >
            <span className="nm">AI 模型</span>
            <span className="defer-tag">工具</span>
            <span className="spacer" />
            <span className={`badge ${BADGE_DONE}`}>
              <BadgeIcon ok />
              已确认
            </span>
          </div>
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
              <BadgeIcon ok={badgeCls === BADGE_DONE} />
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
                novelName={novelName}
              />
            )}
            {panel === "intro" && (
              <IntroPanel
                ref={introRef}
                novelName={novelName}
                projectId={projectId}
                onDirtyChange={handleDirtyChange}
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
              />
            )}
          </div>

          <div className="panel-foot">
            <span className="note" style={{ marginRight: "auto" }}>
              {panelNote}
            </span>
            {confirmed && !isModel && (
              <span className="done-note">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d={CHECK_PATH} />
                </svg>
                已确认
              </span>
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
          />
        ) : panel === "genre" ? (
          <AiWriterAssistant
            rows={genreAiRows}
            footNote="点某行，AI 建议落到左侧对应格下方；采纳才写回，随时可改可重试。"
            aiState={aiState}
            onBlocked={handleAiBlocked}
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

const IntroPanel = forwardRef<
  IntroHandle,
  { projectId: string; novelName?: string; onDirtyChange?: (dirty: boolean) => void }
>(function IntroPanel({ projectId, novelName, onDirtyChange }, ref) {
    const [synopsis, setSynopsis] = useState("");
    const [saving, setSaving] = useState(false);
    const taRef = useRef<HTMLTextAreaElement>(null);
    // P3-4：用户已手动输入时，晚到的挂载 fetch 不得覆盖输入
    const editedRef = useRef(false);
    const { snapshotLoaded, markSaved, markDirty } = useDirtyState(synopsis, onDirtyChange);
    // 前置守卫（O-3）：补缺失必须先体检拿到缺失段
    const introspectedRef = useRef(false);

    useEffect(() => {
      let cancelled = false;
      api
        .fetchStory(projectId)
        .then((r) => {
          if (!cancelled && !editedRef.current) {
            setSynopsis(r.synopsis ?? "");
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
    // AI 结果区状态（tasks 3.3/3.4）：{ label, node, adopt } —— 所有权在本面板
    const [sink, setSink] = useState<
      | { action: IntroAiAction; label: string; node: React.ReactNode; adopt?: () => void }
      | null
    >(null);

    const runAi = useCallback(
      async (action: IntroAiAction) => {
        const content = synopsis;
        if (action === "introspect" && !content.trim()) {
          toast.info("先写两句简介，体检才有东西可查");
          return;
        }
        if (action === "fill" && !introspectedRef.current) {
          toast.info("先点「体检」，AI 才知道缺哪段");
          return;
        }
        setSink(null);
        await introAi(action, { title: novelName ?? "", content }, projectId)
          .then((r) => {
            if (action === "introspect") {
              introspectedRef.current = true;
              const segs = r.six_segments ?? [];
              const hits = r.taboo?.hits ?? [];
              setSink({
                action,
                label: "AI 体检 · 六段逐项",
                node: (
                  <>
                    {/* 行名按模板单源顺序渲染（后端只提供 status/note），保证与六段模板逐字一致 */}
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
                    <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
                      禁忌扫描：
                      {hits.length
                        ? hits.map((h) => h.rule).join(" / ")
                        : `无 ${TABOO_RULES.join(" / ")}`}
                      {r.verdict ? ` · 结论：${r.verdict}` : ""}
                    </p>
                  </>
                ),
              });
            } else if (action === "fill") {
              const miss = r.missing ?? [];
              setSink({
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
                      const add = miss
                        .map((m) => m.candidate)
                        .join("")
                        .trim();
                      const next = (synopsis.trim() + (synopsis.trim() ? "。" : "") + add).slice(
                        0,
                        INTRO_MAX_LEN,
                      );
                      editedRef.current = true;
                      setSynopsis(next);
                      toast.success(
                        next.length >= INTRO_MAX_LEN
                          ? "已追加（已到 500 字上限，尾部截断）"
                          : "已追加进简介，可继续改",
                      );
                    }
                  : undefined,
              });
            } else {
              const polished = r.polished ?? "";
              setSink({
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
                      editedRef.current = true;
                      setSynopsis(polished.slice(0, INTRO_MAX_LEN));
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
        clearAi: () => setSink(null),
        hasIntrospected: () => introspectedRef.current,
      }),
      [save, synopsis, runAi, markDirty],
    );

    return (
      <>
        <div className="field">
          <label>
            故事简介 <span className="opt">≤{INTRO_MAX_LEN} 字</span>
            <span className="cnt" style={{ marginLeft: "auto" }}>
              {synopsis.length}/{INTRO_MAX_LEN}
            </span>
          </label>
          <textarea
            ref={taRef}
            className="textarea"
            rows={4}
            maxLength={INTRO_MAX_LEN}
            placeholder="用几句话讲讲这个故事是关于什么的（主角、世界、核心冲突）"
            value={synopsis}
            disabled={saving}
            onChange={(e) => {
              editedRef.current = true;
              setSynopsis(e.target.value);
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

        {/* AI 结果区：落编辑框下方（tasks 3.3/3.4，采纳后保留、重新请求覆盖） */}
        {sink && (
          <AiSink
            label={sink.label}
            adoptText={sink.action === "fill" ? "采纳 · 追加到简介" : sink.action === "polish" ? "采纳 · 替换简介" : undefined}
            onAdopt={sink.adopt}
            data-od-id="intro-ai-sink"
          >
            {sink.node}
          </AiSink>
        )}

        <p className="opt" style={{ fontSize: 12, margin: "-6px 0 16px" }}>
          简介会作为后续设定和写作的依据。
        </p>
      </>
    );
  },
);
