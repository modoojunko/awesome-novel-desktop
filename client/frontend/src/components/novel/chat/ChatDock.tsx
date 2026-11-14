// ChatDock——右栏常驻对话助手（c-writing-agent 批E）。
// 三层：上下文徽标＋能力盘 chips（随页面换）→ 对话流（消息＋产物卡＋授权卡）→
// 输入框。产物卡过目采纳才落框（ai-modal-confirm-rule 对话形态）；授权卡批复走
// /approve 停车；门控卡不打断对话流（spec writing-assistant）。
// 视觉全部取 base.css 令牌（design:lint 约束）；样式见同目录 chat.css。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  adoptAssistantMessage,
  approveGate,
  loadAssistantSession,
  resetAssistantSession,
  setPermissionTier,
  streamAssistantChat,
} from "@/lib/chatApi";
import { api } from "@/lib/api";
import { matchRegistration, type ChatChip, type ChatPageScope } from "@/lib/chatRegistry";
import type { LandingView } from "@/lib/novelStage";
import { useFeature } from "@/hooks/useTier";
import type { FeatureKey } from "@/lib/features";
import { useChatSession, type ChatMessage } from "@/hooks/useChatSession";
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
  const text = typeof payload === "string" ? payload : JSON.stringify(payload);
  return <p className="cd-pre">{_clip(text, 900)}</p>;
}

