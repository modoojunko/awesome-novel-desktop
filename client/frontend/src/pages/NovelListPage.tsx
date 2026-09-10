import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import AuthGuard from "@/components/auth/AuthGuard";
import DeleteConfirmModal from "@/components/novel/DeleteConfirmModal";
import CreateProjectModal from "@/components/novel/CreateProjectModal";
import ImportNovelModal from "@/components/novel/ImportNovelModal";
import RenameModal from "@/components/novel/RenameModal";
import { Ico, P, genreIconPath } from "@/components/icons";
import { PORTAL_URL } from "@/lib/portal";
import { supportUrl } from "@/lib/support";
import { useTier } from "@/hooks/useTier";
import { STAGE_LABEL, stageFromChapters } from "@/lib/novelStage";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";

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
  /** 卡片富化字段（list 接口附加；缺失时优雅降级） */
  word_count?: number;
  synopsis?: string;
  genre?: string | null;
}

// 阶段标签 + 派生规则单源在 @/lib/novelStage（与「打开书的默认落点」同一模型）：
// 无章=设定、全归档=已归档、其余=写作。原先按 current_phase 派生，会把
// 「归档过几章但整本未完」的书显示成已归档，与落点（写作）自相矛盾。
const STAGE_DOT = {
  writing: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  setting: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  done: '<path d="M5 13l4 4L19 7"/>',
} as const;

/** 相对时间（与原型文案口径：刚刚/N 分钟前/N 小时前/昨天/N 天前/超过一周落日期） */
function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  if (h < 48) return "昨天";
  const d = Math.floor(h / 24);
  if (d < 8) return `${d} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

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
  const [entDegraded, setEntDegraded] = useState(false);
  const [entDetail, setEntDetail] = useState('');
  const [supportLink, setSupportLink] = useState('');
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement>(null);
  // 套餐状态走 LicenseProvider 上下文（Provider 挂在认证路由根壳，两跳刷新后自动更新）
  const { tier, isMember, expired, trialRemainingDays: trialDays } = useTier();

  async function handleDelete() {
    if (!deleteTarget) return;
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
    if (!renameTarget) return;
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

  // 免费待遇 = 非有效会员（免费层或套餐过期），与后端 require_project_limit 口径一致
  const freeLimitReached = !isMember && novels.length >= 1;

  // 书架即「继续」入口：按修改时间倒排，最近有进展的排前面（2026-08-29 用户裁定，
  // 取代原「继续创作条」方案——每张卡片自携继续创作状态，无需顶部重复入口）
  const sortedNovels = useMemo(
    () => [...novels].sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at)),
    [novels],
  );

  const guideUpgrade = () =>
    window.open(portalUrl || PORTAL_URL, "_blank", "noopener,noreferrer");

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

  return (
    <main className="main">
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
          <button
            className="btn btn-primary"
            onClick={() => (freeLimitReached ? guideUpgrade() : setShowCreate(true))}
          >
            {freeLimitReached ? <Ico d={P.lock} /> : <Ico d={P.plus} />}
            新建作品
          </button>
        </div>
      </div>

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
        /* 首启态：三步引导空态（.empty 家族内长出；原型 list.html 同源） */
        <div className="first-run">
          <div className="empty" style={{ padding: "56px 44px 48px" }}>
            <span className="fr-title serif">开始你的第一本书</span>
            <p>本地优先的 AI 长篇小说工作台——大纲、设定、正文，都保存在你这台电脑上。</p>
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
        </div>
      ) : (
        <div className="cards">
          {sortedNovels.map((p) => {
            const stage = stageFromChapters(
              p.total_chapters || 0,
              p.total_archives || 0,
            );
            const words = p.word_count ?? 0;
            return (
              <div
                key={p.id}
                className="book-card"
                role="link"
                tabIndex={0}
                aria-label={`打开《${p.name}》`}
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
                <p className="summary">{p.synopsis || ""}</p>
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
                <div className="foot">
                  <span className="updated">更新于 {relTime(p.updated_at)}</span>
                  <span className="go">
                    {stage === "done" ? "查看" : "继续创作"}
                    <Ico d={P.arrowRight} />
                  </span>
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
          })}
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
    </main>
  );
}
