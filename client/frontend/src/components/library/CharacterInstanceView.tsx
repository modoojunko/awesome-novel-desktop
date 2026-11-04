// 角色实例视图体（c-charlib-into-kb）：原角色库档案柜整体搬进知识库「角色设定」视角。
// 只含视图体（rail 四组筛选/toolbar/双视图/统计/空态＋编辑卡与用到新书弹窗），
// 无页面壳（页头/导航入口随独立页面退役）；样式沿用 lib-* 家族零新增。
// 题材比对与 rail 选项走 genre_norm（#980 读取侧归一；存量自由题材 fallback 原始值）；
// 跨题材通用灌入走 __empty__ 哨兵（"" 在 Filters 语义里是「清除筛选」，不能当筛选值灌入）。
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { useCharacterLibrary } from "@/hooks/useCharacterLibrary";
import type { LibraryCard } from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";
import LibraryAvatar from "@/components/library/LibraryAvatar";
import CardEditorModal from "@/components/library/CardEditorModal";
import UseInNovelModal from "@/components/library/UseInNovelModal";

const KIND_VALUES = ["亲人", "朋友", "挚友", "小弟", "下人", "长辈", "敌人", "其他"];
const SRC_LABEL: Record<string, string> = { book: "书内", deconstruct: "拆书", manual: "手建" };
const ROLE_ORDER = ["主角", "配角", "反派", "路人"];
const PILL_CLS: Record<string, string> = { 主角: "pro", 配角: "support", 反派: "villain" };

/** KB「跨题材通用」灌入哨兵：视角内表达「只看未分题材」，与「全部」（空串）区分开。 */
export const GENRE_EMPTY = "__empty__";

/** KB 左栏题材选中值 → 视角题材筛选预设；「全部题材」＝不预设（视角保持自己的选择）。 */
export function genrePresetOf(kbGenre: string): string | null {
  if (kbGenre === "全部题材") return null;
  return kbGenre === "" ? GENRE_EMPTY : kbGenre;
}

/** KB 来源筛选值 → 视角来源组预设（手录→手建 manual、拆书→deconstruct；官方精选/已隐藏不会走到视角）。 */
export function srcPresetOf(kbSrc: string): "" | "deconstruct" | "manual" {
  if (kbSrc === "手录") return "manual";
  if (kbSrc === "拆书") return "deconstruct";
  return "";
}

/** 卡的归一题材（读取侧归一口径）：genre_norm 优先，自由题材/老卡回落原始值。 */
function normGenre(c: LibraryCard): string {
  return c.genre_norm || c.genre || "";
}

interface Filters {
  genre: string;
  role: string;
  kind: string;
  src: string;
  q: string;
  sort: "default" | "name";
}

const EMPTY_FILTERS: Filters = { genre: "", role: "", kind: "", src: "", q: "", sort: "default" };

function viewInit(): "card" | "list" {
  try {
    return localStorage.getItem("charlib.view") === "list" ? "list" : "card";
  } catch {
    return "card";
  }
}

function normalize(text: string): string {
  return (text || "").normalize("NFKC").toLowerCase();
}

/** 多词 AND 匹配 + 命中词（归一化口径同源，防「亮的不等于筛中的」） */
function matchTerms(card: LibraryCard, terms: string[]): { ok: boolean; hits: string[] } {
  const visible = [
    card.name,
    ...(card.aliases || []),
    card.persona,
    card.dossier?.speech || "",
    ...(card.kind ? [card.kind] : []),
    card.genre,
  ]
    .map(normalize)
    .join("\n");
  const hay = [
    visible,
    normalize(card.dossier?.background || ""),
    normalize(card.dossier?.plot || ""),
    normalize(card.dossier?.faction || ""),
    normalize(card.dossier?.look || ""),
    normalize(card.dossier?.race || ""),
    ...Object.values(card.cog || {}).map(normalize),
    normalize(card.src?.novel_name || ""),
  ].join("\n");
  const hits: string[] = [];
  for (const t of terms) {
    if (!hay.includes(t)) return { ok: false, hits: [] };
    hits.push(t);
  }
  return { ok: true, hits };
}

/** 命中隐藏字段时卡底显示「命中：…」行（回落展示，保证高亮可见） */
function hiddenHitLine(card: LibraryCard, terms: string[]): string {
  if (terms.length === 0) return "";
  const visibleText = normalize(
    [card.name, ...(card.aliases || []), card.persona, card.dossier?.speech || "", card.genre, card.kind].join("\n"),
  );
  const hidden = terms.filter((t) => !visibleText.includes(t));
  if (hidden.length === 0) return "";
  const sources = [
    ["背景", card.dossier?.background || ""],
    ["剧情定位", card.dossier?.plot || ""],
    ["势力", card.dossier?.faction || ""],
    ["外貌", card.dossier?.look || ""],
    ["种族", card.dossier?.race || ""],
    ["认知", Object.values(card.cog || {}).join(" ")],
    ["来源", card.src?.novel_name || ""],
    ["其他格", hidden.join(" ")], // 兜底：hidden 恒非空，最后一项必命中
  ] as const;
  return sources.find(([, text]) => hidden.some((t) => normalize(text).includes(t)))![0];
}

