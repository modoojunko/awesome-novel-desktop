import { useCallback, useEffect, useMemo, useState } from "react";
import { kbApi, type KbEntry, type KbGenreCount, type KbLibrary } from "@/lib/kbApi";

const CONCEPTS = ["文风", "文笔", "世界设定", "角色设定", "手法", "情节"] as const;
const CONCEPT_DESC: Record<string, string> = {
  文风: "这本书的整体声音",
  文笔: "具体句子的写法",
  世界设定: "舞台、力量、势力、铁律",
  角色设定: "造角色的方法，成品在角色库",
  手法: "写每一章时的场面打法",
  情节: "即将上线",
};

export default function KnowledgeBasePage() {
  const [genre, setGenre] = useState("全部题材");
  const [concept, setConcept] = useState("全部");
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

  const loadEntries = useCallback(async (cursorId = "") => {
    setLoading(true);
    try {
      const sp = new URLSearchParams();
      if (genre !== "全部题材") sp.set("genre", genre);
      if (concept !== "全部") sp.set("concept", concept);
      if (q) sp.set("q", q);
      if (cursorId) sp.set("cursor", cursorId);
      const r = await kbApi.entries(Object.fromEntries(sp));
      setEntries((prev) => cursorId ? [...prev, ...r.entries] : r.entries);
      setCursor(r.next_cursor);
    } finally { setLoading(false); }
  }, [genre, concept, q]);

  const loadLibraries = useCallback(async () => {
    const r = await kbApi.libraries(genre !== "全部题材" ? genre : undefined);
    setLibraries(r);
  }, [genre]);

  useEffect(() => {
    kbApi.genres().then(setGenreCounts).catch(() => {});
  }, []);

  useEffect(() => {
    loadEntries();
    loadLibraries();
  }, [genre, concept, q]);

  const visibleGenres = useMemo(() => {
    const filled = genreCounts.filter((g) => g.count > 0);
    if (showMoreGenres) return filled;
    return filled.slice(0, 5);
  }, [genreCounts, showMoreGenres]);

  const moreCount = genreCounts.filter((g) => g.count > 0).length - visibleGenres.length;
  const groups = useMemo(() => {
    const map = new Map<string, KbLibrary[]>();
    libraries.forEach((l) => {
      const key = l.genre || "跨题材通用";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(l);
    });
    return [...map.entries()];
  }, [libraries]);

  const handleManual = async () => {
    setManualError("");
    if (!manualText.trim()) { setManualError("先写一条"); return; }
    if (!manualGenre) { setManualError("选一个题材"); return; }
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
      const err = e as { response?: { data?: { detail?: { errors?: Record<string, string> } } } };
      const errors = err.response?.data?.detail?.errors;
      if (errors) setManualError(Object.values(errors)[0] ?? "保存失败");
      else setManualError("保存失败");
    }
  };

  const hasContent = (g: string) => genreCounts.some((c) => (c.key ?? c.name) === g && c.count > 0);

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--fg)]">
      {/* 顶栏 */}
      <div className="border-b border-[var(--border)] px-6 py-4">
        <p className="font-mono text-[10.5px] tracking-[0.14em] text-[var(--muted)]">—— 写作工具 · 知识库</p>
        <h1 className="mt-2 font-[var(--font-display)] text-4xl font-semibold tracking-wide">知识库</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">存的是拆书拆出的好写法和自己踩过的经验，写新书时能用上。</p>
      </div>

      <div className="mx-auto max-w-[1220px] px-6 pb-16">
        <div className="flex gap-6">
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
              {moreCount > 0 && (
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

            {/* 库分组标题行 */}
            {groups.length > 0 && (
              <div className="mb-4 space-y-1">
                {groups.map(([gname, libs]) => (
                  <div key={gname} className="font-mono text-[10px] tracking-[0.12em] text-[var(--muted)]">
                    {gname} · {libs.length} 个库
                  </div>
                ))}
              </div>
            )}

            {/* 搜索 */}
            <div className="mb-4">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜名字、内容、来源书名"
                className="w-full max-w-xs rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] text-[var(--fg)] placeholder:text-[var(--faint)] focus:border-[var(--accent)] focus:outline-none"
              />
            </div>

            {/* 条目列表 */}
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">{entries.length} 条</span>
            </div>
            <div className="space-y-px">
              {entries.map((e) => (
                <button
                  key={e.id}
                  onClick={() => setSelected(e)}
                  className="block w-full rounded-md px-3 py-2.5 text-left hover:bg-[var(--fg-soft)]"
                >
                  <span className="font-mono text-[9.5px] tracking-[0.1em] text-[var(--faint)]">
                    {e.id.slice(0, 8)} · {e.concept} · {e.genre}
                  </span>
                  <span className="mt-0.5 block text-[14px] font-medium text-[var(--fg)]">{e.title || e.instruction.slice(0, 30)}</span>
                  <span className="mt-0.5 block text-[12px] text-[var(--muted)]">{e.instruction.slice(0, 60)}</span>
                </button>
              ))}
              {cursor && (
                <button
                  onClick={() => loadEntries(cursor)}
                  className="w-full py-3 text-center text-[13px] text-[var(--accent)] hover:underline"
                >加载更多</button>
              )}
              {!entries.length && !loading && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center">
                  <p className="text-[13px] text-[var(--muted)]">还没有条目——先拆书或手录，写法到位后这里会长出来。</p>
                  <button
                    onClick={() => setShowManual(true)}
                    className="mt-3 rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)]"
                  >记一条</button>
                </div>
              )}
            </div>
          </div>
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
            {selected.instruction && (
              <div className="mt-4">
                <p className="text-[10.5px] font-mono tracking-[0.12em] text-[var(--muted)]">指令</p>
                <p className="mt-1 text-[13px] leading-relaxed">{selected.instruction}</p>
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
          </div>
        </div>
      )}
    </div>
  );
}
