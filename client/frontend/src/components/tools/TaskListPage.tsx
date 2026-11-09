// 任务清单页（c-deconstruct-book 5.3）：纯清单多行（六类状态），点行进详情。
// c-tools-badge-seen：进清单＝看过，已完成未取任务当场消账（顶栏徽标不再引导这批）。
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDeconstructTasks } from "../../hooks/useDeconstructTasks";
import { markTasksSeen } from "../../lib/toolsBadgeSeen";
import { parseServerTime } from "../../lib/serverTime";
import { deleteDeconstructTask, type DeconstructTaskSummary } from "../../lib/deconstructApi";
import { useRefineTasks } from "../../hooks/useRefineTasks";
import { kbApi, type RefineTaskRow } from "../../lib/kbApi";

const STATUS_PILL: Record<DeconstructTaskSummary["status"], { label: string; cls: string }> = {
  running: { label: "拆解中", cls: "pill pill-accent" },
  queued: { label: "排队中", cls: "pill pill-warn" },
  completed: { label: "已完成", cls: "pill pill-ok" },
  failed: { label: "已失败", cls: "pill pill-err" },
  cancelled: { label: "已取消", cls: "pill" },
  need_reupload: { label: "需重传", cls: "pill pill-warn" },
  importing: { label: "建书中", cls: "pill pill-accent" },
  imported: { label: "已建书", cls: "pill pill-ok" },
  import_failed: { label: "建书失败", cls: "pill pill-err" },
};

/** 未知状态兜底：旧版本/脏数据不得把整页打成白屏（`pill.cls` 直接取会 TypeError） */
function pillOf(status: string): { label: string; cls: string } {
  return STATUS_PILL[status as DeconstructTaskSummary["status"]] ?? { label: status, cls: "pill" };
}

function statusSummary(t: DeconstructTaskSummary): string {
  /* v8 ignore start — 三态摘要由清单用例逐条断言（v8 对模板串行归属漂移） */
  if (t.status === "importing") return "正在建书，可以离开；建完会出现在书架";
  if (t.status === "imported") return "已建书 · 详情里可打开这本书，产物也能继续导出";
  if (t.status === "import_failed") {
    const err = t.import?.error;
    return err?.retryable === false
      ? err.message || "建书失败，需要先处理原因"
      : `${err?.message || "建书失败"} · 可重试`;
  }
  /* v8 ignore stop */
  /* v8 ignore start — 六类摘要文案已由清单用例逐条断言（v8 对模板串行归属漂移） */
  if (t.status === "queued") return `前面还有 ${t.queued_ahead} 个任务，轮到自动开跑`;
  if (t.status === "completed") return "产物已生成，待选去向（建书 / 存本地文件夹）";
  if (t.status === "failed") return t.error || "拆解失败，可从断点续拆";
  if (t.status === "cancelled") return "已取消，产物按已完成维度保留";
  if (t.status === "need_reupload") return "源文件缺失，重新选择文件后回到原排队位次";
  return "拆解在后台进行，可以离开，回来接着看";
  /* v8 ignore stop */
}

/** 创建时间展示：MM-DD HH:mm（ISO 原串太工程师向）；空值留白。
 *  服务端下发无时区 UTC 串——按本地解析会偏时区（serverTime 单源，c-deconstruct-resilience）。 */
