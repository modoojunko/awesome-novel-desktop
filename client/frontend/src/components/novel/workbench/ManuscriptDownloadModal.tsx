// 下载成稿弹层（manuscript-download，c-manuscript-download）：
//   表单（位置/文件名/格式多选/摘要）→ 进度（总进度 + 逐格式行 + 后台运行）→ 完成（产出清单 + 打开文件夹）/ 失败（可读原因 + 重试）。
//   挂书工作台壳层（照 UpgradeModal）——预览视图条件挂载，挂预览内切视图会丢轮询/toast/会话记忆。
//   会话记忆：目录/文件名/格式存组件 state（壳层常驻），重开沿用；轮询跨视图保活。
//   术语：本弹层只用「下载」；409 按 running_kind 说人话（「已有备份在进行」/「已有下载在进行」）。
import { useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

type Phase = "form" | "running" | "done" | "error";

interface StepRow {
  format: string;
  state: string; // 等待 | 下载中 | 完成 | 失败
  error: string | null;
}

interface JobStatus {
  state: "idle" | "running" | "done" | "error";
  steps?: StepRow[];
  files?: string[];
  target_dir?: string;
  current?: string;
  pct?: number;
  chapter_count?: number;
  word_count?: number;
  error?: { code: string; message: string } | null;
}

const FORMAT_META: Array<{ k: string; tit: string; ext: string; sub: string }> = [
  { k: "md", tit: "Markdown", ext: ".md", sub: "保留标题层级，方便再排版" },
  { k: "txt", tit: "纯文本", ext: ".txt", sub: "只留正文，任何编辑器都能打开" },
  { k: "docx", tit: "Word", ext: ".docx", sub: "保留卷章标题，便于继续编辑" },
];

type Bridge = {
  pick_folder: () => Promise<string | null>;
  open_folder: (path: string) => Promise<boolean>;
  default_dirs?: () => Promise<Array<{ label: string; path: string }>>;
};

function bridge(): Bridge | null {
  return (window as unknown as { pywebview?: { api?: Bridge } }).pywebview?.api ?? null;
}

export default function ManuscriptDownloadModal({
  open,
  onClose,
  projectId,
  bookName,
  stats,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  bookName: string;
  stats: { chapters: number; words: number };
}) {
  const [phase, setPhase] = useState<Phase>("form");
  const [dir, setDir] = useState("");
  const [filename, setFilename] = useState("");
  /** 上一次替用户填的默认名：bookName 就绪/换书时跟随，用户改过即不覆盖 */
  const lastDefaultRef = useRef("");
  const [formats, setFormats] = useState<string[]>(["md", "docx"]);
  const [quickDirs, setQuickDirs] = useState<Array<{ label: string; path: string }>>([]);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [errMsg, setErrMsg] = useState("");

  // 首次打开：探常用位置（原生桥）；默认文件名随书名
  useEffect(() => {
    if (!open) return;
    const def = bookName ? `${bookName} · 主线全稿` : "";
    setFilename((f) => (f && f !== lastDefaultRef.current ? f : def || f));
    lastDefaultRef.current = def;
    const b = bridge();
    if (b?.default_dirs) {
      b.default_dirs().then((dirs) => setQuickDirs(dirs ?? [])).catch(() => setQuickDirs([]));
    }
  }, [open, bookName]);

  // 轮询：running 期间持续（弹层收起/切视图不停）；done → toast；error → 失败态
  useEffect(() => {
    if (phase !== "running") return;
    let alive = true;
    let seq = 0; // 响应序守卫：跨 done 边界的旧响应不得覆盖新态
    const tick = async () => {
      const my = ++seq;
      try {
        // 走 api 封装（自动带 Authorization；裸 fetch 曾致后端 401——见组件测试的鉴权回归）
        const body = await api.get("/manuscript/download/status");
        const data = body?.data as JobStatus;
        if (!alive || my !== seq || !data || data.state === "idle") return;
        setJob(data);
        if (data.state === "done") {
          setPhase("done");
          toast.success(`下载完成 · ${(data.files ?? []).length} 个文件已保存到 ${data.target_dir ?? ""}`);
        } else if (data.state === "error") {
          setPhase("error");
          setErrMsg(data.error?.message ?? "下载失败");
        }
      } catch {
        /* 单次轮询失败忽略，下个周期再取 */
      }
    };
    void tick();
    const timer = setInterval(tick, 600);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [phase]);

  const pickDir = async () => {
    const b = bridge();
    if (!b) return;
    const picked = await b.pick_folder();
    if (picked) setDir(picked);
  };

  const start = async () => {
    if (!bridge()) return; // 无壳双保险（按钮已禁用）
    try {
      await api.post("/manuscript/download/start", {
        book_id: projectId,
        target_dir: dir,
        filename,
        formats,
      });
    } catch (e) {
      // api 封装把 409 的 detail.message 映射进 e.message（job_runner running_kind 文案）
      const err = e as Error & { status?: number };
      if (err.status === 409) {
        toast.info(err.message || "已有任务在进行中");
        return;
      }
      toast.error("下载发起失败，请重试");
      return;
    }
    setJob(null);
    setPhase("running");
  };

  const openFolder = async () => {
    const b = bridge();
    if (!b || !job?.target_dir) return;
    const ok = await b.open_folder(job.target_dir);
    if (!ok) toast.info("无法打开文件夹，可手动前往保存位置");
  };

  const canStart = phase === "form" && !!dir.trim() && formats.length > 0 && !!bridge();

  const resetToForm = () => {
    setPhase("form");
    setJob(null);
  };

  return (
    <Modal
      open={open}
      onClose={onClose} // 运行中关弹层 = 后台运行（不取消任务，轮询在壳层继续）
      title="下载主线全稿"
      wbStyle
      width={480}
      footer={
        phase === "form" ? (
          <>
            {!bridge() && <span className="note">下载成稿需要桌面版应用</span>}
            <button className="btn btn-primary" disabled={!canStart} data-od-id="download-start" onClick={() => void start()}>
              开始下载
            </button>
          </>
        ) : phase === "running" ? (
          <>
            <span className="note">{job?.current || "正在下载…"}</span>
            <button className="btn btn-secondary" onClick={onClose}>
              后台运行
            </button>
          </>
        ) : phase === "error" ? (
          <>
            <button className="btn btn-secondary" onClick={resetToForm}>
              返回修改
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                resetToForm();
                void start();
              }}
            >
              重试
            </button>
          </>
        ) : (
          <button className="btn btn-primary" onClick={() => void openFolder()}>
            打开文件夹
          </button>
        )
      }
    >
      {phase === "form" && (
        <>
          {!bridge() && (
            <p className="dl-need-desktop">
              下载成稿需要桌面版应用。到官网 <a href="https://www.awesomenovel.com" target="_blank" rel="noreferrer">下载桌面版</a> 后即可把主线全稿存到本地。
            </p>
          )}
          <div className="ex-sec">
            <h4>保存位置</h4>
            <div className="ex-path">
              <input
                className="input"
                value={dir}
                onChange={(e) => setDir(e.target.value)}
                placeholder="选择或输入保存目录"
                spellCheck={false}
                aria-label="保存位置"
                data-od-id="download-dir"
              />
              <button className="btn btn-secondary btn-sm" onClick={() => void pickDir()}>
                选择…
              </button>
            </div>
            {quickDirs.length > 0 && (
              <div className="ex-dirs">
                {quickDirs.map((d) => (
                  <button key={d.path} className="chip" onClick={() => setDir(d.path)}>
                    {d.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="ex-sec">
            <h4>文件名</h4>
            <input
              className="input"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              spellCheck={false}
              aria-label="下载文件名"
              data-od-id="download-filename"
            />
          </div>
          <div className="ex-sec">
            <h4>下载格式（可多选）</h4>
            <div className="ex-fmts">
              {FORMAT_META.map((f) => {
                const on = formats.includes(f.k);
                return (
                  <button
                    key={f.k}
                    role="checkbox"
                    aria-checked={on}
                    className={"ex-fmt" + (on ? " on" : "")}
                    data-od-id={`download-fmt-${f.k}`}
                    onClick={() =>
                      setFormats((cur) => (on ? cur.filter((x) => x !== f.k) : [...cur, f.k]))
                    }
                  >
                    <span className="ex-txt">
                      <b>
                        {f.tit} {f.ext}
                      </b>
                      <span>{f.sub}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <p className="ex-sum" data-od-id="download-summary">
            本次下载 {stats.chapters} 章 · {stats.words} 字 · 覆盖全书主线，不含旧稿支线。
          </p>
        </>
      )}

      {phase === "running" && (
        <>
          <p className="ex-stat">正在下载…（关闭弹层后下载继续，完成会提示）</p>
          <div className="ex-bar">
            <i style={{ width: `${job?.pct ?? 5}%` }} />
          </div>
          <ul className="ex-steps">
            {(job?.steps ?? formats.map((f) => ({ format: f, state: "等待", error: null }))).map(
              (s) => (
                <li key={s.format} data-testid={`dl-step-${s.format}`}>
                  <b>
                    {filename}
                    {FORMAT_META.find((f) => f.k === s.format)?.ext}
                  </b>
                  <em className={s.state === "完成" ? "ok" : s.state === "失败" ? "err" : undefined}>
                    {s.state}
                  </em>
                </li>
              ),
            )}
          </ul>
        </>
      )}

      {phase === "done" && (
        <>
          <div className="ex-done">
            <div>
              <b>下载完成</b>
              <p>
                {(job?.files ?? []).length} 个文件已保存到 <span className="mono">{job?.target_dir}</span>
              </p>
            </div>
          </div>
          <ul className="ex-steps">
            {(job?.steps ?? []).map((s) => (
              <li key={s.format}>
                <b>
                  {filename}
                  {FORMAT_META.find((f) => f.k === s.format)?.ext}
                </b>
                <em className="ok">{s.state}</em>
              </li>
            ))}
          </ul>
        </>
      )}

      {phase === "error" && (
        <div className="ex-error" role="alert">
          <b>下载失败</b>
          <p>{errMsg}</p>
          <p className="ex-error-hint">已完成的部分文件保留在保存位置；可返回修改后重试。</p>
        </div>
      )}
    </Modal>
  );
}
