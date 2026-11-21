// Aui2Dock——@agentscope-ai/chat（阿里 Spark Chat）正式版 dock（c-agent-chat-memory
// 批1/批6 定版）。ChatAnywhere 容器＋ref.updateMessage 流式直控＋内置 Markdown。
// 契约保持（writing-assistant spec 全项）：产物卡/授权卡/错误卡真卡面
// （cardConfig）；产物卡「采纳 · 写入」过目写回＋同目标 stale＋已采纳徽标；
// 思考与工具过程＝回合气泡内独立过程泡泡（思考/每次工具各一张，默认单行折叠、
// 点开看全文/详情）；底栏模型/深度思考/授权三控件同排；斜杠命令 /new、
// /compact（命令不进对话历史——后端收口，clear 事件清屏）；线程本地镜像
// （每页签装载一次，切页不丢 live 内容——ChatDock 每线程桶同款语义）；页面切换
// 分隔标记；容量条（≥80% 警示＋/compact 提示）；停止钮断流保底；
// 崩溃兜底由宿主 AuiErrorBoundary 承担。
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { createPortal } from "react-dom";
import {
  writeBackCharacter,
  writeBackSettingsField,
  writeBackVolume,
  writeBackWorld,
} from "@/lib/dockWriteBack";
import { ConfigProvider } from "@agentscope-ai/design";
import { ChatAnywhere, OperateCard, uuid } from "@agentscope-ai/chat";
import type { ChatAnywhereRef } from "@agentscope-ai/chat";
import {
  SparkErrorCircleFill,
  SparkLoadingLine,
  SparkMemoryLine,
  SparkStopCircleLine,
  SparkTrueLine,
} from "@agentscope-ai/icons";
import { threadKeyOf, matchRegistration, type ChatPageScope } from "@/lib/chatRegistry";
import type { FeatureKey } from "@/lib/features";
import { useFeature } from "@/hooks/useTier";
import { useModelStatus } from "@/hooks/useModelStatus";
import { ModelPicker } from "@/components/novel/workbench/modals";
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
// 授权两层（c-agent-page-ops）：确认/自动；allow_all 存量值行为本等价，前端映射为自动档
const TIER_LABEL: Record<string, string> = {
  confirm_each: "每写必确认",
  allow_book: "自动执行·本书内",
};
// 输入框区授权选择器（OpenWorker Composer 权限选择器形态，阿里件＝Sender/ModeSelect）
const AUTH_OPTIONS: {
  value: string;
  icon: ReactNode;
  label: string;
  selectedLabel: string;
  tooltip: string;
}[] = [
  {
    value: "confirm_each",
    icon: <span aria-hidden>🛡️</span>,
    label: "每写必确认",
    selectedLabel: "每写必确认",
    tooltip: "每次写入前弹授权卡，你允许了才执行",
  },
  {
    value: "allow_book",
    icon: <span aria-hidden>⚡</span>,
    label: "自动执行·本书内",
    selectedLabel: "自动执行·本书内",
    tooltip: "写入不再逐次询问；归档等危险操作仍会弹卡确认",
  },
];
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
      {/* 字段级前后对比（c-agent-page-ops）：写工具 preview 带 changes 时渲染
          人话行（OpenWorker ApprovalCard permissionLines 同思路）；旧形状走 pre */}
      {(() => {
        const pv = data.preview as
          | {
              changes?: {
                field?: string;
                label?: string;
                before?: unknown;
                after?: unknown;
              }[];
            }
          | undefined;
        if (pv && Array.isArray(pv.changes) && pv.changes.length > 0) {
          return (
            <div className="cd-preview cd-preview-fields" data-testid="gate-preview-fields">
              {pv.changes.map((c, i) => {
                // 长值截断（review P3）：超 80 字撑卡——预览只求可判断，不求全文
                const clip = (v: unknown) => {
                  const t = String(v ?? "").trim();
                  return t === "" ? "（空）" : t.length > 80 ? `${t.slice(0, 80)}…` : t;
                };
                return (
                  <div className="cd-preview-field" key={`${c.field ?? c.label ?? i}`}>
                    <b>{c.label || c.field}</b>
                    <span className="cd-before">{clip(c.before)}</span>
                    <span className="cd-sep" aria-hidden>
                      →
                    </span>
                    <span className="cd-after">{clip(c.after)}</span>
                  </div>
                );
              })}
            </div>
          );
        }
        return <pre className="cd-preview">{JSON.stringify(data.preview, null, 1)}</pre>;
      })()}
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
  /** 回放去重计数（boss 拍板 2026-11-19）：同签名历史轨迹合并为一张「同样步骤 ×N」，
   *  每轮问答读一遍当前章会攒出成排 1 步卡，回看一张就够。实时运行不计数。 */
  count?: number;
};

