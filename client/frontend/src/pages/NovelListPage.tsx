import LegacyMigrateModal from '@/components/LegacyMigrateModal';
import { useLegacyDb } from '@/hooks/useLegacyDb';
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import AuthGuard from "@/components/auth/AuthGuard";
import DeleteConfirmModal from "@/components/novel/DeleteConfirmModal";
import CreateProjectModal from "@/components/novel/CreateProjectModal";
import ImportNovelModal from "@/components/novel/ImportNovelModal";
import RenameModal from "@/components/novel/RenameModal";
import FinishModal, { type FinishTarget } from "@/components/novel/FinishModal";
import { Ico, P, genreIconPath } from "@/components/icons";
import { PORTAL_URL } from "@/lib/portal";
import { supportUrl } from "@/lib/support";
import { useTier } from "@/hooks/useTier";
import { STAGE_LABEL, stageFromChapters, type NovelStage } from "@/lib/novelStage";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";
import { parseServerTime } from "@/lib/serverTime";
import {
  SHELF_PAGE_SIZE,
  defaultFilters,
  slicePage,
  visibleBooks,
  type ShelfFilters,
  type ShelfSortKey,
} from "@/lib/shelfSort";

interface Novel {
  id: string;
  name: string;
  slug: string;
  current_phase: string;
  total_volumes: number;
  total_chapters: number;
  /** 已归档章节数（list 接口以章表聚合覆盖下发，见 novels/router.py）——卡片阶段判据 */
  total_archives?: number;
  updated_at: string;
  /** 创建时间（排序键「创建时间」；老接口缺省时排序容错归 0，见 lib/shelfSort） */
  created_at?: string;
  /** 完结时间戳（works-finish-flow）：非空＝已完结；null/缺省＝按章派生 */
  finished_at?: string | null;
  /** 卡片富化字段（list 接口附加；缺失时优雅降级） */
  word_count?: number;
  synopsis?: string;
  genre?: string | null;
}

// 阶段标签 + 派生规则单源在 @/lib/novelStage（与「打开书的默认落点」同一模型）：
// 无章=设定、全归档未完结=待完本、完结=已完结、其余=写作（c-works-finish-flow 四态）。
// ready 徽标用旗形（原型 STAGE_ICON.ready）：待完本＝就差完本这个动作的可行动召唤。
const STAGE_DOT = {
  writing: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  setting: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  ready: '<path d="M6 4v16M6 5h11l-2 3 2 3H6"/>',
  done: '<path d="M5 13l4 4L19 7"/>',
} as const;

/** 相对时间（与原型文案口径：刚刚/N 分钟前/N 小时前/昨天/N 天前/超过一周落日期）。
    时间解析走 parseServerTime：后端下发无时区 ISO 串，按本地解析会偏 8 小时（存量 bug）。 */
function relTime(iso: string): string {
  const t = parseServerTime(iso);
  const ms = Date.now() - t.getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  if (h < 48) return "昨天";
  const d = Math.floor(h / 24);
  if (d < 8) return `${d} 天前`;
  return t.toLocaleDateString("zh-CN");
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

/** 卡片阶段派生（四态单源）：列表聚合章数 + finished_at（works-finish-flow）。 */
function stageOf(p: Novel) {
  return stageFromChapters(p.total_chapters || 0, p.total_archives || 0, p.finished_at ?? null);
}

const FILTER_CHIPS: { key: "all" | NovelStage; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "setting", label: STAGE_LABEL.setting },
  { key: "writing", label: STAGE_LABEL.writing },
  { key: "ready", label: STAGE_LABEL.ready },
  { key: "done", label: STAGE_LABEL.done },
];

const SORT_OPTIONS: { key: ShelfSortKey; label: string }[] = [
  { key: "recency", label: "最近更新" },
  { key: "created", label: "创建时间" },
  { key: "words", label: "字数" },
  { key: "title", label: "书名" },
];

export default function NovelListPage() {
  return (
    <AuthGuard>
      <NovelList />
    </AuthGuard>
  );
}

