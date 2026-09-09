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
  genre: "题材决定后续表单模板与 AI 生成的口味，是设定的第一步。",
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
  projectId, initialPanel, settingsStatus, confirmedStatus, confirmSetting, onDirtyChange,
}: SettingsViewProps) {
  const [panel, setPanel] = useState(() => normalizePanel(initialPanel));
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  const formRef = useRef<SettingSaveHandle>(null);
  const genreRef = useRef<GenreHandle>(null);
  const introRef = useRef<IntroHandle>(null);

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
      const saved =
        panel === "genre"
          ? await genreRef.current?.save()
          : panel === "intro"
            ? await introRef.current?.save()
            : await formRef.current?.save();
      if (saved !== true) return;
      if (confirmed) {
        toast.success(`「${item.name}」已保存`);
      } else {
        const ok = await confirmSetting(item.settingsKey);
        if (ok) {
          toast.success(`「${item.name}」已确认`);
          // 确认即前进：切到 SETTINGS_ITEMS 的数组顺序下一项（末项不动；
          // 模型窗（aiModel）不在 SETTINGS_ITEMS，天然被跳过）
          const idx = SETTINGS_ITEMS.findIndex((i) => i.k === panel);
          const next = idx >= 0 ? SETTINGS_ITEMS[idx + 1] : undefined;
          if (next) setPanel(next.k);
        }
      }
    } finally {
      setBusy(false);
    }
  }, [item, panel, confirmed, busy, confirmSetting]);

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
              />
            )}
            {panel === "intro" && (
              <IntroPanel
                ref={introRef}
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
              <ModelSettingForm projectId={projectId} settingKey="ai-model" />
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
        {panel === "arc" ? (
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
}

const IntroPanel = forwardRef<IntroHandle, { projectId: string; onDirtyChange?: (dirty: boolean) => void }>(
  function IntroPanel({ projectId, onDirtyChange }, ref) {
    const [synopsis, setSynopsis] = useState("");
    const [saving, setSaving] = useState(false);
    const taRef = useRef<HTMLTextAreaElement>(null);
    // P3-4：用户已手动输入时，晚到的挂载 fetch 不得覆盖输入
    const editedRef = useRef(false);
    const { snapshotLoaded, markSaved } = useDirtyState(synopsis, onDirtyChange);

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

    useImperativeHandle(
      ref,
      () => ({ save, isEmpty: () => !synopsis.trim(), focus: () => taRef.current?.focus() }),
      [save, synopsis],
    );

    return (
      <>
        <div className="field">
          <label>
            故事简介 <span className="opt">≤500 字</span>
            <span className="cnt" style={{ marginLeft: "auto" }}>
              {synopsis.length}/500
            </span>
          </label>
          <textarea
            ref={taRef}
            className="textarea"
            rows={4}
            maxLength={500}
            placeholder="用几句话讲讲这个故事是关于什么的（主角、世界、核心冲突）"
            value={synopsis}
            disabled={saving}
            onChange={(e) => {
              editedRef.current = true;
              setSynopsis(e.target.value);
            }}
          />
        </div>
        <p className="opt" style={{ fontSize: 12, margin: "-6px 0 16px" }}>
          简介会作为后续设定和写作的依据。
        </p>
      </>
    );
  },
);
