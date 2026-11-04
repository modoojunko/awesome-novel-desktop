import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { kbApi, type KbEntry, type KbGenreCount, type KbLibrary } from "@/lib/kbApi";
import { kbFieldLabel, kbValueLabel } from "@/lib/kbFieldLabels";
import KbGraph from "@/components/tools/KbGraph";
import KbEntryGraph from "@/components/tools/KbEntryGraphView";
import KbOrganizePanel from "@/components/tools/KbOrganizePanel";
import KbEntryRelations from "@/components/tools/KbEntryRelations";
import KbEntryAvatar from "@/components/tools/KbEntryAvatar";
import CharacterInstanceView from "@/components/library/CharacterInstanceView";

const CONCEPTS = ["文风", "文笔", "世界设定", "角色设定", "手法", "情节"] as const;
const CONCEPT_DESC: Record<string, string> = {
  文风: "这本书的整体声音",
  文笔: "具体句子的写法",
  世界设定: "舞台、力量、势力、铁律",
  角色设定: "造好的角色，一人一条",
  手法: "写每一章时的场面打法",
  情节: "即将上线",
};

/** 深链合法值（?concept= 只认六概念；非法/缺省落「全部」）。 */
function conceptFromQuery(v: string | null): string {
  return v && (CONCEPTS as readonly string[]).includes(v) ? v : "全部";
}

/** 通用载荷平铺（概念无关，规格「条目详情抽屉：字段…」实现）：有值键按存储序出
 * (键, 展示串)；数组顿号连、对象/数组元素套对象走紧凑 JSON、空值跳过；标量值
 * 走 kbValueLabel（枚举值/布尔转中文）。 */
export function payloadRows(payload: Record<string, unknown>): [string, string][] {
  const rows: [string, string][] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length) {
        rows.push([k, v.map((x) => (typeof x === "object" && x !== null ? JSON.stringify(x) : String(x))).join("、")]);
      }
      continue;
    }
    if (typeof v === "object") {
      rows.push([k, JSON.stringify(v)]);
      continue;
    }
    rows.push([k, kbValueLabel(k, v)]);
  }
  return rows;
}

// 来源筛选（c-kb-baseline 批B）：官方精选＝只读基线层；手录/拆书＝用户条目
const SOURCE_FILTERS = [
  { key: "全部", label: "全部来源" },
  { key: "官方精选", label: "官方精选" },
  { key: "手录", label: "手录" },
  { key: "拆书", label: "拆书" },
  // 隐藏可逆：这里回读 hide 白名单，恢复默认的唯一入口
  { key: "已隐藏", label: "已隐藏" },
] as const;