function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = parseServerTime(iso);
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function TaskListPage() {
  const navigate = useNavigate();
  const { data, error, refresh } = useDeconstructTasks(true);
  const refine = useRefineTasks();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [removeErr, setRemoveErr] = useState("");

  const tasks = data?.tasks ?? [];
  const refineTasks = refine.data?.tasks ?? [];

  // 合流排序：拆书任务与知识提炼任务同清单，按创建时间新→旧
  const merged: Array<{ kind: "拆书" | "知识提炼"; key: string; at: number; decon?: DeconstructTaskSummary; refine?: RefineTaskRow }> = [
    ...tasks.map((t) => ({ kind: "拆书" as const, key: t.id, at: parseServerTime(t.created_at || "").getTime(), decon: t })),
    ...refineTasks.map((t) => ({ kind: "知识提炼" as const, key: t.id, at: parseServerTime((t.created_at || "").replace(" ", "T")).getTime(), refine: t })),
  ].sort((a, b) => b.at - a.at);

  // 进清单＝看过：已完成未取任务当场消账（顶栏徽标不再引导这批；新任务完成＝新 id 会重亮）
  // 知识提炼任务同口径（评审 P2：只标拆书 id 时提炼徽标永久亮）
  const unpickedKey = [
    ...tasks.filter((t) => t.unpicked).map((t) => t.id),
    ...refineTasks.filter((t) => t.status === "completed" || t.status === "failed").map((t) => t.id),
  ].join("|");
  useEffect(() => {
    if (unpickedKey) markTasksSeen(unpickedKey.split("|"));
  }, [unpickedKey]);

  const remove = async (id: string) => {
    try {
      await deleteDeconstructTask(id);
      setConfirmDelete(null);
      refresh();
    } catch (e) {
      setRemoveErr(e instanceof Error ? e.message : "删除失败");
      setConfirmDelete(null);
    }
  };

  return (
    <main className="main" data-od-id="tools-list">
      <div className="page-head">
        <div>
          <h1>任务清单</h1>
          <p className="sub">写作工具跑的任务都在这里——点一行看详情，一次只跑一个，其余排队</p>
        </div>
        <Link className="btn btn-primary" to="/tools/deconstruct/new" data-od-id="btn-create-task">
          创建任务
        </Link>
      </div>

      {error && (
        <div className="notice" role="alert">
          <span className="nt">
            <b>加载失败</b>
            <span>{error}</span>
          </span>
          <button className="btn btn-secondary btn-sm" onClick={refresh}>
            重试
          </button>
        </div>
      )}

      {removeErr && (
        <div className="notice" role="alert">
          <span className="nt">
            <b>删除失败</b>
            <span>{removeErr}</span>
          </span>
        </div>
      )}

      {merged.length === 0 && !error ? (
        <div className="tk-empty" data-od-id="tk-empty">
          <p className="serif">还没有任务</p>
          <p>从「写作工具 → 拆书」把一本小说拆成 10 份设定与技法材料，</p>
          <p>任务在后台跑，完成后回这里取结果。</p>
          <Link className="btn btn-primary" to="/tools/deconstruct/new">
            创建拆书任务
          </Link>
        </div>
      ) : (
        <div className="tk-list" data-od-id="tk-list">
          {merged.map((m) =>
            m.kind === "拆书" && m.decon ? (
              <DeconRow key={m.key} t={m.decon} onNavigate={navigate} confirmDelete={confirmDelete} setConfirmDelete={setConfirmDelete} remove={remove} />
            ) : m.refine ? (
              <RefineRow key={m.key} t={m.refine} onNavigate={navigate} onDeleted={refine.refresh} />
            ) : null,
          )}
        </div>
      )}
    </main>
  );
}


