// Aui2Dock——@agentscope-ai/chat（阿里 Spark Chat）正式版 dock（c-agent-chat-memory
// 批1/批6 定版）。ChatAnywhere 容器＋ref.updateMessage 流式直控＋内置 Markdown。
// 契约保持（writing-assistant spec 全项）：产物卡/授权卡/错误卡/轨迹卡真卡面
// （cardConfig）；产物卡「采纳 · 写入」过目写回＋同目标 stale＋已采纳徽标；
// 思考增量＋工具轨迹＝trace 卡（生成中展开、完成后折叠回看）；斜杠命令 /new、
// /compact（命令不进对话历史——后端收口，clear 事件清屏）；线程本地镜像
// （每页签装载一次，切页不丢 live 内容——ChatDock 每线程桶同款语义）；页面切换
// 分隔标记；容量条（≥80% 警示＋/compact 提示）；授权档位芯片三档；停止钮断流保底；
// 崩溃兜底由宿主 AuiErrorBoundary 承担。
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  writeBackCharacter,
  writeBackSettingsField,
  writeBackVolume,
  writeBackWorld,
} from "@/lib/dockWriteBack";
import { ConfigProvider } from "@agentscope-ai/design";
import { ChatAnywhere, uuid } from "@agentscope-ai/chat";
import type { ChatAnywhereRef } from "@agentscope-ai/chat";
import { threadKeyOf, matchRegistration, type ChatPageScope } from "@/lib/chatRegistry";
import type { FeatureKey } from "@/lib/features";
import { useFeature } from "@/hooks/useTier";
import {
  streamAssistantChat,
  loadAssistantSession,
  approveGate,
  setPermissionTier,
  adoptAssistantMessage,
  stopAssistantRun,
} from "@/lib/chatApi";
import { CardBody, _clip } from "./CardBody";
import { conversationToMarkdown } from "@/lib/chatCopy";
// chat.css 的唯一入口曾随 ChatDock 退役被带走（dock 全程裸奔＝抽屉/芯片/卡面全无样式）
import "./chat.css";

/** 授权档位（write_gate 三档；硬地板不受档位影响由后端保证） */
const TIER_LABEL: Record<string, string> = {
  confirm_each: "每写必确认",
  allow_book: "本书内放行",
  allow_all: "全部放行",
};
type Tier = keyof typeof TIER_LABEL;

type MirrorEntry = {
  id: string;
  role: "user" | "assistant";
  content: string;
  cards?: { code: string; data: unknown }[];
  msgStatus?: "generating" | "finished" | "error";
  history?: boolean;
};

type CardMsg = { code: string; data: unknown };

/** dock 写入上下文：卡面组件（在 ChatAnywhere 树内渲染）用它翻卡面态/发回执/
 *  写回后按域请宿主刷新（c-agent-panel-consolidate） */
const DockCtx = createContext<{
  apiRef: { current: ChatAnywhereRef | null };
  up: (entry: MirrorEntry) => void;
  /** 采纳账登记（同目标新卡到货判 stale 的依据） */
  markAdopted: (cardId: string) => void;
  /** 采纳写回后的域刷新上抛（宿主走 dirty 守卫再重载面板） */
  refreshDomain?: (domain: "settings" | "chapters") => void;
} | null>(null);

/** 产物卡（cardConfig 注册：code="artifact"）——复用既有 CardBody，视觉零变化；
 *  「采纳 · 写入」按卡种写回（c-agent-panel-consolidate）：卷纲草案 PUT volumes／
 *  settings 字段卡 GET+merge+PUT settings/<stype>／世界观卡（文本格）merge world／
 *  角色草案卡建卡＋写 name/persona（其余字段在卡上照着补）。
 *  adopted 翻已建卡徽标、同目标新卡把旧卡标 stale。 */

