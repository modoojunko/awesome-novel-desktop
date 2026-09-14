import { useRef, useState, type ReactNode } from "react";
import { useFeature } from "@/hooks/useTier";
import type { CharAiCtx } from "@/lib/characterModel";
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
  /** 头部下的作用域行（可选；角色面板＝「当前角色：… 缺 n/m」）。 */
  targetLine?: ReactNode;
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
  targetLine,
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
                ? "你的 PRO 已包含 · 只加工你写的，不代写"
                : BLOCK_TEXT[state]}
          </span>
        </div>
      </div>
      {targetLine != null && (
        <p className="ai-target" data-od-id="ai-target">
          {targetLine}
        </p>
      )}
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

/** 角色右栏 AI 行（character-settings-v2 四行 + bootstrap；作用域见各行）：免费可见、点不动。 */
export function CharsAiRail(props: {
  ctx: CharAiCtx | null;
  aiState?: AiState;
  onBlocked?: (reason: AiState) => void;
  runningKey?: string | null;
  onRun: (key: string) => void | Promise<void>;
}) {
  const { ctx } = props;
  const part = (n: number, max: number) => (n ? `缺 ${n}/${max}` : "已齐");
  const targetLine = ctx ? (
    <>
      当前角色：<b>{ctx.name}</b> <span className="num">#{ctx.code}</span>
      {ctx.role === "路人" ? (
        <> · 路人卡只填基础档案 · 档案{part(ctx.dossierGap, 6)}（性别、年龄不代填）</>
      ) : (
        <>
          {" "}· 人设{part(ctx.personaGap, 1)} · 档案{part(ctx.dossierGap, 6)} · 认知
          {part(ctx.cogGap, 10)}
        </>
      )}
    </>
  ) : null;
  // 主角待立（有主角卡但名字还空着）时出现：与空态引导同源，出稿只补空格
  const bootstrapRow: AiCapabilityRow[] =
    ctx?.role === "主角" && ctx.nameless
      ? [
          {
            key: "bootstrap",
            name: "从简介立主角",
            desc: "读简介，把主角的名字、人设和空格先拟一稿 · 采纳才写入（性别、年龄不代填）",
            onClick: () => props.onRun("bootstrap"),
          },
        ]
      : [];
  const rows: AiCapabilityRow[] = [
    ...bootstrapRow,
    {
      key: "persona",
      name: "人设补充",
      desc: ctx ? `为「${ctx.name}」出一稿 · 会读：这张卡、简介、题材` : "补一句话人设，采纳才覆盖",
      onClick: () => props.onRun("persona"),
    },
    {
      key: "dossier",
      name: "基础信息补充",
      desc: ctx ? `补「${ctx.name}」的档案空格（性别、年龄不代填）· 会读：这张卡、简介、题材、世界` : "补档案空格；性别、年龄不代填",
      onClick: () => props.onRun("dossier"),
    },
    {
      key: "cog",
      name: "认知补充",
      desc: ctx ? `补「${ctx.name}」每层要写的那几格（含技能）· 会读：这张卡、世界（力量与代价）、主线` : "把每层要写的那几格补上，只补空格",
      onClick: () => props.onRun("cog"),
    },
    {
      key: "check",
      name: "一致性体检",
      desc: ctx ? `拿「${ctx.name}」去对整体设定 · 会读：这张卡、简介、题材、世界、主线` : "拿这张卡去对简介、题材、世界、主线",
      onClick: () => props.onRun("check"),
    },
  ];
  return (
    <AiWriterAssistant
      rows={rows}
      footNote="这些行都只对当前选中的角色生效（「从简介立主角」只认主角待立那一张）：先给你一稿，点「采纳 · 写入」才落到卡上，写错了能一步撤销。只补空格——你写过的字一个不动；性别、年龄不代填，留给你自己定。答案都是 AI 现场生成的，这里只是示例，不满意就重新生成。卡片上不放 AI 按钮：免费用户照样可以手填所有字段，这一栏看得见、点不动。"
      targetLine={targetLine}
      aiState={props.aiState}
      onBlocked={props.onBlocked}
      runningKey={props.runningKey}
      data-od-id="ai-assist-chars"
    />
  );
}