export default function CharacterInstanceView({
  kbGenre = "全部题材",
  kbSrc = "全部",
}: {
  /** 宿主（知识库页）题材栏选中值：单向灌入视角，视角内改选不回写（design D3）。 */
  kbGenre?: string;
  /** 宿主来源筛选值：手录→手建、拆书→拆书、全部→全部（官方精选/已隐藏不会挂载本视图）。 */
  kbSrc?: string;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useCharacterLibrary();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [view, setView] = useState<"card" | "list">(viewInit);
  const [editing, setEditing] = useState<LibraryCard | null>(null);
  const [creating, setCreating] = useState(false);
  const [usingCard, setUsingCard] = useState<LibraryCard | null>(null);

  // KB 左栏单向灌入（D3）：题材/来源预设变化即重置对应筛选；视角内手选不被打扰，
  // 直到 KB 栏再次变化。跨题材通用走哨兵，不把「清除筛选」的 "" 当筛选值灌入。
  useEffect(() => {
    const g = genrePresetOf(kbGenre);
    if (g !== null) setFilters((f) => ({ ...f, genre: g === GENRE_EMPTY ? GENRE_EMPTY : g }));
  }, [kbGenre]);
  useEffect(() => {
    setFilters((f) => ({ ...f, src: srcPresetOf(kbSrc) }));
  }, [kbSrc]);

  const items = data?.items || [];
  const terms = useMemo(
    () => normalize(filters.q).split(/\s+/).filter(Boolean),
    [filters.q],
  );

  const visible = useMemo(() => {
    const list = items
      .filter((c) => {
        if (!filters.genre) return true;
        if (filters.genre === GENRE_EMPTY) return !normGenre(c);
        return normGenre(c) === filters.genre;
      })
      .filter((c) => (!filters.role || c.role === filters.role))
      .filter((c) => (!filters.kind || c.kind === filters.kind))
      .filter((c) => (!filters.src || c.src.kind === filters.src))
      .filter((c) => matchTerms(c, terms).ok);
    if (filters.sort === "name") {
      list.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
    } else {
      list.sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
    }
    return list;
  }, [items, filters, terms]);

  // 题材 rail 选项走归一题材（D3）：目录内卡同域命中；目录外自由题材保留原样可见
  const genres = useMemo(() => {
    const seen: string[] = [];
    for (const c of items) {
      const g = normGenre(c);
      if (g && !seen.includes(g)) seen.push(g);
    }
    return seen;
  }, [items]);

  // 「未分题材」档（跨题材通用）：与 KB 题材栏同名档同口径
  const emptyGenreCount = useMemo(
    () => items.filter((c) => !normGenre(c)).length,
    [items],
  );

  const bookTotal = useMemo(
    () => new Set(items.map((c) => c.src.novel_name).filter(Boolean)).size,
    [items],
  );

  const hit = (text: string): (string | { hit: string })[] => {
    if (terms.length === 0) return [text];
    const norm = normalize(text);
    const ranges: [number, number][] = [];
    for (const t of terms) {
      let from = 0;
      for (;;) {
        const idx = norm.indexOf(t, from);
        if (idx < 0) break;
        ranges.push([idx, idx + t.length]);
        from = idx + t.length;
      }
    }
    if (ranges.length === 0) return [text];
    ranges.sort((a, b) => a[0] - b[0]);
    const out: (string | { hit: string })[] = [];
    let cursor = 0;
    for (const [start, end] of ranges) {
      if (start < cursor) continue;
      if (start > cursor) out.push(text.slice(cursor, start));
      out.push({ hit: text.slice(start, end) });
      cursor = end;
    }
    if (cursor < text.length) out.push(text.slice(cursor));
    return out;
  };
  const render = (text: string) =>
    hit(text).map((part, i) =>
      typeof part === "string" ? (
        <span key={i}>{part}</span>
      ) : (
        <mark key={i} className="lib-hl">
          {part.hit}
        </mark>
      ),
    );

  const switchView = (v: "card" | "list") => {
    setView(v);
    try {
      localStorage.setItem("charlib.view", v);
    } catch {
      /* 本地存储不可用：本会话内仍生效 */
    }
  };

  const railGroup = (
    title: string,
    key: keyof Pick<Filters, "genre" | "role" | "kind" | "src">,
    options: { value: string; label: string; count: number }[],
    extra?: { value: string; label: string; count: number }[],
  ) => (
    <div className="lib-rail-group" data-testid={`lib-rail-${key}`}>
      <div className="lib-rail-cap">{title}</div>
      <button className={filters[key] === "" ? "on" : ""} onClick={() => setFilters((f) => ({ ...f, [key]: "" }))}>
        全部<span className="lib-n">{String(items.length).padStart(2, "0")}</span>
      </button>
      {options.map((o) => (
        <button
          key={o.value}
          className={filters[key] === o.value ? "on" : ""}
          onClick={() => setFilters((f) => ({ ...f, [key]: o.value }))}
        >
          {o.label}
          <span className="lib-n">{String(o.count).padStart(2, "0")}</span>
        </button>
      ))}
      {(extra ?? []).map((o) => (
        <button
          key={o.value}
          className={filters[key] === o.value ? "on" : ""}
          onClick={() => setFilters((f) => ({ ...f, [key]: o.value }))}
        >
          {o.label}
          <span className="lib-n">{String(o.count).padStart(2, "0")}</span>
        </button>
      ))}
    </div>
  );

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: queryKeys.characterLibrary });
  };

  const renderCard = (c: LibraryCard, idx: number) => {
    const hiddenLine = hiddenHitLine(c, terms);
    return (
      <article
        key={c.id}
        className="lib-cell"
        onClick={() => setEditing(c)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setEditing(c);
          }
        }}
        tabIndex={0}
        role="button"
        aria-label={`编辑 ${c.name || "未命名"}`}
        data-testid="lib-card"
      >
        <div className="lib-cell-top">
          <LibraryAvatar card={c} />
          <span className={`lib-pill ${PILL_CLS[c.role] || ""}`}>{c.role}</span>
          <span className="lib-fno">档 {String(idx + 1).padStart(3, "0")}</span>
        </div>
        <div className="lib-cname">{render(c.name || "未命名")}</div>
        <p className="lib-cpersona">{render(c.persona || "还没写一句话人设")}</p>
        <div className="lib-cspeech">语言特征：{c.dossier?.speech ? render(c.dossier.speech) : "没填"}</div>
        {hiddenLine && (
          <div className="lib-hitline">
            命中：{hiddenLine} 里的「{terms.filter((t) => !normalize(c.name + c.persona + (c.dossier?.speech || "")).includes(t)).join("、")}」
          </div>
        )}
        <div className="lib-cell-foot">
          {c.kind && <span className="lib-tag">{c.kind}</span>}
          <span className="lib-tag src">{SRC_LABEL[c.src.kind] || "手建"}</span>
          <span className="lib-born">{c.src.novel_name ? `诞生于 ${c.src.novel_name}` : "手建"}</span>
        </div>
        <span className="lib-acts">
          <button
            className="lib-act use"
            onClick={(e) => {
              e.stopPropagation();
              setUsingCard(c);
            }}
          >
            用到新书
          </button>
          <button
            className="lib-act edit"
            onClick={(e) => {
              e.stopPropagation();
              setEditing(c);
            }}
          >
            编辑
          </button>
        </span>
      </article>
    );
  };

  const renderRow = (c: LibraryCard) => (
    <div
      key={c.id}
      className="lib-rowline"
      onClick={() => setEditing(c)}
      onKeyDown={(e) => {
        if (e.key === "Enter") setEditing(c);
      }}
      tabIndex={0}
      role="button"
      data-testid="lib-row"
    >
      <div className="lib-r1">
        <LibraryAvatar card={c} />
        <span className="lib-nm">{render(c.name || "未命名")}</span>
        {c.aliases?.length > 0 && <span className="lib-alias">（别名 {c.aliases.join("、")}）</span>}
        <span className={`lib-pill ${PILL_CLS[c.role] || ""}`}>{c.role}</span>
        <span className="lib-tags">{c.kind && <span className="lib-tag">{c.kind}</span>}</span>
        <span className="lib-spacer" />
        <span className="lib-src">{c.src.novel_name || "手建"} · {SRC_LABEL[c.src.kind]}</span>
        <span className="lib-ga">
          {c.dossier?.gender || ""}
          {c.dossier?.age ? ` · ${c.dossier.age}` : ""}
        </span>
        <span className="lib-acts">
          <button
            className="lib-act use"
            onClick={(e) => {
              e.stopPropagation();
              setUsingCard(c);
            }}
          >
            用到新书
          </button>
          <button
            className="lib-act edit"
            onClick={(e) => {
              e.stopPropagation();
              setEditing(c);
            }}
          >
            编辑
          </button>
        </span>
      </div>
      <div className="lib-r2">
        {render(c.persona || "")}
        <span className="lib-spk">　——　语言特征：{c.dossier?.speech ? render(c.dossier.speech) : "没填"}</span>
      </div>
    </div>
  );

  return (
    <div className="lib-view" data-testid="char-instance-view">
      {/* 视图头部统计（原页头三枚随视图体走；新建角色入口同级） */}
      <div className="lib-view-head">
        <div className="lib-view-title">
          <b>人物档案</b>
          <span>· 拆书 / 书内 / 手建</span>
        </div>
        <div className="lib-stats" data-testid="lib-stats">
          <div className="lib-stat">
            <div className="lib-stat-n">{items.length}</div>
            <div className="lib-stat-t">角色</div>
          </div>
          <div className="lib-stat">
            <div className="lib-stat-n">{genres.length}</div>
            <div className="lib-stat-t">题材</div>
          </div>
          <div className="lib-stat">
            <div className="lib-stat-n">{bookTotal}</div>
            <div className="lib-stat-t">作品</div>
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)} data-testid="lib-new">
          新建角色
        </button>
      </div>

      {error && (
        <div className="notice" role="alert" style={{ marginBottom: 12 }}>
          <span className="nt">
            <b>加载失败</b>
            <span>{error}</span>
          </span>
          <button className="btn btn-secondary btn-sm" onClick={() => void refetch()}>
            重试
          </button>
        </div>
      )}

      <div className="lib-body">
        <div className="lib-rail">
          {railGroup(
            "题材",
            "genre",
            genres.map((g) => ({
              value: g,
              label: g,
              count: items.filter((c) => normGenre(c) === g).length,
            })),
            [{ value: GENRE_EMPTY, label: "未分题材", count: emptyGenreCount }],
          )}
          {railGroup(
            "定位",
            "role",
            ROLE_ORDER.map((r) => ({ value: r, label: r, count: items.filter((c) => c.role === r).length })),
          )}
          {railGroup(
            "来源",
            "src",
            ["deconstruct", "book", "manual"].map((k) => ({
              value: k,
              label: SRC_LABEL[k],
              count: items.filter((c) => c.src.kind === k).length,
            })),
          )}
          {railGroup(
            "小类",
            "kind",
            KIND_VALUES.map((k) => ({ value: k, label: k, count: items.filter((c) => c.kind === k).length })),
          )}
        </div>

        <div className="lib-main">
          <div className="lib-toolbar">
            <div className="lib-search">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                <circle cx="11" cy="11" r="7" />
                <path d="M20 20l-3.5-3.5" />
              </svg>
              <input
                value={filters.q}
                onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                placeholder="搜名字、别名、人设、语言特征、背景、来源书名，可多个词空格隔开"
                data-testid="lib-search"
              />
            </div>
            <div className="lib-sort">
              排序
              <select
                value={filters.sort}
                onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value as Filters["sort"] }))}
                data-testid="lib-sort"
              >
                <option value="default">最近收录</option>
                <option value="name">按姓名</option>
              </select>
            </div>
            <div className="lib-viewseg" data-testid="lib-viewseg">
              <button className={view === "card" ? "on" : ""} onClick={() => switchView("card")}>
                卡片
              </button>
              <button className={view === "list" ? "on" : ""} onClick={() => switchView("list")}>
                列表
              </button>
            </div>
          </div>

          <div className="lib-count-line">
            {isLoading ? "加载中…" : `共 ${visible.length} 位角色`}
          </div>

          {!isLoading && items.length === 0 ? (
            <div className="lib-empty">
              <b>柜子还空着</b>
              把书里的角色收进来，或者先手建一个——开新书时换个名字就能用。
              <div>
                <button className="btn btn-secondary btn-sm" onClick={() => navigate("/tools/deconstruct/new")}>
                  去拆书收角色
                </button>{" "}
                <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>
                  新建角色
                </button>
              </div>
            </div>
          ) : view === "card" ? (
            <div className="lib-cells">
              {visible.map((c, i) => renderCard(c, i))}
              {!isLoading && visible.length === 0 && (
                <div className="lib-empty" style={{ gridColumn: "1 / -1" }}>
                  <b>没有符合筛选的角色</b>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setFilters((f) => ({ ...EMPTY_FILTERS, sort: f.sort }))}
                  >
                    清空筛选
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="lib-rows-wrap">
              {visible.map(renderRow)}
              {!isLoading && visible.length === 0 && (
                <div className="lib-empty">
                  <b>没有符合筛选的角色</b>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setFilters((f) => ({ ...EMPTY_FILTERS, sort: f.sort }))}
                  >
                    清空筛选
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <CardEditorModal
        open={editing !== null || creating}
        card={editing}
        onClose={() => {
          setEditing(null);
          setCreating(false);
          void refresh();
        }}
      />
      <UseInNovelModal
        card={usingCard}
        onClose={() => setUsingCard(null)}
        onDone={() => toast.info("去那本书的角色页就能看到 TA 了")}
      />
    </div>
  );
}
