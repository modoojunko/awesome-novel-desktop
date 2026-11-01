// 本章写法块只读条（c-kb-write-block 批D）：生成流 SSE write_block 事件驱动——
// 自动注入、不落库、不进提示词编辑区；逐条「有用/没用」回写账号级权重（可改口）。
// 未启用知识库/零命中的书后端不下发事件＝本组件零渲染（未启用书零变化）。
import { useRef, useState } from "react";
import type { WriteBlockItem } from "@/lib/ai";
import { kbApi } from "@/lib/kbApi";

export default function WriteBlockPanel({
  block,
  runId,
  items,
}: {
  block: string;
  runId: string;
  items: WriteBlockItem[];
}) {
  /** 已标记态（本地回显：entry_id → true=有用 false=没用；可改口） */
  const [marked, setMarked] = useState<Record<string, boolean>>({});
  // 防抖闸用 ref（state 闭包陈旧：同 tick 连点第二发读不到未提交的 busy＝防抖失效）
  const busyRef = useRef(false);

  const mark = async (entryId: string, useful: boolean) => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      await kbApi.pref(entryId, useful);
      setMarked((m) => ({ ...m, [entryId]: useful }));
    } catch {
      // 权重回写失败静默（不影响正文；重试可再点）
    } finally {
      busyRef.current = false;
    }
  };

  return (
    <div className="write-block-panel" data-testid="write-block-panel" data-run-id={runId}>
      <div className="wb-head">
        <span className="wb-title">本章写法块</span>
        <span className="wb-opt">自动注入 · 不落库 · 只约束写法不改变剧情</span>
      </div>
      <pre className="wb-body">{block}</pre>
      {items.length > 0 && (
        <ul className="wb-items" data-testid="write-block-items">
          {items.map((it) => (
            <li key={it.entry_id} className="wb-item">
              <span className="wb-item-clause">{it.clause}</span>
              <span className="wb-item-text">{it.text}</span>
              <span className="wb-mark">
                <button
                  type="button"
                  className={marked[it.entry_id] === true ? "on" : ""}
                  data-testid={`wb-useful-${it.entry_id}`}
                  onClick={() => void mark(it.entry_id, true)}
                >
                  有用
                </button>
                <button
                  type="button"
                  className={marked[it.entry_id] === false ? "on" : ""}
                  data-testid={`wb-useless-${it.entry_id}`}
                  onClick={() => void mark(it.entry_id, false)}
                >
                  没用
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
