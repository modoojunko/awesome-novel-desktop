/**
 * 批量添加角色弹层（c-char-batch-import）：单路径＝下载模版 → Excel/WPS 填好 →
 * 上传导入 → 预览（行级状态/就地改/删行）→ 确认（建卡回调上抛，串行由调用方执行）。
 * 草稿保留：rows 活在组件体（Modal 子树 200ms 退场后卸载也不丢），仅建卡成功后清空；
 * 停批＝failMsg 红条＋剩余行留在预览可重试。
 * 字段说明折叠块与模版「填写说明」sheet 共用 IMPORT_FIELD_GUIDE（同源，禁手抄）。
 */
import { useMemo, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import {
  BATCH_DEFAULT_ROLE,
  IMPORT_FIELD_GUIDE,
  IMPORT_FIELD_NOTES,
  TEMPLATE_HEADERS,
  type BatchRow,
  buildTemplateWorkbook,
  effectiveRole,
  loadXlsx,
  readFileAsRows,
  rowStatus,
  statusContext,
} from "@/lib/characterImport";
import { ROLES } from "@/lib/characterModel";

export interface BatchCreateOutcome {
  created: number;
  skipped: number;
  createdIds: string[];
  /** 停批文案（非重名错误）；remaining＝未建的剩余行，留在预览可重试 */
  failMsg?: string;
  remaining?: BatchRow[];
}

interface BatchAddModalProps {
  open: boolean;
  /** 库内已有名字（重名判定；调用方从列表整形） */
  existingNames: Set<string>;
  /** 库内是否已有主角（主角约束判定） */
  hasProtagonist: boolean;
  onClose: () => void;
  onToast: (msg: string) => void;
  /** 确认建卡（调用方串行执行）；onProgress 回报「建卡中 done/total」 */
  onSubmit: (
    rows: BatchRow[],
    onProgress: (done: number, total: number) => void,
    /** retry＝停批后的重试：调用方据此累积撤销范围（覆盖整个导入会话） */
    meta: { retry: boolean },
  ) => Promise<BatchCreateOutcome>;
}

export default function BatchAddModal(props: BatchAddModalProps) {
  const { open, existingNames, hasProtagonist, onClose, onToast, onSubmit } = props;
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [fmt, setFmt] = useState("");
  const [parseErr, setParseErr] = useState("");
  const [fileName, setFileName] = useState("");
  const [failMsg, setFailMsg] = useState("");
  /** 停批后的重试态：确认时上抛给调用方累积撤销范围；换文件/成功后清除 */
  const [retrying, setRetrying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const ctx = useMemo(
    () => statusContext(rows, { existingNames, hasProtagonist }),
    [rows, existingNames, hasProtagonist],
  );
  const statuses = rows.map((r, i) => rowStatus(r, i, ctx));
  const okN = statuses.filter((s) => s.ok).length;
  const skipN = rows.length - okN;
  /** 主角冲突等 err 行存在＝拦截确认（spec：标红拦截，改掉为止）；单纯跳过行不拦 */
  const hasErr = statuses.some((s) => s.cls === "err");

  const resetDraft = () => {
    setRows([]);
    setFmt("");
    setParseErr("");
    setFileName("");
    setFailMsg("");
    setRetrying(false);
  };

  /* v8 ignore start -- jsdom 无 URL.createObjectURL，下载路径由 e2e「下载模版回读」钉 */
  const downloadTemplate = async () => {
    const X = await loadXlsx();
    X.writeFile(await buildTemplateWorkbook(), "角色批量导入模版.xlsx");
    onToast("模版已下载——填好角色后点「选择文件」导入");
  };
  /* v8 ignore end */

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setFailMsg("");
    setRetrying(false); // 换了文件＝新一轮导入，重试态作废
    try {
      const parsed = await readFileAsRows(file);
      setRows(parsed);
      setParseErr("");
      setFmt(`${file.name} · ${parsed.length} 行`);
      setFileName(file.name);
    } catch (e) {
      setRows([]);
      setFmt("");
      setParseErr((e as Error).message || "文件解析失败");
      setFileName(file.name);
    }
  };

  const editRow = (idx: number, patch: Partial<BatchRow>) => {
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const confirm = async () => {
    if (busy) return;
    const targets = rows.filter((_, i) => statuses[i].ok);
    if (!targets.length) return;
    setBusy(true);
    setProgress({ done: 0, total: targets.length });
    try {
      const outcome = await onSubmit(targets, (done, total) => setProgress({ done, total }), {
        retry: retrying,
      });
      if (outcome.failMsg) {
        setRows(outcome.remaining ?? []);
        setFailMsg(outcome.failMsg);
        setRetrying(true);
        setFmt(outcome.remaining ? `${outcome.remaining.length} 行未建` : fmt);
      } else {
        resetDraft();
        onClose();
      }
    } catch (e) {
      // onSubmit 整体拒绝（如建卡前保存队列网络失败）：红条＋行保留，弹层不关可重试
      setFailMsg((e as Error).message || "导入失败——请重试");
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  const guide = (
    <details className="cb-guide" data-testid="char-batch-guide">
      <summary>字段怎么填？点开看说明和示例</summary>
      <div className="cb-guide-scroll">
        <table className="cb-guide-t">
          <thead>
            <tr><th>字段</th><th>填什么</th><th>示例</th></tr>
          </thead>
          <tbody>
            {IMPORT_FIELD_GUIDE.map((g) => (
              <tr key={g.field}>
                <td>{g.field}</td>
                <td>{g.what}</td>
                <td>{g.example}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="cb-note">{IMPORT_FIELD_NOTES}</p>
      </div>
    </details>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="批量添加角色"
      locked={busy}
      width={760}
      wbStyle
      footer={
        <>
          <span className="note">重名的角色会跳过，不覆盖已有卡。</span>
          <span className="cb-cnt" data-testid="char-batch-count">
            {busy && progress
              ? `建卡中 ${progress.done}/${progress.total}…`
              : (fmt ? `${fmt} · ` : "") + `建 ${okN} 张` + (skipN ? ` · 跳过 ${skipN}` : "")}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            data-testid="char-batch-confirm"
            disabled={busy || okN === 0 || hasErr}
            onClick={() => void confirm()}
          >
            {busy ? "建卡中…" : `建 ${okN} 张卡`}
          </button>
        </>
      }
    >
      <p className="cb-hint">
        下载模版，在 Excel / WPS 里一行一个角色填好再导入。<b>只填名字也行</b>；类型四选一
        （{ROLES.join("/")}），不填默认{BATCH_DEFAULT_ROLE}；别名用 <code>·</code> 分隔；
        模版里的「示例-」行导入时会自动跳过。填不动可以让 AI 照列头帮你填，粘回表格再导入。中英文列头都认。
      </p>
      <div className="cb-file-row" data-testid="char-batch-file-row">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void downloadTemplate()}>
          下载模版(.xlsx)
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          data-testid="char-batch-upload"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          选择文件…
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.csv"
          hidden
          data-testid="char-batch-file-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            void onFile(f);
          }}
        />
        <span className="cb-filename" data-testid="char-batch-filename">
          {fileName || "未选择文件"}
        </span>
      </div>
      {parseErr ? (
        <div className="cb-err" role="alert" data-testid="char-batch-parse-err">{parseErr}</div>
      ) : null}
      {failMsg ? (
        <div className="cb-err" role="alert" data-testid="char-batch-fail">{failMsg}</div>
      ) : null}
      <div className="cb-pv" data-testid="char-batch-preview">
        <div className="cb-pv-head">
          <span className="cb-no">#</span>
          <span className="cb-name">名字</span>
          <span className="cb-role">类型</span>
          <span className="cb-persona">一句话人设（可补）</span>
          <span className="cb-st">状态</span>
        </div>
        {!rows.length && !parseErr ? (
          <div className="cb-empty">
            点「下载模版」，在 Excel / WPS 里填好角色再导入——这里实时解析预览。
            <br />
            识别不了的会标红，可以就地改。
          </div>
        ) : null}
        {rows.map((r, i) => {
          const st = statuses[i];
          return (
            <div key={i} className={`cb-row${st.cls === "err" ? " bad" : st.cls === "warn" ? " warn" : ""}`} data-testid="char-batch-row">
              <span className="cb-no num">{i + 1}</span>
              <span className="cb-name">
                <input
                  className="cb-input"
                  value={r.name}
                  placeholder="名字"
                  aria-label={`第 ${i + 1} 行名字`}
                  onChange={(e) => editRow(i, { name: e.target.value })}
                />
              </span>
              <span className="cb-role">
                <select
                  className="cb-input"
                  value={effectiveRole(r)}
                  aria-label={`第 ${i + 1} 行类型`}
                  onChange={(e) => editRow(i, { role: e.target.value })}
                >
                  {ROLES.map((role) => (
                    <option key={role}>{role}</option>
                  ))}
                </select>
              </span>
              <span className="cb-persona">
                <input
                  className="cb-input"
                  value={r.persona}
                  placeholder="一句话人设"
                  aria-label={`第 ${i + 1} 行人设`}
                  onChange={(e) => editRow(i, { persona: e.target.value })}
                />
              </span>
              <span className={`pill pill-${st.cls} cb-st`} data-testid={`char-batch-status-${i + 1}`}>
                {st.text}
              </span>
              <button
                type="button"
                className="cb-x"
                title="去掉这行"
                aria-label={`去掉第 ${i + 1} 行`}
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      {guide}
      <p className="cb-headers-hint">模版列头：{TEMPLATE_HEADERS.join("｜")}</p>
    </Modal>
  );
}
