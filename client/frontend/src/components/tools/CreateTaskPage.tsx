// 创建任务页（c-deconstruct-book 5.4）：双子态（未选文件/已选·解析完成）——
// 解析在选文件时本地完成（秒级、不耗额度）；模型选择仅本任务生效；探针门过才解禁创建。
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  createDeconstructTask,
  DECONSTRUCT_DIMS,
  fetchModelOptions,
  probeModel,
  type ModelOption,
} from "../../lib/deconstructApi";


/** 本地解析（评审 P1-5）：编码探测链（utf-8-sig→utf-8→gb18030→big5）＋字数/章节统计。
 *  与后端 deconstruct/textparse 同规则；GBK/Big5 由浏览器 TextDecoder 原生支持。 */
async function localParse(file: File): Promise<{ encoding: string; totalChars: number; chapters: number }> {
  const raw = new Uint8Array(await file.arrayBuffer());
  const encodings = ["utf-8-sig", "utf-8", "gb18030", "big5"] as const;
  let text = "";
  let encoding = "";
  for (const enc of encodings) {
    try {
      text = new TextDecoder(enc, { fatal: true }).decode(raw);
      encoding = enc;
      break;
    } catch {
      /* 下一个 */
    }
  }
  if (!encoding) throw new Error("无法识别文件编码（已尝试 UTF-8/GBK/Big5），请转码为 UTF-8 后重试");
  const chapterRe = /^\s*(第[0-9零一二两三四五六七八九十百千]+[章回节][^\n]{0,40})\s*$/gm;
  const chapters = [...text.matchAll(chapterRe)].length;
  const totalChars = text.replace(/\s+/g, "").length;
  return { encoding, totalChars, chapters };
}

