import { useState, useEffect, useMemo } from "react";
import { api } from "@/lib/api";
import { diffLines, diffWords } from "diff";
import type { Change } from "diff";
import { Ico, P } from "@/components/icons";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Version {
  version: string;
  time: number;
  comment: string;
  isCurrent: boolean;
}

interface VersionDiffProps {
  projectId: string;
  chapterRef: string;
  versions: Version[];
  /** 初始选中（版本历史弹窗「对比」入口预选 所选版本 → 当前）；缺省=最新两条 */
  initialOldVersionId?: string;
  initialNewVersionId?: string;
}

interface VersionContent {
  version: string;
  time: number;
  comment: string;
  prose: string;
}

type DiffMode = "line" | "word";

interface DiffLine {
  text: string;
  type: "add" | "del" | "same" | "skip";
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(ts: number): string {
  // 后端为 13 位毫秒；历史脏数据可能为秒级 → 归一
  const ms = ts > 1e12 ? ts : ts * 1000;
  const diff = Date.now() - ms;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return `${Math.floor(days / 30)}个月前`;
}

function versionLabel(v: Version): string {
  return `v${v.version} — ${relativeTime(v.time)}${v.comment ? ` [${v.comment}]` : ""}`;
}

// ---------------------------------------------------------------------------
// Line diff processing
// ---------------------------------------------------------------------------

function processLineDiff(parts: Change[]): { lines: DiffLine[]; added: number; removed: number } {
  const allLines: DiffLine[] = [];

  for (const part of parts) {
    const rawLines = part.value.split("\n");
    if (rawLines[rawLines.length - 1] === "") rawLines.pop();

    for (const line of rawLines) {
      if (part.added) {
        allLines.push({ text: line, type: "add" });
      } else if (part.removed) {
        allLines.push({ text: line, type: "del" });
      } else {
        allLines.push({ text: line, type: "same" });
      }
    }
  }

  const added = allLines.filter((l) => l.type === "add").length;
  const removed = allLines.filter((l) => l.type === "del").length;

  // Compress long unchanged runs to 3 context lines
  const compressed: DiffLine[] = [];
  let sameRun: DiffLine[] = [];

  const flushSame = () => {
    if (sameRun.length <= 6) {
      compressed.push(...sameRun);
    } else {
      compressed.push(...sameRun.slice(0, 3));
      compressed.push({ text: `... 省略 ${sameRun.length - 6} 行`, type: "skip" });
      compressed.push(...sameRun.slice(-3));
    }
    sameRun = [];
  };

  for (const line of allLines) {
    if (line.type === "same") {
      sameRun.push(line);
    } else {
      flushSame();
      compressed.push(line);
    }
  }
  flushSame();

  return { lines: compressed, added, removed };
}

// ---------------------------------------------------------------------------
// Word diff rendering
// ---------------------------------------------------------------------------

function renderWordDiff(
  oldProse: string,
  newProse: string,
): { content: React.ReactNode; added: number; removed: number } {
  const parts = diffWords(oldProse, newProse);
  let addedChars = 0;
  let removedChars = 0;
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const part of parts) {
    const segments = part.value.split("\n");

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];

      if (i > 0) {
        elements.push(<br key={`br-${key}`} />);
      }

      // Leading newline in this part means the first segment is empty
      if (seg === "" && i === 0 && segments.length > 1) continue;
      if (seg === "") continue;

      if (part.added) {
        addedChars += seg.length;
        elements.push(
          <span
            key={key}
            className="rounded px-0.5"
            style={{ backgroundColor: "var(--ok-25)" }}
          >
            {seg}
          </span>,
        );
      } else if (part.removed) {
        removedChars += seg.length;
        elements.push(
          <span
            key={key}
            className="rounded px-0.5 line-through"
            style={{ backgroundColor: "var(--err-25)" }}
          >
            {seg}
          </span>,
        );
      } else {
        elements.push(<span key={key}>{seg}</span>);
      }
      key++;
    }
  }

  return {
    content: (
      <div
        className="rounded-lg px-3 py-2 font-mono text-sm leading-relaxed whitespace-pre-wrap break-all"
        style={{ border: "1px solid var(--border)", background: "var(--fg-soft)" }}
      >
        {elements}
      </div>
    ),
    added: addedChars,
    removed: removedChars,
  };
}

// ---------------------------------------------------------------------------
// DiffViewer (handles long-text collapse)
// ---------------------------------------------------------------------------

