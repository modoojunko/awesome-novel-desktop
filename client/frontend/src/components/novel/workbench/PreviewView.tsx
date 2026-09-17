// 预览阅读器（preview-reader，c-preview-reader）：
//   三栏 = 全书目录（字数 + 成稿状态标签）/ 阅读区（章级导航 + 章元信息）/ 右栏（阅读配置 + 全书概览）。
//   成稿状态（拟定/草稿/已归档，已归档优先）取代章纲三态 dot——章纲缺口细节归写作视图
//   （ADJUSTMENTS「preview.html」#2）。
//   选中章与阅读配置均为预览本地态（ADJUSTMENTS #12/#13）：切章不回写写作视图；
//   阅读配置走 pref.book.{pid}.read.*（独立于写作偏好 fs/lh，互不污染）。
//   语义沿 ADJUSTMENTS #12：全书只读通读（草稿与归档章皆可读）；旧稿支线不进目录与概览。
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { nodeLabel } from "@/lib/nodeTitle";
import {
  getBookReadingPrefs,
  setBookReadingPref,
  type ReadingPrefs,
} from "@/lib/prefs";
import type { WorkbenchVolume } from "@/hooks/useWorkbench";

interface PreviewViewProps {
  projectId: string;
  /** 全量卷章结构（wb.volumes 常驻内存可能滞后 → 挂载时对齐一次） */
  volumes: WorkbenchVolume[];
  onRefresh: () => void;
  /** 初始定档章（写作视图当前章；缺省/失效回退首章） */
  initialRef?: string | null;
  /** 空书出口：去写作视图建卷建章 */
  onGoWrite: () => void;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[m] ?? m,
  );
}

/** prose（\n 分段）→ 段落 HTML（只读渲染用） */
function proseToHtml(prose: string): string {
  return prose
    .split("\n")
    .map((p) => `<p>${escapeHtml(p) || "<br>"}</p>`)
    .join("");
}

function volNo(name: string): number {
  const m = name.match(/^vol-(\d+)$/);
  return m ? parseInt(m[1], 10) : 0;
}

interface FlatChapter {
  ref: string;
  v: WorkbenchVolume;
  c: WorkbenchVolume["chapters"][number];
}

/** 成稿状态（已归档优先）：拟定 / 草稿 / 已归档。 */
function statusOf(c: { archived?: boolean; has_prose?: boolean; word_count: number }) {
  const hasProse = c.has_prose ?? c.word_count > 0;
  if (c.archived) return { label: "已归档", cls: "pill" };
  if (hasProse) return { label: "草稿", cls: "pill pill-accent" };
  return { label: "拟定", cls: "pill" };
}

const READING_SIZE_PX: Record<ReadingPrefs["size"], string> = {
  s: "14px",
  m: "16px",
  l: "18px",
};
const READING_LINE: Record<ReadingPrefs["line"], string> = {
  tight: "1.6",
  comfy: "1.85",
  loose: "2.2",
};

