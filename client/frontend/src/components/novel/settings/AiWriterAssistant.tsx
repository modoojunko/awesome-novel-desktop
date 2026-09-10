import { useRef, useState } from "react";
import { useFeature } from "@/hooks/useTier";
import { toast } from "@/lib/toast";
import type { AiState } from "@/types/api-config";

/**
 * AI 写作助手卡片（genre-signup-redesign tasks 3.2 / D4）。
 *
 * 结构：PRO 徽标并头部 + 标题 + 套餐归属/只加工不代写 + 若干**并列**能力行
 * （每行＝名称上 + 描述下从属 + 右箭头，整行可点）+ 底部来源/去向声明。
 *
 * 门控：`useFeature('settings-ai-fields')`（已登记的 memberOnly key，非 ai-assistant）。
 * 免费版＝可见 + 锁定（整卡降透明 .locked，点击给统一升级提示，不各自弹窗）。
 */
export interface AiCapabilityRow {
  /** 能力标识（data-aiact，供 e2e 定位）。 */
  key: string;
  /** 能力名称（上，粗体）。 */
  name: string;
  /** 能力描述（下，从属灰字）。 */
  desc: string;
  onClick: () => void | Promise<void>;
  /** 前置未满足（如补缺失需先体检）→ 该行置灰 + hint（D14 前置守卫）。 */
  disabled?: boolean;
  /** 置灰原因（如「先体检」）。 */
  hint?: string;
}

export interface AiWriterAssistantProps {
  rows: AiCapabilityRow[];
  /** 底部来源/去向声明。 */
  footNote: string;
  title?: string;
  /**
   * 后端判定层下发的本书 AI 就绪态（D13）。传了就**只读它**做一次分派
   * （不再 useFeature + ai_state 两处判）；不传则退回 tier 门控（兼容旧调用方）。
   */
  aiState?: AiState;
  /** 被前置拦下时的跳转（如去模型配置 / 去选模型）；不传则只弹提示。 */
  onBlocked?: (reason: AiState) => void;
  /**
   * 运行中的能力 key（受控）。父组件可下发以驱动「生成中…」视觉；
   * 不传时组件内部自管（两者都只在 UI 层，真正的在途互斥由调用方面板保证）。
   */
  runningKey?: string | null;
  "data-od-id"?: string;
}

const BLOCK_TEXT: Record<string, string> = {
  member_required: "这是会员功能，升级 PRO 后解锁——免费版写作能力完整",
  no_key: "先去「模型配置」添加 API Key",
  missing_model: "先在本书选择模型",
  invalid: "本书绑定的模型已失效，重新选择模型",
};

export default function AiWriterAssistant({
  rows,
  footNote,
  title = "AI 写作助手",
  aiState,
  onBlocked,
  runningKey: runningKeyProp,
  "data-od-id": odId = "ai-assist",
}: AiWriterAssistantProps) {
  const unlocked = useFeature("settings-ai-fields");
  // aiState 提供时以它为准（同一事实源）；未提供才退回 tier 门控
  const state: AiState = aiState ?? (unlocked ? "ready" : "member_required");
  const locked = state === "member_required";
  // 在途互斥用 **ref**（同步判定）而不是 state：state 要等重渲染才生效，
  // 连点会在同一 tick 内全部穿过（实测 6 连点 = 6 请求）。ref 让并发窗口归零。
  const busyRef = useRef(false);
  const [runningKeyInternal, setRunningKeyInternal] = useState<string | null>(null);
  const runningKey = runningKeyProp !== undefined ? runningKeyProp : runningKeyInternal;

  const guard = (key: string, fn: () => void | Promise<void>) => async () => {
    if (busyRef.current) return;
    if (state !== "ready") {
      if (onBlocked) onBlocked(state);
      else toast.info(BLOCK_TEXT[state] ?? "AI 暂不可用");
      return;
    }
    busyRef.current = true;
    setRunningKeyInternal(key);
    try {
      await fn();
    } finally {
      busyRef.current = false;
      setRunningKeyInternal(null);
    }
  };

  return (
    <div className={`rail-assist${locked ? " locked" : ""}`} data-od-id={odId}>
      <div className="ra-head">
        <span className="plan-badge">PRO</span>
        <div className="rh-t">
          <b>{title}</b>
          <span>
            {locked
              ? "未解锁 · 升级 PRO 后本书 AI 即可用"
              : state === "ready"
                ? "已解锁 · 包含在你的 PRO 套餐（Max 同享）· 只加工你写的，不代写"
                : BLOCK_TEXT[state]}
          </span>
        </div>
      </div>
      {rows.map((r) => {
        const running = runningKey === r.key;
        return (
          <button
            key={r.key}
            className={`ra-step${r.disabled ? " ra-off" : ""}${running ? " ra-running" : ""}`}
            type="button"
            data-aiact={r.key}
            aria-busy={running || undefined}
            disabled={r.disabled || runningKey !== null}
            onClick={() => void guard(r.key, r.onClick)()}
          >
            <span className="ra-body">
              <b>
                {r.name}
                {r.disabled && r.hint && <span className="ra-hint">{r.hint}</span>}
              </b>
              <i>{running ? "生成中…" : r.desc}</i>
            </span>
            <span className="ra-arrow" aria-hidden="true">
              {running ? "" : "›"}
            </span>
          </button>
        );
      })}
      <p className="ra-foot">{footNote}</p>
    </div>
  );
}
