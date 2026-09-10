/**
 * 改动回执 + 单步撤销（用户 2026-09-10 拍板，范围：模型设定 / 简介 / 题材 三面板）。
 *
 * 为什么需要：设定是 AI 写作注入的输入，改错了不会当场报错，只让后面每一章越写越差。
 * 该治的是「改了不知道 + 改错退不回」，不是「控件能不能改」——所以不做查看/编辑态，
 * 只在**一次点击就能改变内容**的动作后给一条回执 + 一步撤销（回执是提示，不是模式；
 * 面板永远只有 1 个主按钮 + 最多 1 条回执，不产生第三层状态）。
 *
 * 分级口径（不按控件类型，按**改动来源**）：
 *   · 一触即变（胶囊/滑块松手/清空/一键覆盖文本）→ 脚部回执 + 撤销
 *   · 自己敲的字 → 不进脚部回执（会刷屏），走 `RestoreHint`：失焦后框下一条轻提示
 */

import { useCallback, useState } from "react";

export interface ChangeReceiptState {
  /** 作者视角的改动说明，如「已把吃苦指数从 6 调到 8」。 */
  text: string;
  /** 一步撤销：回退这次改动并清掉回执。 */
  undo: () => void;
}

/**
 * 面板脚部回执状态。`onChange` 交给 SettingsView 渲染在 `.panel-foot` 里
 * （与主按钮同一行，回执在左、按钮在右）。
 */
export function useChangeReceipt(onChange?: (r: ChangeReceiptState | null) => void) {
  const [receipt, setReceipt] = useState<ChangeReceiptState | null>(null);

  const publish = useCallback(
    (next: ChangeReceiptState | null) => {
      setReceipt(next);
      onChange?.(next);
    },
    [onChange],
  );

  /** 记一次改动：先 apply，再挂回执（撤销＝revert 后清回执）。 */
  const record = useCallback(
    (text: string, apply: () => void, revert: () => void) => {
      apply();
      publish({
        text,
        undo: () => {
          revert();
          publish(null);
        },
      });
    },
    [publish],
  );

  const clear = useCallback(() => publish(null), [publish]);

  return { receipt, record, clear };
}

/** 面板脚部渲染的回执行（回执在左、主按钮在右）。 */
export function ChangeReceiptBar({ receipt }: { receipt: ChangeReceiptState | null }) {
  if (!receipt) return null;
  return (
    <span className="receipt" data-od-id="panel-receipt">
      {/* 长回执单行截断（脚部不许折行，见 book.css），全文走 title 悬浮可读 */}
      <span className="rt" title={receipt.text}>
        {receipt.text}
      </span>
      <button
        type="button"
        className="undo"
        data-od-id="panel-undo"
        onClick={receipt.undo}
        title="回到这次改动之前"
      >
        撤销
      </button>
    </span>
  );
}

/**
 * 文本字段的「已修改 · 恢复到打开时的原文」：**失焦后**才出现（打字时不刷屏）。
 * 与脚部回执分工：脚部管"一键覆盖类"，这里管"自己敲的字"。
 */
export function RestoreHint({
  show,
  onRestore,
  label = "恢复到打开时的原文",
}: {
  show: boolean;
  onRestore: () => void;
  label?: string;
}) {
  if (!show) return null;
  return (
    <p className="field-restore" data-od-id="field-restore">
      已修改 ·{" "}
      <button type="button" className="undo" onClick={onRestore} data-od-id="field-restore-btn">
        {label}
      </button>
    </p>
  );
}
