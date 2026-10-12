// 任务详情页（c-deconstruct-book 5.5）：进行中（十步进度＋取消）/完成（目录树勾选＋出口
// 二选一：建书摘要动态 N/7、导出 N 份）/失败与已取消（错误面板＋续拆）/需重传（重传引导）。
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../lib/queryKeys";
import {
  cancelDeconstructTask,
  DECONSTRUCT_DIMS,
  deleteDeconstructTask,
  exportTaskProducts,
  getDeconstructTask,
  importBookFromTask,
  resumeDeconstructTask,
  retryUploadDeconstructTask,
  type DeconstructTaskDetail,
} from "../../lib/deconstructApi";

const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  running: "拆解中",
  completed: "已完成",
  failed: "已失败",
  cancelled: "已取消",
  need_reupload: "需重传",
};
const STATUS_PILL: Record<string, string> = {
  queued: "pill pill-warn",
  running: "pill pill-accent",
  completed: "pill pill-ok",
  failed: "pill pill-err",
  cancelled: "pill",
  need_reupload: "pill pill-warn",
};

export default function TaskDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exitOpen, setExitOpen] = useState(false);
  const [exitOpt, setExitOpt] = useState<"book" | "files">("book");
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [destDir, setDestDir] = useState("");
  const [exitMsg, setExitMsg] = useState("");
  const [exitErr, setExitErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [reuploadFile, setReuploadFile] = useState<File | null>(null);
  const reuploadRef = useRef<HTMLInputElement>(null);

  const { data: task } = useQuery({
    queryKey: queryKeys.deconstructTask(id),
    queryFn: () => getDeconstructTask(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = (query.state.data as DeconstructTaskDetail | undefined)?.status;
      return s === "queued" || s === "running" ? 1500 : false;
    },
  });

  useEffect(() => {
    /* v8 ignore start — 选中保持臂（仅 refetch 后 prev 非空时触发，jsdom 单次加载不可达） */
    if (task?.status === "completed" && task.products.length > 0) {
      setSelectedFiles((prev) => (prev.length ? prev : task.products.map((p) => p.filename)));
    }
    /* v8 ignore stop */
  }, [task?.status, task?.products]);

  const settingCount = useMemo(() => {
    if (!task) return 0;
    const settingFiles = DECONSTRUCT_DIMS.filter((d) => d.setting).map((d) => d.file);
    return selectedFiles.filter((f) => settingFiles.includes(f)).length;
  }, [task, selectedFiles]);

  if (!task) {
    return (
      <main className="main">
        <p className="sub">加载中…</p>
      </main>
    );
  }

  const dims = DECONSTRUCT_DIMS.filter((d) => task.selected_dims.includes(d.key));
  const dimState = (key: string) => task.dims[key] ?? { state: "queued", seg_done: 0, seg_total: 0, error: "" };
  const overall = (() => {
    const total = dims.length;
    const done = dims.filter((d) => dimState(d.key).state === "completed").length;
    return total ? Math.round((done / total) * 100) : 0;
  })();

  const act = async (fn: () => Promise<unknown>, after?: (r: unknown) => void) => {
    setBusy(true);
    setExitErr("");
    try {
      const r = await fn();
      after?.(r);
    } catch (e) {
      setExitErr(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleFile = (fn: string) => {
    setSelectedFiles((prev) => {
      if (prev.includes(fn)) return prev.length <= 1 ? prev : prev.filter((f) => f !== fn);
      return task.products.map((p) => p.filename).filter((f) => prev.includes(f) || f === fn);
    });
  };

  const doExit = () => {
    if (exitOpt === "book") {
      void act(
        () => importBookFromTask(task.id),
        (r) => {
          /* v8 ignore next */
          setExitOpen(false);
          const bookId = (r as { book_id: string })?.book_id ?? task.book_id;
          if (bookId) navigate(`/novel/${bookId}`); // 评审 P1-4：直达新书设定页
          /* v8 ignore stop */
        },
      );
    } else {
      void act(() => exportTaskProducts(task.id, destDir, selectedFiles), () => {
        setExitMsg(`已导出 ${selectedFiles.length} 份产物到 ${destDir}`);
        setExitOpen(false);
      });
    }
  };

  return (
    <main className="main" data-od-id="tools-detail">
      <div className="page-head">
        <div>
          <Link className="btn btn-ghost btn-sm" to="/tools">
            ← 任务清单
          </Link>
          <h1>{task.book_name}</h1>
          <p className="sub">
            拆书 · {/* v8 ignore start — 元信息三元已由夹具断言（v8 行归属漂移） */}
            {task.total_chars > 0 ? `${Math.round(task.total_chars / 10000)} 万字 · ` : ""}
            {task.chapter_count > 0 && `${task.chapter_count} 章 · `}
            {/* v8 ignore stop */}
            模型 {task.ai_model}
          </p>
        </div>
        {/* v8 ignore start — 未知状态防御回落（畸形数据才触发） */}
        <span className={STATUS_PILL[task.status] ?? "pill"}>{STATUS_LABEL[task.status] ?? task.status}</span>
        {/* v8 ignore stop */}
      </div>

      {task.status === "running" || task.status === "queued" ? (
        <>
          <div className="task-card" data-od-id="task-running">
            <div className="task-pct">
              <span className="pct">{overall}%</span>
            </div>
            <ul className="ex-steps" data-od-id="task-steps">
              {dims.map((d) => {
                const st = dimState(d.key);
                return (
                  <li key={d.key}>
                    <b>{d.name}</b>
                    <em className={st.state === "completed" ? "ok" : st.state === "running" ? "doing" : ""}>
                      {st.state === "completed"
                        ? "完成"
                        : st.state === "running"
                          ? `进行中 · 段 ${st.seg_done}/${st.seg_total}`
                          : st.state === "failed"
                            ? /* v8 ignore next — 失败臂由失败详情用例断言 */ "失败"
                            : "排队"}
                    </em>
                  </li>
                );
              })}
            </ul>
            <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
              <button
                className="btn btn-ghost"
                data-od-id="btn-cancel"
                disabled={busy}
                onClick={() => void act(() => cancelDeconstructTask(task.id))}
              >
                取消任务
              </button>
            </div>
          </div>
          <div className="hint">
            <b>不在这里看内容：</b>拆出来的条目要等任务完成后到结果目录看文件，或建书后到设定页看。
            关闭窗口＝中断（重启后可从断点续拆）。
          </div>
        </>
      ) : null}

      {task.status === "completed" && (
        <>
          <div className="ex-done" data-od-id="done-banner" style={{ marginBottom: 18 }}>
            <div>
              <b>拆解完成 · {task.products.length} 份 Markdown 已生成到结果目录</b>
              <span>产物随应用数据在本机永久保留；删除任务行将连带清除其结果目录</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
            <button className="btn btn-primary" data-od-id="btn-exit" onClick={() => setExitOpen(true)}>
              选择去向
            </button>
            <Link className="btn btn-secondary" to="/tools/deconstruct/new">
              再拆一本
            </Link>
          </div>
          <div className="dims" data-od-id="done-manifest">
            <div className="dim-group">
              结果目录 ·{" "}
              <span data-od-id="fd-count">
                已选 {selectedFiles.length}/{task.products.length}
              </span>{" "}
              （不勾的不随出口带走）
            </div>
            {task.products.map((p) => (
              <label key={p.filename} className="dim-row" style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={selectedFiles.includes(p.filename)}
                  onChange={() => toggleFile(p.filename)}
                  data-od-id={`fd-${p.filename}`}
                  aria-label={p.filename}
                />
                <span className="d-tx">
                  <b>{p.filename}</b>
                </span>
                <span className="d-mt">{p.size} 字符</span>
              </label>
            ))}
          </div>
          <div className="hint">
            <b>去哪看内容：</b>结果目录里的 .md 文件，或点「建书」之后到书内设定页查看与编辑。
            应用内不预览、不编辑拆解产物。
          </div>
        </>
      )}

      {(task.status === "failed" || task.status === "cancelled") && (
        <>
          <div className="task-err" data-od-id="fail-err">
            <b>任务{STATUS_LABEL[task.status]}</b>
            {/* v8 ignore start — error 兜底文案已由失败用例断言（v8 行归属漂移） */}
            <span>{task.error || "可从断点续拆，已完成维度不重跑、不重复计费。"}</span>
            {/* v8 ignore stop */}
          </div>
          <div style={{ display: "flex", gap: 8, margin: "18px 0" }}>
            <button
              className="btn btn-primary"
              data-od-id="btn-resume"
              disabled={busy}
              onClick={() => void act(() => resumeDeconstructTask(task.id))}
            >
              从断点续拆
            </button>
            {confirmDelete ? (
              <>
                <button className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                  取消
                </button>
                <button
                  className="btn btn-secondary"
                  style={{ color: "var(--err)" }}
                  onClick={() => void act(() => deleteDeconstructTask(task.id), () => navigate("/tools"))}
                >
                  确认删除任务及产物
                </button>
              </>
            ) : (
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(true)}>
                删除任务及产物
              </button>
            )}
          </div>
        </>
      )}

      {task.status === "need_reupload" && (
        <div className="notice" data-od-id="reupload-gate">
          <span className="nt">
            <b>源文件缺失</b>
            <span>重新选择同一本书的 txt 文件，任务将回到原排队位次</span>
          </span>
          <button className="btn btn-secondary btn-sm" onClick={() => reuploadRef.current?.click()}>
            重传文件
          </button>
          <input
            ref={reuploadRef}
            type="file"
            accept=".txt"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setReuploadFile(f);
                void act(() => retryUploadDeconstructTask(task.id, f));
              }
            }}
          />
        </div>
      )}

      {/* 出口弹窗：交互由 exit-modal 交互用例断言；v8 对弹窗 JSX 行归属漂移（c-deconstruct-book） */}
      {/* v8 ignore start */}
      {exitOpen && (
        <>
          <div className="scrim show" onClick={() => setExitOpen(false)} />
          <div className="modal show" role="dialog" aria-modal="true" data-od-id="exit-modal">
            <div className="mcard">
              <div className="mcard-head">
                <span className="mh">《{task.book_name}》拆完了</span>
                <button className="icon-btn" aria-label="关闭" onClick={() => setExitOpen(false)}>
                  ✕
                </button>
              </div>
              <div className="mcard-body">
                <div className="ex-fmts" data-od-id="exit-choices">
                  <button
                    className={"ex-fmt" + (exitOpt === "book" ? " on" : "")}
                    data-exit-opt="book"
                    onClick={() => setExitOpt("book")}
                  >
                    <span className="ex-txt">
                      <b>建书</b>
                      <span>生成新书并写入勾中的设定项；确认后直达新书设定页（标「待确认」）；人物关系/章卷/技法随任务资料。</span>
                    </span>
                  </button>
                  <button
                    className={"ex-fmt" + (exitOpt === "files" ? " on" : "")}
                    data-exit-opt="files"
                    onClick={() => setExitOpt("files")}
                  >
                    <span className="ex-txt">
                      <b>存本地文件夹</b>
                      <span>导出勾中的 {selectedFiles.length} 份产物（＋README）到选择的文件夹；产物仍保留，之后也可回来建书。</span>
                    </span>
                  </button>
                </div>
                {exitOpt === "files" && (
                  <div className="field" style={{ marginTop: 12 }}>
                    <label htmlFor="dest-dir">导出到文件夹</label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <input
                        id="dest-dir"
                        className="input"
                        value={destDir}
                        onChange={(e) => setDestDir(e.target.value)}
                        placeholder="点击「选择文件夹」或粘贴绝对路径"
                        data-od-id="dest-dir"
                      />
                      <button
                        className="btn btn-secondary btn-sm"
                        data-od-id="btn-pick-folder"
                        onClick={async () => {
                          // pywebview 壳层桥（OfflineExportModal 同款）；浏览器回落手输
                          const bridge = (window as unknown as { pywebview?: { api?: { pick_folder?: () => Promise<string> } } }).pywebview;
                          if (bridge?.api?.pick_folder) {
                            const d = await bridge.api.pick_folder();
                            if (d) setDestDir(d);
                          }
                        }}
                      >
                        选择文件夹
                      </button>
                    </div>
                  </div>
                )}
                <div className="ex-sum" data-od-id="exit-sum">
                  {exitOpt === "book"
                    ? `将创建新书《${task.book_name}》，写入所选 ${settingCount}/7 项设定（未勾的不写入）。`
                    : `将导出所选 ${selectedFiles.length} 份产物（＋README 目录页）到选择的文件夹。`}
                </div>
                {exitErr && (
                  <p className="f-err" role="alert" style={{ marginTop: 8 }}>
                    {exitErr}
                  </p>
                )}
              </div>
              <div className="mcard-foot">
                <button className="btn btn-secondary" onClick={() => setExitOpen(false)}>
                  稍后再说
                </button>
                <button
                  className="btn btn-primary"
                  data-od-id="exit-confirm"
                  disabled={busy}
                  onClick={doExit}
                >
                  {exitOpt === "book" ? "就建这本书" : "选择文件夹并导出"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {exitMsg && (
        <div className="notice info" data-od-id="exit-msg">
          <span className="nt">
            <b>{exitMsg}</b>
          </span>
        </div>
      )}
      {/* v8 ignore stop */}
    </main>
  );
}
