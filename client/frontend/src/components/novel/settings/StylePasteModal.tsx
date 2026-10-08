/**
 * 粘贴文风样本弹窗（c-style-paste-distill）：蒸馏第三路样本输入。
 *
 * 弹窗只管输入——提交后由面板续跑既有三步管线（step1→step3→画像确认→落卡）。
 * 字数口径同后端（去空白、码点迭代），但前端计数只是预判，后端强校验为权威。
 * 超限 fast-path：原始长度远超上限时跳过精确计数直接给超限提示，防整本粘贴时
 * 受控 textarea 每键 O(n) 重计数卡顿；不做硬截断（静默截断＝数据丢失陷阱）。
 *
 * 形态照 workbench AiModal 先例（Modal wbStyle＋PRO 标＋大 textarea）；
 * .ai-prompt/.btn/.paste-* 为全局类，portal 到 body 后样式仍生效。
 */
import { useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import { minTierOf, tierLabel } from "@/lib/features";
import { SAMPLE_MAX, SAMPLE_MIN, countSampleChars } from "@/lib/styleApi";

interface Props {
  open: boolean;
  onClose: () => void;
  /** 区间内提交（前端已预判；后端会再次校验并作显式重启） */
  onSubmit: (text: string) => void;
}

/** fast-path 阈值：原始长度超过上限 4 倍时精确计数必然超限（正常样本远短于此）。 */
const RAW_OVER_LIMIT = SAMPLE_MAX * 4;

export default function StylePasteModal({ open, onClose, onSubmit }: Props) {
  const [text, setText] = useState("");

  // 关闭即清空：半截草稿不跨开合残留（重开一贴即新样本）
  useEffect(() => {
    if (!open) setText("");
  }, [open]);

  const rawOver = text.length > RAW_OVER_LIMIT;
  const n = rawOver ? text.length : countSampleChars(text);
  const inRange = !rawOver && n >= SAMPLE_MIN && n <= SAMPLE_MAX;

  let hint = `需 ${SAMPLE_MIN.toLocaleString()}–${SAMPLE_MAX.toLocaleString()} 字`;
  let tone = "";
  if (rawOver || n > SAMPLE_MAX) {
    hint = `超过 ${SAMPLE_MAX.toLocaleString()} 字——挑最有代表性的几章`;
    tone = "warn";
  } else if (n > 0 && n < SAMPLE_MIN) {
    hint = `还差 ${(SAMPLE_MIN - n).toLocaleString()} 字——再补一些你认可的文章`;
    tone = "warn";
  } else if (inRange) {
    hint = "区间内，可以开始蒸馏";
    tone = "ok";
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="粘贴文风样本"
      width={560}
      wbStyle
      afterTitle={<span className="ai-tag">{tierLabel(minTierOf("style-quant"))}</span>}
      footer={
        <>
          <span className="paste-note" style={{ marginRight: "auto" }}>
            样本只用于这一次蒸馏；之后可随时「重新蒸馏」换掉。
          </span>
          <button className="btn btn-ghost" type="button" data-od-id="btn-paste-cancel" onClick={onClose}>
            取消
          </button>
          <button className="btn btn-primary" type="button" data-od-id="btn-paste-start" disabled={!inRange} onClick={() => onSubmit(text)}>
            开始蒸馏
          </button>
        </>
      }
    >
      <p className="paste-note" style={{ margin: "0 0 10px" }}>
        把你认可的文字直接贴进来——小说正文、散文都行，越像你平时的写法越好。交{" "}
        {SAMPLE_MIN.toLocaleString()}–{SAMPLE_MAX.toLocaleString()} 字，AI 学出六行基线。
      </p>
      <textarea
        className="ai-prompt"
        data-od-id="input-paste-sample"
        rows={12}
        placeholder="粘贴你最满意的文章……"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="paste-meta">
        {rawOver ? (
          // fast-path 生效时未剔除空白，不冒充精确计数——如实标注原始长度
          <span>原始 {text.length.toLocaleString()} 字（超长，未剔除空白）</span>
        ) : (
          <span>
            已贴 <b className="num">{n.toLocaleString()}</b> 字（不含空白）
          </span>
        )}
        <span className="spacer" />
        <span className={tone} data-od-id="paste-hint">
          {hint}
        </span>
      </div>
    </Modal>
  );
}