/** 拆书任务行（原渲染体抽出，合流清单共用） */
function DeconRow({ t, onNavigate, confirmDelete, setConfirmDelete, remove }: {
  t: DeconstructTaskSummary;
  onNavigate: (to: string) => void;
  confirmDelete: string | null;
  setConfirmDelete: (id: string | null) => void;
  remove: (id: string) => void;
}) {
  const pill = pillOf(t.status);
  return (
    <div className="tk-row" data-od-id={`tk-row-${t.id}`}>
      <button className="tk-open-row" onClick={() => onNavigate(`/tools/deconstruct/${t.id}`)} aria-label={`查看任务 ${t.book_name}`}>
        <span className="tk-time">{fmtTime(t.created_at)}</span>
        <span className="tk-type">拆书</span>
        <span className="tk-title">{t.book_name}</span>
        <span className={pill.cls}>{pill.label}</span>
        <div className="tk-meta">
          {/* v8 ignore start — 摘要文案已由六类用例断言（v8 对 JSX 三元行归属漂移） */}
          {t.total_chars > 0 && `${Math.round(t.total_chars / 10000)} 万字 · `}
          {t.chapter_count > 0 && `${t.chapter_count} 章 · `}
          {t.status === "completed"
            ? `${t.product_count} 份产物 · 待选去向`
            : statusSummary(t)}
          {/* v8 ignore stop */}
        </div>
      </button>
      {confirmDelete === t.id ? (
        <div className="tk-foot">
          <span className="tk-sum">删除任务将连带清除其全部产物，确认？</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(null)}>取消</button>
          <button
            className="btn btn-secondary btn-sm"
            style={{ color: "var(--err)" }}
            data-od-id={`btn-confirm-delete-${t.id}`}
            onClick={() => remove(t.id)}
          >
            确认删除
          </button>
        </div>
      ) : (
        <div className="tk-foot">
          <span className="tk-sum" />
          <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(t.id)}>删除</button>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate(`/tools/deconstruct/${t.id}`)}>详情</button>
        </div>
      )}
    </div>
  );
}

/** 知识提炼任务行（原型定稿 2026-11-08：类型章「知识提炼」，详情进 /tools/refine/:id） */
function refinePill(status: RefineTaskRow["status"]): { label: string; cls: string } {
  if (status === "running") return { label: "提炼中", cls: "pill pill-accent" };
  if (status === "queued") return { label: "排队中", cls: "pill pill-warn" };
  if (status === "completed") return { label: "已完成", cls: "pill pill-ok" };
  if (status === "cancelled") return { label: "已取消", cls: "pill" };
  return { label: "已失败", cls: "pill pill-err" };
}

function refineSummary(t: RefineTaskRow): string {
  if (t.status === "queued") return "排队等待，轮到自动开跑";
  if (t.status === "running") return t.current_step || "提炼在后台进行，可以离开，回来接着看";
  if (t.status === "failed") return t.error || "提炼失败，材料原样留在「其他」";
  if (t.status === "cancelled") return "已取消——已归位的批保留，剩余材料留守「其他」";
  const r = t.result;
  if (!r) return "已完成";
  return `归位 ${r.moved} 条 · 新知识点 ${r.nodes_created} 个 · 新关系 ${r.relations} 条 · 留守 ${r.kept} 条`;
}

function RefineRow({ t, onNavigate, onDeleted }: { t: RefineTaskRow; onNavigate: (to: string) => void; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [delErr, setDelErr] = useState("");
  const pill = refinePill(t.status);
  const remove = async () => {
    try {
      await kbApi.refineTasks.delete(t.id);
      onDeleted();
    } catch (e) {
      setDelErr(e instanceof Error ? e.message : "删除失败");
    }
    setConfirming(false);
  };
  return (
    <div className="tk-row" data-testid={`tk-refine-row-${t.id}`}>
      <button className="tk-open-row" onClick={() => onNavigate(`/tools/refine/${t.id}`)} aria-label="查看知识提炼任务">
        <span className="tk-time">{fmtTime(t.created_at)}</span>
        <span className="tk-type">知识提炼</span>
        <span className="tk-title">{t.genre}知识库</span>
        <span className={pill.cls}>{pill.label}</span>
        <div className="tk-meta">{refineSummary(t)}</div>
      </button>
      {delErr && <div className="tk-meta" style={{ color: "var(--err)" }}>{delErr}</div>}
      {confirming ? (
        <div className="tk-foot">
          <span className="tk-sum">删除这条任务记录？原始材料不受影响。</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setConfirming(false)}>取消</button>
          <button className="btn btn-secondary btn-sm" style={{ color: "var(--err)" }} onClick={() => void remove()}>确认删除</button>
        </div>
      ) : (
        <div className="tk-foot">
          <span className="tk-sum" />
          <button className="btn btn-ghost btn-sm" onClick={() => setConfirming(true)}>删除</button>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate(`/tools/refine/${t.id}`)}>详情</button>
        </div>
      )}
    </div>
  );
}