/** 思考与轨迹卡（cardConfig 注册：code="trace"）——生成中实时展开，收口折叠回看 */
function TraceCard({ data }: { data: TraceCardData }) {
  const { thinking, steps, live, count } = data;
  const hasBody = Boolean(thinking.trim() || steps.length);
  if (!hasBody) return null;
  const names = [...new Set(steps.map((x) => x.split(" ")[0]))].join("、");
  return (
    <details className="cd-trace" data-testid="chat-trace" open={live && Boolean(thinking.trim())}>
      <summary>
        {live
          ? "思考与轨迹（进行中）"
          : count && count > 1
            ? `运行轨迹（同样步骤 ×${count}：${names}）`
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

/** 过程泡泡（c-agent-thinking-bubbles）：思考与每次工具调用各自一张 OperateCard——
 *  默认单行折叠、点开看全文/详情，和正文区分。挂在本回合 assistant 消息的 cards 上，
 *  库先渲染卡片再渲染正文（过程在上、回答在下，coding agent 同款顺序）。 */
export type ProcApiCall = {
  op: string;
  model: string;
  ms: number;
  tokens_in: number;
  tokens_out: number;
  ok: boolean;
};

export type TraceThinkingData = {
  text: string;
  /** 仍在流式思考→头「思考中」+ 转圈 */
  live?: boolean;
};

export type TraceToolData = {
  tool: string;
  /** 模型这一步的打算（step_start.label） */
  label?: string;
  /** 结果摘要（step_end.resultNote） */
  note?: string;
  /** 本步参数 JSON 预览（截断 ≤600 字） */
  args?: string;
  ok?: boolean;
  running?: boolean;
  interrupted?: boolean;
  apiCalls?: ProcApiCall[];
};

/** 过程进度行（列表首）：真实事件/计时派生，不渲染假进度 */
export type TraceStatusData = {
  live: boolean;
  startedAt?: number;
  endedAt?: number;
  failed?: boolean;
  /** 已完成的工具步数 */
  stepCount: number;
  /** 当前步序（运行中从 1 起；收口不用） */
  stepNo?: number;
  /** 当前动作：思考中/正在执行 X/整理回答/等待授权 */
  current?: string;
};

type ProcThinkingItem = { kind: "thinking"; id: string; text: string; live?: boolean };
type ProcToolItem = {
  kind: "tool";
  id: string;
  stepId?: string;
  tool: string;
  label?: string;
  note?: string;
  args?: string;
  ok?: boolean;
  running?: boolean;
  interrupted?: boolean;
  apiCalls?: ProcApiCall[];
};
type ProcItem = ProcThinkingItem | ProcToolItem;

type ProcBuf = {
  items: ProcItem[];
  live: boolean;
  startedAt: number;
  endedAt?: number;
  failed?: boolean;
  /** 授权卡停车等待作家批复（状态行显示「等待授权」） */
  waiting?: boolean;
  /** 正文已开流（状态行「整理回答」，不再是「等待模型」） */
  replying?: boolean;
};

type ProcCard = { code: string; id: string; data: unknown };

function fmtElapsed(sec: number): string {
  return sec < 60 ? `${sec} 秒` : `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
}

/** 过程缓冲 → 卡片：列首进度行 + 思考/工具卡（顺序＝发生顺序） */
function toProcCards(buf: ProcBuf): ProcCard[] {
  const items = buf.items;
  if (!items.length && !buf.live) return [];
  const toolCount = items.filter((it) => it.kind === "tool").length;
  const running = items.find(
    (it): it is ProcToolItem => it.kind === "tool" && Boolean(it.running),
  );
  const last = items[items.length - 1];
  const thinkingLive = last?.kind === "thinking" && Boolean(last.live);
  const hasInterrupted = items.some(
    (it) => it.kind === "tool" && Boolean(it.interrupted),
  );
  const current = buf.waiting
    ? "等待授权"
    : running
      ? `正在执行 ${running.tool}`
      : thinkingLive
        ? "思考中"
        : buf.live
          ? buf.replying || items.length
            ? "整理回答"
            : "等待模型"
          : undefined;
  const cards: ProcCard[] = [
    {
      code: "trace_status",
      id: "status",
      data: {
        live: buf.live,
        startedAt: buf.startedAt,
        endedAt: buf.endedAt,
        failed: Boolean(buf.failed || (!buf.live && hasInterrupted)),
        stepCount: toolCount,
        stepNo: toolCount + (running ? 0 : 1),
        current,
      } satisfies TraceStatusData,
    },
  ];
  for (const item of items) {
    cards.push(
      item.kind === "thinking"
        ? {
            code: "trace_thinking",
            id: item.id,
            data: { text: item.text, live: item.live } satisfies TraceThinkingData,
          }
        : {
            code: "trace_tool",
            id: item.id,
            data: {
              tool: item.tool,
              label: item.label,
              note: item.note,
              args: item.args,
              ok: item.ok,
              running: item.running,
              interrupted: item.interrupted,
              apiCalls: item.apiCalls,
            } satisfies TraceToolData,
          },
    );
  }
  return cards;
}

/** 历史回放：assistant 行 payload.process → 同序过程卡；无该键＝旧会话走旧轨迹卡 */
function processCardsFromPayload(payload: Record<string, unknown>): ProcCard[] | null {
  const raw = payload?.process;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const cards: ProcCard[] = [];
  let toolCount = 0;
  let interruptedCount = 0;
  raw.forEach((it, i) => {
    if (!it || typeof it !== "object") return;
    const item = it as Record<string, unknown>;
    if (item.kind === "thinking" && typeof item.text === "string" && item.text.trim()) {
      cards.push({
        code: "trace_thinking",
        id: `think-${i}`,
        data: { text: item.text, live: false } satisfies TraceThinkingData,
      });
    } else if (item.kind === "tool" && typeof item.tool === "string" && item.tool) {
      toolCount += 1;
      if (item.interrupted || item.running) interruptedCount += 1;
      cards.push({
        code: "trace_tool",
        id: `tool-${String(item.stepId || i)}`,
        data: {
          tool: item.tool,
          label: typeof item.label === "string" ? item.label : undefined,
          note: typeof item.note === "string" ? item.note : undefined,
          args: typeof item.args === "string" ? item.args : undefined,
          ok: typeof item.ok === "boolean" ? item.ok : undefined,
          running: false,
          interrupted: Boolean(item.interrupted || item.running),
          apiCalls: Array.isArray(item.apiCalls) ? (item.apiCalls as ProcApiCall[]) : undefined,
        } satisfies TraceToolData,
      });
    }
  });
  if (!cards.length) return null;
  return [
    {
      code: "trace_status",
      id: "status",
      data: {
        live: false,
        failed: interruptedCount > 0,
        stepCount: toolCount,
      } satisfies TraceStatusData,
    },
    ...cards,
  ];
}

/** 进度行（非折叠）：运行中实时走秒；收口/回放只给步数/用时 */
export function TraceStatusCard({ data }: { data: TraceStatusData }) {
  const { live, startedAt, endedAt, failed, stepCount, stepNo, current } = data;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live || !startedAt) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [live, startedAt]);
  const secs =
    startedAt != null
      ? Math.max(0, Math.round(((endedAt ?? now) - startedAt) / 1000))
      : null;
  const time = secs != null ? fmtElapsed(secs) : "";
  const text = live
    ? `运行中${current ? ` · ${current}` : ""} · 第 ${stepNo ?? 1} 步${time ? ` · 已等 ${time}` : ""}`
    : `${failed ? "已停止" : "完成"} · ${stepCount} 步${time ? ` · 用时 ${time}` : ""}`;
  const icon = live ? (
    <SparkLoadingLine spin />
  ) : failed ? (
    <SparkStopCircleLine />
  ) : (
    <SparkTrueLine />
  );
  return (
    <div className="cd-trace-status" data-testid="chat-trace-status">
      {icon}
      <span>{text}</span>
    </div>
  );
}

function TraceThinkingCard({ data }: { data: TraceThinkingData }) {
  const { text, live } = data;
  return (
    <div className="cd-proc-card" data-testid="chat-proc-thinking">
      <OperateCard
        header={{
          icon: live ? <SparkLoadingLine spin /> : <SparkMemoryLine />,
          title: live ? "思考中" : "思考过程",
        }}
        body={{
          defaultOpen: false,
          children: (
            <OperateCard.LineBody>
              <div className="cd-proc-think">{text}</div>
            </OperateCard.LineBody>
          ),
        }}
      />
    </div>
  );
}

/** 工具结果摘要里的人话头：读类返回结构化 JSON 时不把裸 JSON 顶在单行头上 */
function toolNoteHead(tool: string, note: string): string {
  const t = note.trim();
  if (!t) return "";
  if (t.startsWith("{") || t.startsWith("[")) {
    return tool.startsWith("read_") ? "已读取" : "已返回";
  }
  return note;
}

function isJsonNote(note: string): boolean {
  const t = note.trim();
  return t.startsWith("{") || t.startsWith("[");
}

function TraceToolCard({ data }: { data: TraceToolData }) {
  const { tool, label, note, args, ok, running, interrupted, apiCalls } = data;
  const failed = ok === false;
  const noteHead = toolNoteHead(tool, note ?? "");
  const icon = running ? (
    <SparkLoadingLine spin />
  ) : interrupted ? (
    <SparkStopCircleLine />
  ) : failed ? (
    <SparkErrorCircleFill />
  ) : (
    <SparkTrueLine />
  );
  const summary = running
    ? label || "正在执行…"
    : interrupted
      ? "被打断"
      : noteHead || (failed ? "没成功" : "已完成");
  const hasDetail = Boolean(label || note || args || apiCalls?.length);
  const apiOps = apiCalls?.length
    ? [...new Set(apiCalls.map((c) => c.op))].join("、")
    : "";
  const apiModels = apiCalls?.length
    ? [...new Set(apiCalls.map((c) => c.model))].join("、")
    : "";
  return (
    <div className="cd-proc-card" data-testid="chat-proc-tool">
      <OperateCard
        header={{ icon, title: tool, description: summary }}
        body={
          hasDetail
            ? {
                defaultOpen: false,
                children: (
                  <OperateCard.LineBody>
                    <div className="cd-proc-detail">
                      {label ? (
                        <div className="cd-proc-line">
                          <b>打算</b>
                          <span>{label}</span>
                        </div>
                      ) : null}
                      {args ? (
                        <div className="cd-proc-line">
                          <b>参数</b>
                          <span className="cd-proc-json">{args}</span>
                        </div>
                      ) : null}
                      {note ? (
                        <div className="cd-proc-line">
                          <b>结果</b>
                          <span className={isJsonNote(note) ? "cd-proc-json" : undefined}>
                            {note}
                          </span>
                        </div>
                      ) : null}
                      {apiCalls?.length ? (
                        <div className="cd-proc-line">
                          <b>模型调用</b>
                          <span>
                            {apiCalls.length} 次 · {apiOps}
                            {apiModels ? ` · ${apiModels}` : ""}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </OperateCard.LineBody>
                ),
              }
            : undefined
        }
      />
    </div>
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

/** 任务计划卡（cardConfig 注册：code="plan"）——多件交付物的逐项进度；
 *  四态映射 §5 状态语言：还没动/在做/做完了/没做成。 */
export type PlanItem = {
  id?: string;
  title: string;
  status: "pending" | "active" | "done" | "failed";
};
export type PlanCardData = {
  plan: { id?: string; items?: PlanItem[]; note?: string };
  incomplete?: number;
};

const PLAN_LABEL: Record<string, string> = {
  pending: "还没动",
  active: "在做",
  done: "做完了",
  failed: "没做成",
};

function PlanCard({ data }: { data: PlanCardData }) {
  const items = data.plan?.items ?? [];
  if (!items.length) return null;
  const done = items.filter((it) => it.status === "done").length;
  const undone = data.incomplete ?? items.length - done;
  return (
    <div className="cd-card cd-plan" data-testid="chat-plan">
      <div className="cd-card-head">
        <b>这次要做的事</b>
        <span className="cd-dim">
          {undone > 0 ? `做完 ${done} 件 · 还有 ${undone} 件没做` : "都做完了"}
        </span>
      </div>
      <div className="cd-plan-list">
        {items.map((it, i) => {
          const st = PLAN_LABEL[it.status] ? it.status : "pending";
          return (
            <div className="cd-plan-item" data-state={st} key={it.id ?? i}>
              <span className="cd-plan-dot">
                {st === "done" ? "✓" : st === "failed" ? "!" : st === "active" ? "·" : ""}
              </span>
              <span className="cd-plan-name">{it.title}</span>
              <span className="cd-plan-st">{PLAN_LABEL[st]}</span>
            </div>
          );
        })}
      </div>
      {data.plan.note && <p className="cd-plan-note">{data.plan.note}</p>}
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
  trace_status: TraceStatusCard,
  trace_thinking: TraceThinkingCard,
  trace_tool: TraceToolCard,
  error: ErrorCard,
  sys_action: SysActionCard,
  plan: PlanCard,
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
  pageUnsaved,
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
  /** 页面未保存标记（c-agent-page-ops）：随消息上行进提示词（界面零渲染） */
  pageUnsaved?: string[];
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
  /** 助手模型候选（底栏模型 pill；默认回落本书模型，不改本书绑定） */
  const modelStatus = useModelStatus(projectId);
  const bookModelKey =
    modelStatus.currentConfigId && modelStatus.currentModel
      ? `${modelStatus.currentConfigId}::${modelStatus.currentModel}`
      : "";
  const bookModelKeyRef = useRef(bookModelKey);
  bookModelKeyRef.current = bookModelKey;
  /** 深度思考开关（默认开；按线程记 localStorage——coding agent 底栏语义） */
  const prefsKey = `${projectId}:${threadKey}`;
  const [thinkingOn, setThinkingOn] = useState(true);
  const thinkingOnRef = useRef(true);
  /** 助手模型按会话覆盖（`${api_config_id}::${model}`；空/等于本书模型＝不覆盖） */
  const [modelKey, setModelKey] = useState("");
  useEffect(() => {
    let think = true;
    let savedModel = "";
    try {
      const t = window.localStorage.getItem(`assistant:think:${prefsKey}`);
      think = t !== "0";
      savedModel = window.localStorage.getItem(`assistant:model:${prefsKey}`) ?? "";
    } catch {
      /* localStorage 不可用（隐私模式等）：用默认值，不打断对话 */
    }
    thinkingOnRef.current = think;
    setThinkingOn(think);
    setModelKey(savedModel);
  }, [prefsKey]);
  const optionKeys = new Set(
    modelStatus.modelOptions.map((o) => `${o.api_config_id}::${o.model}`),
  );
  // 失效选择（配置被删/模型不在清单）回退本书模型——请求也不得发旧覆盖对
  const validModelKey = modelKey && optionKeys.has(modelKey) ? modelKey : "";
  const modelKeyRef = useRef(validModelKey);
  modelKeyRef.current = validModelKey;
  const effectiveModelKey = validModelKey || bookModelKey;
  const modelLabel =
    modelStatus.modelOptions.find(
      (o) => `${o.api_config_id}::${o.model}` === effectiveModelKey,
    )?.model || "选模型";
  const toggleThinking = useCallback(() => {
    const next = !thinkingOnRef.current;
    thinkingOnRef.current = next;
    setThinkingOn(next);
    try {
      window.localStorage.setItem(`assistant:think:${prefsKey}`, next ? "1" : "0");
    } catch {
      /* 记不住也不打断：本次生效 */
    }
  }, [prefsKey]);
  const chooseModel = useCallback(
    (key: string) => {
      setModelKey(key);
      try {
        window.localStorage.setItem(`assistant:model:${prefsKey}`, key);
      } catch {
        /* 记不住也不打断：本次生效 */
      }
    },
    [prefsKey],
  );
  /** chips 结构化触发（c-tool-flow 批2）：下一次 submit 携带的 tool_hint */
  const pendingHintRef = useRef<{ tool: string; args: Record<string, unknown> } | null>(null);
  /** 授权档位芯片（会话级 grants；切换即时生效＋持久化，失败回滚上一档） */
  const [tier, setTierState] = useState<Tier>("confirm_each");
  const tierRef = useRef<Tier>("confirm_each");
  const [authOpen, setAuthOpen] = useState(false); // 授权菜单展开态（输入框底栏 pill）
  const authWrapRef = useRef<HTMLDivElement | null>(null);
  const authMenuRef = useRef<HTMLDivElement | null>(null);
  // 弹层落点（portal 到 body：sender-content 有 overflow:hidden，内联绝对定位会被裁切）
  const [authMenuPos, setAuthMenuPos] = useState<{ left: number; bottom: number } | null>(null);
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
  /** 过程泡泡本地账（按 assistant 消息 id：卡片随正文更新不丢步） */
  const procBufRef = useRef<Map<string, ProcBuf>>(new Map());
  /** 当前 delta 段已流文本（narration 收口按内容前缀对账补尾——缺尾修复） */
  const deltaTailRef = useRef<string>("");

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

  /** 过程泡泡：思考/工具卡挂本轮 assistant 消息（正文之上，coding agent 顺序） */
  const upsertProc = useCallback(
    (assistantId: string, mutate: (s: ProcBuf) => ProcBuf) => {
      const prev = procBufRef.current.get(assistantId) ?? {
        items: [],
        live: true,
        startedAt: Date.now(),
      };
      const next = mutate({ ...prev, items: prev.items.map((it) => ({ ...it })) });
      procBufRef.current.set(assistantId, next);
      const cur = mirrorRef.current
        .get(threadKeyRef.current)
        ?.find((x) => x.id === assistantId);
      threadUp({
        id: assistantId,
        role: "assistant",
        content: cur?.content ?? "",
        msgStatus: cur?.msgStatus ?? "generating",
        cards: toProcCards(next),
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
          // 装载期间新提交的活体消息（ref 就绪前点了发送／chip）：服务端装载会
          // removeAllMessages，不补放就被吞掉（c-agent-thinking-bubbles 竞态实锤）
          const liveEntries = bucket.filter((e) => !e.id.startsWith("greet-"));
          api.removeAllMessages();
          let serverCount = 0;
          let lastPage = "";
          let pendingTrace: { id: string; data: TraceCardData } | null = null;
          // 新会话回合带 payload.process（思考/工具过程卡）——该回合后续旧 tool
          // 行不再折叠成旧轨迹卡，避免同一段过程回放两次
          let suppressLegacyTrace = false;
          // 回放去重账（签名→首张卡）：同签名轨迹合并计数，不另起新卡
          const traceSigs = new Map<string, { id: string; data: TraceCardData }>();
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
            if (!pendingTrace) return;
            const data: TraceCardData = { ...pendingTrace.data, live: false };
            const sig = data.steps.join("\n");
            const seen = traceSigs.get(sig);
            if (seen) {
              // 计数必须回写签名账：不回写则每次 bump 都从首卡 count=1 起算，永远 ×2
              const nextData: TraceCardData = {
                ...seen.data,
                count: (seen.data.count ?? 1) + 1,
                live: false,
              };
              traceSigs.set(sig, { id: seen.id, data: nextData });
              pushEntry({
                id: seen.id,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "trace", data: nextData }],
              });
            } else {
              traceSigs.set(sig, { id: pendingTrace.id, data });
              pushEntry({
                id: pendingTrace.id,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "trace", data }],
              });
            }
            pendingTrace = null;
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
              if (m.role === "user") suppressLegacyTrace = false;
              const procCards =
                m.role === "assistant"
                  ? processCardsFromPayload((m.payload ?? {}) as Record<string, unknown>)
                  : null;
              pushEntry({
                id: String(m.id ?? uuid()),
                role: m.role,
                content: m.content,
                history: true,
                ...(procCards ? { cards: procCards } : {}),
              });
              if (m.role === "assistant") suppressLegacyTrace = Boolean(procCards);
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
            } else if (m.role === "event" && m.cardKind === "plan") {
              // 计划快照回放（c-agent-action-contract）：同一计划 id 原地覆盖，
              // 取最新快照；旧前端对空 content event 行本就直接跳过
              const plan = (m.payload as { plan?: PlanCardData["plan"] })?.plan;
              if (plan) {
                flushTrace();
                pushEntry({
                  id: `plan-${plan.id ?? "current"}`,
                  role: "assistant",
                  content: "",
                  msgStatus: "finished",
                  cards: [{ code: "plan", data: { plan } }],
                });
                serverCount += 1;
              }
            } else if ((m.role === "tool" || m.role === "event") && m.content?.trim()) {
              if (!suppressLegacyTrace) {
                if (!pendingTrace)
                  pendingTrace = { id: `trace-${m.id}`, data: { thinking: "", steps: [], live: true } };
                pendingTrace.data.steps.push(m.content.trim());
              }
            }
            // 空 event 行（授权挂起载荷等）不进流
          }
          flushTrace();
          // 装载期间产生的活体消息补放（服务端历史之后；夹具/真机都不丢）
          for (const e of liveEntries) {
            api.updateMessage({
              id: e.id,
              role: e.role,
              content: e.content,
              ...(e.history ? { history: true } : {}),
              ...(e.msgStatus ? { msgStatus: e.msgStatus } : {}),
              ...(e.cards ? { cards: e.cards } : {}),
            });
          }
          if (serverCount === 0 && bucket.every((e) => e.id.startsWith("greet-"))) greet();
          mirrorRef.current.set(threadKey, bucket);
          loadedThreadsRef.current.add(threadKey);
          const raw = String((sess.grants as { tier?: string } | undefined)?.tier ?? "confirm_each");
          const t = raw === "allow_all" ? "allow_book" : raw; // 存量「全部放行」≡自动档
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

  // 选项行外点/Esc 收起（ChatDock 同款守卫；authbar 容器内点击不收）
  useEffect(() => {
    if (!authOpen) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (authWrapRef.current?.contains(t)) return;
      if (authMenuRef.current?.contains(t)) return; // portal 菜单在 body 下，须单独守护
      setAuthOpen(false);
    };
    const onResize = () => setAuthOpen(false); // 落点按打开时坐标算——窗口变化即收
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAuthOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [authOpen]);

  const switchTier = useCallback(
    (next: Tier) => {
      const prev = tierRef.current;
      setAuthOpen(false);
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
      threadUp({ id: assistantId, role: "assistant", content: "", msgStatus: "generating" });
      // 过程进度行立即出现（不等第一个 thinking/step）；起始时刻=本轮提交
      procBufRef.current.set(assistantId, {
        items: [],
        live: true,
        startedAt: Date.now(),
      });
      upsertProc(assistantId, (s) => s);

      // delta 段对账账本按轮清零（c-agent-narration-persist）：上一轮的尾巴不能
      // 参与本轮前缀对账，否则本轮收口整段会被误判「非覆盖」而重复上屏。
      deltaTailRef.current = "";
      setStreaming(true);
      onStreamingChange?.(true);
      // hint 一次性（c-agent-writing-flow-context）：spec 语义＝「tool_hint 随下一次
      // 发送携带」（assistant-chat-ui）——读走即清，不得随后续消息重放强制执行旧工具。
      const pendingHint = pendingHintRef.current;
      pendingHintRef.current = null;
      // 模型按会话覆盖：只有选了非本书模型才随请求发（等于本书模型＝不覆盖）
      const picked = modelKeyRef.current;
      let modelSel: { api_config_id: string; model: string } | undefined;
      if (picked && picked !== bookModelKeyRef.current) {
        const cut = picked.indexOf("::");
        if (cut > 0) {
          modelSel = { api_config_id: picked.slice(0, cut), model: picked.slice(cut + 2) };
        }
      }
      abortRef.current = streamAssistantChat(
        projectId,
        {
          message: query,
          page,
          thread: threadKeyRef.current,
          focus: scope.chapterRef ? { ref: scope.chapterRef } : undefined,
          page_state: pageUnsaved?.length ? { unsaved: pageUnsaved } : undefined,
          tool_hint: pendingHint ?? undefined,
          ...(modelSel
            ? { api_config_id: modelSel.api_config_id, model: modelSel.model }
            : {}),
          thinking: thinkingOnRef.current,
        },
        {
          onEvent: (e) => {
            const cur = mirrorRef.current
              .get(threadKeyRef.current)
              ?.find((x) => x.id === assistantId);
            const base = cur?.content ?? "";
            // 正文开流：撤销「等待授权」、从「等待模型」切到「整理回答」
            const markReplying = () => {
              const buf = procBufRef.current.get(assistantId);
              if (buf && (buf.waiting || !buf.replying)) {
                upsertProc(assistantId, (s) => ({
                  ...s,
                  waiting: false,
                  replying: true,
                }));
              }
            };
            if (e.type === "narration_delta") {
              markReplying();
              const chunk = String(e.text ?? "");
              deltaTailRef.current += chunk;
              estCharsRef.current += chunk.length;
              threadUp({
                id: assistantId,
                role: "assistant",
                content: base + chunk,
                msgStatus: "generating",
              });
            } else if (e.type === "narration") {
              markReplying();
              // 整段 narration 与 delta 段按内容前缀对账（缺尾修复
              // c-agent-narration-tail-loss）：整段覆盖已流 delta 时只补未流
              // 尾巴（旧口径 seenDelta 整段跳过会把扣尾/冻结窗尾巴吞掉——生产
              // 实锤显示缺「你说走哪条，我跟着动。」尾 8 字）；非覆盖＝新段
              // （工具步叙述/降级兜底）按 \n\n 追加；零流式批次交付同此径。
              const chunk = String(e.text ?? "");
              const tail = deltaTailRef.current;
              const tailTrim = tail.replace(/\s+$/, "");
              let suffix = "";
              let covered = false;
              if (tail && chunk.startsWith(tail)) {
                // 欠覆盖：整段比已流 delta 长——补未流尾巴
                suffix = chunk.slice(tail.length);
                covered = true;
              } else if (tail && (chunk === tailTrim || (tailTrim && chunk.startsWith(tailTrim)))) {
                // 过覆盖（哨兵前换行进过 delta）：已流内容已含整段——只收敛不追加
                suffix = chunk.startsWith(tailTrim) ? chunk.slice(tailTrim.length) : "";
                covered = true;
              }
              if (covered) {
                deltaTailRef.current = chunk;
                if (suffix) {
                  estCharsRef.current += suffix.length;
                  threadUp({
                    id: assistantId,
                    role: "assistant",
                    content: base + suffix,
                    msgStatus: "generating",
                  });
                }
              } else {
                deltaTailRef.current = "";
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
              // 思考增量 → 独立思考泡泡（默认单行；点开看全文）——不占正文、
              // 不计入上下文容量（思考不进外发窗口）
              const chunk = String(e.text ?? "");
              if (chunk) {
                upsertProc(assistantId, (s) => {
                  const items = s.items;
                  const last = items[items.length - 1];
                  if (last?.kind === "thinking") {
                    return {
                      ...s,
                      waiting: false,
                      items: [
                        ...items.slice(0, -1),
                        { ...last, text: last.text + chunk, live: true },
                      ],
                    };
                  }
                  return {
                    ...s,
                    waiting: false,
                    items: [
                      ...items,
                      { kind: "thinking", id: `think-${items.length}`, text: chunk, live: true },
                    ],
                  };
                });
              }
            } else if (e.type === "step_start") {
              // 工具调用 → 独立工具泡泡（运行中：转圈 + 这一步的打算）
              const tool = String(e.tool ?? "tool");
              const stepId = String(e.stepId ?? "");
              upsertProc(assistantId, (s) => ({
                ...s,
                waiting: false,
                items: [
                  ...s.items.map((it) =>
                    it.kind === "thinking" ? { ...it, live: false } : it,
                  ),
                  {
                    kind: "tool",
                    id: `tool-${stepId || s.items.length}`,
                    stepId,
                    tool,
                    label: e.label ? String(e.label) : undefined,
                    running: true,
                  },
                ],
              }));
            } else if (e.type === "step_end") {
              // 原位补该步结果/模型调用（不新起卡；不在正文追加 ● tool ✓）
              const tool = String(e.tool ?? "tool");
              const stepId = String(e.stepId ?? "");
              const note = String(e.resultNote ?? "");
              const argsRaw =
                e.args &&
                typeof e.args === "object" &&
                Object.keys(e.args).length > 0
                  ? JSON.stringify(e.args)
                  : "";
              const args =
                argsRaw.length > 600 ? `${argsRaw.slice(0, 600)}…` : argsRaw;
              upsertProc(assistantId, (s) => {
                const items = s.items;
                const idx = items.findIndex(
                  (it) => it.kind === "tool" && it.stepId === stepId,
                );
                const patch: Partial<ProcToolItem> = {
                  running: false,
                  note,
                  ...(args ? { args } : {}),
                  ...(typeof e.ok === "boolean" ? { ok: e.ok } : {}),
                  ...(Array.isArray(e.apiCalls) ? { apiCalls: e.apiCalls } : {}),
                };
                if (idx >= 0) {
                  const next = [...items];
                  next[idx] = { ...(next[idx] as ProcToolItem), ...patch };
                  return { ...s, waiting: false, items: next };
                }
                return {
                  ...s,
                  waiting: false,
                  items: [
                    ...items,
                    {
                      kind: "tool",
                      id: `tool-${stepId || items.length}`,
                      stepId,
                      tool,
                      ...patch,
                    },
                  ],
                };
              });
              // delta 段按步分段（c-agent-narration-persist）：上一模型的叙述尾巴
              // 不得带进下一步的前缀对账——否则下一步收口整段被误判「非覆盖」，
              // 已流 delta 与整段 narration 双份上屏（回归钉实锤）。
              deltaTailRef.current = "";
            } else if (e.type === "plan" && e.plan) {
              // 计划快照实时更新（c-agent-action-contract）：同一计划原地翻态
              const plan = e.plan as PlanCardData["plan"];
              threadUp({
                id: `plan-${plan.id ?? "current"}`,
                role: "assistant",
                content: "",
                msgStatus: "finished",
                cards: [{ code: "plan", data: { plan } }],
              });
            } else if (e.type === "run_end") {
              // run_end 携带本轮写操作 effects → 缓存待 onDone 回调宿主
              if (Array.isArray(e.effects)) {
                pendingEffectsRef.current = e.effects;
              }
              // 收口安全网后的最终计划快照（active 已降级）＋未完成计数
              if (e.plan) {
                const plan = e.plan as PlanCardData["plan"];
                threadUp({
                  id: `plan-${plan.id ?? "current"}`,
                  role: "assistant",
                  content: "",
                  msgStatus: "finished",
                  cards: [
                    {
                      code: "plan",
                      data: {
                        plan,
                        incomplete: Number(e.planIncomplete ?? 0),
                      },
                    },
                  ],
                });
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
              procBufRef.current.clear();
              apiRef.current?.removeAllMessages();
              estCharsRef.current = 0;
              setCtx(null);
            } else if (e.type === "artifact") {
              // 产物卡＝独立卡消息（cardConfig 按 code 渲染 CardBody 原卡面）；
              // 同目标旧卡标 stale（过目采纳链：一目标一版有效）
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
              if (e.gateId) {
                upsertProc(assistantId, (s) => ({ ...s, waiting: true }));
              }
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
              if (e.gateId) {
                upsertProc(assistantId, (s) => ({ ...s, waiting: true }));
              }
            } else if (e.type === "error") {
              // 错误卡收尾（保留已产出内容——错误独立成卡不覆写正文）；
              // 进度行同步停表标「已停止」
              upsertProc(assistantId, (s) => ({
                ...s,
                live: false,
                endedAt: Date.now(),
                failed: true,
                items: s.items.map((it) =>
                  it.kind === "thinking"
                    ? { ...it, live: false }
                    : it.running
                      ? { ...it, running: false, interrupted: true }
                      : it,
                ),
              }));
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
            upsertProc(assistantId, (s) => ({
              ...s,
              live: false,
              waiting: false,
              endedAt: Date.now(),
              failed: true,
              items: s.items.map((it) =>
                it.kind === "thinking"
                  ? { ...it, live: false }
                  : it.running
                    ? { ...it, running: false, interrupted: true }
                    : it,
              ),
            }));
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
            // 过程收口：思考停转、未完成的工具步标打断（回看如实）；进度行停表
            upsertProc(assistantId, (s) => ({
              ...s,
              live: false,
              waiting: false,
              endedAt: Date.now(),
              items: s.items.map((it) =>
                it.kind === "thinking"
                  ? { ...it, live: false }
                  : it.running
                    ? { ...it, running: false, interrupted: true }
                    : it,
              ),
            }));
            threadUp({
              id: assistantId,
              role: "assistant",
              content: cur?.content ?? "",
              msgStatus: "finished",
            });
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
    [projectId, page, scope.chapterRef, pageUnsaved, upsertProc, onStreamingChange, onEffects, onEffect],
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
        <div className="cd-mode-head">
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
            onInput={{
              onSubmit,
              // 授权模式选择器进输入框底栏左端（c-agent-page-ops review 整改：ZCode
              // 位置——pill 与发送按钮同一行；footer 插槽会渲染在 actions 行之下另起
              // 一行（实测 pill y=907 vs 发送 y=875），morePrefixActions 才是底栏左端）
              morePrefixActions: (
                <div className="cd-footbar" data-testid="aui2-footbar">
                  {modelStatus.modelOptions.length > 0 ? (
                    <ModelPicker
                      options={modelStatus.modelOptions}
                      value={effectiveModelKey}
                      bookValue={bookModelKey}
                      onPick={chooseModel}
                      label="助手模型"
                      triggerLabel={modelLabel}
                      triggerTitle={`助手模型：${modelLabel}（只影响助手对话，不改本书写作模型）`}
                      triggerClass="cd-auth-pill cd-model-pill"
                      panelWidth={300}
                    />
                  ) : (
                    <button
                      type="button"
                      className="cd-auth-pill cd-model-pill"
                      disabled
                      title={
                        modelStatus.loading
                          ? "正在读模型配置"
                          : "还没有可用的模型配置"
                      }
                    >
                      {modelStatus.loading ? "模型加载中…" : "未配模型"}
                    </button>
                  )}
                  <button
                    type="button"
                    className={`cd-auth-pill cd-think-pill${thinkingOn ? " on" : ""}`}
                    data-testid="aui2-think-pill"
                    aria-pressed={thinkingOn}
                    title={
                      thinkingOn
                        ? "深度思考已开——助手先想再动手，慢一点但更稳；点一下关掉"
                        : "深度思考已关——直接答更快；点一下打开"
                    }
                    onClick={toggleThinking}
                  >
                    <span className="cd-think-dot" aria-hidden />
                    深度思考
                  </button>
                  <div
                    className="cd-authwrap"
                    ref={authWrapRef}
                    data-testid="aui2-authbar"
                  >
                  <button
                    type="button"
                    className="cd-auth-pill"
                    data-testid="aui2-auth-pill"
                    aria-haspopup="menu"
                    aria-expanded={authOpen}
                    aria-label="授权模式"
                    onClick={() => {
                      if (authOpen) {
                        setAuthOpen(false);
                        return;
                      }
                      const r = authWrapRef.current?.getBoundingClientRect();
                      if (!r) return;
                      setAuthMenuPos({
                        left: r.left,
                        bottom: window.innerHeight - r.top + 8,
                      });
                      setAuthOpen(true);
                    }}
                  >
                    <span className="cd-auth-ico" aria-hidden>
                      {tier === "allow_book" ? "⚡" : "🛡️"}
                    </span>
                    {TIER_LABEL[tier] ?? tier}
                    <span className="cd-auth-caret" aria-hidden>
                      ▾
                    </span>
                  </button>
                  </div>
                </div>
              ),
            }}
            onUpload={[]}
            uiConfig={{ quickInput: [] }}
            cardConfig={CARD_REGISTRY}
            onStop={() => stopRun()}
          />
        </DockCtx.Provider>
      </ConfigProvider>
      {authOpen &&
        authMenuPos &&
        createPortal(
          <div
            className="cd-auth-menu"
            role="menu"
            data-testid="aui2-auth-menu"
            ref={authMenuRef}
            style={{ left: authMenuPos.left, bottom: authMenuPos.bottom }}
          >
            {AUTH_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                role="menuitemradio"
                aria-checked={tier === o.value}
                className={`cd-auth-item${tier === o.value ? " on" : ""}`}
                data-testid={`aui2-auth-item-${o.value}`}
                onClick={() => {
                  switchTier(o.value as Tier);
                  setAuthOpen(false);
                }}
              >
                <span className="cd-auth-ico" aria-hidden>
                  {o.icon}
                </span>
                <span className="cd-auth-main">
                  <span className="cd-auth-label">
                    {o.label}
                    {tier === o.value ? " ✓" : ""}
                  </span>
                  <span className="cd-auth-desc">{o.tooltip}</span>
                </span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
