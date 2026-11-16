// ChatDock——右栏常驻对话助手（c-writing-agent 批E）。
// 三层：上下文徽标＋能力盘 chips（随页面换）→ 对话流（消息＋产物卡＋授权卡）→
// 输入框。产物卡过目采纳才落框（ai-modal-confirm-rule 对话形态）；授权卡批复走
// /approve 停车；门控卡不打断对话流（spec writing-assistant）。
// 视觉全部取 base.css 令牌（design:lint 约束）；样式见同目录 chat.css。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatWan } from "@/lib/chatApi";
import {
  adoptAssistantMessage,
  setPermissionTier,
  approveGate,
  loadAssistantSession,
  streamAssistantChat,
} from "@/lib/chatApi";
import { api } from "@/lib/api";
import { matchRegistration, threadKeyOf, type ChatChip, type ChatPageScope } from "@/lib/chatRegistry";
import type { LandingView } from "@/lib/novelStage";
import { useFeature } from "@/hooks/useTier";
import type { FeatureKey } from "@/lib/features";
import { useChatSession, type ChatMessage } from "@/hooks/useChatSession";
import ChatMarkdown from "./ChatMarkdown";
import "./chat.css";

interface ChatDockProps {
  projectId: string;
  page: string;
  scope: ChatPageScope;
  /** 会话存活性上抛：宿主并入树锁定/切页守卫 */
  onStreamingChange?: (streaming: boolean) => void;
  onUpgrade?: (feature?: FeatureKey) => void;
  /** 窄屏抽屉：关闭抽屉（仅抽屉态由宿主注入） */
  onCloseDrawer?: () => void;
  /** 富交互入口（open chip）：宿主开既有弹窗（AiModal/抽卡/推演） */
  onOpenAction?: (action: string) => void;
  /** 采纳写回后由宿主调用（卡片置「已采纳」） */
  registerAdoptNotifier?: (fn: (cardId: string) => void) => void;
}

function isSentimentAuth(m: ChatMessage): boolean {
  return m.kind === "auth";
}

