import { useCallback, useEffect, useRef, useState } from "react";

/**
 * P2-1 脏状态跟踪：current 偏离上次「加载/保存」快照时通知 onDirtyChange(true)。
 * 父组件（AdvancedSettingsView）据此在切换面板前弹确认，避免未保存输入被静默丢弃。
 *
 * 用法：
 *   const { isDirty, snapshotLoaded, markSaved } = useDirtyState(currentShape, onDirtyChange);
 *   // 挂载 fetch 落库后：
 *   snapshotLoaded(normalizedPayload);
 *   // 保存成功后：
 *   markSaved();
 *
 * isDirty 为 state 值（每次渲染重建，勿放 effect deps）；
 * snapshotLoaded / markSaved 为稳定引用（useCallback），可安全放入 effect deps。
 */
export function useDirtyState(
  current: unknown,
  onDirtyChange: ((dirty: boolean) => void) | undefined,
) {
  const [isDirty, setIsDirty] = useState(false);
  const snapshotRef = useRef<string | null>(null);
  const currentRef = useRef(current);
  currentRef.current = current;
  const notifyRef = useRef(onDirtyChange);
  notifyRef.current = onDirtyChange;

  // 每次渲染对比；快照未就绪（null，仍在加载）不报
  useEffect(() => {
    if (snapshotRef.current === null) return;
    const dirty = JSON.stringify(currentRef.current) !== snapshotRef.current;
    setIsDirty(dirty);
    notifyRef.current?.(dirty);
  });

  const snapshotLoaded = useCallback((value: unknown) => {
    snapshotRef.current = JSON.stringify(value);
    setIsDirty(false);
    notifyRef.current?.(false);
  }, []);

  const markSaved = useCallback(() => {
    snapshotRef.current = JSON.stringify(currentRef.current);
    setIsDirty(false);
    notifyRef.current?.(false);
  }, []);

  /** 强制回到 dirty（O-4：save 成功但 confirm 400 时，不假装已确认）。 */
  const markDirty = useCallback(() => {
    snapshotRef.current = "__forced_dirty__";
    setIsDirty(true);
    notifyRef.current?.(true);
  }, []);

  return { isDirty, snapshotLoaded, markSaved, markDirty };
}
