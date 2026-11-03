import { useRef, useState, type ReactNode } from "react";
import PromptPackCard from "@/components/novel/license/PromptPackCard";
import { useFeature, usePlanBadge } from "@/hooks/useTier";
import type { CharAiCtx } from "@/lib/characterModel";
import { toast } from "@/lib/toast";
import type { AiState } from "@/types/api-config";

/**
 * AI 写作助手卡片（genre-signup-redesign tasks 3.2 / D4）。
 *
 * 结构：档位角标（随套餐：免费版/标准会员/PRO 会员/MAX 会员）＋标题
 * ＋可选状态副行 ＋若干**并列**能力行（每行＝名称上 + 描述下从属 + 右箭头，整行可点）
 * ＋底部来源/去向声明。卡头 SHALL NOT 出套餐营销文案：各档差异由角标＋能力行可用性体现，
 * 副行只承载功能性状态（无 Key/缺模型/能力包未就绪等下一步动作）。
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
  /** e2e 稳定锚（data-testid；迁移自各域旧按钮的 testid 沿用）。 */
  testid?: string;
  /** 设计走查锚（data-od-id 透传口，c-character-intro 4.2）。 */
  odId?: string;
  /** 名称旁徽章插槽（c-zhuque-ai-detect：PRO 专属 warn 章/新增标）。 */
  badge?: ReactNode;
  /** 行变体（c-zhuque-ai-detect）：guide=虚线引导行（仍可点）；maxlk=锁定视觉但保持可点（走升级出口）。
   *  两变体 SHALL NOT 置 disabled——disabled 会吞 onClick，与「点击有出口」冲突。 */
  variant?: "guide" | "maxlk";
  /** 运行中描述覆盖（缺省「生成中…」；检测行为「检测中…」）。 */
  runningHint?: string;
  /** 无档位门：本地免费能力（c-renwei-check 人味检测）——整卡 tier 锁定时不走升级出口，
   *  照常执行 onClick。SHALL NOT 用于任何需要会员/Key 的动作。 */
  ungated?: boolean;
}

export interface AiWriterAssistantProps {
  rows: AiCapabilityRow[];
  /** 底部来源/去向声明。 */
  footNote: string;
  /** 头部下的作用域行（可选；角色面板＝「当前角色：… 缺 n/m」）。 */
  targetLine?: ReactNode;
  title?: string;
  /**
   * 功能性副行（可选）：与无 Key/缺模型等功能状态同槽，只承载「当前为什么这样」的功能说明
   * （如朱雀检测显示开关关闭＝「朱雀检测已关闭 · 其余可用」）；SHALL NOT 用来放套餐文案。
   * 功能状态（no_key/missing_model/…）优先，无状态时显示本注记。
   */
  statusNote?: string;
  /**
   * 后端判定层下发的本书 AI 就绪态（D13）。传了就**只读它**做一次分派
   * （不再 useFeature + ai_state 两处判）；不传则退回 tier 门控（兼容旧调用方）。
   */
  aiState?: AiState;
  /** 后端下发的 no_key 引导文案（key-crypto-selfcontained：死文态＝重新粘贴保存）；no_key 时优先生效 */
  aiStateMessage?: string;
  /** 被前置拦下时的跳转（如去模型配置 / 去选模型）；不传则只弹提示。 */
  onBlocked?: (reason: AiState) => void;
  /**
   * 运行中的能力 key（受控）。父组件可下发以驱动「生成中…」视觉；
   * 不传时组件内部自管（两者都只在 UI 层，真正的在途互斥由调用方面板保证）。
   */
  runningKey?: string | null;
  /** 行清单之后、底部声明之前的附加内容插槽（报告组/台账等内容型区块）。 */
  children?: ReactNode;
  "data-od-id"?: string;
  "data-testid"?: string;
}

const BLOCK_TEXT: Record<string, string> = {
  // member_required 的 message 由 403 detail 透传（分档口径），此处为兜底文案
  member_required: "这是会员功能——开通后可用；免费版写作能力完整",
  no_key: "先去「模型配置」添加 API Key",
  missing_model: "先在本书选择模型",
  invalid: "本书绑定的模型已失效，重新选择模型",
  // c-prompt-pack-client：四态卡（PromptPackCard）承担引导与出口，此处为兜底文案
  // 已登录失败不再「自动获取」（onboard-modal 定诊）：出口指向账号菜单手动重新获取
  prompts_missing: "写作能力还没就绪——在账号菜单「写作能力」里重新获取",
};