/** 产物卡体：按 cardKind 渲染 payload 摘要（struct/text/report/pick/gate）。 */
function CardBody({ kind, payload }: { kind: string; payload: unknown }) {
  const data = (payload ?? {}) as Record<string, unknown>;
  if (kind === "report") {
    const groups = (data.report as { name: string; items: { status: string; text: string }[] }[] | undefined) ?? [];
    return (
      <div className="cd-report">
        {groups.map((g) => (
          <div key={g.name} className="cd-report-g">
            <b>{g.name}</b>
            <ul>
              {g.items.map((it, i) => (
                <li key={i} className={`cd-st-${it.status}`}>
                  {it.text}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {groups.length === 0 && <p className="cd-dim">（报告为空）</p>}
      </div>
    );
  }
  if (kind === "pick") {
    const candidates = (data.candidates as { name: string; rationale: string }[] | undefined) ?? [];
    return (
      <ul className="cd-pick">
        {candidates.map((c) => (
          <li key={c.name}>
            <b>{c.name}</b>
            <span className="cd-dim"> — {c.rationale}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (kind === "struct" && Array.isArray(data.characters)) {
    const characters = data.characters as { name: string; role: string; persona: string; origin_note?: string; origin?: string }[];
    return (
      <div>
        {characters.map((c) => (
          <div key={c.name} className="cd-char">
            <b>
              {c.name}
              {c.origin === "divergent" && <span className="cd-badge">草案·发散</span>}
            </b>
            <span className="cd-dim">（{c.role}）</span>
            <p>{c.persona}</p>
            {c.origin_note && <p className="cd-anchor">锚点：{c.origin_note}</p>}
          </div>
        ))}
      </div>
    );
  }
  // 角色草案确认卡（draft_character）：字段化＋确认·建卡（作家点确认才调建卡）
  if (data.character_draft) {
    const d = data.character_draft as Record<string, string>;
    const rows: [string, string][] = [
      ["名字", d.name ?? ""],
      ["性别年龄", d.gender_age ?? ""],
      ["身份背景", d.identity ?? ""],
      ["与现有角色关系", d.relation ?? ""],
      ["剧情功能", d.function ?? ""],
      ["性格特质", d.personality ?? ""],
    ];
    return (
      <div className="cd-draft" data-testid="char-draft-card">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="cd-draft-row">
              <b>{k}</b>
              <span>{v}</span>
            </div>
          ))}

      </div>
    );
  }
  // 章纲补全卡（settings_og_fill）：fills 逐项字段化
  if (data.fills && typeof data.fills === "object") {
    const fills = data.fills as Record<string, unknown>;
    const LABELS: Record<string, string> = {
      summary: "一句话概要", characters: "出场角色", changes: "必须完成的变化",
      prohibitions: "必须维持悬念", mood: "阶段",
    };
    return (
      <div className="cd-draft">
        {Object.entries(fills).map(([k, v]) => (
          <div key={k} className="cd-draft-row">
            <b>{LABELS[k] ?? k}</b>
            <span>{typeof v === "string" ? v : JSON.stringify(v)}</span>
          </div>
        ))}
        <p className="cd-dim">产物不落库——到章纲表单核对后采纳保存。</p>
      </div>
    );
  }
  // 设定字段 AI 卡（settings_* 工具）：字符串值直渲染；对象值走通用人话渲染
  // （禁 JSON.stringify 上对话框——boss 红线 2026-11-16，简介卡 result 曾整段裸 JSON）
  if (data.value != null || data.result != null) {
    const body = data.value != null ? data.value : data.result;
    if (typeof body === "string") {
      return <div className="cd-md cd-settings">{body}</div>;
    }
    const generic = renderGenericPayload(body as Record<string, unknown>);
    if (generic) {
      return <div className="cd-md cd-settings">{generic}</div>;
    }
    return null;
  }
  // 卷纲草稿（draft_volume_expand 卡）：字段化渲染，禁裸 JSON
  if (data.draft && typeof data.draft === "object") {
    const d = data.draft as Record<string, unknown>;
    const rows: [string, unknown][] = [
      ["卷名", d.name],
      ["主旨", d.summary],
      ["核心冲突", d.conflict],
      ["卷末", d.ending],
      ["对手线", d.antagonist_line],
      ["章节目标", d.chapter_target],
    ];
    return (
      <div className="cd-draft">
        {rows
          .filter(([, v]) => v != null && String(v).trim())
          .map(([k, v]) => (
            <div key={k} className="cd-draft-row">
              <b>{k}</b>
              <span>{String(v)}</span>
            </div>
          ))}
        {Array.isArray(d.plants) && d.plants.length > 0 && (
          <p className="cd-dim">埋设 {d.plants.length} 条 · 揭示 {Array.isArray(d.reveals) ? d.reveals.length : 0} 条</p>
        )}
      </div>
    );
  }
  // text/其余：分段正文
  const diff = data.diff as { one_liner?: string[] } | undefined;
  if (Array.isArray(diff?.one_liner)) {
    return (
      <ol className="cd-lines">
        {(diff?.one_liner ?? []).map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
    );
  }
  // 人话 draft（收编工具产卡：推演/抽卡/盘点）——禁裸 JSON 上对话（boss 红线）
  if (typeof data.draft === "string" && data.draft.trim()) {
    return <p className="cd-pre">{_clip(data.draft, 1200)}</p>;
  }
  // 通用兜底：未知 payload 走结构化人话渲染（中文标签＋列表/条目展开），
  // 禁 JSON.stringify——程序文案不上对话框（boss 红线 2026-11-16）
  const generic = renderGenericPayload(data);
  if (generic) {
    return <div className="cd-generic">{generic}</div>;
  }
  const text = typeof payload === "string" ? payload : "";
  return text ? <p className="cd-pre">{_clip(text, 900)}</p> : null;
}

/** 已知键的中文标签（通用兜底渲染用；未收录键回退原键名）。 */
const GENERIC_LABELS: Record<string, string> = {
  directions: "剧情方向", versions: "剧情清单", plans: "本卷走法", branches: "支线候选",
  candidates: "候选", items: "清单", entry: "进场", exit: "退场", beat: "拍点",
  who: "谁", place: "地点", moves: "走向", spine: "主轴", conflict: "冲突",
  ending: "结局", focus: "侧重", focus_axis: "侧重轴", antagonist_type: "反派类型",
  axis: "轴", stage: "阶段", grade: "评级", note: "备注", summary: "概要",
  characters: "角色", name: "名", synopsis: "梗概", label: "标签", hints: "提示",
  rows: "逐段盘点", verdict: "判定", echo: "段落原文", role: "角色",
  persona: "人设", duty: "差事", entrance: "进场", exit_note: "退场",
  checks: "自检", warnings: "提醒", diff: "差异", one_liner: "一句话",
};

function genericLabel(k: string): string {
  return GENERIC_LABELS[k] ?? k;
}

function genericValue(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v.trim();
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v).slice(0, 120);
  } catch {
    return String(v);
  }
}

/** 未知 payload 的结构化人话渲染：字符串字段逐行、对象字段展开一层、
 *  列表逐条编号。全部为空/噪音时返回 null（不渲染空卡）。 */
function renderGenericPayload(data: Record<string, unknown>): React.ReactNode | null {
  const NOISE = new Set(["ok", "act", "source", "pacing_fingerprint", "is_final", "why_not_old"]);
  const entries = Object.entries(data).filter(
    ([k, v]) => !NOISE.has(k) && !(k in GENERIC_LABELS && k === "diff") && v != null &&
      !(Array.isArray(v) && v.length === 0) &&
      (typeof v !== "object" || JSON.stringify(v) !== "{}"),
  );
  const out: React.ReactNode[] = [];
  let n = 0;
  for (const [k, v] of entries) {
    const label = genericLabel(k);
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      const t = genericValue(v);
      if (t) {
        n += 1;
        out.push(
          <div key={k} className="cd-draft-row">
            <b>{label}</b>
            <span>{_clip(t, 300)}</span>
          </div>,
        );
      }
    } else if (Array.isArray(v)) {
      const objs = v.filter((x) => x && typeof x === "object");
      if (objs.length) {
        n += 1;
        out.push(
          <div key={k} className="cd-generic-list">
            <b>{label}</b>
            {objs.map((item, i) => {
              const fields = Object.entries(item as Record<string, unknown>).filter(
                ([ik, iv]) => !NOISE.has(ik) && genericValue(iv),
              );
              return (
                <div key={i} className="cd-generic-item">
                  <b>
                    {label}
                    {String(i + 1)}
                  </b>
                  {fields.map(([ik, iv]) => (
                    <div key={ik} className="cd-draft-row">
                      <b>{genericLabel(ik)}</b>
                      <span>{_clip(genericValue(iv), 160)}</span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>,
        );
      } else {
        const strs = v.map((x) => genericValue(x)).filter(Boolean);
        if (strs.length) {
          n += 1;
          out.push(
            <div key={k} className="cd-generic-list">
              <b>{label}</b>
              {strs.map((t, i) => (
                <div key={i}>
                  {_clip(t, 160)}
                </div>
              ))}
            </div>,
          );
        }
      }
    } else if (typeof v === "object") {
      const fields = Object.entries(v as Record<string, unknown>).filter(
        ([ik, iv]) => !NOISE.has(ik) && genericValue(iv),
      );
      if (fields.length) {
        n += 1;
        out.push(
          <div key={k} className="cd-generic-list">
            <b>{label}</b>
            {fields.map(([ik, iv]) => (
              <div key={ik} className="cd-draft-row">
                <b>{genericLabel(ik)}</b>
                <span>{_clip(genericValue(iv), 160)}</span>
              </div>
            ))}
          </div>,
        );
      }
    }
  }
  return n > 0 ? out : null;
}

function _clip(text: string, budget: number): string {
  if (text.length <= budget) return text;
  return `${text.slice(0, budget - 1)}…`;
}

// 长文折叠（移植自 OpenWorker Transcript.tsx ClampedUserText，MIT）：作家长粘贴
// 会吞掉对话记录——超 1200 字截断＋展开/收起钮，全文仍完整发给模型。
const USER_CLAMP_CHARS = 1200;

function ClampedText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= USER_CLAMP_CHARS) return <>{text}</>;
  return (
    <>
      {open ? text : text.slice(0, USER_CLAMP_CHARS).trimEnd() + "…"}
      <button
        type="button"
        className="cd-clamp-toggle"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "收起" : "展开全文"}
      </button>
    </>
  );
}

// hover 复制条（移植自 OpenWorker Transcript.tsx BubbleMeta，MIT）：零高度绝对
// 定位挂在气泡下缘——hover 显形不推移布局；复制成功才打勾（WebKit 静默拒绝
// 不谎报成功）。
function CopyStrip({
  text,
  align,
  ts,
}: {
  text: string;
  align: "left" | "right";
  ts?: number;
}) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {});
  };
  const when =
    ts != null
      ? new Date(ts * 1000).toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;
  return (
    <div className="cd-copy-strip">
      <div className={`cd-copy ${align === "right" ? "right" : "left"}`}>
        {when && <span className="cd-copy-time">{when}</span>}
        <button
          type="button"
          className="cd-copy-btn"
          data-testid={copied ? undefined : "chat-copy"}
          onClick={copy}
        >
          {copied ? "已复制 ✓" : "复制"}
        </button>
      </div>
    </div>
  );
}

export default function ChatDock({
  projectId,
  page,
  scope,
  onStreamingChange,
  onUpgrade,
  onCloseDrawer,
  onOpenAction,
  registerAdoptNotifier,
}: ChatDockProps) {
  const { state, dispatch, onEvent, newSendId } = useChatSession();
  const threadKey = threadKeyOf(scope);
  const messages = state.threads[threadKey] ?? [];
  /** 上下文窗口（/session 下发；缺省 128k——compact DEFAULT_CONTEXT_WINDOW 同值） */
  const [ctxWindow, setCtxWindow] = useState(128_000);
  /** 脚部 ？帮助浮层（非模态：外点/Esc/再点关闭——boss 拍板 2026-11-15 长文收进 ？） */
  const [helpOpen, setHelpOpen] = useState(false);
  const helpAnchorRef = useRef<HTMLDivElement | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  /** 授权档位芯片（ZCode composer 同款——当前档常显＋下拉切换，boss 拍板 2026-11-15） */
  const [tier, setTierState] = useState("confirm_each");
  const [modeOpen, setModeOpen] = useState(false);
  const modeAnchorRef = useRef<HTMLDivElement | null>(null);
  // 本地实时估算（与后端 estimate_tokens 同口径：序列化字符/4）
  const ctxEst = useMemo(() => {
    let chars = 0;
    for (const m of messages) {
      chars += (m.text?.length ?? 0) + (m.thinking?.length ?? 0);
      for (const st of m.steps) chars += st.resultNote?.length ?? 0;
      if (m.kind === "card" && m.cardPayload != null) {
        try { chars += JSON.stringify(m.cardPayload).length; } catch { /* ignore */ }
      }
    }
    return Math.round(chars / 4);
  }, [messages]);
  const ctxPct = Math.min(100, Math.round((ctxEst / ctxWindow) * 1000) / 10);
  const ctxHot = ctxPct >= 80;
  const [input, inputSet] = useState("");
  const [secs, setSecs] = useState(0);
  const abortRef = useRef<(() => void) | null>(null);
  const streamRef = useRef(false);
  const greetedPageRef = useRef<string | null>(null);
  const streamBoxRef = useRef<HTMLDivElement | null>(null);
  const fPlan = useFeature("ai-plan");
  const fGen = useFeature("ai-generate");
  const fPlot = useFeature("ai-plot");
  const fDiv = useFeature("assistant-diverge");
  const fFields = useFeature("settings-ai-fields");
  const featureEnabled = (key?: FeatureKey): boolean | undefined => {
    if (!key) return undefined;
    switch (key) {
      case "ai-plan": return fPlan;
      case "ai-generate": return fGen;
      case "ai-plot": return fPlot;
      case "assistant-diverge": return fDiv;
      case "settings-ai-fields": return fFields;
      default: return undefined;
    }
  };
  const registration = useMemo(() => matchRegistration(scope), [scope]);

  // 历史回看（projectId 就绪才拉；随线程切换——每页签一个对话，切回接续）
  useEffect(() => {
    if (!projectId) return; // 路由参数未就绪的空串帧不发请求（批F 修正：空 id 命中曾让历史误空）
    let cancelled = false;
    void loadAssistantSession(projectId, threadKey)
      .then((s) => {
        if (cancelled || s.messages.length === 0) return;
        const mapped = s.messages.map((m): ChatMessage | null => {
          const card = (m.payload as { card?: unknown } | undefined)?.card;
          const auth = (m.payload as { authorization_card?: Record<string, unknown> } | undefined)
            ?.authorization_card;
          if (m.cardKind && m.cardKind !== "gate" && card) {
            return {
              id: m.id,
              role: "assistant" as const,
              kind: "card" as const,
              text: "",
              cardKind: m.cardKind as ChatMessage["cardKind"],
              cardId: String((m.payload as { cardId?: string })?.cardId ?? m.id),
              cardPayload: card,
              cardStatus: (m.status === "adopted" ? "adopted" : "draft") as ChatMessage["cardStatus"],
              steps: [],
            };
          }
          if (auth) {
            return {
              id: m.id,
              role: "system" as const,
              kind: "auth" as const,
              text: "",
              gateId: String(auth.gateId ?? ""),
              gatePreview: auth.preview,
              gateHumanOnly: Boolean(auth.humanOnly),
              gateState: "expired" as const, // 重启后待决授权过期（批B durable pending 挂账二期）
              steps: [],
            };
          }
          if (m.role === "tool") {
            if (!m.content?.trim()) return null as unknown as (typeof messages)[number]; // 空结果行不进轨迹
            return { id: m.id, role: "system" as const, kind: "trace" as const, text: m.content, steps: [] };
          }
          if (m.role === "user" || (m.role === "assistant" && m.content)) {
            const ts = m.createdAt ? Math.floor(new Date(m.createdAt.replace(" ", "T")).getTime() / 1000) : undefined;
            return {
              id: m.id,
              role: m.role as "user" | "assistant",
              kind: "text" as const,
              text: m.content,
              page: m.page,
              steps: [],
              ts: Number.isFinite(ts) ? ts : undefined,
            };
          }
          if (m.role === "event" && !m.content?.trim()) {
            return null as unknown as (typeof messages)[number]; // 空 event 行不进轨迹
          }
          return { id: m.id, role: "system" as const, kind: "trace" as const, text: m.content, steps: [] };
        });
        const messages = mapped.filter((m): m is ChatMessage => m != null);
        if (s.context?.window) setCtxWindow(s.context.window);
        const g = (s.grants ?? {}) as { tier?: string };
        if (g.tier) setTierState(g.tier);
        // 连续工具/事件行合并为一条折叠轨迹（boss 走查判例 2026-11-15：历史回放
        // 曾把工具结果铺成裸文本行——与 live 的折叠形态不一致）
        const merged: typeof messages = [];
        for (const m of messages) {
          const prev = merged[merged.length - 1];
          if (m.kind === "trace" && prev && prev.kind === "trace") {
            prev.text = `${prev.text}\n${m.text}`;
            continue;
          }
          merged.push(m);
        }
        dispatch({ type: "load_history", thread: threadKey, messages: merged });
      })
      .catch(() => {/* 首次失败静默——发消息时会再暴露 */});
    return () => {
      cancelled = true;
    };
  }, [projectId, threadKey, dispatch]);

  // 开场白：线程内首见投递一次（每页签一个对话——空线程给状态感知开场白）
  useEffect(() => {
    if (!registration || messages.length > 0) return;
    const greeting = registration.greeting(scope);
    if (greeting && greetedPageRef.current !== threadKey) {
      greetedPageRef.current = threadKey;
      dispatch({
        type: "gate",
        thread: threadKey,
        text: greeting,
      });
    }
  }, [registration, scope, threadKey, messages.length, dispatch]);

  // 流式存活上抛（宿主并入树锁定守卫）
  useEffect(() => {
    onStreamingChange?.(state.runActive);
  }, [state.runActive, onStreamingChange]);

  // 贴底滚动
  useEffect(() => {
    const box = streamBoxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [messages, state.thinkingText]);

  // 计秒（生成中态）
  useEffect(() => {
    if (!state.runActive) {
      setSecs(0);
      return;
    }
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [state.runActive]);

  // ？浮层：外点/Esc 关闭（非模态，不遮全屏）
  useEffect(() => {
    if (!helpOpen && !modeOpen) return;
    const onDown = (e: MouseEvent) => {
      if (helpOpen && !helpAnchorRef.current?.contains(e.target as Node)) setHelpOpen(false);
      if (modeOpen && !modeAnchorRef.current?.contains(e.target as Node)) setModeOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setHelpOpen(false);
        setModeOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [helpOpen, modeOpen]);

  /** 角色草案确认：作家点确认 → POST /characters 既有建卡链 → 回执＋已建徽标 */
  const confirmCharacter = useCallback(
    async (cardId: string, payload: Record<string, unknown>) => {
      const draft = payload.character_draft as Record<string, string> | undefined;
      if (!draft) return;
      setConfirmBusy(true);
      try {
        await api.post(`/novels/${projectId}/characters`, {
          name: draft.name,
          role: "配角",
          persona: [draft.gender_age, draft.identity, draft.relation, draft.function]
            .filter(Boolean)
            .join("。"),
        });
        dispatch({ type: "adopt_card", cardId });
        // 建卡回执落库（best-effort）：重开书后「已建卡 ✓」徽标不丢、确认钮不复活（防重复建卡）
        void adoptAssistantMessage(projectId, cardId).catch(() => {});
        dispatch({ type: "gate", thread: threadKey, text: `「${draft.name}」已建卡——角色库和名册里都能看到。` });
      } catch (e) {
        dispatch({ type: "error", thread: threadKey, message: (e as Error)?.message || "建卡失败" });
      } finally {
        setConfirmBusy(false);
      }
    },
    [projectId, threadKey, dispatch],
  );

  const adoptNotifier = useCallback(
    (cardId: string) => dispatch({ type: "adopt_card", cardId }),
    [dispatch],
  );
  useEffect(() => {
    registerAdoptNotifier?.(adoptNotifier);
  }, [registerAdoptNotifier, adoptNotifier]);

  /** 卷纲草稿采纳：payload.draft → PUT 既有卷端点（VolumeUpdate 校验链），回执落流。 */
  const adoptVolumeDraft = useCallback(
    async (cardId: string, payload: Record<string, unknown>) => {
      const draft = payload.draft as Record<string, unknown> | undefined;
      const volNo = payload.vol_no as number | undefined;
      if (!draft || volNo == null) return;
      try {
        await api.put(`/novels/${projectId}/volumes/vol-${volNo}`, {
          title: draft.name,
          summary: draft.summary,
          core_conflict: draft.conflict,
          ending: draft.ending,
          chapter_target: draft.chapter_target,
          antagonist_type: draft.antagonist_type,
          antagonist_line: draft.antagonist_line,
        });
        dispatch({ type: "adopt_card", cardId });
        // 采纳回执落库（best-effort）：重开书后「已采纳」徽标与 stale 防护不丢
        void adoptAssistantMessage(projectId, cardId).catch(() => {});
        dispatch({
          type: "gate",
          thread: threadKey,
          text: `已写入第 ${volNo} 卷的卷纲要点，可继续改。`,
        });
      } catch (e) {
        dispatch({ type: "error", message: (e as Error)?.message || "写入失败" });
      }
    },
    [projectId, threadKey, dispatch],
  );

  const stopRun = useCallback(() => {
    abortRef.current?.();
    dispatch({ type: "run_end", thread: threadKey });
    streamRef.current = false;
  }, [threadKey, dispatch]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streamRef.current) return;
      streamRef.current = true;
      dispatch({ type: "user_send", thread: threadKey, id: newSendId(), text: trimmed, page });
      // 聚焦对象随行（「这章/这一卷」的锚）：章视图带当前章 ref
      const focus = scope.chapterRef ? { ref: scope.chapterRef } : undefined;
      const abort = streamAssistantChat(
        projectId,
        { message: trimmed, page, thread: threadKey, focus },
        {
          // run 事件绑定发起线程：切走页签后事件仍落到原线程桶（切回接续）
          onEvent: (e) => onEvent(e, threadKey),
          onError: (msg) => {
            dispatch({ type: "error", thread: threadKey, message: msg });
            streamRef.current = false;
          },
          onDone: () => {
            streamRef.current = false;
          },
        },
      );
      abortRef.current = abort;
      inputSet("");
    },
    [projectId, page, threadKey, dispatch, onEvent, newSendId],
  );

  const approve = useCallback(
    (gateId: string, decision: "approved" | "denied") => {
      dispatch({ type: "gate_resolved", gateId, approved: decision === "approved" });
      void approveGate(projectId, gateId, decision).catch((e: Error) =>
        dispatch({ type: "gate", thread: threadKey, text: e.message }),
      );
    },
    [projectId, threadKey, dispatch],
  );

  const sendDisabled = !input.trim() || state.runActive;
  const chips: ChatChip[] = registration ? registration.chips(scope) : [];
  // 生成中面板的工具步取本 run 文本气泡（review 判例：曾取末条消息——卡片追加后
  // 步骤列表会闪空）
  let runSteps: ChatMessage["steps"] = [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.kind === "text" && m.role === "assistant") {
      runSteps = m.steps;
      break;
    }
  }

  return (
    <div className="chatdock" data-testid="chat-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手</b>
        {onCloseDrawer && (
          <button
            type="button"
            className="chatdock-close"
            data-testid="chat-drawer-close"
            aria-label="关闭助手"
            onClick={onCloseDrawer}
          >
            ✕
          </button>
        )}
        <span className="chatdock-ctx">你在：{registration?.label ?? page}</span>
        <div className="chatdock-sub-row">
          <span className="chatdock-sub">每页一个会话 · 切回接着聊</span>
          <div className="cd-mode-anchor cd-mode-head" ref={modeAnchorRef}>
            <button
              type="button"
              className="cd-mode-chip"
              data-testid="mode-chip"
              aria-expanded={modeOpen}
              onClick={() => setModeOpen((v) => !v)}
              title="授权模式：AI 写回前要不要先问你"
            >
              <span className="cd-mode-dot" aria-hidden />
              {TIER_LABEL[tier] ?? tier}
              <span className="cd-mode-caret" aria-hidden>▾</span>
            </button>
            {modeOpen && (
              <div className="cd-mode-pop" data-testid="mode-pop" role="menu">
                <p className="cd-mode-head">授权模式</p>
                {Object.entries(TIER_LABEL).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    role="menuitemradio"
                    aria-checked={tier === key}
                    className={`cd-mode-item${tier === key ? " on" : ""}`}
                    data-testid={`mode-item-${key}`}
                    onClick={() => {
                      setModeOpen(false);
                      setTierState(key);
                      setPermissionTier(projectId, key as "confirm_each" | "allow_book" | "allow_all")
                        .catch(() => dispatch({ type: "gate", thread: threadKey, text: "档位切换失败，稍后再试。" }));
                    }}
                  >
                    <span className="cd-mode-check" aria-hidden>{tier === key ? "✓" : ""}</span>
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {chips.length === 0 && registration && (
        <div className="chatdock-nochips" data-testid="chat-nochips">
          本页不接入助手。
        </div>
      )}
      {chips.length > 0 && (
        <div className="chatdock-chips" data-testid="chat-chips">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              className="chatchip"
              disabled={c.disabled}
              title={c.hint}
              data-testid={`chat-chip-${c.key}`}
              onClick={() => {
                const enabled = featureEnabled(c.feature ?? undefined);
                if (enabled === false) {
                  onUpgrade?.(c.feature);
                  return;
                }
                if (c.open) onOpenAction?.(c.open);
                else send(c.command);
              }}
            >
              {c.label}
            </button>
          ))}
          <span className="chatdock-tierhint">发散类需 MAX · 起草类需 PRO</span>
        </div>
      )}

      <div className="chatdock-stream" ref={streamBoxRef} data-testid="chat-stream">
        {messages.map((m) => {
          if (m.kind === "divider") {
            return (
              <div key={m.id} className="cd-divider">
                <span>—— 切换到{m.page || "新页面"} ——</span>
              </div>
            );
          }
          if (m.kind === "trace") {
            const lines = (m.text ?? "").split("\n").filter(Boolean);
            return (
              <details key={m.id} className="cd-trace" data-testid="chat-trace-history">
                <summary>运行轨迹（{lines.length} 步）</summary>
                <ul>
                  {lines.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </details>
            );
          }
          if (m.kind === "gate") {
            return (
              <div key={m.id} className="cd-msg assistant">
                <div className="cd-bubble">{m.text}</div>
              </div>
            );
          }
          if (m.kind === "error") {
            return (
              <div key={m.id} className="cd-msg error" data-testid="chat-error">
                <div className="cd-bubble">{m.text}</div>
              </div>
            );
          }
          if (m.kind === "auth") {
            return (
              <div key={m.id} className="cd-msg assistant">
                <div className="cd-card gate" data-testid="auth-card">
                  <div className="cd-card-head">
                    <b>{m.gateHumanOnly ? "需要你确认" : "授权写入"}</b>
                  </div>
                  <pre className="cd-preview">{JSON.stringify(m.gatePreview, null, 1)}</pre>
                  {m.gateState === "pending" ? (
                    <div className="cd-card-foot">
                      <button
                        type="button"
                        className="cd-btn primary"
                        onClick={() => approve(m.gateId!, "approved")}
                      >
                        允许
                      </button>
                      <button
                        type="button"
                        className="cd-btn"
                        onClick={() => approve(m.gateId!, "denied")}
                      >
                        不允许
                      </button>
                    </div>
                  ) : (
                    <div className="cd-card-foot">
                      <span className="cd-dim">
                        {m.gateState === "approved"
                          ? "已允许并执行 ✓"
                          : m.gateState === "denied"
                            ? "已拒绝"
                            : "已过期——重发指令即可"}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          }
          if (m.kind === "card") {
            const isCharDraft = !!(m.cardPayload as Record<string, unknown> | undefined)?.character_draft;
            return (
              <div key={m.id} className="cd-msg assistant">
                <div className="cd-card" data-testid={`chat-card-${m.cardKind}`}>
                  <div className="cd-card-head">
                    <b>{isCharDraft ? "角色草案" : CARD_TITLES[m.cardKind ?? "text"] ?? "草案"}</b>
                    {m.cardStatus === "adopted" && <span className="cd-badge ok">已建卡 ✓</span>}
                  </div>
                  <CardBody kind={m.cardKind ?? "text"} payload={m.cardPayload} />
                  {isCharDraft && (m.cardStatus === "draft" || m.cardStatus === "stale") && (
                    <div className="cd-card-foot">
                      <button
                        type="button"
                        className="cd-btn primary"
                        data-testid="char-confirm"
                        disabled={confirmBusy}
                        onClick={() => void confirmCharacter(m.cardId!, (m.cardPayload ?? {}) as Record<string, string>)}
                      >
                        确认 · 建卡
                      </button>
                      <span className="cd-dim">确认后写入角色名册。</span>
                    </div>
                  )}
                  {(m.cardStatus === "draft" || m.cardStatus === "stale") && (
                    <div className="cd-card-foot">
                      {m.cardKind === "text" &&
                        typeof (m.cardPayload as Record<string, unknown> | undefined)?.draft === "object" && (
                          <button
                            type="button"
                            className="cd-btn primary"
                            data-testid="chat-adopt"
                            onClick={() => void adoptVolumeDraft(m.cardId!, (m.cardPayload ?? {}) as Record<string, unknown>)}
                          >
                            采纳 · 写入
                          </button>
                        )}
                      {m.cardStatus === "stale" ? (
                        <span className="cd-dim">已有一版采纳过——点采纳就换成这一版。</span>
                      ) : (
                        <span className="cd-dim">初稿——觉得哪里要改，直接说。</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          }
          const isUser = m.role === "user";
          return (
            <div key={m.id} className={`cd-msg ${isUser ? "user" : "assistant"}`}>
              <div className={`cd-bubble${isUser ? "" : " md"}`}>
                {isUser ? <ClampedText text={m.text} /> : <ChatMarkdown text={m.text} />}
                <CopyStrip text={m.text} align={isUser ? "right" : "left"} ts={m.ts} />
              </div>
              {/* TraceFolded（批E TraceFolded 组件语义内联）：run 收口后工具步折叠可回看 */}
              {(m.steps.length > 0 || m.thinking) && (
                <details className="cd-trace" data-testid="chat-trace">
                  <summary>
                    {m.steps.find((s) => s.domain)?.domain &&
                      `${m.steps.find((s) => s.domain)!.domain}助手 · `}
                    运行轨迹
                    {m.steps.length > 0 &&
                      `（${m.steps.length} 步：${m.steps.map((s) => s.tool).join("、")}）`}
                    {m.thinking && m.steps.length === 0 && "（思考过程）"}
                  </summary>
                  {m.thinking && (
                    <div className="cd-trace-think" data-testid="chat-trace-think">
                      <b>思考过程</b>
                      <pre>{_clip(m.thinking, 2000)}</pre>
                    </div>
                  )}
                  <ul>
                    {m.steps.map((s) => {
                      const modelCalls = (s.apiCalls ?? []).length;
                      return (
                        <li key={s.stepId}>
                          <b>{s.tool}</b>
                          {s.resultNote ? ` — ${s.resultNote}` : ""}
                          {modelCalls > 0 && (
                            <span className="cd-step-api">
                              {" "}
                              · 调用模型 ×{modelCalls}
                              {`（${(s.apiCalls ?? []).map((a) => a.op).join("、")}）`}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </details>
              )}
            </div>
          );
        })}

        {state.runActive && (
          <div className="cd-generating" data-testid="chat-generating">
            <div className="cd-gen-bar" />
            <span>
              AI 想着… {secs}s{" "}
              <button type="button" className="cd-reset" data-testid="chat-stop" onClick={stopRun}>
                停止
              </button>
            </span>
            {state.thinkingText && (
              <details className="cd-think">
                <summary>思考过程</summary>
                <pre>{_clip(state.thinkingText, 1200)}</pre>
              </details>
            )}
            <ul className="cd-steps">
              {runSteps.map((s) => (
                <li key={s.stepId}>
                  <b>{s.tool}</b>
                  {s.resultNote ? ` — ${_clip(s.resultNote, 80)}` : "（进行中）"}
                  {(s.apiCalls ?? []).length > 0 && (
                    <span className="cd-step-api"> · 调用模型 ×{(s.apiCalls ?? []).length}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {state.error && !messages.some((m) => m.kind === "error") && (
          <div className="cd-msg error">
            <div className="cd-bubble">{state.error}</div>
          </div>
        )}
      </div>

      {messages.length > 0 && (
        <div className={`cd-ctx${ctxHot ? " hot" : ""}`} data-testid="ctx-meter">
          <div className="cd-ctx-bar">
            <div className="cd-ctx-fill" style={{ width: `${Math.min(100, ctxPct)}%` }} />
          </div>
          <span className="cd-ctx-label">
            上下文 {formatWan(ctxEst)}/{formatWan(ctxWindow)}（{ctxPct}%）
            {ctxHot && " · 建议输入 /compact 压缩"}
          </span>
        </div>
      )}
      <div className="chatdock-composer">
        <div className="cd-help-anchor">
          {helpOpen && (
            <section className="cd-help-pop" data-testid="dock-help-pop" aria-label="助手须知">
              <h2 className="cd-help-title">助手须知</h2>
              <p className="cd-help-fence">我只做这本书和你的知识库内的事。其他的，我做不了。</p>
              <div className="cd-help-divider" aria-hidden="true" />
              <div className="cd-help-cmd">
                <code>/new</code>
                <div>
                  <b>开新对话</b>
                  <span>清空当前页签，从头开始。</span>
                </div>
              </div>
              <div className="cd-help-cmd">
                <code>/compact</code>
                <div>
                  <b>压缩会话历史</b>
                  <span>上下文紧张时用，保留要点。</span>
                </div>
              </div>
              <p className="cd-help-note">
                <i aria-hidden="true" />
                <span>上下文到 80% 时，我会提醒你压缩。</span>
              </p>
            </section>
          )}
          <button
            type="button"
            className={`cd-help-btn${helpOpen ? " on" : ""}`}
            data-testid="dock-help-btn"
            aria-label="查看助手须知"
            aria-expanded={helpOpen}
            onClick={() => setHelpOpen((v) => !v)}
          >
            ?
          </button>
        </div>
        <input
          value={input}
          placeholder={inputPlaceholder(page)}
          data-testid="chat-input"
          onChange={(e) => inputSet(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !sendDisabled) send(input);
          }}
        />
        <button
          type="button"
          className="cd-btn primary"
          data-testid="chat-send"
          disabled={sendDisabled}
          onClick={() => send(input)}
        >
          发送
        </button>
      </div>

    </div>
  );
}

const TIER_LABEL: Record<string, string> = {
  confirm_each: "每写必确认",
  allow_book: "本书内放行",
  allow_all: "全部放行",
};

const CARD_TITLES: Record<string, string> = {
  struct: "草案卡",
  text: "草案",
  report: "体检报告",
  pick: "候选",
};

function inputPlaceholder(page: string): string {
  if (page.includes("卷")) return "说说这一卷你想达成什么…";
  if (page.includes("角色")) return "说说这个角色想改哪，或让助手起草…";
  return "想改哪里、要写什么，直接说…";
}

