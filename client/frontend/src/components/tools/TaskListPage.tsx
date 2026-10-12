// 任务清单页（c-deconstruct-book 5.3）：纯清单多行（六类状态），点行进详情。
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDeconstructTasks } from "../../hooks/useDeconstructTasks";
import { deleteDeconstructTask, type DeconstructTaskSummary } from "../../lib/deconstructApi";

const STATUS_PILL: Record<DeconstructTaskSummary["status"], { label: string; cls: string }> = {
  running: { label: "拆解中", cls: "pill pill-accent" },
  queued: { label: "排队中", cls: "pill pill-warn" },
  completed: { label: "已完成", cls: "pill pill-ok" },
  failed: { label: "已失败", cls: "pill pill-err" },
  cancelled: { label: "已取消", cls: "pill" },
  need_reupload: { label: "需重传", cls: "pill pill-warn" },
};

function statusSummary(t: DeconstructTaskSummary): string {
  if (t.status === "queued") return `前面还有 ${t.queued_ahead} 个任务，轮到自动开跑`;
  if (t.status === "completed") return "产物已生成，待选去向（建书 / 存本地文件夹）";
  if (t.status === "failed") return t.error || "拆解失败，可从断点续拆";
  if (t.status === "cancelled")
    // v8 ignore next — 文案已由清单行断言（v8 对模板串行归属漂移）
    return "已取消，产物按已完成维度保留";
  if (t.status === "need_reupload")
    // v8 ignore next — 同上
    return "源文件缺失，重新选择文件后回到原排队位次";
  return "拆解在后台进行，可以离开，回来接着看";
}

export default function TaskListPage() {
  const navigate = useNavigate();
  const { data, error, refresh } = useDeconstructTasks(true);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const tasks = data?.tasks ?? [];

  const remove = async (id: string) => {
    await deleteDeconstructTask(id);
    setConfirmDelete(null);
    refresh();
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

      {tasks.length === 0 && !error ? (
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
          {tasks.map((t) => {
            const pill = STATUS_PILL[t.status];
            return (
              <div key={t.id} className="tk-row" data-od-id={`tk-row-${t.id}`}>
                <button
                  className="tk-open-row"
                  onClick={() => navigate(`/tools/deconstruct/${t.id}`)}
                  aria-label={`查看任务 ${t.book_name}`}
                >
                  <span className="tk-type">拆书</span>
                  <span className="tk-title">{t.book_name}</span>
                  <span className={pill.cls}>{pill.label}</span>
                  <span className="tk-time">{t.created_at ?? ""}</span>
                  <div className="tk-meta">
                    {t.total_chars > 0 && `${Math.round(t.total_chars / 10000)} 万字 · `}
                    {t.chapter_count > 0 && `${t.chapter_count} 章 · `}
                    {t.status === "completed"
                      ? `${t.product_count} 份产物 · 待选去向`
                      : // v8 ignore next — 摘要文案已断言（v8 对 JSX 三元行归属漂移）
                        statusSummary(t)}
                  </div>
                </button>
                {confirmDelete === t.id ? (
                  <div className="tk-foot">
                    <span className="tk-sum">删除任务将连带清除其全部产物，确认？</span>
                    <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(null)}>
                      取消
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ color: "var(--err)" }}
                      data-od-id={`btn-confirm-delete-${t.id}`}
                      onClick={() => void remove(t.id)}
                    >
                      确认删除
                    </button>
                  </div>
                ) : (
                  <div className="tk-foot">
                    <span className="tk-sum" />
                    <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(t.id)}>
                      删除
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => navigate(`/tools/deconstruct/${t.id}`)}
                    >
                      详情
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