export default function AiWriterAssistant({
  rows,
  footNote,
  targetLine,
  title = "AI 写作助手",
  statusNote,
  aiState,
  aiStateMessage,
  onBlocked,
  runningKey: runningKeyProp,
  children,
  "data-od-id": odId = "ai-assist",
  "data-testid": testId,
}: AiWriterAssistantProps) {
  const unlocked = useFeature("settings-ai-fields");
  // 卡头角标＝当前档位（免费版/标准会员/PRO 会员/MAX 会员/试用剩 N 天），不再写死 PRO
  const planBadge = usePlanBadge();
  // aiState 提供时以它为准（同一事实源）；未提供才退回 tier 门控
  const state: AiState = aiState ?? (unlocked ? "ready" : "member_required");
  const locked = state === "member_required";
  // 副行只承载功能性状态（无 Key/缺模型/能力包未就绪等下一步）＋调用方的功能性注记；
  // 档位差异由角标＋下面各能力行的可用性体现，故 ready/member_required 不出任何套餐文案。
  // 优先级：功能性状态（可操作）> 调用方注记（解释当前形态）> 不显示。
  const subText =
    state === "no_key" && aiStateMessage
      ? aiStateMessage
      : state === "ready" || state === "member_required"
        ? statusNote ?? null
        : BLOCK_TEXT[state];
  // 在途互斥用 **ref**（同步判定）而不是 state：state 要等重渲染才生效，
  // 连点会在同一 tick 内全部穿过（实测 6 连点 = 6 请求）。ref 让并发窗口归零。
  const busyRef = useRef(false);
  const [runningKeyInternal, setRunningKeyInternal] = useState<string | null>(null);
  const runningKey = runningKeyProp !== undefined ? runningKeyProp : runningKeyInternal;

  const guard = (key: string, fn: () => void | Promise<void>, ungated = false) => async () => {
    if (busyRef.current) return;
    if (state !== "ready" && !ungated) {
      const blockText =
        state === "no_key" && aiStateMessage ? aiStateMessage : BLOCK_TEXT[state] ?? "AI 暂不可用";
      if (onBlocked) onBlocked(state);
      else toast.info(blockText);
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
    <>
      {/* 写作能力包四态卡：已就绪/获取中不渲染（全静默）；c-prompt-pack-client 4.2 */}
      <PromptPackCard />
      <div className={`rail-assist${locked ? " locked" : ""}`} data-od-id={odId} data-testid={testId}>
      <div className="ra-head">
        {planBadge && (
          <span className={`plan-badge plan-badge-${planBadge.tone}`} data-testid="plan-badge">
            {planBadge.text}
          </span>
        )}
        <div className="rh-t">
          <b>{title}</b>
          {subText != null && <span>{subText}</span>}
        </div>
      </div>
      {targetLine != null && (
        <p className="ai-target" data-od-id="ai-target">
          {targetLine}
        </p>
      )}
      {rows.map((r) => {
        const running = runningKey === r.key;
        const variantCls =
          r.variant === "guide" ? " zq-guide" : r.variant === "maxlk" ? " zq-maxlk" : "";
        // guide/maxlk 行保持可点（出口语义），SHALL NOT 因运行期整卡禁用而失能；
        // 普通行维持既有口径（含运行行自身 disabled＋aria-busy）
        const interactive = r.variant !== undefined;
        return (
          <button
            key={r.key}
            className={`ra-step${r.disabled ? " ra-off" : ""}${running ? " ra-running" : ""}${variantCls}`}
            type="button"
            data-aiact={r.key}
            data-od-id={r.odId}
            data-testid={r.testid}
            aria-busy={running || undefined}
            disabled={interactive ? r.disabled || runningKey === r.key : r.disabled || runningKey !== null}
            onClick={() => void guard(r.key, r.onClick, r.ungated)()}
          >
            <span className="ra-body">
              <b>
                {r.name}
                {r.badge}
                {r.disabled && r.hint && <span className="ra-hint">{r.hint}</span>}
              </b>
              <i>{running ? r.runningHint || "生成中…" : r.desc}</i>
            </span>
            <span className="ra-arrow" aria-hidden="true">
              {running ? "" : "›"}
            </span>
          </button>
        );
      })}
        {children}
        <p className="ra-foot">{footNote}</p>
      </div>
    </>
  );
}

/** 角色右栏 AI 行（c-chars-draft-all：起草角色＋体检＋空态立主角）：免费可见、点不动。 */
export function CharsAiRail(props: {
  ctx: CharAiCtx | null;
  /** 书里还没有任何角色卡（列表已载入且为空）：右栏直接给「从简介立主角」入口。
   *  未载入/载入失败时传 false，避免把「还不知道」当成「没有卡」误建主角。 */
  noCard?: boolean;
  /** 列表已载入且至少有一张卡：未选中卡时「起草角色」＝新建一张。 */
  hasCards?: boolean;
  /** 02 简介是否已确认：空态立主角的前置（未确认＝行置灰并给出「先写简介」出口）。 */
  introReady?: boolean;
  /** 是否至少有一项已确认设定（题材/简介/世界/主线）：「起草角色」的前置。 */
  hasConfirmed?: boolean;
  aiState?: AiState;
  onBlocked?: (reason: AiState) => void;
  runningKey?: string | null;
  onRun: (key: string) => void | Promise<void>;
}) {
  const { ctx, noCard, hasCards, introReady, hasConfirmed } = props;
  const part = (n: number, max: number) => (n ? `缺 ${n}/${max}` : "已齐");
  const targetLine = noCard ? (
    <>还没有角色卡 · 先立主角（主角必立，确认「角色」的前提）</>
  ) : ctx ? (
    <>
      当前角色：<b>{ctx.name}</b> <span className="num">#{ctx.code}</span>
      {ctx.role === "路人" ? (
        <> · 路人卡只填基础档案 · 档案{part(ctx.dossierGap, 8)}</>
      ) : (
        <>
          {" "}· 人设{part(ctx.personaGap, 1)} · 档案{part(ctx.dossierGap, 8)} · 认知
          {part(ctx.cogGap, 10)}
        </>
      )}
    </>
  ) : hasCards ? (
    <>未选中角色 · 「起草角色」会按已确认设定新建一张卡</>
  ) : null;
  // 主角待立（有主角卡但名字还空着）时出现：与空态引导同源，出稿只补空格
  const bootstrapRow: AiCapabilityRow[] =
    ctx?.role === "主角" && ctx.nameless
      ? [
          {
            key: "bootstrap",
            name: "从简介立主角",
            desc: "读简介，把主角的名字、人设和空格先拟一稿 · 采纳才写入",
            onClick: () => props.onRun("bootstrap"),
          },
        ]
      : [];
  // 空态（书里还没有任何卡）：右栏首位给「从简介立主角」——与中栏引导卡同一端点，
  // 采纳才建卡写入。简介未确认时行置灰＋hint（不是藏起来：入口要看得见、点得动）。
  const emptyBootstrapRow: AiCapabilityRow[] =
    noCard && !ctx
      ? [
          {
            key: "bootstrap",
            name: "从简介立主角",
            desc: "读简介，把主角的名字、人设和空格先拟一稿 · 采纳才写入",
            disabled: !introReady,
            hint: introReady ? undefined : "先写 02 简介",
            onClick: () => props.onRun("bootstrap"),
            testid: "char-rail-bootstrap",
          },
        ]
      : [];
  // 起草角色（c-chars-draft-all）：有卡且还有空格 → 补空格；有卡但未选中 → 新建。
  // 路人只补档案空格；主角待立走「从简介立主角」，不重复给起草行。
  // 名字空格也算「剩下的」：其他格填满、只留下空名/占位名时仍应可点。
  const nameGap = ctx?.nameless ? 1 : 0;
  const draftGaps = ctx
    ? (ctx.role === "路人"
        ? ctx.dossierGap
        : ctx.personaGap + ctx.dossierGap + ctx.cogGap) + nameGap
    : 0;
  const canDraftAll =
    !noCard &&
    !(ctx?.role === "主角" && ctx.nameless) &&
    (ctx ? draftGaps > 0 : !!hasCards);
  const draftAllRow: AiCapabilityRow[] = canDraftAll
    ? [
        {
          key: "draftAll",
          name: "起草角色",
          desc: ctx
            ? ctx.role === "路人"
              ? `补「${ctx.name || "未命名"}」的基础档案空格 · 采纳才写入`
              : `一次补齐「${ctx.name || "未命名"}」剩下的空格（人设/档案/认知）· 采纳才写入`
            : "按已确认设定新建一张角色卡（配角/反派）· 采纳才建卡",
          disabled: !hasConfirmed,
          hint: hasConfirmed ? undefined : "先确认设定",
          onClick: () => props.onRun("draftAll"),
          testid: "char-rail-draft-all",
        },
      ]
    : [];
  const checkRow: AiCapabilityRow[] = ctx
    ? [
        {
          key: "check",
          name: "一致性体检",
          desc: `拿「${ctx.name}」去对整体设定 · 会读：这张卡、已确认设定、现有角色`,
          onClick: () => props.onRun("check"),
        },
      ]
    : [];
  const rows: AiCapabilityRow[] = [
    ...emptyBootstrapRow,
    ...bootstrapRow,
    ...draftAllRow,
    ...checkRow,
  ];
  return (
    <AiWriterAssistant
      rows={rows}
      footNote={
        noCard && !ctx
          ? "还没有角色卡：首行「从简介立主角」直接可用（需先在 02 简介写几句并确认），出稿在弹窗里过目，点「采纳 · 写入」才建卡落字。卡片上不放 AI 按钮：免费用户照样可以手填所有字段。"
          : "「起草角色」一次补齐整张卡：卡上你写过的字一个不动，只补空格；没选中卡时按已确认的题材/简介/世界/主线＋现有角色新建一张（可切配角/反派），采纳才建卡。一致性体检只读不写。卡片上不放 AI 按钮：免费用户照样可以手填所有字段。"
      }
      targetLine={targetLine}
      aiState={props.aiState}
      onBlocked={props.onBlocked}
      runningKey={props.runningKey}
      data-od-id="ai-assist-chars"
    />
  );
}
