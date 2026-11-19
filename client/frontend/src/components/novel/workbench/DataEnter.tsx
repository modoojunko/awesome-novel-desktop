import { createContext, useContext, useEffect, useState } from "react";

// ── 工作台启动闸（boot gate）＋数据落位包装 ──────────────────────────────
// 病史两段（2026-11-19）：
// ① 打开书「先有框再出数据」——实测数据 128ms 就绪、框架 70ms，两波感来自
//   动画错峰：page-enter（400ms）让框架 ~250ms 先清晰，data-enter（128ms 起
//   再播 250ms）让数据拖到 ~378ms 才清晰。修＝boot 窗口（600ms）内挂载的
//   区块**不播** data-enter，首屏数据并进 page-enter 单波；窗口结束后新挂载
//   （切面板/切视图/采纳写回）照常轻淡入。
// ② boot 翻转时给**已挂载**元素中途加动画类会闪可见内容——所以冻结语义一律
//   「挂载时刻拍板、此后不变」：useState 惰性初始化捕获首渲染 booting。

const WorkbenchBootContext = createContext(true);

/** 600ms > 首屏数据典型到达（本机实测 ~130ms）；超慢数据到达时已出窗，照常淡入。 */
const BOOT_WINDOW_MS = 600;

export function WorkbenchBootProvider({ children }: { children: React.ReactNode }) {
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    const t = window.setTimeout(() => setBooting(false), BOOT_WINDOW_MS);
    return () => window.clearTimeout(t);
  }, []);
  return <WorkbenchBootContext.Provider value={booting}>{children}</WorkbenchBootContext.Provider>;
}

export function useWorkbenchBooting(): boolean {
  return useContext(WorkbenchBootContext);
}

/** 挂载期淡入包装：挂载时不在 boot 窗口 ⇒ 挂载即轻淡入（.data-enter，index.css）；
 *  在窗口内 ⇒ 本挂载永不淡入（并进 page-enter 单波）。className 其余部分透传。 */
export function DataEnter({
  children,
  className,
  ...rest
}: {
  children: React.ReactNode;
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  const booting = useWorkbenchBooting();
  const [fxOn] = useState(() => !booting);
  const cls = [fxOn ? "data-enter" : "", className ?? ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
