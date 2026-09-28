/**
 * AI 出卡确认弹窗（c-settings-ai-confirm-modal）：设定域全部 AI 能力的统一结果
 * 渲染面——右栏能力行、行内「AI 帮我填」、格头快捷钮、体检「AI 补」全部进弹窗，
 * 内嵌结果区（.ai-sink）退役。复用 design/Modal 壳，四卡形只差 footer 按钮组：
 * 文本/结构化卡＝关闭＋换一个＋确认键；候选勾选卡同（canAdopt 置灰）；体检报告卡＝
 * 关闭＋重新检查（无写回键）。
 * 关闭即弃：确认才写回（回调上抛）；生成中允许关闭，最近一次结果缓存在调用方
 * 面板 state，重开同一行直接展示缓存（cached=true 给来源提示条），「换一个」才
 * 重新生成（D9）；「换一个」在途期间旧版保持可读可采纳（D3）。
 */
import { useEffect, useRef, type ReactNode } from "react";
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";

export interface AiCardState {
  /** 弹窗标题（如「AI 填 · 起草主线」）。 */
  label: string;
  /** text＝文本卡 / report＝体检报告卡（无写回）/ pick＝候选勾选卡 / struct＝结构化卡。 */
  kind: "text" | "report" | "pick" | "struct";
  /** 卡体内容（各域私有渲染，词汇沿 .ai-card-body 作用域）。 */
  node: ReactNode;
  /** 确认键回调；报告卡不传＝无写回。确认后由调用方关弹窗＋记回执。 */
  adopt?: () => void;
  /** 确认键文案；缺省＝「接受这个」（text）/「采纳」（其余）。 */
  adoptText?: string;
  /** false 时确认键置灰（如候选全未勾选）。 */
  canAdopt?: boolean;
  /** 展示的是缓存结果（重开未重新生成）→ 卡顶给来源提示条。 */
  cached?: boolean;
}

interface AiCardModalProps {
  open: boolean;
  card: AiCardState | null;
  /** 该卡的生成在途（首跑＝loading 占位；已有卡在途＝「换一个」进行中，旧版保持可读）。 */
  running: boolean;
  /** 生成失败信息（无卡时＝错误体；有卡时＝旧版上方提示条）。 */
  error?: string;
  /** 已生成版数（第 N 版，从 1 起）。 */
  version?: number;
  onClose: (opts?: { skipRestore?: boolean }) => void;
  /** 「换一个」（生成类）/「重新检查」（报告卡）。 */
  onRegenerate?: () => void;
  /** 外部程序化关弹窗（如体检报告行跳转聚焦）时置 true 再关——跳过 Modal 焦点还原。
   *  不传则用内部 ref（只覆盖 onClose(opts) 路径）。 */
  skipRestoreRef?: { current: boolean };
  "data-testid"?: string;
}

export default function AiCardModal({
  open,
  card,
  running,
  error,
  version,
  onClose,
  onRegenerate,
  skipRestoreRef: skipRestoreRefProp,
  "data-testid": testId,
}: AiCardModalProps) {
  // 跳转出口关闭（如伏笔体检行跳转聚焦）：跳过 Modal 关闭后的焦点还原
  const internalSkipRef = useRef(false);
  const skipRestoreRef = skipRestoreRefProp ?? internalSkipRef;
  const close = (opts?: { skipRestore?: boolean }) => {
    skipRestoreRef.current = !!opts?.skipRestore;
    onClose(opts);
  };
  useEffect(() => {
    if (open) skipRestoreRef.current = false;
  }, [open]);

  const hasCard = !!card;
  const kind = card?.kind ?? "text";
  const adoptText = card?.adoptText ?? (kind === "text" ? "接受这个" : "采纳");
  const regenText = kind === "report" ? "重新检查" : "换一个";
  const initialLoading = running && !card;

  return (
    <Modal
      open={open}
      onClose={() => close()}
      restoreFocus={!skipRestoreRef.current}
      title={card?.label ?? "AI 助手"}
      width={520}
      wbStyle
      afterTitle={
        version && version > 0 ? (
          <span className="ac-ver" data-testid="ai-card-version" data-od-id="ai-card-version">
            第 {version} 版
          </span>
        ) : undefined
      }
      footer={
        initialLoading ? (
          <button className="btn btn-secondary btn-sm" onClick={() => close()}>
            关闭
          </button>
        ) : (
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => close()}>
              关闭
            </button>
            {onRegenerate && (
              <button
                className="btn btn-ghost btn-sm"
                disabled={running}
                onClick={onRegenerate}
                data-testid="ai-card-regen"
              >
                {regenText}
              </button>
            )}
            {hasCard && card?.adopt && (
              <button
                className="btn btn-primary btn-sm"
                data-testid="ai-card-adopt"
                disabled={card.canAdopt === false}
                onClick={card.adopt}
              >
                <Ico d={P.check} size={13} />
                {adoptText}
              </button>
            )}
          </>
        )
      }
    >
      <div className="ai-card-body" data-testid={testId} data-od-id="ai-card-body">
        {initialLoading ? (
          <div className="ac-loading" aria-busy="true" data-testid="ai-card-loading" data-od-id="ai-card-loading">
            <Ico d={P.spinner} className="spin" size={26} style={{ color: "var(--accent)" }} />
            <span>AI 正在生成…</span>
          </div>
        ) : (
          <>
            {running && (
              <p className="ac-busy" aria-busy="true">
                <Ico d={P.spinner} className="spin" size={13} />
                正在生成新一版…
              </p>
            )}
            {error && !running && (
              <p className="ac-err" data-testid="ai-card-error" data-od-id="ai-card-error">
                {error}
              </p>
            )}
            {card?.cached && !running && (
              <p className="ac-cache" data-testid="ai-card-cache" data-od-id="ai-card-cache">
                {kind === "report"
                  ? "上次体检结果 · 点「重新检查」刷新"
                  : "上次生成结果 · 点「换一个」重新生成"}
              </p>
            )}
            {card?.node}
          </>
        )}
      </div>
    </Modal>
  );
}
