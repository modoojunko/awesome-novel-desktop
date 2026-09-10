/**
 * [uikit 候选] 改动回执 + 单步撤销 + 文本恢复提示（2026-09-10 genre-signup-redesign 沉淀）。
 *
 * 现网实现：`client/frontend/src/components/novel/settings/ChangeReceipt.tsx`（锁死在
 * settings/ 下，与本文件逐字同构——搬运目标 `src/components/ui/`，搬完删旧路径）。
 * 首批使用者：模型设定 / 简介 / 题材三面板（PR #347）。
 *
 * 为什么需要：设定是 AI 写作的输入，改错了不会当场报错，只让后面每一章越写越差。
 * 该治的是「改了不知道 + 改错退不回」，不是「控件能不能改」——所以**不做查看/编辑模式**，
 * 只在「一次点击就能改变内容」的动作后给一条回执 + 一步撤销（回执是提示，不是模式；
 * 面板永远只有 1 个主按钮 + 最多 1 条回执，不产生第三层状态）。
 *
 * 分级口径（不按控件类型，按**改动来源**）：
 *   · 一键覆盖类（胶囊一次改多格 / 勾选 / 滑块松手 / 清空 / AI 采纳 / 设为当前）
 *       → 脚部 `ChangeReceiptBar` 回执 + 撤销
 *   · 作者自己敲的字 → 不进脚部（会随每次键入刷屏），走 `RestoreHint`：
 *       失焦后字段下方一条轻提示「已修改 · 恢复到打开时的原文」
 *
 * ┌─ 布局纪律（违反过一次，都是真事故）──────────────────────────────┐
 * │ 1. 脚部不许折行：折出的第二行会落到窗口底部固定状态条（fixed）之下，      │
 * │    主按钮被盖住点不到。回执单行截断、全文挂 title（触屏无 hover 时      │
 * │    title 是唯一全文入口，是已知 P2 遗留）。                          │
 * │ 2. `.rt` 要 `display:block` 才吃 `overflow:hidden`——inline span 上写   │
 * │    ellipsis 无效。                                                 │
 * │ 3. 面板容器若是栅格 `1fr` 轨道，必须 `min-width: 0`：长回执会把中栏撑宽、   │
 * │    把右栏挤出视口，且**点击会在 mousedown/mouseup 之间因重排丢失**        │
 * │    （React onClick 不触发、e2e 干等超时、后端零请求＝特征签名）。          │
 * └────────────────────────────────────────────────────────────────┘
 *
 * 使用纪律（评审换来的）：
 *   · `recordChange` 只能在事件回调里调，**禁止写进 `setData` 的 updater**——
 *     updater 可能被 React 重复调用（updater 里 setState = 渲染期副作用）。
 *   · 撤销基准取「改动瞬间」的值：AI 结果节点若缓存在 state 里，其闭包会停在
 *     创建那次渲染——基准要读 ref（采纳瞬间的 dataRef），否则会抹掉结果到达之后
 *     作家自己敲的字。
 *   · 勾选类撤销用**差量**（只动这一项），不用整字段快照——快照会把这次改动之后
 *     发生的非回执改动（如手敲的自定义项）一起回滚。
 *   · revert 允许异步（如撤销「设为本书模型」是一次真实落库写）：抛错则保留回执
 *     让用户重试，由调用方 toast。
 *   · 保存成功后必须清回执（撤销只能改内存，与库不一致）；切面板同理
 *     （建议在宿主用 `useEffect(() => setReceipt(null), [panel])` 统一兜，
 *     别在各跳转路径各自清——四条路径漏三条就是 P0 死撤销）。
 */

import { useCallback, useState } from "react";

export interface ChangeReceiptState {
  /** 作者视角的改动说明，如「已把吃苦指数从 6 调到 8」。 */
  text: string;
  /** 一步撤销：回退这次改动并清掉回执。**抛错则保留回执**（如网络写失败）。 */
  undo: () => void | Promise<void>;
}

/**
 * 面板脚部回执状态。`onChange` 交给面板宿主渲染在 `.panel-foot` 里
 * （回执在左、主按钮在右）。
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

  /** 记一次改动：先 apply，再挂回执（撤销＝revert 后清回执；revert 抛错保留回执）。 */
  const record = useCallback(
    (text: string, apply: () => void, revert: () => void | Promise<void>) => {
      apply();
      publish({
        text,
        undo: async () => {
          try {
            await revert();
            publish(null);
          } catch {
            // revert 失败（如撤销要写服务端）→ 保留回执，用户可再试
          }
        },
      });
    },
    [publish],
  );

  const clear = useCallback(() => publish(null), [publish]);

  return { receipt, record, clear };
}

/** 面板脚部渲染的回执行（回执在左、主按钮在右）。role=status：这条回执就是
 *  「改了知道」本身，读屏也得听得到；撤销按钮的可及名带内容，与字段恢复提示
 *  同页共存时可区分。 */
export function ChangeReceiptBar({ receipt }: { receipt: ChangeReceiptState | null }) {
  if (!receipt) return null;
  return (
    <span className="receipt" data-od-id="panel-receipt" role="status" aria-live="polite">
      {/* 长回执单行截断（脚部不许折行，见文件头），全文走 title 悬浮可读 */}
      <span className="rt" title={receipt.text}>
        {receipt.text}
      </span>
      <button
        type="button"
        className="undo"
        data-od-id="panel-undo"
        onClick={() => void receipt.undo()}
        title="回到这次改动之前"
        aria-label={`撤销：${receipt.text}`}
      >
        撤销
      </button>
    </span>
  );
}

/**
 * 文本字段的「已修改 · 恢复到打开时的原文」：**失焦后**才出现（打字时不刷屏）。
 * 与脚部回执分工：脚部管"一键覆盖类"，这里管"自己敲的字"。
 *
 * 纪律：`show` 的判定基准是「打开面板/最近一次保存」的原值 ref——保存成功后
 * 基线必须前移并撤下提示，否则一键恢复会把刚存进去的正文改回旧版。
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