function ArtifactCard(props: { data: ArtifactCardData; id?: string }) {
  const { data, id } = props;
  const ctx = useContext(DockCtx);
  const [busy, setBusy] = useState(false);
  const payload = (data.payload ?? {}) as Record<string, unknown>;
  const status = data.status ?? "draft";
  const isVolumeDraft =
    data.kind === "text" &&
    typeof (payload.draft as Record<string, unknown> | undefined) === "object" &&
    payload.vol_no != null;
  // 可写回卡种判定（c-agent-panel-consolidate）：settings 字段卡／世界观文本格卡／角色草案卡
  const isSettingsField = payload.stype != null && payload.field != null && payload.value != null;
  const isWorldCard =
    data.kind === "text" && payload.topic != null && payload.draft != null && payload.vol_no == null;
  const isCharacterDraft = payload.character_draft != null;
  const adoptable = isVolumeDraft || isSettingsField || isWorldCard || isCharacterDraft;

  const adopt = async () => {
    if (!id || !data.projectId || !ctx) return;
    setBusy(true);
    try {
      let receipt: string;
      if (isVolumeDraft) {
        receipt = await writeBackVolume(data.projectId, payload);
      } else if (isSettingsField) {
        receipt = await writeBackSettingsField(data.projectId, payload);
      } else if (isWorldCard) {
        receipt = await writeBackWorld(data.projectId, payload);
      } else if (isCharacterDraft) {
        receipt = await writeBackCharacter(data.projectId, payload);
      } else {
        throw new Error("这张卡没有对应的写入动作——按卡面提示回面板操作。");
      }
      ctx.markAdopted(id);
      if (data.cardId) {
        // 采纳回执落库（best-effort×3 退避）：事件到前端可能早于服务端 append 落卡
        // （404 竞态）——重开书后「已采纳」徽标与 stale 防护不丢
        void (async () => {
          for (let i = 0; i < 3; i += 1) {
            await new Promise((r) => setTimeout(r, 400 * (i + 1)));
            try {
              await adoptAssistantMessage(data.projectId!, data.cardId!);
              return;
            } catch {
              /* 404 竞态重试；三连败放弃（徽标本地已翻，仅回执落库缺失） */
            }
          }
        })();
      }
      ctx.up({ id, role: "assistant", content: "", msgStatus: "finished", cards: [{ code: "artifact", data: { ...data, status: "adopted" } }] });
      // 写回后按域刷新（c-agent-panel-consolidate）：settings 域走宿主 dirty 守卫
      ctx.refreshDomain?.(isSettingsField || isWorldCard ? "settings" : "chapters");
      ctx.up({ id: `rcpt-${id}`, role: "assistant", content: receipt });
    } catch (e) {
      ctx.up({
        id: `err-${id}`,
        role: "assistant",
        content: "",
        msgStatus: "finished",
        cards: [{ code: "error", data: { message: (e as Error)?.message || "写入失败" } }],
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cd-card" data-testid={`chat-card-${data.kind}`}>
      <div className="cd-card-head">
        <b>产物</b>
        {status === "adopted" && <span className="cd-badge ok">已建卡 ✓</span>}
        {status === "stale" && <span className="cd-badge">旧版</span>}
      </div>
      <CardBody kind={data.kind} payload={payload} />
      {(status === "draft" || status === "stale") && (
        <div className="cd-card-foot">
          {adoptable && (
            <button
              type="button"
              className="cd-btn primary"
              disabled={busy}
              data-testid="chat-adopt"
              onClick={() => void adopt()}
            >
              采纳 · 写入
            </button>
          )}
          {status === "stale" ? (
            <span className="cd-dim">已有一版采纳过——点采纳就换成这一版。</span>
          ) : (
            <span className="cd-dim">初稿——觉得哪里要改，直接说。</span>
          )}
        </div>
      )}
    </div>
  );
}

type GateCardData = {
  gateId: string;
  preview: unknown;
  humanOnly: boolean;
  projectId: string;
  resolved?: "approved" | "denied";
  failNote?: string;
  /** 历史回放的待决授权＝已过期（重启不跨——重发指令即可） */
  expired?: boolean;
};

/** 授权卡（cardConfig 注册：code="gate"）——流内批复，批完原地翻卡面态 */
function GateCard(props: { data: GateCardData; id?: string }) {
  const { data, id } = props;
  const ctx = useContext(DockCtx);
  const [busy, setBusy] = useState(false);

  const decide = async (decision: "approved" | "denied") => {
    setBusy(true);
    try {
      await approveGate(data.projectId, data.gateId, decision);
      if (id && ctx) {
        ctx.up({
          id,
          role: "assistant",
          content: "",
          msgStatus: "finished",
          cards: [{ code: "gate", data: { ...data, resolved: decision } }],
        });
      }
    } catch (e) {
      if (id && ctx) {
        ctx.up({
          id,
          role: "assistant",
          content: "",
          msgStatus: "finished",
          cards: [
            {
              code: "gate",
              data: { ...data, resolved: "denied", failNote: (e as Error)?.message ?? "" },
            },
          ],
        });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cd-card gate" data-testid="aui2-auth-card">
      <div className="cd-card-head">
        <b>{data.humanOnly ? "需要你确认" : "授权写入"}</b>
      </div>
      <pre className="cd-preview">{JSON.stringify(data.preview, null, 1)}</pre>
      {data.expired ? (
        <div className="cd-dim" style={{ padding: "6px 10px" }}>
          这张授权单已过期——重新说一声要做的事，我再请你确认。
        </div>
      ) : data.resolved ? (
        <div className="cd-dim" style={{ padding: "6px 10px" }}>
          {data.resolved === "approved"
            ? data.humanOnly
              ? "已确认。"
              : "已授权，这一步写进书里了，想反悔随时撤销。"
            : "已拒绝，这一步没有执行。"}
          {data.failNote ? `（${data.failNote}）` : ""}
        </div>
      ) : (
        <div className="cd-card-foot">
          <button
            type="button"
            className="cd-btn primary"
            disabled={busy}
            data-testid="aui2-gate-approve"
            onClick={() => void decide("approved")}
          >
            {data.humanOnly ? "确认" : "允许"}
          </button>
          <button
            type="button"
            className="cd-btn"
            disabled={busy}
            data-testid="aui2-gate-deny"
            onClick={() => void decide("denied")}
          >
            拒绝
          </button>
        </div>
      )}
    </div>
  );
}

export type TraceCardData = {
  /** 思考增量累计（回看全文） */
  thinking: string;
  /** 工具步摘要（`tool ✓ — note`；summary 取首段工具名） */
  steps: string[];
  /** 生成中＝展开；收口后折叠（回看不丢） */
  live: boolean;
};

/** 思考与轨迹卡（cardConfig 注册：code="trace"）——生成中实时展开，收口折叠回看 */
function TraceCard({ data }: { data: TraceCardData }) {
  const { thinking, steps, live } = data;
  const hasBody = Boolean(thinking.trim() || steps.length);
  if (!hasBody) return null;
  const names = [...new Set(steps.map((x) => x.split(" ")[0]))].join("、");
  return (
    <details className="cd-trace" data-testid="chat-trace" open={live && Boolean(thinking.trim())}>
      <summary>
        {live
          ? "思考与轨迹（进行中）"
          : `运行轨迹（${steps.length} 步${names ? `：${names}` : ""}）`}
      </summary>
      {thinking.trim() && <pre>{_clip(thinking, 2000)}</pre>}
      {steps.length > 0 && (
        <ul>
          {steps.map((st, i) => {
            const [tool, ...rest] = st.split(" ");
            return (
              <li key={i}>
                <b>{tool}</b>
                {rest.length > 0 && <span> {rest.join(" ")}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </details>
  );
}

/** 错误卡（cardConfig 注册：code="error"）——错误以卡收尾并保留已产出内容 */
function ErrorCard({ data }: { data: { message: string } }) {
  return (
    <div className="cd-msg error" data-testid="chat-error">
      <div className="cd-bubble">⚠ {data.message}</div>
    </div>
  );
}

/** 系统引导动作卡（code="sys_action"）——no_key 等系统 gate 的可点击出口
 *  （action: config_model → 模型配置页；2026-11-18 boss 走查口径：引导要给出口） */
function SysActionCard({ data }: { data: { action?: string; label?: string } }) {
  const navigate = useNavigate();
  const target = data.action === "config_model" || !data.action ? "/config" : null;
  if (!target) return null;
  return (
    <div className="cd-msg" data-testid="chat-sys-action">
      <button
        type="button"
        className="cd-btn primary"
        onClick={() => navigate(target)}
      >
        {data.label || "去处理"}
      </button>
    </div>
  );
}

const CARD_REGISTRY = {
  artifact: ArtifactCard,
  gate: GateCard,
  trace: TraceCard,
  error: ErrorCard,
  sys_action: SysActionCard,
};

type ArtifactCardData = {
  kind: string;
  payload: unknown;
  /** 采纳回执落库锚（assistant_messages id）＋写回目标（vol_no/draft） */
  cardId?: string;
  projectId?: string;
  /** draft | adopted | stale（过目采纳才写回——writing-assistant spec 硬契约） */
  status?: "draft" | "adopted" | "stale";
};

/** 产物卡目标键（同目标才判 stale——ChatDock 同款） */
function cardTargetKey(kind: string, payload: unknown): string {
  const d = (payload ?? {}) as Record<string, unknown>;
  if (d.vol_no != null) return `vol-${d.vol_no}`;
  if (typeof d.ref === "string" && d.ref) return d.ref;
  if (typeof d.entry_id === "string" && d.entry_id) return d.entry_id;
  if (typeof d.chapter_ref === "string" && d.chapter_ref) return d.chapter_ref;
  return kind;
}

const PAGE_LABELS: Record<string, string> = {
  volume: "卷纲",
  chapter: "章节",
  chars: "设定 · 角色",
  genre: "设定 · 题材",
  premise: "设定 · 主线",
  preview: "预览",
};

function pageLabel(page: string): string {
  if (!page) return "新页面";
  return PAGE_LABELS[page] ?? page;
}

export function Aui2Dock({
  projectId,
  page,
  scope,
  onUpgrade,
  onCloseDrawer,
  onOpenAction,
  onStreamingChange,
  onEffects,
  onEffect,
  autoAsk,
}: {
  projectId: string;
  page: string;
  scope: ChatPageScope;
  /** 权益不足引导（feature 门禁失败时上浮——ChatDock 同款） */
  onUpgrade?: (feature?: FeatureKey) => void;
  /** 窄屏抽屉态关闭（ChatDock 同款） */
  onCloseDrawer?: () => void;
  /** 富交互入口（open 芯片→既有弹窗/检测流——对话不吞弹窗） */
  onOpenAction?: (action: string) => void;
  /** 流式存活上抛（宿主并入树锁定守卫——ChatDock 同款契约） */
  onStreamingChange?: (v: boolean) => void;
  /** agent 写操作后的前端效果回调（NovelWorkspace 按域刷新数据） */
  onEffects?: (effects: { action: string; domain: string; target?: string }[]) => void;
  /** 单条即时 effect（c-agent-nav：navigate 中途翻页——活体事件，不入镜像不落库） */
  onEffect?: (effect: { action: string; domain: string; target?: string; description?: string }) => void;
  /** 面板「让助手办」命令式触发（c-agent-panel-consolidate）：seq 变更即自动
   *  提交 message——与手输同一条 submit 链，键校验/域校验/授权梯度零绕过 */
  autoAsk?: { seq: number; message: string };
}) {
  const threadKey = threadKeyOf(scope);
  const apiRef = useRef<ChatAnywhereRef | null>(null);
  const threadKeyRef = useRef(threadKey);
  threadKeyRef.current = threadKey;
  /** scope 镜像（开场白取 greeting 用；scope 是内联对象——进 deps 会循环重装载） */
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  /** chips 结构化触发（c-tool-flow 批2）：下一次 submit 携带的 tool_hint */
  const pendingHintRef = useRef<{ tool: string; args: Record<string, unknown> } | null>(null);
  /** 授权档位芯片（会话级 grants；切换即时生效＋持久化，失败回滚上一档） */
  const [tier, setTierState] = useState<Tier>("confirm_each");
  const tierRef = useRef<Tier>("confirm_each");
  const [modeOpen, setModeOpen] = useState(false);
  const modeAnchorRef = useRef<HTMLDivElement | null>(null);
  /** 流式中止（本地兜底 abort——主路径是 stop 端点协同取消，保收口回执落库） */
  const abortRef = useRef<(() => void) | null>(null);
  /** agent 写操作 effects 缓存（run_end 携带，onDone 时回调宿主） */
  const pendingEffectsRef = useRef<{ action: string; domain: string; target?: string }[]>([]);
  /** 停止当前 run（服务端协同取消优先；端点失败回落本地断流） */
  const stopRun = useCallback(() => {
    const localAbort = abortRef.current;
    stopAssistantRun(projectId, threadKeyRef.current).catch(() => localAbort?.());
  }, [projectId]);
  /** 流式中（chat-stop 显隐；与 onStreamingChange 同源） */
  const [streaming, setStreaming] = useState(false);
  /** 复制对话反馈（c-chat-copy）：「已复制 ✓」驻留 1.6s 后还原；写不进剪贴板
   *  静默还原（AiCardModal 提示词复制同款口径）。倒计时挂 handler 内——卸载后
   *  setState 为 React 18 安全 no-op，无需 effect 清理。 */
  const [copiedAll, setCopiedAll] = useState(false);
  const copyResetRef = useRef<number | null>(null);
  /** 复制整段对话（c-chat-copy）：ChatAnywhere ref 拿当前会话全量消息 →
   *  纯函数拼 Markdown → 剪贴板。trace 卡/空回执不进（chatCopy 口径）。 */
  const copyConversation = async () => {
    const md = conversationToMarkdown(apiRef.current!.getMessages());
    if (!md) return;
    try {
      await navigator.clipboard.writeText(md);
      if (copyResetRef.current != null) window.clearTimeout(copyResetRef.current);
      // v8 行归因怪癖：执行由「已复制 ✓」文案断言实锤（454 行在 453 行之后），计量恒 0
      /* v8 ignore next */
      copyResetRef.current = window.setTimeout(() => setCopiedAll(false), 1600);
      setCopiedAll(true);
    } catch {
      /* 剪贴板不可写静默还原：不弹错不打断 */
    }
  };
  /** 容量估算（chars/4 同后端口径；装载时以服务端 estTokens 播种） */
  const estCharsRef = useRef(0);
  const [ctx, setCtx] = useState<{ estTokens: number; window: number; pct: number } | null>(null);
  /** 产物卡目标账（同目标 stale 判定）＋已采纳账（不翻 stale） */
  const cardTargetsRef = useRef<Map<string, string>>(new Map());
  const adoptedTargetsRef = useRef<Set<string>>(new Set());
  /**
   * 线程本地镜像（切页接续的关键）：每线程一份消息镜像，装载一次（服务端回放
   * 灌镜像）后切回不再拉服务器——直接重放镜像（live 内容不丢，ChatDock 时代
   * useChatSession 每线程桶的同款语义；跨重启持久仍靠服务端装载）。
   */
  const mirrorRef = useRef<Map<string, MirrorEntry[]>>(new Map());
  const loadedThreadsRef = useRef<Set<string>>(new Set());
  /** trace 卡本地账（按 traceId 累计——避免 getMessage 读回的丢更新） */
  const traceBufRef = useRef<Map<string, TraceCardData>>(new Map());
  /** 本 run 是否走过 delta 流（narration 兜底的去重依据） */
  const seenDeltaRef = useRef<Set<string>>(new Set());

  /** 线程镜像 upsert＝唯一写路径（镜像与画面同源不漂移） */
  const threadUp = useCallback((entry: MirrorEntry) => {
    const thread = threadKeyRef.current;
    const bucket = mirrorRef.current.get(thread) ?? [];
    const i = bucket.findIndex((e) => e.id === entry.id);
    if (i >= 0) bucket[i] = { ...bucket[i], ...entry };
    else bucket.push(entry);
    mirrorRef.current.set(thread, bucket);
    apiRef.current?.updateMessage({
      id: entry.id,
      role: entry.role,
      content: entry.content,
      ...(entry.history ? { history: true } : {}),
      ...(entry.msgStatus ? { msgStatus: entry.msgStatus } : {}),
      ...(entry.cards ? { cards: entry.cards } : {}),
    });
  }, []);

  /** dock 上下文（卡面组件翻态/发回执走同一 upsert；采纳账同步登记；写回后域刷新） */
  const markAdopted = useCallback((cardId: string) => {
    adoptedTargetsRef.current.add(cardId);
  }, []);
  const refreshDomain = useCallback(
    (domain: "settings" | "chapters") => {
      onEffects?.([{ action: "refresh", domain }]);
    },
    [onEffects],
  );
  const dockCtx = useMemo(
    () => ({ apiRef, up: threadUp, markAdopted, refreshDomain }),
    [threadUp, markAdopted, refreshDomain],
  );

  /** trace 卡：本地账累计（同帧多次事件不丢步）＋镜像 upsert */
  const upsertTrace = useCallback(
    (traceId: string, mutate: (d: TraceCardData) => TraceCardData) => {
      const prev = traceBufRef.current.get(traceId) ?? { thinking: "", steps: [], live: true };
      const next = mutate({ ...prev });
      traceBufRef.current.set(traceId, next);
      threadUp({
        id: traceId,
        role: "assistant",
        content: "",
        msgStatus: next.live ? "generating" : "finished",
        cards: [{ code: "trace", data: next }],
      });
    },
    [threadUp],
  );

  // 权益门（ChatDock 同款五 feature——芯片点击分流用）
  const fPlan = useFeature("ai-plan");
  const fGen = useFeature("ai-generate");
  const fPlot = useFeature("ai-plot");
  const fDiv = useFeature("assistant-diverge");
  const fFields = useFeature("settings-ai-fields");
  const featureEnabled = (key?: FeatureKey): boolean | undefined => {
    if (!key) return undefined;
    switch (key) {
      case "ai-plan":
        return fPlan;
      case "ai-generate":
        return fGen;
      case "ai-plot":
        return fPlot;
      case "assistant-diverge":
        return fDiv;
      case "settings-ai-fields":
        return fFields;
      default:
        return undefined;
    }
  };

  // 历史接续：切线程时——已装载线程重放本地镜像（live 内容不丢）；首见线程服务端
  // 装载灌镜像（工具/事件行折叠 trace 卡；页面变化插切换标记；授权卡过期回显）
  useEffect(() => {
    if (!projectId) return; // 无书态（书架/过渡帧）：不发 session 请求（404 噪音）
    estCharsRef.current = 0;
    setCtx(null);
    let cancelled = false;

    /** 等待 ref 就绪（ChatAnywhere ref 在子树首次 commit 后才有值）＋双帧缓冲 */
    const whenReady = (fn: (api: ChatAnywhereRef) => void, tries = 120) => {
      const api = apiRef.current;
      if (cancelled) return;
      if (!api) {
        if (tries > 0) requestAnimationFrame(() => whenReady(fn, tries - 1));
        return;
      }
      let frames = 2;
      const kick = () => {
        if (cancelled) return;
        if (frames > 0) {
          frames -= 1;
          requestAnimationFrame(kick);
        } else {
          fn(api);
        }
      };
      requestAnimationFrame(kick);
    };

    const replay = (api: ChatAnywhereRef) => {
      /** 开场白：空线程给状态感知开场白（仅本地呈现，不落库——挂载即发，首帧可见；
       *  历史非空时随装载被覆盖） */
      const greet = () => {
        const sc = scopeRef.current;
        const greeting = matchRegistration(sc)?.greeting(sc);
        if (greeting)
          threadUp({ id: `greet-${threadKeyRef.current}`, role: "assistant", content: greeting });
      };

      if (loadedThreadsRef.current.has(threadKey)) {
        // 已装载线程：重放本地镜像（服务端不重拉——live 内容保留）
        api.removeAllMessages();
        for (const e of mirrorRef.current.get(threadKey) ?? []) {
          api.updateMessage({
            id: e.id,
            role: e.role,
            content: e.content,
            ...(e.history ? { history: true } : {}),
            ...(e.msgStatus ? { msgStatus: e.msgStatus } : {}),
            ...(e.cards ? { cards: e.cards } : {}),
          });
        }
        return;
      }

      greet();
      void (async () => {
        try {
          const sess = await loadAssistantSession(projectId, threadKey);
          if (cancelled) return;
          const bucket = mirrorRef.current.get(threadKey) ?? [];
          const seen = new Set(bucket.map((e) => e.id));
          api.removeAllMessages();
          let serverCount = 0;
          let lastPage = "";
          let pendingTrace: { id: string; data: TraceCardData } | null = null;
          const pushEntry = (e: MirrorEntry) => {
            const i = bucket.findIndex((x) => x.id === e.id);
            if (i >= 0) bucket[i] = { ...bucket[i], ...e };
            else bucket.push(e);
            api.updateMessage({
              id: e.id,
              role: e.role,
              content: e.content,
              ...(e.history ? { history: true } : {}),
              ...(e.msgStatus ? { msgStatus: e.msgStatus } : {}),
              ...(e.cards ? { cards: e.cards } : {}),
            });
          };
          const flushTrace = () => {
            if (pendingTrace) {
              pushEntry({
                id: pendingTrace.id,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "trace", data: { ...pendingTrace.data, live: false } }],
              });
              pendingTrace = null;
            }
          };
          for (const m of sess.messages ?? []) {
            // 页面切换标记：相邻消息 page 变化即插一行（spec：流内落切换标记）
            const p = m.page ?? "";
            if (p && lastPage && p !== lastPage) {
              flushTrace();
              pushEntry({
                id: `div-${m.id}`,
                role: "assistant",
                content: `—— 切换到${pageLabel(p)} ——`,
              });
            }
            if (p) lastPage = p;
            if ((m.role === "user" || m.role === "assistant") && m.content) {
              flushTrace();
              pushEntry({
                id: String(m.id ?? uuid()),
                role: m.role,
                content: m.content,
                history: true,
              });
              serverCount += 1;
              estCharsRef.current += m.content.length;
            } else if (m.cardKind === "gate" && m.role === "assistant") {
              // 历史授权卡＝已过期（待决授权不跨重启——重发指令即可）
              const auth = ((m.payload ?? {}) as Record<string, unknown>).pending_gate as
                | Record<string, unknown>
                | undefined;
              if (auth) {
                flushTrace();
                pushEntry({
                  id: String(m.id ?? uuid()),
                  role: "assistant",
                  content: "",
                  msgStatus: "finished",
                  cards: [
                    {
                      code: "gate",
                      data: {
                        gateId: String(auth.gate_id ?? ""),
                        preview: auth.preview ?? {},
                        humanOnly: Boolean(auth.humanOnly),
                        projectId,
                        expired: true,
                      },
                    },
                  ],
                });
              }
            } else if (m.cardKind && m.role === "assistant") {
              // 历史产物卡：回执落库的 adopted 态回显（重开书徽标不丢）
              flushTrace();
              const payload = (m.payload ?? {}) as Record<string, unknown>;
              const card = (payload.card ?? payload) as Record<string, unknown>;
              const isAdopted = m.status === "adopted";
              const mid = String(m.id ?? uuid());
              const cardData: ArtifactCardData = {
                kind: m.cardKind,
                payload: card,
                cardId: String((payload as { cardId?: string }).cardId ?? mid),
                projectId,
                status: isAdopted ? "adopted" : "draft",
              };
              if (isAdopted) adoptedTargetsRef.current.add(mid);
              cardTargetsRef.current.set(mid, cardTargetKey(cardData.kind, card));
              flushTrace();
              pushEntry({
                id: mid,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "artifact", data: cardData }],
              });
              serverCount += 1;
            } else if ((m.role === "tool" || m.role === "event") && m.content?.trim()) {
              if (!pendingTrace)
                pendingTrace = { id: `trace-${m.id}`, data: { thinking: "", steps: [], live: true } };
              pendingTrace.data.steps.push(m.content.trim());
            }
            // 空 event 行（授权挂起载荷等）不进流
          }
          flushTrace();
          if (serverCount === 0 && bucket.every((e) => e.id.startsWith("greet-"))) greet();
          mirrorRef.current.set(threadKey, bucket);
          loadedThreadsRef.current.add(threadKey);
          const t = String((sess.grants as { tier?: string } | undefined)?.tier ?? "confirm_each");
          if (t in TIER_LABEL) {
            setTierState(t as Tier);
            tierRef.current = t as Tier;
          }
          if (sess.context?.window) {
            const seeded = sess.context.estTokens ?? 0;
            estCharsRef.current = Math.max(estCharsRef.current, seeded * 4);
            setCtx({ estTokens: seeded, window: sess.context.window, pct: sess.context.pct ?? 0 });
          }
        } catch {
          /* 历史失败静默——开场白已在就绪时给出 */
        }
      })();
    };

    whenReady(replay);
    return () => {
      cancelled = true;
    };
  }, [projectId, threadKey, threadUp]);

  // 授权下拉外点收起（ChatDock 同款守卫）
  useEffect(() => {
    if (!modeOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!modeAnchorRef.current?.contains(e.target as Node)) setModeOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setModeOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [modeOpen]);

  const switchTier = useCallback(
    (next: Tier) => {
      const prev = tierRef.current;
      setModeOpen(false);
      setTierState(next);
      tierRef.current = next;
      setPermissionTier(projectId, next as "confirm_each" | "allow_book" | "allow_all").catch(() => {
        // 失败回滚到切换前档位（不打断对话；下次打开下拉可见真实档位）
        setTierState(prev);
        tierRef.current = prev;
      });
    },
    [projectId],
  );

  const onSubmit = useCallback(
    async (data: { query: string }) => {
      const query = (data?.query ?? "").trim();
      if (!query) return;
      const isCommand = query.startsWith("/");
      // 斜杠命令不进对话历史（spec：命令本身 SHALL NOT 进入对话历史）
      if (!isCommand) {
        threadUp({ id: uuid(), role: "user", content: query });
        estCharsRef.current += query.length;
      }
      const assistantId = uuid();
      const traceId = `trace-${assistantId}`;
      threadUp({ id: assistantId, role: "assistant", content: "", msgStatus: "generating" });

      setStreaming(true);
      onStreamingChange?.(true);
      // hint 一次性（c-agent-writing-flow-context）：spec 语义＝「tool_hint 随下一次
      // 发送携带」（assistant-chat-ui）——读走即清，不得随后续消息重放强制执行旧工具。
      const pendingHint = pendingHintRef.current;
      pendingHintRef.current = null;
      abortRef.current = streamAssistantChat(
        projectId,
        {
          message: query,
          page,
          thread: threadKeyRef.current,
          focus: scope.chapterRef ? { ref: scope.chapterRef } : undefined,
          tool_hint: pendingHint ?? undefined,
        },
        {
          onEvent: (e) => {
            const cur = mirrorRef.current
              .get(threadKeyRef.current)
              ?.find((x) => x.id === assistantId);
            const base = cur?.content ?? "";
            if (e.type === "narration_delta") {
              const chunk = String(e.text ?? "");
              seenDeltaRef.current.add(assistantId);
              estCharsRef.current += chunk.length;
              threadUp({
                id: assistantId,
                role: "assistant",
                content: base + chunk,
                msgStatus: "generating",
              });
            } else if (e.type === "narration") {
              // 整段 narration：delta 路径的正文已增量送达（seenDelta）→ 不重拼；
              // 无 delta（协议批次路径）→ 追加（步轨迹行已占 base 也不能吞收口回复）
              const chunk = String(e.text ?? "");
              if (!seenDeltaRef.current.has(assistantId)) {
                estCharsRef.current += chunk.length;
                const sep = base ? "\n\n" : "";
                threadUp({
                  id: assistantId,
                  role: "assistant",
                  content: base + sep + chunk,
                  msgStatus: "generating",
                });
              }
            } else if (e.type === "thinking") {
              // 思考增量 → trace 卡实时展开（收口折叠回看）
              const chunk = String(e.text ?? "");
              estCharsRef.current += chunk.length;
              upsertTrace(traceId, (d) => ({ ...d, thinking: d.thinking + chunk }));
            } else if (e.type === "step_end") {
              // 工具步：轻量轨迹行（过程信息用文本）＋trace 卡步列表（回看）
              const tool = String(e.tool ?? "tool");
              const note = e.resultNote ? ` — ${_clip(String(e.resultNote), 80)}` : "";
              threadUp({
                id: assistantId,
                role: "assistant",
                content: base + `\n\n● ${tool} ✓`,
                msgStatus: "generating",
              });
              upsertTrace(traceId, (d) => ({ ...d, steps: [...d.steps, `${tool} ✓${note}`] }));
            } else if (e.type === "run_end") {
              // run_end 携带本轮写操作 effects → 缓存待 onDone 回调宿主
              if (Array.isArray(e.effects)) {
                pendingEffectsRef.current = e.effects;
              }
            } else if (e.type === "effect") {
              // 即时 effect（c-agent-nav：navigate 中途翻页）——直接回调宿主；
              // 不进镜像不落库（活体事件，历史回放不 teleport）
              onEffect?.({
                action: String(e.action ?? ""),
                domain: String(e.domain ?? ""),
                target: e.target == null ? undefined : String(e.target),
                description: e.description == null ? undefined : String(e.description),
              });
            } else if (e.type === "clear") {
              // /new：服务端已清，前端同步清屏（命令与旧对话都不留）
              mirrorRef.current.set(threadKeyRef.current, []);
              apiRef.current?.removeAllMessages();
              estCharsRef.current = 0;
              setCtx(null);
            } else if (e.type === "artifact") {
              // 产物卡＝独立卡消息（cardConfig 按 code 渲染 CardBody 原卡面）；
              // 交付前把挂着的 trace 卡收口（交付物与过程分离）。
              // 同目标旧卡标 stale（过目采纳链：一目标一版有效）
              upsertTrace(traceId, (d) => ({ ...d, live: false }));
              const payload = (e.payload ?? {}) as Record<string, unknown>;
              const cardData: ArtifactCardData = {
                kind: String(e.kind ?? payload.kind ?? "text"), // kind 在事件层（后端契约；payload.kind 兼容旧桩）
                payload,
                cardId: e.cardId ? String(e.cardId) : undefined,
                projectId,
                status: "draft",
              };
              const cardId = String(e.cardId ?? uuid());
              const targetKey = cardTargetKey(cardData.kind, payload);
              // 同目标已有 adopted 卡 → 新卡到货即标 stale「旧版」（旧卡保持已采纳；
              // stale 卡仍可再采纳＝替换写回——ChatDock 语义）
              const hasAdoptedSameTarget = [...cardTargetsRef.current.entries()].some(
                ([mid, key]) => key === targetKey && adoptedTargetsRef.current.has(mid),
              );
              if (hasAdoptedSameTarget) cardData.status = "stale";
              cardTargetsRef.current.set(cardId, targetKey);
              threadUp({
                id: cardId,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "artifact", data: cardData }],
              });
            } else if (e.type === "permission_required") {
              // 写授权卡（write_gate 停车）：gateId/preview/humanOnly 全在事件顶层
              threadUp({
                id: String(e.gateId ?? uuid()),
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [
                  {
                    code: "gate",
                    data: {
                      gateId: String(e.gateId ?? ""),
                      preview: e.preview ?? {},
                      humanOnly: Boolean(e.humanOnly),
                      projectId,
                    },
                  },
                ],
              });
            } else if (e.type === "gate") {
              // 系统提示类 gate（no_key/client_error——无 gateId 带 message）：
              // 引导语按助手话术呈现，SHALL NOT 兜进授权卡渲染成空预览卡
              if (!e.gateId && !e.refusal && (e.message || e.reason)) {
                const action = String((e as Record<string, unknown>).action ?? "");
                threadUp({
                  id: `sys-${assistantId}`,
                  role: "assistant",
                  content: String(e.message ?? e.reason ?? ""),
                  ...(action
                    ? {
                        cards: [
                          {
                            code: "sys_action",
                            data: { action, label: "去配模型" },
                          },
                        ],
                      }
                    : {}),
                });
                return;
              }
              // 权益引导（无 gateId 的 gate 事件）：引导语按助手话术呈现
              if (e.refusal && !e.gateId) {
                threadUp({
                  id: `up-${assistantId}`,
                  role: "assistant",
                  content: String(e.refusal ?? ""),
                });
                return;
              }
              // 授权卡＝独立卡消息（允许/拒绝流内批复）
              threadUp({
                id: String(e.gateId ?? uuid()),
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [
                  {
                    code: "gate",
                    data: {
                      gateId: String(e.gateId ?? ""),
                      preview: (e as Record<string, unknown>).preview ?? {},
                      humanOnly: Boolean((e as Record<string, unknown>).humanOnly),
                      projectId,
                    },
                  },
                ],
              });
            } else if (e.type === "error") {
              // 错误卡收尾（保留已产出内容——错误独立成卡不覆写正文）
              threadUp({
                id: `err-${assistantId}`,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "error", data: { message: String(e.message ?? "") } }],
              });
            }
          },
          onError: (msg) => {
            // 错误卡收尾（已产出内容保留在原气泡——错误独立成卡）
            threadUp({
              id: `err-${assistantId}`,
              role: "assistant",
              content: "",
              msgStatus: "finished",
              cards: [{ code: "error", data: { message: msg } }],
            });
            setStreaming(false);
            onStreamingChange?.(false);
            abortRef.current = null;
          },
          onDone: () => {
            const cur = mirrorRef.current
              .get(threadKeyRef.current)
              ?.find((x) => x.id === assistantId);
            threadUp({
              id: assistantId,
              role: "assistant",
              content: cur?.content ?? "",
              msgStatus: "finished",
            });
            // trace 卡收口折叠（思考回看不丢——coding agent 口径）
            upsertTrace(traceId, (d) => ({ ...d, live: false }));
            // 容量条即时续算（服务端口径 chars/4；下一轮装载以服务端回读校准）
            setCtx((c) => {
              if (!c) return c;
              const est = Math.max(0, Math.round(estCharsRef.current / 4));
              return {
                ...c,
                estTokens: est,
                pct: Math.min(100, Math.round((est / c.window) * 1000) / 10),
              };
            });
            setStreaming(false);
            onStreamingChange?.(false);
            abortRef.current = null;
            // agent 写操作 effects 回调宿主（NovelWorkspace 按域刷新）
            if (pendingEffectsRef.current.length > 0 && onEffects) {
              onEffects(pendingEffectsRef.current);
              pendingEffectsRef.current = [];
            }
          },
        },
      );
    },
    [projectId, page, scope.chapterRef, upsertTrace, onStreamingChange, onEffects, onEffect],
  );

  // 面板「让助手办」自动提交（c-agent-panel-consolidate）：seq 消费一次即记账
  // （防 effect 重跑重发）；与手输同一条 onSubmit 链——键校验/域校验/授权梯度零绕过
  const autoAskSeqRef = useRef(0);
  useEffect(() => {
    const seq = autoAsk?.seq ?? 0;
    const message = (autoAsk?.message ?? "").trim();
    if (!seq || seq === autoAskSeqRef.current || !message) return;
    autoAskSeqRef.current = seq;
    void onSubmit({ query: message });
  }, [autoAsk, onSubmit]);

  const ctxPct = ctx ? Math.min(100, ctx.pct) : 0;
  const ctxHot = ctxPct >= 80;

  return (
    <div className="chatdock aui2" data-testid="aui2-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手</b>
        <div className="cd-mode-anchor cd-mode-head" ref={modeAnchorRef}>
          <button
            type="button"
            className="cd-mode-chip"
            data-testid="aui2-mode-chip"
            aria-expanded={modeOpen}
            title="授权模式：AI 写回前要不要先问你"
            onClick={() => setModeOpen((v) => !v)}
          >
            <span className="cd-mode-dot" aria-hidden />
            {TIER_LABEL[tier] ?? tier}
            <span className="cd-mode-caret" aria-hidden>
              ▾
            </span>
          </button>
          <button
            type="button"
            className="cd-btn"
            data-testid="chat-copy-all"
            title="把整段对话复制成 Markdown（也可拖选后右键/Cmd+C 复制片段）"
            onClick={() => void copyConversation()}
          >
            {copiedAll ? "已复制 ✓" : "复制对话"}
          </button>
          {streaming && (
            <button
              type="button"
              className="cd-btn"
              data-testid="chat-stop"
              title="停止生成（已产出保留）"
              onClick={() => stopRun()}
            >
              停止
            </button>
          )}
          {onCloseDrawer && (
            <button
              type="button"
              className="cd-btn"
              data-testid="chat-drawer-close"
              aria-label="收起助手"
              onClick={onCloseDrawer}
            >
              收起
            </button>
          )}
          {modeOpen && (
            <div className="cd-mode-pop" data-testid="aui2-mode-pop" role="menu">
              <p className="cd-mode-head">授权模式</p>
              {(Object.entries(TIER_LABEL) as [Tier, string][]).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="menuitemradio"
                  aria-checked={tier === key}
                  className={`cd-mode-item${tier === key ? " on" : ""}`}
                  data-testid={`aui2-mode-item-${key}`}
                  onClick={() => switchTier(key)}
                >
                  <span className="cd-mode-check" aria-hidden>
                    {tier === key ? "✓" : ""}
                  </span>
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <ConfigProvider>
        <DockCtx.Provider value={dockCtx}>
          <div className="chatdock-chips" data-testid="aui2-chips">
            {(matchRegistration(scope)?.chips(scope) ?? []).map((c) => (
              <button
                key={c.key}
                type="button"
                className="chatchip"
                disabled={c.disabled}
                title={c.hint}
                data-testid={`aui2-chip-${c.key}`}
                onClick={() => {
                  const enabled = featureEnabled(c.feature ?? undefined);
                  if (enabled === false) {
                    onUpgrade?.(c.feature);
                    return;
                  }
                  if (c.open) onOpenAction?.(c.open);
                  else {
                    pendingHintRef.current = { tool: c.key, args: c.args ?? {} };
                    void onSubmit({ query: c.command });
                  }
                }}
              >
                {c.label}
              </button>
            ))}
            <span className="chatdock-tierhint">发散类需 MAX · 起草类需 PRO</span>
          </div>
          {ctx && ctx.estTokens > 0 && (
            <div className={`cd-ctx${ctxHot ? " hot" : ""}`} data-testid="aui2-ctx-meter">
              <div className="cd-ctx-bar">
                <div className="cd-ctx-fill" style={{ width: `${ctxPct}%` }} />
              </div>
              <span className="cd-ctx-label">
                上下文 {ctx.estTokens}/{ctx.window}（{ctxPct}%）
                {ctxHot ? " · 建议输入 /compact 压缩" : ""}
              </span>
            </div>
          )}
          <ChatAnywhere
            ref={apiRef}
            onInput={{ onSubmit }}
            onUpload={[]}
            uiConfig={{ quickInput: [] }}
            cardConfig={CARD_REGISTRY}
            onStop={() => stopRun()}
          />
        </DockCtx.Provider>
      </ConfigProvider>
    </div>
  );
}