export default function KnowledgeBasePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [genre, setGenre] = useState("全部题材");
  // ?concept= 深链（c-charlib-into-kb）：/tools/characters 重定向落位用；消费后即清，
  // URL 回到干净态（页签选择本身不进 URL，刷新回「全部」是预期）。
  const [concept, setConcept] = useState(() => conceptFromQuery(searchParams.get("concept")));
  const [src, setSrc] = useState("全部");
  const [q, setQ] = useState("");
  const [entries, setEntries] = useState<KbEntry[]>([]);
  const [libraries, setLibraries] = useState<KbLibrary[]>([]);
  const [genreCounts, setGenreCounts] = useState<KbGenreCount[]>([]);
  const [cursor, setCursor] = useState("");
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<KbEntry | null>(null);
  const [showManual, setShowManual] = useState(false);
  const [manualText, setManualText] = useState("");
  const [manualGenre, setManualGenre] = useState("");
  const [manualError, setManualError] = useState("");
  const [showMoreGenres, setShowMoreGenres] = useState(false);
  const [view, setView] = useState<"list" | "graph" | "entries">("list");
  const [showOrganize, setShowOrganize] = useState(false);
  const [opBusy, setOpBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncNote, setSyncNote] = useState("");
  // 「存为我的副本」（写时复制）：官方原件不动，编辑结果落用户层
  const [editDraft, setEditDraft] = useState(false);
  const [draft, setDraft] = useState("");
  const [opNote, setOpNote] = useState("");

  const loadEntries = useCallback(async (cursorId = "") => {
    setLoading(true);
    try {
      const sp = new URLSearchParams();
      if (genre !== "全部题材") sp.set("genre", genre);
      if (concept !== "全部") sp.set("concept", concept);
      if (src !== "全部") sp.set("src", src);
      if (q) sp.set("q", q);
      if (cursorId) sp.set("cursor", cursorId);
      const r = await kbApi.entries(Object.fromEntries(sp));
      setEntries((prev) => cursorId ? [...prev, ...r.entries] : r.entries);
      setCursor(r.next_cursor);
    } finally { setLoading(false); }
  }, [genre, concept, src, q]);

  // 角色设定视角（c-charlib-into-kb）：角色设定页签＋实例侧来源 → 档案柜视图体；
  // 官方精选/已隐藏两臂回通用列表（官方方法论与隐藏管理住在通用列表）。
  const viewMode = concept === "角色设定" && (src === "全部" || src === "手录" || src === "拆书");

  const loadLibraries = useCallback(async () => {
    // 视角模式下库分组卡隐藏，库列表零消费不发（D4 门控）
    if (viewMode) return;
    const r = await kbApi.libraries(genre !== "全部题材" ? genre : undefined);
    setLibraries(r);
  }, [genre, viewMode]);

  useEffect(() => {
    kbApi.genres().then(setGenreCounts).catch(() => {});
  }, []);

  useEffect(() => {
    if (!searchParams.get("concept")) return;
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在挂载后消费一次深链参数
  }, []);

  useEffect(() => {
    loadEntries();
    loadLibraries();
  }, [genre, concept, src, q]);

  const visibleGenres = useMemo(() => {
    const filled = genreCounts.filter((g) => g.count > 0);
    if (showMoreGenres) return filled;
    return filled.slice(0, 5);
  }, [genreCounts, showMoreGenres]);

  const moreCount = genreCounts.filter((g) => g.count > 0).length - visibleGenres.length;
  const showFoldToggle = moreCount > 0 || showMoreGenres;
  const groups = useMemo(() => {
    const map = new Map<string, KbLibrary[]>();
    libraries.forEach((l) => {
      const key = l.genre || "跨题材通用";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(l);
    });
    return [...map.entries()];
  }, [libraries]);

  /* 官方精选只读操作面（c-kb-baseline 批B）：隐藏＝白名单外记录；恢复官方版＝删副本。
     原件永不修改，失败静默（刷新后状态即真相）。 */
  // 只有「无筛选」时官方精选空集才等价于「没同步下来」（有筛选＝该筛选下没有）
  const noFilters = genre === "全部题材" && concept === "全部" && !q.trim();

  const handleBaselineOp = async (entry: KbEntry, action: "hide" | "clear") => {
    /* v8 ignore start -- 双保险：按钮同时 disabled，UI 面走不到该早退（真机连点防护） */
    if (opBusy) return;
    /* v8 ignore stop */
    setOpBusy(true);
    try {
      if (action === "hide") await kbApi.baselineOverride(entry.id, "hide");
      else await kbApi.clearBaselineOverride(entry.id);
      setSelected(null);
      await loadEntries();
      kbApi.genres().then(setGenreCounts).catch(() => {});
    } catch { /* 静默：下一次列表刷新即真实状态 */ }
    finally { setOpBusy(false); }
  };

  /* 编辑基线条目＝存一份用户副本（写时复制）：官方原件 SHALL NOT 被改动；
     过 C 端同一套入库闸门，失败把后端提示原样给用户。 */
  const handleBaselineEdit = async (entry: KbEntry) => {
    /* v8 ignore start -- 双保险：按钮同时 disabled，UI 面走不到该早退（真机连点防护） */
    if (opBusy) return;
    /* v8 ignore stop */
    setOpBusy(true);
    setOpNote("");
    try {
      await kbApi.baselineOverride(entry.id, "edit", draft);
      setSelected(null);
      setEditDraft(false);
      await loadEntries();
      kbApi.genres().then(setGenreCounts).catch(() => {});
    } catch (e: unknown) {
      // 后端 422 的 message＝第一条闸门原因（api.ts 不变量），原样给用户
      const err = e as { message?: string };
      setOpNote(err.message || "没存上——检查字数与格式后再试");
    } finally { setOpBusy(false); }
  };

  /* 官方精选未就绪的重试面（c-kb-baseline：启动补偿失败可手动重试，幂等） */
  const handleBaselineSync = async () => {
    /* v8 ignore start -- 双保险：按钮同时 disabled，UI 面走不到该早退 */
    if (syncBusy) return;
    /* v8 ignore stop */
    setSyncBusy(true);
    setSyncNote("");
    try {
      const r = await kbApi.baselineSync();
      setSyncNote(
        r.status === "synced"
          ? "官方精选已更新"
          : r.status === "current"
            ? "已经是最新版本"
            : r.status === "failed"
              ? "同步没成功，稍后再试"
              : "暂时取不到官方精选",
      );
      await loadEntries();
      kbApi.genres().then(setGenreCounts).catch(() => {});
    } catch {
      setSyncNote("同步没成功，稍后再试");
    } finally {
      setSyncBusy(false);
    }
  };

  const handleManual = async () => {
    setManualError("");
    /* v8 ignore start -- 手录表单校验三臂：空文本/空题材由表单交互覆盖（真机段） */
    if (!manualText.trim()) { setManualError("先写一条"); return; }
    if (!manualGenre) { setManualError("选一个题材"); return; }
    /* v8 ignore stop */
    try {
      await kbApi.createEntry({
        genre: manualGenre,
        concept: "",
        instruction: manualText,
      });
      setManualText("");
      setShowManual(false);
      loadEntries();
      loadLibraries();
      kbApi.genres().then(setGenreCounts).catch(() => {});
    } catch (e: unknown) {
      // ApiError：422 的 message = 后端第一条闸门错误（api.ts 不变量：4xx message 恒非空）
      const err = e as { message?: string };
      setManualError(err.message || "保存失败");
    }
  };

  return (
    // 版式对齐写作工具系各页（c-kb-header-align）：共用 .main 居中容器＋.page-head
    // 标题行（h1 30px/副标题 .sub/右侧动作），不再用整幅通栏大标题
    <main className="main" data-od-id="kb-home">
      <div className="page-head">
        <div>
          <h1>知识库</h1>
          <p className="sub">存的是拆书拆出的好写法和自己踩过的经验，写新书时能用上。</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          <button
            onClick={() => setShowOrganize(true)}
            className="rounded-md border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)]"
          >
            知识整理
          </button>
          <div className="flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5">
            {(["list", "graph", "entries"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${view === v ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >
                {v === "list" ? "列表" : v === "graph" ? "图谱" : "条目图"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === "graph" && <KbGraph />}
        {view === "entries" && <KbEntryGraph genre={genre !== "全部题材" ? genre : ""} />}
        {showOrganize && (
          <KbOrganizePanel
            genre={genre !== "全部题材" ? genre : "玄幻"}
            onClose={() => setShowOrganize(false)}
            onChanged={() => { void loadEntries(); void loadLibraries(); }}
          />
        )}
        <div className="flex gap-6" style={{ display: view === "graph" ? "none" : undefined }}>
          {/* 左栏 */}
          <aside className="w-52 flex-none pt-4">
            <p className="mb-2 font-mono text-[9.5px] tracking-[0.14em] text-[var(--muted)]">题材</p>
            <nav className="space-y-0.5">
              <button
                onClick={() => setGenre("全部题材")}
                className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] ${genre === "全部题材" ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >
                <span>全部</span><span className="font-mono text-[10px] opacity-70">{entries.length}</span>
              </button>
              {visibleGenres.map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className={`flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] ${genre === (g.key ?? g.name) ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
                >
                  <span>{g.name}</span><span className="font-mono text-[10px] opacity-70">{g.count}</span>
                </button>
              ))}
              {showFoldToggle && (
                <button
                  onClick={() => setShowMoreGenres(!showMoreGenres)}
                  className="w-full rounded-md px-3 py-1.5 text-left text-[11px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  {showMoreGenres ? "收起" : `更多题材 (${moreCount})`}
                </button>
              )}
              {!showMoreGenres && genreCounts.filter((g) => g.count === 0).slice(0, 2).map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  <span>{g.name}</span><span className="font-mono text-[10px]">0</span>
                </button>
              ))}
              {showMoreGenres && genreCounts.filter((g) => g.count === 0).map((g) => (
                <button
                  key={g.key ?? g.name}
                  onClick={() => setGenre(g.key ?? g.name)}
                  className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[13px] text-[var(--faint)] hover:text-[var(--muted)]"
                >
                  <span>{g.name}</span><span className="font-mono text-[10px]">0</span>
                </button>
              ))}
            </nav>
            <p className="mt-4 text-[10.5px] leading-relaxed text-[var(--faint)]">
              拆书时按题材归档；一本书只用一个题材的库。
            </p>
          </aside>

          {/* 主内容 */}
          <div className="min-w-0 flex-1 pt-4">
            {/* 概念页签 */}
            <div className="mb-4 flex flex-wrap gap-1.5">
              <button
                onClick={() => setConcept("全部")}
                className={`rounded-md px-3 py-1.5 text-[13px] ${concept === "全部" ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"}`}
              >全部</button>
              {CONCEPTS.map((c) => (
                <button
                  key={c}
                  onClick={() => setConcept(c)}
                  title={CONCEPT_DESC[c]}
                  className={`rounded-md px-3 py-1.5 text-[13px] ${concept === c ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"} ${c === "情节" ? "cursor-not-allowed opacity-40" : ""}`}
                  disabled={c === "情节"}
                >
                  {c}
                  {c === "情节" && <span className="ml-1 text-[9px] text-[var(--faint)]">即将上线</span>}
                </button>
              ))}
            </div>

            {/* 库分组：标题行＋库卡（c-kb-snapshot 库卡亮相）；视角模式下退位（D4） */}
            {!viewMode && groups.length > 0 && (
              <div className="mb-4 space-y-5">
                {groups.map(([gname, libs]) => (
                  <div key={gname}>
                    <div className="mb-2 font-mono text-[10px] tracking-[0.12em] text-[var(--muted)]">
                      {gname} · {libs.length} 个库
                    </div>
                    <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
                      {libs.map((l) => (
                        <div
                          key={l.id}
                          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[13px] font-medium text-[var(--fg)]">{l.name}</span>
                            {l.bound_in_book ? (
                              <span className="flex-none rounded-full bg-[var(--accent-soft)] px-2 py-0.5 font-mono text-[9.5px] text-[var(--accent)]">
                                本书已启用
                              </span>
                            ) : null}
                          </div>
                          {l.purpose ? (
                            <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-[var(--muted)]">{l.purpose}</p>
                          ) : null}
                          <div className="mt-2 flex gap-3 font-mono text-[10px] text-[var(--faint)]">
                            <span>{l.entry_count ?? 0} 条</span>
                            {(l.bound_novels ?? 0) > 0 && <span>{l.bound_novels} 本书在用</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 来源筛选（c-kb-baseline 批B）：官方精选可单独过滤 */}
            <div className="mb-3 flex flex-wrap gap-1.5">
              {SOURCE_FILTERS.map((s) => (
                <button
                  key={s.key}
                  data-testid={`kb-src-${s.key}`}
                  onClick={() => setSrc(s.key)}
                  className={`rounded-md border px-3 py-1 text-[12px] ${src === s.key ? "border-[var(--accent)] bg-[var(--accent-soft)] font-medium text-[var(--accent)]" : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--fg)]"}`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* 搜索（视角模式下由视图体自带搜索接管，D4） */}
            {!viewMode && (
              <div className="mb-4">
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="搜名字、内容、来源书名"
                  className="w-full max-w-xs rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] text-[var(--fg)] placeholder:text-[var(--faint)] focus:border-[var(--accent)] focus:outline-none"
                />
              </div>
            )}

            {/* 角色设定视角：档案柜视图体（c-charlib-into-kb）——题材/来源经 props 单向灌入 */}
            {viewMode && <CharacterInstanceView kbGenre={genre} kbSrc={src} />}

            {/* 条目列表（视角模式下退位） */}
            {!viewMode && (<>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">{entries.length} 条</span>
            </div>
            <div className="space-y-px">
              {entries.map((e) => (
                <button
                  key={e.id}
                  onClick={() => { setSelected(e); setEditDraft(false); setOpNote(""); }}
                  className="block w-full rounded-md px-3 py-2.5 text-left hover:bg-[var(--fg-soft)]"
                >
                  <span className="flex items-start gap-2.5">
                    {e.concept === "角色设定" && <KbEntryAvatar entry={e} />}
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-[9.5px] tracking-[0.1em] text-[var(--faint)]">
                        {e.id.slice(0, 8)} · {e.concept} · {e.genre}
                      </span>
                      <span className="mt-0.5 block text-[14px] font-medium text-[var(--fg)]">{e.title || e.instruction.slice(0, 30)}</span>
                      <span className="mt-0.5 block text-[12px] text-[var(--muted)]">{e.instruction.slice(0, 60)}</span>
                    </span>
                  </span>
                  {e.layer === "baseline" && (
                    <span className="mt-1 flex flex-wrap gap-1">
                      <span className="rounded-full bg-[var(--accent-soft)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--accent)]">
                        官方精选
                      </span>
                      {e.overlaid && (
                        <span className="rounded-full bg-[var(--fg-soft)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--muted)]">
                          我的副本
                        </span>
                      )}
                      {e.hidden && (
                        <span className="rounded-full bg-[var(--fg-soft)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--muted)]">
                          已隐藏
                        </span>
                      )}
                      {e.official_update && (
                        <span className="rounded-full border border-[var(--accent)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--accent)]">
                          官方有新版
                        </span>
                      )}
                    </span>
                  )}
                </button>
              ))}
              {cursor && (
                <button
                  onClick={() => loadEntries(cursor)}
                  className="w-full py-3 text-center text-[13px] text-[var(--accent)] hover:underline"
                >加载更多</button>
              )}
              {!entries.length && !loading && src === "官方精选" && noFilters && (
                <div data-testid="kb-baseline-empty" className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">官方精选还没有同步下来。</p>
                  {syncNote && <p className="mt-1 text-[12px] text-[var(--muted)]">{syncNote}</p>}
                  <button
                    data-testid="kb-baseline-sync"
                    disabled={syncBusy}
                    onClick={() => { void handleBaselineSync(); }}
                    className="mt-3 rounded-lg border border-[var(--accent)] px-4 py-2 text-[13px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
                  >重新同步</button>
                </div>
              )}
              {!entries.length && !loading && src === "官方精选" && !noFilters && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">当前筛选下没有官方精选条目。</p>
                </div>
              )}
              {!entries.length && !loading && src === "已隐藏" && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">没有隐藏的官方精选条目。</p>
                </div>
              )}
              {!entries.length && !loading && src !== "官方精选" && src !== "已隐藏" && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">还没有条目——先拆书或手录，写法到位后这里会长出来。</p>
                  <button
                    onClick={() => setShowManual(true)}
                    className="mt-3 rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)]"
                  >记一条</button>
                </div>
              )}
            </div>
            </>)}
          </div>
        </div>

      {/* 手录表单 */}
      {showManual && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-xl">
            <h2 className="mb-4 text-lg font-semibold">记一条</h2>
            <div className="mb-3">
              <label className="mb-1 block text-[12px] text-[var(--muted)]">题材 *</label>
              <select
                value={manualGenre}
                onChange={(e) => setManualGenre(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px]"
              >
                <option value="">选一个</option>
                {genreCounts.map((g) => (
                  <option key={g.key ?? g.name} value={g.key ?? g.name}>{g.name}</option>
                ))}
              </select>
            </div>
            <div className="mb-3">
              <label className="mb-1 block text-[12px] text-[var(--muted)]">写什么（以句号结尾）*</label>
              <textarea
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder="你想记什么写法？贴上来"
                rows={3}
                maxLength={240}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] resize-none"
              />
              <p className="mt-1 text-right text-[10px] text-[var(--faint)]">{manualText.length}/240</p>
            </div>
            {manualError && <p className="mb-3 text-[12px] text-red-500">{manualError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowManual(false)} className="rounded-lg border border-[var(--border)] px-4 py-2 text-[13px]">取消</button>
              <button onClick={handleManual} className="rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)]">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 详情抽屉 */}
      {selected && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSelected(null)} />
          <div className="absolute right-0 top-0 h-full w-96 border-l border-[var(--border)] bg-[var(--surface)] p-6 shadow-xl overflow-y-auto">
            <div className="mb-4 flex items-center justify-between">
              <span className="font-mono text-[9.5px] tracking-[0.1em] text-[var(--faint)]">
                {selected.id.slice(0, 8)} · {selected.concept} · {selected.genre}
              </span>
              <button onClick={() => setSelected(null)} className="text-[var(--faint)] hover:text-[var(--fg)]">✕</button>
            </div>
            <h2 className="text-xl font-semibold text-[var(--fg)]">{selected.title || selected.instruction.slice(0, 30)}</h2>
            {/* 指令＝一句人设是闸门惯例（角色条目）；与一句话人设相同时不再重复显示 */}
            {selected.instruction && selected.payload?.persona !== selected.instruction && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">指令</p>
                <p className="mt-1 text-[13px] leading-relaxed">{selected.instruction}</p>
              </div>
            )}
            {payloadRows(selected.payload).length > 0 && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">字段</p>
                <dl className="mt-1 space-y-1.5">
                  {payloadRows(selected.payload).map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">{kbFieldLabel(selected.concept, k)}</dt>
                      <dd className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-[var(--fg)]">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {selected.example && (
              <div className="mt-4 border-l-2 border-[var(--accent)] pl-3">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">正例</p>
                <p className="mt-1 text-[13px]">{selected.example}</p>
              </div>
            )}
            {selected.negative_example && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">反例</p>
                <p className="mt-1 text-[13px]">{selected.negative_example}</p>
              </div>
            )}
            {selected.evidence && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">证据</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">{selected.evidence}</p>
              </div>
            )}
            {selected.src_novel_name && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">源自小说</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">{selected.src_novel_name}</p>
              </div>
            )}
            {selected.layer === "baseline" && (
              <div className="mt-6 border-t border-[var(--border)] pt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--accent)]">官方精选 · 只读</p>
                <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--muted)]">
                  官方条目不能删除；想改就存一份你的副本（官方原件不变）。隐藏后可在「已隐藏」里恢复。
                </p>
                {selected.official_update && (
                  <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--accent)]">
                    官方已更新这条，当前显示的是你的副本，可恢复官方版。
                  </p>
                )}
                {!selected.hidden && (
                  <div className="mt-3">
                    {!editDraft ? (
                      <button
                        data-testid="kb-baseline-edit"
                        disabled={opBusy}
                        onClick={() => {
                          setEditDraft(true);
                          setDraft(selected.instruction);
                          setOpNote("");
                        }}
                        className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--fg)] disabled:opacity-50"
                      >
                        存为我的副本
                      </button>
                    ) : (
                      <div className="space-y-2">
                        <textarea
                          data-testid="kb-baseline-draft"
                          value={draft}
                          onChange={(ev) => setDraft(ev.target.value)}
                          rows={4}
                          maxLength={240}
                          className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 text-[12.5px] leading-relaxed text-[var(--fg)]"
                        />
                        <p className="text-right font-mono text-[10px] text-[var(--faint)]">
                          {draft.length}/240
                        </p>
                        <div className="flex gap-2">
                          <button
                            data-testid="kb-baseline-save"
                            disabled={opBusy}
                            onClick={() => { void handleBaselineEdit(selected); }}
                            className="rounded-lg border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
                          >
                            保存副本
                          </button>
                          <button
                            data-testid="kb-baseline-edit-cancel"
                            disabled={opBusy}
                            onClick={() => { setEditDraft(false); setOpNote(""); }}
                            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--fg)] disabled:opacity-50"
                          >
                            取消
                          </button>
                        </div>
                        {opNote && (
                          <p data-testid="kb-baseline-op-note" className="text-[11.5px] text-[var(--muted)]">
                            {opNote}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-3">
                  {selected.hidden ? (
                    <button
                      data-testid="kb-baseline-unhide"
                      disabled={opBusy}
                      onClick={() => { void handleBaselineOp(selected, "clear"); }}
                      className="rounded-lg border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
                    >
                      恢复默认
                    </button>
                  ) : selected.overlaid ? (
                    <button
                      data-testid="kb-baseline-restore"
                      disabled={opBusy}
                      onClick={() => { void handleBaselineOp(selected, "clear"); }}
                      className="rounded-lg border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
                    >
                      恢复官方版
                    </button>
                  ) : (
                    <button
                      data-testid="kb-baseline-hide"
                      disabled={opBusy}
                      onClick={() => { void handleBaselineOp(selected, "hide"); }}
                      className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--fg)] disabled:opacity-50"
                    >
                      隐藏这条
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