export default function PreviewView({
  projectId,
  volumes,
  onRefresh,
  initialRef,
  onGoWrite,
}: PreviewViewProps) {
  const [selRef, setSelRef] = useState<string | null>(null);
  const [prose, setProse] = useState("");
  const [loading, setLoading] = useState(false);
  /** 阅读配置：挂载读一次入 state，之后仅本地 set（不触发 volumes 重取） */
  const [reading, setReading] = useState<ReadingPrefs>(() =>
    getBookReadingPrefs(projectId),
  );

  // 挂载时对齐一次卷章结构（wb.volumes 仅靠事件增量刷新，可能滞后于本页外变更）
  useEffect(() => {
    onRefresh();
  }, [onRefresh]);

  const chTotal = volumes.reduce((a, v) => a + v.chapters.length, 0);

  /** 全书主线扁平序（卷升序 + 章升序；旧稿支线不在 volumes 主列表内） */
  const flatChapters = useMemo<FlatChapter[]>(() => {
    const list: FlatChapter[] = [];
    for (const v of volumes)
      for (const c of v.chapters) list.push({ ref: `${v.name}-ch-${c.chapter}`, v, c });
    return list;
  }, [volumes]);

  const chapterIndex = useMemo(
    () => new Map(flatChapters.map((f) => [f.ref, f])),
    [flatChapters],
  );

  // 有效选中：本地选择失效（章已删）→ 回退初始章 → 回退首章
  const activeRef =
    selRef && chapterIndex.has(selRef)
      ? selRef
      : initialRef && chapterIndex.has(initialRef)
        ? initialRef
        : (flatChapters[0]?.ref ?? null);
  const active = activeRef ? chapterIndex.get(activeRef) : undefined;
  const activeIdx = active ? flatChapters.findIndex((f) => f.ref === active.ref) : -1;
  const prev = activeIdx > 0 ? flatChapters[activeIdx - 1] : null;
  const next = active && activeIdx < flatChapters.length - 1 ? flatChapters[activeIdx + 1] : null;

  useEffect(() => {
    if (!projectId || !activeRef) return;
    let cancelled = false;
    setLoading(true);
    api
      .get(`/novels/${projectId}/chapters/${activeRef}`)
      .then((d: { prose?: string }) => {
        if (!cancelled) setProse(d.prose ?? "");
      })
      .catch(() => {
        if (!cancelled) setProse("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, activeRef]);

  const step = (d: -1 | 1) => {
    const target = d === -1 ? prev : next;
    if (target) setSelRef(target.ref);
  };

  const setReadingPref = <K extends keyof ReadingPrefs>(key: K, value: ReadingPrefs[K]) => {
    setReading((r) => ({ ...r, [key]: value }));
    setBookReadingPref(projectId, key, value);
  };

  // 概览统计（主线 = volumes 主列表；与目录行同源）
  const totalWords = volumes.reduce(
    (a, v) => a + v.chapters.reduce((b, c) => b + (c.word_count || 0), 0),
    0,
  );
  const nArchived = volumes.reduce(
    (a, v) => a + v.chapters.filter((c) => c.archived).length,
    0,
  );
  const nDraft = volumes.reduce(
    (a, v) =>
      a + v.chapters.filter((c) => !c.archived && (c.has_prose ?? c.word_count > 0)).length,
    0,
  );
  const nPlanned = chTotal - nArchived - nDraft;

  const activeVolLabel = active ? nodeLabel("卷", volNo(active.v.name), active.v.title) : "";
  const activeChLabel = active ? nodeLabel("章", active.c.chapter, active.c.title) : "";
  const activeStatus = active ? statusOf(active.c) : null;

  const seg = (
    kind: keyof ReadingPrefs,
    label: string,
    opts: Array<[string, string]>,
  ) => (
    <div className="pv-card">
      <h4>{label}</h4>
      <div className="pv-seg" role="group" aria-label={label} data-od-id={`seg-pv-${kind}`}>
        {opts.map(([v, t]) => (
          <button
            key={v}
            className={reading[kind] === v ? "on" : undefined}
            aria-pressed={reading[kind] === v}
            onClick={() => setReadingPref(kind, v as never)}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );

  const proseHtml = !active
    ? ""
    : loading
      ? ""
      : prose
        ? proseToHtml(prose)
        : `<p class="vempty">本章还没有正文，回到「写作」开始写。</p>`;

  const rootCls = [
    "view preview-v on",
    reading.theme !== "paper" ? `pv-theme-${reading.theme}` : "",
    reading.font !== "serif" ? `pv-font-${reading.font}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={rootCls}
      style={
        {
          "--pv-size": READING_SIZE_PX[reading.size],
          "--pv-line": READING_LINE[reading.line],
        } as React.CSSProperties
      }
    >
      <aside className="col-tree pv-tree">
        <div className="pv-head">
          <span className="t">全书目录</span>
          <span className="sub" data-testid="pv-count">
            {chTotal > 0
              ? `主线 ${chTotal} 章 · ${volumes.length} 卷 · 不含旧稿`
              : "还没有卷与章节"}
          </span>
        </div>
        <div className="pv-toc" aria-label="预览目录">
          {volumes.map((v) => (
            <div key={v.name}>
              <div className="pv-vol">
                <b>{nodeLabel("卷", volNo(v.name), v.title)}</b> · {v.chapters.length} 章
              </div>
              {v.chapters.map((c) => {
                const ref = `${v.name}-ch-${c.chapter}`;
                const st = statusOf(c);
                const hasProse = c.has_prose ?? c.word_count > 0;
                return (
                  <button
                    key={ref}
                    type="button"
                    className={"pv-ch" + (ref === activeRef ? " on" : "")}
                    aria-pressed={ref === activeRef}
                    data-od-id="pv-ch"
                    onClick={() => setSelRef(ref)}
                  >
                    <span className="ti">{nodeLabel("章", c.chapter, c.title)}</span>
                    {hasProse && <span className="wc">{c.word_count}字</span>}
                    <span className={st.cls}>{st.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
          {volumes.length === 0 && (
            <div className="pv-toc-empty">还没有卷与章节。回到「写作」添加第一卷。</div>
          )}
        </div>
      </aside>

      <section className="pv-read">
        <div className="pv-read-top">
          <span className="pos" data-testid="pv-pos">
            {active ? `${activeVolLabel} · ${activeChLabel}` : "暂无可预览的章节"}
          </span>
          <button
            type="button"
            className="pv-turn"
            aria-disabled={!prev}
            data-testid="pv-prev"
            data-od-id="pv-prev"
            onClick={() => step(-1)}
          >
            上一章
          </button>
          <button
            type="button"
            className="pv-turn"
            aria-disabled={!next}
            data-testid="pv-next"
            data-od-id="pv-next"
            onClick={() => step(1)}
          >
            下一章
          </button>
        </div>
        <div className="pv-prose-wrap" data-testid="preview-prose-wrap">
          {active ? (
            <div className="pv-chapter" data-testid="pv-chapter">
              <p className="pv-voltag">{activeVolLabel}</p>
              <h2>{activeChLabel}</h2>
              <p className="pv-meta" data-testid="pv-meta">
                {activeStatus?.label}
                {(active.c.has_prose ?? active.c.word_count > 0) && ` · ${active.c.word_count} 字`}
                {active.c.stale ? " · 基于旧设定" : ""}
              </p>
            </div>
          ) : (
            <p className="vempty">这本书还没有可预览的章节。</p>
          )}
          <div
            className="pv-prose"
            data-testid="preview-prose"
            dangerouslySetInnerHTML={{ __html: proseHtml }}
          />
        </div>
      </section>

      <aside className="pv-side">
        {volumes.length === 0 ? (
          <div className="pv-card">
            <h4>全书概览</h4>
            <p className="pv-side-empty">还没有卷与章节。</p>
            <button className="btn btn-primary btn-sm" onClick={onGoWrite}>
              去写作
            </button>
          </div>
        ) : (
          <div className="pv-card" data-od-id="pv-overview">
            <h4>全书概览</h4>
            <div className="stat-line">
              <span>
                章节 <b>{chTotal}</b>
              </span>
              <span>
                字数 <b>{totalWords}</b>
              </span>
              <span>
                已归档 <b>{nArchived}</b> · 草稿 {nDraft} · 拟定 {nPlanned}
              </span>
            </div>
          </div>
        )}
        {seg("size", "字号", [
          ["s", "小"],
          ["m", "中"],
          ["l", "大"],
        ])}
        {seg("font", "字体", [
          ["serif", "衬线"],
          ["sans", "黑体"],
          ["kai", "楷体"],
        ])}
        {seg("line", "行距", [
          ["tight", "紧凑"],
          ["comfy", "舒适"],
          ["loose", "宽松"],
        ])}
        {seg("theme", "主题", [
          ["paper", "白纸"],
          ["sepia", "护眼"],
          ["night", "夜间"],
        ])}
      </aside>
    </div>
  );
}