function _clip(text: string, budget: number): string {
  if (text.length <= budget) return text;
  return `${text.slice(0, budget - 1)}…`;
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

  // 历史回看（projectId 就绪才拉；重开即续聊——转写即状态）
  useEffect(() => {
    if (!projectId) return; // 路由参数未就绪的空串帧不发请求（批F 修正：空 id 命中曾让历史误空）
    let cancelled = false;
    void loadAssistantSession(projectId)
      .then((s) => {
        if (cancelled || s.messages.length === 0) return;
        const messages = s.messages.map((m) => {
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
            return { id: m.id, role: "system" as const, kind: "trace" as const, text: m.content, steps: [] };
          }
          if (m.role === "user" || (m.role === "assistant" && m.content)) {
            return {
              id: m.id,
              role: m.role as "user" | "assistant",
              kind: "text" as const,
              text: m.content,
              page: m.page,
              steps: [],
            };
          }
          return { id: m.id, role: "system" as const, kind: "trace" as const, text: m.content, steps: [] };
        });
        dispatch({ type: "load_history", messages });
      })
      .catch(() => {/* 首次失败静默——发消息时会再暴露 */});
    return () => {
      cancelled = true;
    };
  }, [projectId, dispatch]);

  // 开场白：会话内首见该页投递一次（spec §每页注册制）
  useEffect(() => {
    if (!registration || state.messages.length > 0) return;
    const greeting = registration.greeting(scope);
    if (greeting && greetedPageRef.current !== registration.id) {
      greetedPageRef.current = registration.id;
      dispatch({
        type: "gate",
        text: greeting,
      });
    }
  }, [registration, scope, state.messages.length, dispatch]);

  // 流式存活上抛（宿主并入树锁定守卫）
  useEffect(() => {
    onStreamingChange?.(state.runActive);
  }, [state.runActive, onStreamingChange]);

  // 贴底滚动
  useEffect(() => {
    const box = streamBoxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [state.messages, state.thinkingText]);

  // 计秒（生成中态）
  useEffect(() => {
    if (!state.runActive) {
      setSecs(0);
      return;
    }
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [state.runActive]);

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
          text: `已写入第 ${volNo} 卷的卷纲要点，可继续改。`,
        });
      } catch (e) {
        dispatch({ type: "error", message: (e as Error)?.message || "写入失败" });
      }
    },
    [projectId, dispatch],
  );

  const stopRun = useCallback(() => {
    abortRef.current?.();
    dispatch({ type: "run_end" });
    streamRef.current = false;
  }, [dispatch]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streamRef.current) return;
      streamRef.current = true;
      dispatch({ type: "user_send", id: newSendId(), text: trimmed, page });
      const abort = streamAssistantChat(
        projectId,
        { message: trimmed, page },
        {
          onEvent,
          onError: (msg) => {
            dispatch({ type: "error", message: msg });
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
    [projectId, page, dispatch, onEvent, newSendId],
  );

  const approve = useCallback(
    (gateId: string, decision: "approved" | "denied") => {
      dispatch({ type: "gate_resolved", gateId, approved: decision === "approved" });
      void approveGate(projectId, gateId, decision).catch((e: Error) =>
        dispatch({ type: "gate", text: e.message }),
      );
    },
    [projectId, dispatch],
  );

  const sendDisabled = !input.trim() || state.runActive;
  const chips: ChatChip[] = registration ? registration.chips(scope) : [];
  // 生成中面板的工具步取本 run 文本气泡（review 判例：曾取末条消息——卡片追加后
  // 步骤列表会闪空）
  let runSteps: ChatMessage["steps"] = [];
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const m = state.messages[i];
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
        <span className="chatdock-sub">每本书一个会话 · 跨页面连续</span>
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
        {state.messages.map((m) => {
          if (m.kind === "divider") {
            return (
              <div key={m.id} className="cd-divider">
                <span>—— 切换到{m.page || "新页面"} ——</span>
              </div>
            );
          }
          if (m.kind === "trace") {
            return (
              <div key={m.id} className="cd-trace-line">
                {m.text}
              </div>
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
            return (
              <div key={m.id} className="cd-msg assistant">
                <div className="cd-card" data-testid={`chat-card-${m.cardKind}`}>
                  <div className="cd-card-head">
                    <b>{CARD_TITLES[m.cardKind ?? "text"] ?? "草案"}</b>
                    {m.cardStatus === "adopted" && <span className="cd-badge ok">已采纳 ✓</span>}
                    {m.cardStatus === "stale" && <span className="cd-badge">旧版</span>}
                  </div>
                  <CardBody kind={m.cardKind ?? "text"} payload={m.cardPayload} />
                  {(m.cardStatus === "draft" || m.cardStatus === "stale") && (
                    <div className="cd-card-foot">
                      {m.cardKind === "text" &&
                        (m.cardPayload as Record<string, unknown> | undefined)?.draft != null && (
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
              <div className="cd-bubble">{m.text}</div>
              {/* TraceFolded（批E TraceFolded 组件语义内联）：run 收口后工具步折叠可回看 */}
              {m.steps.length > 0 && (
                <details className="cd-trace" data-testid="chat-trace">
                  <summary>
                    运行轨迹（{m.steps.length} 步：{m.steps.map((s) => s.tool).join("、")}）
                  </summary>
                  <ul>
                    {m.steps.map((s) => (
                      <li key={s.stepId}>
                        <b>{s.tool}</b>
                        {s.resultNote ? ` — ${s.resultNote}` : ""}
                      </li>
                    ))}
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
                </li>
              ))}
            </ul>
          </div>
        )}
        {state.error && !state.messages.some((m) => m.kind === "error") && (
          <div className="cd-msg error">
            <div className="cd-bubble">{state.error}</div>
          </div>
        )}
      </div>

      <div className="chatdock-composer">
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
      <div className="chatdock-foot">
        <button
          type="button"
          className="cd-reset"
          onClick={() => {
            void resetAssistantSession(projectId)
              .then(() => dispatch({ type: "reset" }))
              .catch(() => dispatch({ type: "gate", text: "重置失败，稍后再试。" }));
          }}
        >
          清空会话
        </button>
        {onUpgrade && <button type="button" className="cd-reset" onClick={() => onUpgrade?.()}>查看档位</button>}
        <span className="cd-dim">只做这本书和你的知识库内的事——其他的我没能力做。</span>
      </div>
    </div>
  );
}

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

function setPermissionTierStub(): void {
  // 档位设置入口在设置页（writer profile 面板，批F）；此处保留引用防 tree-shake
  void setPermissionTier;
}
void setPermissionTierStub;