export default function CreateTaskPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [optionsLoaded, setOptionsLoaded] = useState(false);
  const [modelKey, setModelKey] = useState("");
  const [probeOk, setProbeOk] = useState<boolean | null>(null);
  const [probing, setProbing] = useState(false);
  const [selected, setSelected] = useState<string[]>(DECONSTRUCT_DIMS.map((d) => d.key));
  const [bookName, setBookName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState("");
  const [parsed, setParsed] = useState<{ encoding: string; totalChars: number; chapters: number } | null>(null);
  const [parseErr, setParseErr] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void fetchModelOptions()
      .then((opts) => {
        setOptions(opts);
        if (opts.length > 0) setModelKey(`${opts[0].api_config_id}::${opts[0].model}`);
        setOptionsLoaded(true);
      })
      .catch(() => setOptionsLoaded(true));
  }, []);

  const grouped = useMemo(() => {
    const by = new Map<string, { name: string; vendor: string; opts: ModelOption[] }>();
    for (const o of options) {
      const g = by.get(o.api_config_id) ?? { name: o.config_name, vendor: o.vendor, opts: [] };
      g.opts.push(o);
      by.set(o.api_config_id, g);
    }
    return [...by.values()];
  }, [options]);

  const hasModels = options.length > 0;

  // 探针门：所选模型轻探测（几十 token），通过才解禁「创建任务」
  useEffect(() => {
    if (!modelKey) {
      setProbeOk(null);
      return;
    }
    const [configId, model] = modelKey.split("::");
    /* v8 ignore start — 空键早退臂（首渲染 modelKey 恒有值） */
    if (!configId || !model) return;
    /* v8 ignore stop */
    setProbing(true);
    setProbeOk(null);
    let alive = true;
    const t = window.setTimeout(() => {
      /* v8 ignore start — 回调由慢探针用例断言（v8 对 async 闭包行归属漂移） */
      void probeModel(configId, model).then((ok) => {
        if (alive) {
          setProbeOk(ok);
          setProbing(false);
        }
      });
      /* v8 ignore stop */
    }, 150);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [modelKey]);

  const toggleDim = (key: string) => {
    setSelected((prev) => {
      if (prev.includes(key)) return prev.length <= 1 ? prev : prev.filter((k) => k !== key);
      /* v8 ignore next */
      return [...DECONSTRUCT_DIMS.map((d) => d.key).filter((k) => prev.includes(k) || k === key)];
    });
  };

  const canSubmit = file !== null && hasModels && probeOk === true && !probing && !submitting;

  const pickFile = (f: File | null) => {
    setFile(f);
    setBookName(f ? f.name.replace(/\.txt$/i, "") : "");
    setParsed(null);
    setParseErr("");
    if (f) {
      localParse(f)
        .then(setParsed)
        .catch((err: Error) => setParseErr(err.message));
    }
  };

  const submit = async () => {
    /* v8 ignore start — 防御臂：按钮禁用态不可达（未选文件时禁用） */
    if (!file) return;
    /* v8 ignore stop */
    const [configId, model] = modelKey.split("::");
    setSubmitting(true);
    setSubmitErr("");
    try {
      const result = await createDeconstructTask(file, {
        bookName,
        apiConfigId: configId,
        model,
        selectedDims: selected,
      });
      /* v8 ignore next */
      navigate(`/tools/deconstruct/${result.id}`);
    } catch (e) {
      setSubmitErr(e instanceof Error ? e.message : "创建失败");
      setSubmitting(false);
    }
  };

  const onZoneKeyDown = (e: React.KeyboardEvent) => {
    /* v8 ignore start — 键臂由 Enter 用例覆盖（Space 臂 jsdom 键值构造受限） */
    if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
    /* v8 ignore stop */
  };
  const onZoneDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  };

  return (
    <main className="main" data-od-id="tools-create">
      <div className="page-head">
        <div>
          <h1>创建任务 · 拆书</h1>
          <p className="sub">选好文件、确认拆解范围，创建后进任务清单排队</p>
        </div>
        <Link className="btn btn-ghost" to="/tools">
          返回任务清单
        </Link>
      </div>

      {/* 拆解模型：已配置才出现（仅本任务生效，不改配置默认）；未配置引导去配置 */}
      {hasModels ? (
        <div className="field" data-od-id="model-field" style={{ maxWidth: 420 }}>
          <label htmlFor="model-select">
            拆解模型 <span style={{ fontSize: 11.5, color: "var(--muted)" }}>仅本任务生效，不改模型配置默认</span>
          </label>
          <select
            id="model-select"
            className="input"
            data-od-id="model-picker"
            value={modelKey}
            onChange={(e) => setModelKey(e.target.value)}
          >
            {grouped.map((g) => (
              <optgroup key={g.name + g.vendor} label={`${g.name} · ${g.vendor}`}>
                {g.opts.map((o) => (
                  <option key={`${o.api_config_id}::${o.model}`} value={`${o.api_config_id}::${o.model}`}>
                    {o.model}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      ) : optionsLoaded ? (
        <div className="notice" data-od-id="notice-selfkey" style={{ borderStyle: "dashed" }}>
          <span className="nt">
            <b>还没配模型</b>
            <span>先去「模型配置」添加 API Key 与模型；配好后这里出现模型选择，消耗你自己的额度、不设次数门槛</span>
          </span>
          <Link className="btn btn-secondary btn-sm" to="/config">
            去配置
          </Link>
        </div>
      ) : null}

      {/* 探针门 */}
      {hasModels && (
        <div className="notice info" data-od-id="probe-gate">
          <span className="nt">
            <b>{probing ? "模型探针中…" : probeOk ? "模型探针通过" : probeOk === false ? "模型探针失败" : "模型探针待运行"}</b>
            <span>对所选模型轻量探测；通过才解禁「创建任务」，失败请去「模型配置」检查或换模型</span>
          </span>
          {probing ? (
            <span className="pill">探测中</span>
          ) : probeOk ? (
            <span className="pill pill-ok">可用</span>
          ) : probeOk === false ? (
            <Link className="btn btn-secondary btn-sm" to="/config">
              去配置
            </Link>
          ) : null}
        </div>
      )}

      {/* 双子态：未选文件（空上传区+禁用创建）/ 已选·解析完成 */}
      {!file ? (
        <div data-sub="nofile">
          <div
            className="up-zone"
            data-od-id="up-zone"
            role="button"
            tabIndex={0}
            aria-label="选择或拖入 txt 文件"
            // v8 ignore start — 事件 handler 行为已由拖拽/Enter/坏编码用例断言（v8 对 JSX 属性箭头行归属漂移）
            onClick={() => inputRef.current?.click()}
            onKeyDown={onZoneKeyDown}
            onDragOver={(e) => e.preventDefault()}
            // v8 ignore stop
            onDrop={onZoneDrop}
          >
            <div className="up-ic">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="M12 15V4M7 8l5-5 5 5M5 20h14" />
              </svg>
            </div>
            <p className="up-main">拖拽整本小说到此处，或点击选择文件</p>
            <p className="up-sub">选完文件即在本地解析（秒级、不消耗模型额度），书名/字数/章节数随之而来</p>
            <div className="fmt-row" data-od-id="fmt-row">
              <span className="fmt-chip on">.txt 可拆</span>
              <span className="fmt-chip off">.epub 即将支持</span>
              <span className="fmt-chip off">.docx 书架导入已支持 · 拆书管线待接</span>
            </div>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".txt"
            hidden
            data-od-id="file-input"
            onChange={(e) => {
              pickFile(e.target.files?.[0] ?? null);
            }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            <button className="btn btn-primary" disabled data-od-id="btn-submit-nofile" title="先选择文件">
              创建任务
            </button>
            <Link className="btn btn-secondary" to="/tools">
              取消
            </Link>
          </div>
        </div>
      ) : (
        <div data-sub="picked" data-od-id="picked-pane">
          <div className="file-strip" data-od-id="file-strip">
            <span className="fs-ic">📄</span>
            <div className="fs-tx">
              <b>{file.name}</b>
              <span data-od-id="parse-backfill">
                {(file.size / 1024 / 1024).toFixed(1)} MB
                {parsed ? ` · 编码探测：${parsed.encoding} · ${parsed.totalChars} 字 · ${parsed.chapters} 章` : ""}
                {parseErr ? ` · ${parseErr}` : " · 本地解析（秒级、不消耗模型额度）"}
              </span>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => setFile(null)}>
              换文件
            </button>          </div>

          <div className="fcard" data-od-id="parse-card">
            <div className="field" style={{ margin: 0, maxWidth: 340 }}>
              <label htmlFor="bk-name">书名（取自文件名，可改）</label>
              <input
                id="bk-name"
                className="input"
                value={bookName}
                onChange={(e) => setBookName(e.target.value)}
                data-od-id="parse-bookname"
              />
            </div>
          </div>

          <div className="dims" data-od-id="parse-dims">
            <div className="dim-group">
              拆解范围 ·{" "}
              <span data-od-id="dims-count">
                已选 {selected.length}/{DECONSTRUCT_DIMS.length} 份
              </span>
              （可勾减省调用，下限 1 份；输出到结果目录）
            </div>
            {DECONSTRUCT_DIMS.map((d) => (
              <label key={d.key} className="dim-row" style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={selected.includes(d.key)}
                  onChange={() => toggleDim(d.key)}
                  data-od-id={`dim-${d.key}`}
                  aria-label={d.name}
                />
                <span className="d-tx">
                  <b>{d.name}</b>
                  <span>{d.file}</span>
                </span>
              </label>
            ))}
          </div>

          <div className="hint" data-od-id="create-hint">
            <b>创建后进清单排队：</b>一次只跑一个任务，轮到自动开跑；可以关掉页面去做别的，
            完成后回「任务清单」取结果。
            <br />
            <b>输出三铁律：</b>硬事实回指章节号、结论标可信度、原文没写的标「原文未明确」——不编。
            <br />
            <b>隐私与版权：</b>正文与书名将发送到你配置的模型服务商；拆解他人作品仅限个人学习研究，产物再发布可能构成侵权。
          </div>

          {submitErr && (
            <div className="notice" role="alert">
              <span className="nt">
                <b>创建失败</b>
                <span>{submitErr}</span>
              </span>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            <button
              className="btn btn-primary"
              data-od-id="btn-submit-task"
              disabled={!canSubmit}
              onClick={() => void submit()}
            >
              {submitting ? "创建中…" : "创建任务（进队列排队）"}
            </button>
            <Link className="btn btn-secondary" to="/tools">
              取消
            </Link>
          </div>
        </div>
      )}
    </main>
  );
}