function NovelList() {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [portalUrl, setPortalUrl] = useState<string>('');
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Novel | null>(null);
  const [renameTarget, setRenameTarget] = useState<Novel | null>(null);
  const [showKeyHint, setShowKeyHint] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [finishTarget, setFinishTarget] = useState<Novel | null>(null);
  /** 检索与组织状态（c-works-toolbar）：单对象，任何变更原子重置分页（原型口径） */
  const [filters, setFilters] = useState<ShelfFilters>(defaultFilters);
  const [entDegraded, setEntDegraded] = useState(false);
  const [entDetail, setEntDetail] = useState('');
  const [supportLink, setSupportLink] = useState('');
  const navigate = useNavigate();
  // db-generation：旧库检测（免登端点；空书架开口行 + 向导）
  const legacyDb = useLegacyDb();
  const [legacyModal, setLegacyModal] = useState(false);
  const legacyAutoShown = useRef(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  // 套餐状态走 LicenseProvider 上下文（Provider 挂在认证路由根壳，两跳刷新后自动更新）
  const { tier, isMember, expired, trialRemainingDays: trialDays } = useTier();

  async function handleDelete() {
    /* v8 ignore start -- 防御分支：删除确认弹窗只在 deleteTarget 非空时渲染 */
    if (!deleteTarget) return;
    /* v8 ignore stop */
    const { id, name } = deleteTarget;
    try {
      await api.delete(`/novels/${id}`);
      setNovels((prev: Novel[]) => prev.filter((p) => p.id !== id));
      toast.success(`《${name}》已删除`);
      setDeleteTarget(null);
    } catch {
      toast.error("删除失败");
    }
  }

  async function handleRename(next: string) {
    /* v8 ignore start -- 防御分支：改名弹窗只在 renameTarget 非空时渲染 */
    if (!renameTarget) return;
    /* v8 ignore stop */
    try {
      const updated = await api.renameNovel(renameTarget.id, next);
      setNovels((prev: Novel[]) =>
        prev.map((p) => (p.id === updated.id ? { ...p, name: updated.name } : p)),
      );
      toast.success(`已更名为《${updated.name}》`);
      setRenameTarget(null);
    } catch {
      toast.error("改名失败");
    }
  }

  const fetchNovels = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const data = await api.get("/novels");
      setNovels(data);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNovels();
    api.post("/auth/verify").then((r: any) => {
      // 权益快照异常（c-s-entitlement-sync）：后端已按档位标准兜底，提示用户可求助
      if (r.entitlement_degraded !== undefined) setEntDegraded(r.entitlement_degraded);
      if (r.entitlement_degraded) {
        setEntDetail(JSON.stringify({
          reason: "entitlement_incomplete_snapshot",
          tier: r.tier ?? "",
          fetched_at: r.entitlement_fetched_at ?? "",
        }));
      }
    }).catch(() => {});
    // 检查 API Key 配置状态 + 取 S端 门户地址（续费/开通引导用）
    api.get("/auth/config").then((cfg: any) => {
      if (!cfg.has_api_key) setShowKeyHint(true);
      if (cfg.portal_url) setPortalUrl(cfg.portal_url);
    }).catch(() => {});
    supportUrl().then(setSupportLink).catch(() => {});
  }, [fetchNovels]);

  // 卡片 ⋯ 菜单：点外部收起
  useEffect(() => {
    if (!menuFor) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuFor(null);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuFor]);

  function handleCreated(novelId: string) {
    setShowCreate(false);
    navigate(`/novel/${novelId}`);
  }

  // 完本/撤完本后本地更新（响应带服务端时钟的 finished_at/updated_at），不整表重拉
  const handleFinished = useCallback(
    (u: { id: string; finished_at: string | null; updated_at: string }) => {
      setNovels((prev: Novel[]) =>
        prev.map((p) =>
          p.id === u.id ? { ...p, finished_at: u.finished_at, updated_at: u.updated_at } : p,
        ),
      );
    },
    [],
  );

  const handleReopened = useCallback(
    (u: { id: string; finished_at: string | null; updated_at: string }) => {
      setNovels((prev: Novel[]) =>
        prev.map((p) =>
          p.id === u.id ? { ...p, finished_at: u.finished_at, updated_at: u.updated_at } : p,
        ),
      );
    },
    [],
  );

  // 免费待遇 = 非有效会员（免费层或套餐过期），与后端 require_project_limit 口径一致
  const freeLimitReached = !isMember && novels.length >= 1;

  // 检索与组织：过滤（状态+书名）→ 状态 rank 恒优先排序 → 分页切片（纯函数单源 lib/shelfSort）
  const visible = useMemo(() => visibleBooks(novels, filters), [novels, filters]);
  const shownList = useMemo(() => slicePage(visible, filters.shown), [visible, filters.shown]);
  const filtered = filters.kind !== "all" || filters.q.trim() !== "";

  // 任何筛选/搜索/排序变更都原子重置分页（含重复点同一 chip——原型口径）
  const patchFilters = useCallback((p: Partial<ShelfFilters>) => {
    setFilters((f) => ({ ...f, shown: SHELF_PAGE_SIZE, ...p }));
  }, []);

  // 分页：加载更多按钮进入视口即自动加载（rootMargin 160px）；jsdom 无 IO 时按钮仍可用
  const visibleCountRef = useRef(0);
  visibleCountRef.current = visible.length;
  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((x) => x.isIntersecting)) {
          setFilters((f) =>
            f.shown >= visibleCountRef.current
              ? f
              : { ...f, shown: Math.min(f.shown + SHELF_PAGE_SIZE, visibleCountRef.current) },
          );
        }
      },
      { rootMargin: "160px" },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [filters.shown, visible.length]);

  const guideUpgrade = () =>
    window.open(portalUrl || PORTAL_URL, "_blank", "noopener,noreferrer");

  const createAction = () => (freeLimitReached ? guideUpgrade() : setShowCreate(true));

  const upgradeBtn = (label: string) =>
    portalUrl ? (
      <a href={portalUrl} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
        {label}
      </a>
    ) : (
      /* 定价区块已随静态首页改版删除：兜底直连 S端 门户常量 */
      <a href={PORTAL_URL} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
        {label}
      </a>
    );

  /** 回看：一次性落点覆盖（useWorkbench 认领后即清，刷新不重放） */
  const openPreview = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    navigate(`/novel/${id}`, { state: { landingView: "archives" } });
  };

  const renderCard = (p: Novel) => {
    const stage = stageOf(p);
    const words = p.word_count ?? 0;
    return (
      <div
        key={p.id}
        className="book-card"
        role="link"
        tabIndex={0}
        aria-label={`打开《${p.name}》`}
        data-od-id={`book-card-${p.id}`}
        onClick={() => navigate(`/novel/${p.id}`)}
        onKeyDown={(e) => {
          if (e.key === "Enter") navigate(`/novel/${p.id}`);
        }}
      >
        <div className="top">
          <span className="mono">{(p.name || "书")[0]}</span>
          {/* 题材胶囊：取值来自题材（后端单源下发 `genre`：大类 · 子类）；
              未完成题材设定时用「待定题材」占位——胶囊位恒在，不因题材缺失而空缺。
              title 供挤压时补齐被省略的全称 */}
          <span
            className={`genre${p.genre ? "" : " pending"}`}
            title={p.genre || GENRE_PENDING_LABEL}
          >
            <Ico d={genreIconPath(p.genre)} />
            {p.genre || GENRE_PENDING_LABEL}
          </span>
          <span className={`b ${stage}`}>
            <Ico d={STAGE_DOT[stage]} sw={2.4} />
            {STAGE_LABEL[stage]}
          </span>
          <button
            className="icon-btn card-menu-btn"
            aria-label="更多操作"
            onClick={(e) => {
              e.stopPropagation();
              setMenuFor(menuFor === p.id ? null : p.id);
            }}
          >
            <Ico d={P.dots} />
          </button>
        </div>
        <h3>《{p.name}》</h3>
        <p className="summary">{p.synopsis}</p>
        <div className="stats">
          <span>
            <b className="num">{p.total_volumes || 0} 卷</b>结构
          </span>
          <span>
            <b className="num">{p.total_chapters || 0} 章</b>章节
          </span>
          <span>
            <b className="num">{fmt(words)}</b>总字数
          </span>
        </div>
        {/* 分状态页脚（works.html v2）：待完本＝回看＋完本；已完结＝完结于＋回看＋查看 */}
        <div className="foot">
          {stage === "ready" ? (
            <>
              <span className="updated">全书 {p.total_chapters} 章已归档</span>
              <span className="foot-acts">
                <button className="btn btn-secondary btn-sm" onClick={(e) => openPreview(e, p.id)}>
                  回看
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  data-od-id={`finish-open-${p.id}`}
                  title="全书章节都已归档 · 完结这本书"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFinishTarget(p);
                  }}
                >
                  完本
                </button>
              </span>
            </>
          ) : stage === "done" ? (
            <>
              <span className="updated">完结于{relTime(p.finished_at || p.updated_at)}</span>
              <span className="foot-acts">
                <button className="btn btn-secondary btn-sm" onClick={(e) => openPreview(e, p.id)}>
                  回看
                </button>
                <span className="go">
                  查看
                  <Ico d={P.arrowRight} />
                </span>
              </span>
            </>
          ) : (
            <>
              <span className="updated">更新于 {relTime(p.updated_at)}</span>
              <span className="foot-acts">
                <span className="go">
                  继续创作
                  <Ico d={P.arrowRight} />
                </span>
              </span>
            </>
          )}
        </div>
        {menuFor === p.id && (
          <div ref={menuRef} className="card-menu" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => {
                setMenuFor(null);
                setRenameTarget(p);
              }}
            >
              <Ico d={P.pencil} />
              重命名
            </button>
            {stage === "done" && (
              <button
                onClick={() => {
                  setMenuFor(null);
                  setFinishTarget(p);
                }}
              >
                <Ico d={P.check} />
                完本信息 · 撤完本
              </button>
            )}
            <button
              className="danger"
              onClick={() => {
                setMenuFor(null);
                setDeleteTarget(p);
              }}
            >
              <Ico d={P.trash} />
              删除
            </button>
          </div>
        )}
      </div>
    );
  };

  const renderGrid = (items: { book: Novel }[], odId: string) => (
    <div className="cards" data-od-id={odId}>
      {items.map((it) => renderCard(it.book))}
      {freeLimitReached && (
        <div
          className="lock-tile"
          role="button"
          tabIndex={0}
          data-od-id="lock-tile"
          onClick={guideUpgrade}
          onKeyDown={(e) => {
            if (e.key === "Enter") guideUpgrade();
          }}
        >
          <span className="lt-ic">
            <Ico d={P.lock} />
          </span>
          <b>书架已满</b>
          <span>升级后不限作品数 · 现有作品不受影响</span>
          <span className="btn btn-secondary btn-sm">
            <Ico d={P.spark} />
            升级
          </span>
        </div>
      )}
    </div>
  );

  return (
    // pg-works：书架屏垂直节奏（works.html 口径，list.css 屏级作用域；ADJUSTMENTS 换代节 #12）
    <main className="main pg-works">
      {/* 权益快照异常（c-s-entitlement-sync）：后端已按档位标准兜底，可复制详情找客服 */}
      {entDegraded && (
        <div className="notice">
          <span className="nt">
            <b>权益信息同步异常，已按套餐标准处理</b>
            <span>若功能与套餐不符，可复制问题信息联系客服核对</span>
          </span>
          <span className="flex items-center gap-2">
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => navigator.clipboard?.writeText(entDetail).catch(() => {})}
            >
              复制问题信息
            </button>
            {supportLink && (
              <a className="btn btn-secondary btn-sm" href={supportLink} target="_blank" rel="noreferrer">
                联系客服
              </a>
            )}
          </span>
        </div>
      )}
      {/* 过期降级 Banner（2026-08-18 口径：过期降为免费待遇） */}
      {expired && tier !== 'none' && (
        <div className="notice">
          <span className="nt">
            <b>套餐已过期，已降为免费待遇</b>
            <span>AI 功能与多项目已暂停 · 免费待遇下可手工创作 1 本小说</span>
          </span>
          {upgradeBtn("续费恢复")}
        </div>
      )}
      {/* 试用中 Banner：提示剩余天数 + 到期影响，引导续费 */}
      {tier === 'trial' && !expired && (
        <div className="notice info">
          <span className="nt">
            <b>{trialDays > 0 ? `试用还剩 ${trialDays} 天` : '试用期进行中'}</b>
            <span>
              {trialDays > 0
                ? '试用内可免费用全部 AI 功能，到期后降为免费待遇（可手工创作 1 本小说）'
                : '可免费用全部 AI 功能，到期后降为免费待遇'}
            </span>
          </span>
          {upgradeBtn("开通 PRO")}
        </div>
      )}
      {/* 免费层 Banner：从未开通过套餐，引导试用 */}
      {tier === 'none' && (
        <div className="notice info">
          <span className="nt">
            <b>开通 7 天免费试用</b>
            <span>试用期内免费使用全部 AI 功能，到期自动降为免费待遇（可手工创作 1 本小说）</span>
          </span>
          {upgradeBtn("免费试用")}
        </div>
      )}
      {showKeyHint && (
        <div className="notice info">
          <span className="nt">
            还没配置 API Key，AI 功能不可用。
          </span>
          <Link to="/config" className="btn btn-secondary btn-sm">去配置</Link>
        </div>
      )}

      {/* 满额态：一句话说明 + 升级出口（正解口径：锁定可见，不隐藏入口） */}
      {!loading && !loadError && freeLimitReached && (
        <div className="notice info">
          <span className="nt">
            <b>
              免费版书架已满（<span className="num">{novels.length}/1</span>）
            </b>
            <span>升级后不限作品数，现有作品不受影响</span>
          </span>
          {upgradeBtn("升级")}
        </div>
      )}

      <div className="page-head">
        <div>
          <h1>我的作品</h1>
          <p className="sub">建书即写 · 设定与大纲是高级配置，随时可补</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary"
            onClick={() => (freeLimitReached ? guideUpgrade() : setShowImport(true))}
            title="导入已有稿子（.md / .txt / .docx）"
          >
            <Ico d={P.upload} />
            导入
          </button>
          {/* 锁定可见：满额时主按钮带锁仍可点，点击引导升级 */}
          <button className="btn btn-primary" onClick={createAction}>
            {freeLimitReached ? <Ico d={P.lock} /> : <Ico d={P.plus} />}
            新建作品
          </button>
        </div>
      </div>

      {/* 页头工具栏（c-works-toolbar）：有书态渲染；零书/加载/失败不渲染（登记偏差） */}
      {!loading && !loadError && novels.length > 0 && (
        <div className="bk-toolbar" data-od-id="works-toolbar">
          <label className="bk-search" data-od-id="works-search">
            <Ico d={P.search} />
            <input
              type="search"
              placeholder="搜索书名"
              autoComplete="off"
              spellCheck={false}
              aria-label="搜索书名"
              value={filters.q}
              onChange={(e) => patchFilters({ q: e.target.value })}
            />
          </label>
          <div className="bk-chips" role="group" aria-label="按状态筛选">
            {FILTER_CHIPS.map((c) => (
              <button
                key={c.key}
                className={`chip${filters.kind === c.key ? " on" : ""}`}
                aria-pressed={filters.kind === c.key}
                data-od-id={`filter-${c.key}`}
                onClick={() => patchFilters({ kind: c.key })}
              >
                {c.label}
              </button>
            ))}
          </div>
          <select
            className="bk-sort"
            data-od-id="works-sort"
            aria-label="排序方式"
            value={filters.sort}
            onChange={(e) => patchFilters({ sort: e.target.value as ShelfSortKey })}
          >
            {SORT_OPTIONS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {loadError ? (
        <div className="empty">
          <div className="serif">作品加载失败</div>
          <p>请检查网络后重试</p>
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-secondary" onClick={() => void fetchNovels()}>
              重新加载
            </button>
          </div>
        </div>
      ) : loading ? (
        <div className="cards">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card-skeleton">
              <div className="sk bar w40" />
              <div className="sk bar w90" />
              <div className="sk bar w70" />
            </div>
          ))}
        </div>
      ) : novels.length === 0 ? (
        /* 首启态：三步引导空态（.empty 家族内长出；原型 list.html 同源）
           ——零书不采用 v2 简空态（用户裁定 2026-09-20，ADJUSTMENTS 换代 v2 章 #2） */
        <div className="first-run">
          <div className="empty" style={{ padding: "56px 44px 48px" }}>
            <span className="fr-title serif">开始你的第一本书</span>
            <p>本地优先的 AI 长篇小说工作台——大纲、设定、正文，都保存在你这台电脑上。</p>
            {legacyDb.status?.candidates?.length ? (
              <p className="fr-note">
                这台电脑上有旧版作品 ·{' '}
                <button className="text-btn" onClick={() => setLegacyModal(true)}>找回我的书</button>
              </p>
            ) : null}
            <div className="fr-steps">
              <div className="step">
                <span className="fr-n">STEP 01</span>
                <span className="fr-ic">
                  <Ico d={P.plus} />
                </span>
                <b>新建作品</b>
                <p>起书名、选题材，30 秒建好全书骨架。</p>
              </div>
              <div className="step">
                <span className="fr-n">STEP 02</span>
                <span className="fr-ic">
                  <Ico d={P.doc} />
                </span>
                <b>配置模型</b>
                <p>填入你自己的 API Key，只存本机，不经过第三方。</p>
              </div>
              <div className="step">
                <span className="fr-n">STEP 03</span>
                <span className="fr-ic">
                  <Ico d={P.pencil} />
                </span>
                <b>开写第一章</b>
                <p>第一句想到什么就写什么，正文永远是最短路径。</p>
              </div>
            </div>
            <div className="fr-cta">
              <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
                <Ico d={P.plus} />
                新建作品
              </button>
              <button className="btn btn-secondary" onClick={() => setShowImport(true)}>
                <Ico d={P.upload} />
                导入已有文稿
              </button>
            </div>
            <p className="fr-note">
              免费版可创建 <span className="num">1</span> 部作品 · 无需绑卡
            </p>
          </div>
          <LegacyMigrateModal
            open={legacyModal}
            candidates={legacyDb.status?.candidates ?? []}
            onClose={() => setLegacyModal(false)}
            onDone={() => void legacyDb.refresh()}
          />
        </div>
      ) : (
        /* 检索无果：bk-empty（不放进 .cards 网格避免 1/3 列宽）；其余走列表/分组 */
        <div className="bk-list">
          {visible.length === 0 ? (
            <div className="bk-empty" data-od-id="empty-state">
              <span className="em">没有找到符合条件的作品</span>
              <p className="es">换个关键词或状态再试试。</p>
              <div className="acts">
                <button
                  className="btn btn-secondary"
                  data-od-id="empty-clear"
                  onClick={() => setFilters(defaultFilters())}
                >
                  清除筛选
                </button>
                <button className="btn btn-primary" data-od-id="empty-create" onClick={createAction}>
                  新建作品
                </button>
              </div>
            </div>
          ) : filters.kind === "all" ? (
            renderGrid(shownList, "cards-all")
          ) : (
            <div className="bk-group" data-od-id={`group-${filters.kind}`}>
              <div className="bk-group-head">
                <span className="gh-label">
                  <span className={`dot ${filters.kind}`} />
                  {STAGE_LABEL[filters.kind]}
                </span>
                <span className="gh-count">
                  {visible.length} 本{filters.kind === "ready" ? " · 主线已收齐" : ""}
                </span>
                {filters.kind === "ready" && (
                  <div className="gh-acts">
                    <button
                      className="btn btn-primary btn-sm"
                      data-od-id="group-finish"
                      onClick={() => setFinishTarget(visible[0].book)}
                    >
                      去完本
                    </button>
                  </div>
                )}
              </div>
              {renderGrid(shownList, `group-cards-${filters.kind}`)}
            </div>
          )}
          {visible.length > filters.shown && (
            <div className="load-more" ref={loadMoreRef}>
              <button
                className="btn btn-secondary"
                data-od-id="load-more"
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    shown: Math.min(f.shown + SHELF_PAGE_SIZE, visible.length),
                  }))
                }
              >
                显示更多 · <b className="num">{filters.shown} / {visible.length}</b>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Create Project Modal */}
      <CreateProjectModal
        open={showCreate}
        onClose={() => { setShowCreate(false); }}
        onCreated={handleCreated}
        isMember={isMember}
        novelCount={novels.length}
      />

      {/* Import Novel Modal */}
      <ImportNovelModal
        open={showImport}
        onClose={() => setShowImport(false)}
        onImported={handleCreated}
      />

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <DeleteConfirmModal
          title="小说"
          confirmText={deleteTarget.name}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Rename modal */}
      {renameTarget && (
        <RenameModal
          name={renameTarget.name}
          onConfirm={handleRename}
          onCancel={() => setRenameTarget(null)}
        />
      )}

      {/* 完本清单弹窗（works-finish-flow）：待完本态三行检查；已完结态撤完本 */}
      {finishTarget && (
        <FinishModal
          target={finishTarget}
          onClose={() => setFinishTarget(null)}
          onFinished={handleFinished}
          onReopened={handleReopened}
        />
      )}
    </main>
  );
}