function DiffViewer({
  oldProse,
  newProse,
  diffMode,
}: {
  oldProse: string;
  newProse: string;
  diffMode: DiffMode;
}) {
  const [expanded, setExpanded] = useState(false);

  const { content, added, removed } = useMemo(() => {
    if (diffMode === "word") {
      return renderWordDiff(oldProse, newProse);
    }

    const parts = diffLines(oldProse, newProse);
    const { lines, added, removed } = processLineDiff(parts);

    const rendered = lines.map((line, i) => {
      if (line.type === "skip") {
        return (
          <div
            key={i}
            className="px-3 py-0.5 text-xs text-center select-none italic"
            style={{ color: "var(--fg-30)" }}
          >
            {line.text}
          </div>
        );
      }

      const isAdd = line.type === "add";
      const isDel = line.type === "del";

      return (
        <div
          key={i}
          className="px-3 py-0.5 font-mono text-sm leading-relaxed flex"
          style={
            isAdd
              ? {
                  background: "var(--ok-15)",
                  borderLeft: "2px solid var(--ok)",
                }
              : isDel
                ? {
                    background: "var(--err-15)",
                    borderLeft: "2px solid var(--err)",
                  }
                : { color: "var(--muted)" }
          }
        >
          <span className="select-none w-5 shrink-0 text-right mr-2">
            {isAdd ? "+" : isDel ? "-" : " "}
          </span>
          <span className="min-w-0 break-all">{line.text || " "}</span>
        </div>
      );
    });

    return {
      content: (
        <div
          className="rounded-lg overflow-x-auto"
          style={{ border: "1px solid var(--border)", background: "var(--fg-soft)" }}
        >
          {rendered}
        </div>
      ),
      added,
      removed,
    };
  }, [oldProse, newProse, diffMode]);

  // Long-text detection
  const isLong = useMemo(() => {
    if (diffMode === "word") return false;
    return Math.max(oldProse.split("\n").length, newProse.split("\n").length) > 200;
  }, [oldProse, newProse, diffMode]);

  return (
    <div>
      {/* Stats badge */}
      <div className="flex items-center gap-2 mb-2 text-xs">
        {added > 0 && removed > 0 && (
          <>
            <span className="font-mono font-medium" style={{ color: "var(--ok)" }}>+{added}</span>
            <span className="font-mono font-medium" style={{ color: "var(--err)" }}>-{removed}</span>
          </>
        )}
        {added > 0 && removed === 0 && (
          <span className="font-mono font-medium" style={{ color: "var(--ok)" }}>+{added}</span>
        )}
        {added === 0 && removed > 0 && (
          <span className="font-mono font-medium" style={{ color: "var(--err)" }}>-{removed}</span>
        )}
        {added === 0 && removed === 0 && (
          <span className="font-mono" style={{ color: "var(--muted)" }}>+0 -0 无变化</span>
        )}
      </div>

      {/* Content with collapse for long text */}
      {isLong && !expanded ? (
        <div className="relative overflow-hidden" style={{ maxHeight: "12rem" }}>
          {content}
          <div
            className="absolute bottom-0 left-0 right-0 h-16 pointer-events-none"
            style={{ background: "linear-gradient(to top, var(--surface), transparent)" }}
          />
          <div className="absolute bottom-0 left-0 right-0 flex justify-center pb-2">
            <button
              className="btn btn-ghost btn-xs"
              style={{ color: "var(--accent)" }}
              onClick={() => setExpanded(true)}
            >
              展开全部内容
            </button>
          </div>
        </div>
      ) : (
        <>
          {content}
          {isLong && (
            <div className="flex justify-center mt-1">
              <button
                className="btn btn-ghost btn-xs"
                onClick={() => setExpanded(false)}
              >
                收起
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function VersionDiff({ projectId, chapterRef, versions, initialOldVersionId, initialNewVersionId }: VersionDiffProps) {
  const sorted = useMemo(() => [...versions].sort((a, b) => b.time - a.time), [versions]);

  const [oldVersionId, setOldVersionId] = useState("");
  const [newVersionId, setNewVersionId] = useState("");
  const [diffMode, setDiffMode] = useState<DiffMode>("line");
  const [oldContent, setOldContent] = useState<VersionContent | null>(null);
  const [newContent, setNewContent] = useState<VersionContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  // Set default selections (newest vs second-newest; 弹窗对比入口可预选)
  useEffect(() => {
    if (sorted.length >= 2) {
      setNewVersionId(initialNewVersionId || sorted[0].version);
      setOldVersionId(initialOldVersionId || sorted[1].version);
    }
  }, [sorted, initialOldVersionId, initialNewVersionId]);

  // Fetch version content
  useEffect(() => {
    if (!oldVersionId || !newVersionId || oldVersionId === newVersionId) return;

    setLoading(true);
    setError(null);
    setOldContent(null);
    setNewContent(null);

    Promise.all([
      api.get(
        `/novels/${projectId}/chapters/${chapterRef}/versions/${oldVersionId}/content`,
      ) as Promise<VersionContent>,
      api.get(
        `/novels/${projectId}/chapters/${chapterRef}/versions/${newVersionId}/content`,
      ) as Promise<VersionContent>,
    ])
      .then(([oldData, newData]) => {
        setOldContent(oldData);
        setNewContent(newData);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "获取版本内容失败");
      })
      .finally(() => setLoading(false));
  }, [oldVersionId, newVersionId, projectId, chapterRef, retryKey]);

  // -----------------------------------------------------------------------
  // Empty / single-version states
  // -----------------------------------------------------------------------

  if (sorted.length === 0) {
    return (
      <div
        className="rounded-lg border-dashed p-6 text-center text-sm"
        style={{ border: "1px dashed var(--border)", background: "var(--fg-soft)", color: "var(--muted)" }}
      >
        暂无版本
      </div>
    );
  }

  if (sorted.length === 1) {
    return (
      <div
        className="rounded-lg border-dashed p-6 text-center text-sm"
        style={{ border: "1px dashed var(--border)", background: "var(--fg-soft)", color: "var(--muted)" }}
      >
        <p className="mb-1">暂无版本对比数据</p>
        <p className="text-xs">保存新版本后即可查看差异</p>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Controls + diff area
  // -----------------------------------------------------------------------

  return (
    <div className="mt-6">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Old version selector */}
        <select
          className="input text-xs"
          style={{ maxWidth: 240 }}
          value={oldVersionId}
          onChange={(e) => setOldVersionId(e.target.value)}
          aria-label="旧版本"
        >
          {sorted.map((v) => (
            <option key={v.version} value={v.version} disabled={v.version === newVersionId}>
              {versionLabel(v)}
            </option>
          ))}
        </select>

        <span className="text-sm" style={{ color: "var(--fg-30)" }}>&rarr;</span>

        {/* New version selector */}
        <select
          className="input text-xs"
          style={{ maxWidth: 240 }}
          value={newVersionId}
          onChange={(e) => setNewVersionId(e.target.value)}
          aria-label="新版本"
        >
          {sorted.map((v) => (
            <option key={v.version} value={v.version} disabled={v.version === oldVersionId}>
              {versionLabel(v)}
            </option>
          ))}
        </select>

        {/* Diff mode toggle */}
        <div className="seg ml-auto">
          <button
            className={diffMode === "line" ? "on" : ""}
            onClick={() => setDiffMode("line")}
          >
            行对比
          </button>
          <button
            className={diffMode === "word" ? "on" : ""}
            onClick={() => setDiffMode("word")}
          >
            词对比
          </button>
        </div>
      </div>

      {/* Content area */}
      {loading ? (
        <div className="rounded-lg p-8" style={{ border: "1px solid var(--border)" }}>
          <div className="flex flex-col items-center gap-4">
            <Ico d={P.spinner} className="spin" size={26} style={{ color: "var(--accent)" }} />
            <div className="space-y-3 w-full max-w-lg">
              <div className="h-4 w-full rounded" style={{ background: "var(--fg-soft)" }} />
              <div className="h-4 w-3/4 rounded" style={{ background: "var(--fg-soft)" }} />
              <div className="h-4 w-5/6 rounded" style={{ background: "var(--fg-soft)" }} />
              <div className="h-4 w-2/3 rounded" style={{ background: "var(--fg-soft)" }} />
              <div className="h-4 w-4/5 rounded" style={{ background: "var(--fg-soft)" }} />
            </div>
          </div>
        </div>
      ) : error ? (
        <div
          className="rounded-lg p-4"
          style={{
            border: "1px solid var(--err-35)",
            background: "var(--err-8)",
          }}
        >
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--err)" }}>
            <Ico d={P.alert} size={15} />
            <span>{error}</span>
          </div>
          <button
            className="btn btn-ghost btn-xs mt-2"
            style={{ color: "var(--err)" }}
            onClick={() => setRetryKey((k) => k + 1)}
          >
            重试
          </button>
        </div>
      ) : oldContent && newContent ? (
        oldContent.prose === newContent.prose ? (
          <div
            className="rounded-lg p-4"
            style={{
              border: "1px solid var(--accent-35)",
              background: "var(--accent-8)",
            }}
          >
            <div className="flex items-center gap-2 text-sm" style={{ color: "var(--accent-strong)" }}>
              <Ico d={P.info} size={15} />
              <span>两个版本内容相同，无差异</span>
            </div>
          </div>
        ) : (
          <DiffViewer oldProse={oldContent.prose} newProse={newContent.prose} diffMode={diffMode} />
        )
      ) : null}
    </div>
  );
}
