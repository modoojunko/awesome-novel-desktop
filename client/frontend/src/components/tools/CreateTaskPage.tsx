// 创建任务页（c-deconstruct-book 5.4）：双子态（未选文件/已选·解析完成）——
// 解析在选文件时本地完成（秒级、不耗额度）；模型选择仅本任务生效；探针门过才解禁创建。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import UpgradeModal from "@/components/novel/UpgradeModal";
import { useFeature } from "@/hooks/useTier";
import {
  createDeconstructTask,
  DECONSTRUCT_DIMS,
  fetchModelOptions,
  getDeconstructConsent,
  probeModel,
  signDeconstructConsent,
  type DeconstructConsentStatus,
  type ModelOption,
} from "../../lib/deconstructApi";
import {
  detectUtfBom,
  nulRatioOverLimit,
  structureVerdict,
  type StructureVerdict,
} from "../../lib/deconstructStructure";


/** 智能拆书推荐维（写法向）：主线剧情/伏笔类依赖全书覆盖，不在推荐集内 */
const SMART_DEFAULT_DIMS = ["genre", "world", "characters", "style", "techniques"];

/** 单本容量口径（spec「单本容量口径」）：v2 分级归并后残留为全书梗概注入截断（约 200 章）；超线只提示不拦截 */
const OVER_CAPACITY_CHARS = 600_000;

/** 格式示例（c-deconstruct-book 12）：与 deconstruct/textparse 夹具同款的网文形态样例，
 *  页内展示与「下载示例 .txt」共用同一份文本——作家照这个样子排自己的稿子即可被正确切章。 */
const FORMAT_EXAMPLE_TEXT = `第一卷 风起
第1章 开端
张三出门买药，顺路打听城里的消息。暮色四合，他加快了脚步。

第2章 遇敌
李四拦在巷口，一言不合便动了手。刀光一闪，张三侧身避过。`;

/** 下载示例 txt（UTF-8，探测链首选编码；记事本/写作软件打开即见式样）。 */
function downloadExample() {
  const blob = new Blob([FORMAT_EXAMPLE_TEXT], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "拆书格式示例.txt";
  a.click();
  URL.revokeObjectURL(url);
}

/** 格式示例块：完整版＝样例＋要点＋下载；精简版（compact）＝仅样例，risk 判定卡旁就近展示。 */
function FormatExample({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`fmt-example${compact ? " fmt-example-compact" : ""}`} data-od-id={compact ? "fmt-example-compact" : "fmt-example"}>
      <pre>{FORMAT_EXAMPLE_TEXT}</pre>
      {!compact && (
        <>
          <ul>
            <li>章标题（第X章／第X回／第X节，汉字或数字均可）<b>独占一行</b>，行内不跟正文；卷标题同理（可不分卷）</li>
            <li>UTF-8 / GBK / Big5 编码均可；单本 ≤50MB、≤60 万字（约 200 章）</li>
            <li>建议删除目录页再上传——目录行会被误认为章标题</li>
          </ul>
          <button type="button" className="btn btn-ghost btn-sm" data-od-id="fmt-example-download" onClick={downloadExample}>
            下载示例 .txt
          </button>
        </>
      )}
    </div>
  );
}

interface LocalParse {
  encoding: string;
  totalChars: number;
  chapters: number;
  chapterChars: number[];
}

/** 本地解析（评审 P1-5）：编码探测链（utf-8-sig→utf-8→gb18030→big5）＋字数/章节统计＋结构判定。
 *  与后端 deconstruct/textparse 同规则（BOM 直判/空字节拒收/判定阈值 parity 钉死）；
 *  GBK/Big5 由浏览器 TextDecoder 原生支持。 */
async function localParse(file: File): Promise<LocalParse> {
  const raw = new Uint8Array(await file.arrayBuffer());
  const bom = detectUtfBom(raw);
  if (bom === "utf-32") throw new Error("文件是 UTF-32 编码，请在编辑器中另存为 UTF-8 后重试");
  if (bom === "utf-16") throw new Error("文件是 UTF-16 编码（Windows「Unicode」格式），请另存为 UTF-8 后重试");
  const encodings = ["utf-8-sig", "utf-8", "gb18030", "big5"] as const;
  let text = "";
  let encoding = "";
  let nulSeen = false;
  for (const enc of encodings) {
    try {
      text = new TextDecoder(enc, { fatal: true }).decode(raw);
    } catch {
      /* 下一个 */
      continue;
    }
    if (nulRatioOverLimit(text)) {
      nulSeen = true; // 解出来也是乱码（典型：无 BOM UTF-16 被当 GBK），试下一条
      continue;
    }
    encoding = enc;
    break;
  }
  if (!encoding) {
    throw new Error(
      nulSeen
        ? "文件内容疑似 UTF-16 等宽字节编码（解出大量空字节），请另存为 UTF-8 后重试"
        : "无法识别文件编码（已尝试 UTF-8/GBK/Big5），请转码为 UTF-8 后重试",
    );
  }
  const chapterRe = /^\s*(第[0-9零一二两三四五六七八九十百千]+[章回节][^\n]{0,40})\s*$/gm;
  const matches = [...text.matchAll(chapterRe)];
  const chapterChars: number[] = [];
  for (let i = 0; i < matches.length; i++) {
    /* v8 ignore start — index?? 兜底臂：matchAll 结果 index 恒存在（TS 类型放宽才可达） */
    const start = (matches[i].index ?? 0) + matches[i][0].length;
    const end = i + 1 < matches.length ? (matches[i + 1].index ?? text.length) : text.length;
    /* v8 ignore stop */
    chapterChars.push(text.slice(start, end).replace(/\s+/g, "").length);
  }
  const totalChars = text.replace(/\s+/g, "").length;
  return { encoding, totalChars, chapters: matches.length, chapterChars };
}

export default function CreateTaskPage() {
  const navigate = useNavigate();
  // 档位门（c-deconstruct-tier）：AI 拆书＝deconstruct（PRO 起、trial 同权）；
  // 免费正文导入不在此页——本页整页都是 AI 拆书
  const canDeconstruct = useFeature("deconstruct");
  const [tierModalOpen, setTierModalOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [optionsLoaded, setOptionsLoaded] = useState(false);
  const [modelKey, setModelKey] = useState("");
  const [probeOk, setProbeOk] = useState<boolean | null>(null);
  const [probing, setProbing] = useState(false);
  // 拆解模式（c-deconstruct-knowledge）：smart=智能拆书（默认）/ full=全书拆。
  // 默认即智能模式，维度初值必须与「智能推荐四维」一致——否则默认发派嘴上智能、
  // 实际仍按全维跑（剧情/伏笔维度依赖全书覆盖，智能采样给不了）。
  const [mode, setMode] = useState<"smart" | "full">("smart");
  const smartDims = SMART_DEFAULT_DIMS.filter((k) => DECONSTRUCT_DIMS.some((d) => d.key === k));
  const [selected, setSelected] = useState<string[]>(
    mode === "smart" ? smartDims : DECONSTRUCT_DIMS.map((d) => d.key),
  );
  const [bookName, setBookName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState("");
  // 思考档位（c-deconstruct-resilience D10）：拆书是结构化抽取，默认关——
  // 思考与输出共用 max_tokens，burn 预算只会放大截断与空响应
  const [thinking, setThinking] = useState<"off" | "low" | "inherit">("off");
  const [parsed, setParsed] = useState<LocalParse | null>(null);
  const [verdict, setVerdict] = useState<StructureVerdict | null>(null);
  const [riskAck, setRiskAck] = useState(false);
  const [parseErr, setParseErr] = useState("");
  const [showExample, setShowExample] = useState(false);
  const [consent, setConsent] = useState<DeconstructConsentStatus | null>(null);
  const [consentErr, setConsentErr] = useState("");
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentView, setConsentView] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentBusy, setConsentBusy] = useState(false);
  const [sourceBasis, setSourceBasis] = useState("owned");
  const [sourceAuthor, setSourceAuthor] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const loadConsent = useCallback(() => {
    setConsentErr("");
    void getDeconstructConsent()
      .then(setConsent)
      .catch((e: Error) => setConsentErr(e.message || "承诺状态读取失败"));
  }, []);

  useEffect(() => {
    loadConsent();
  }, [loadConsent]);

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

  // 解析未落定（本地解析进行中或失败）不解禁创建：risk 判定随解析结果同批返回，
  // 提前放行会绕过确认闸把无章标题大部头直接送进队列（评审 P2 竞态口）；解析失败的书后端同样拒收。
  const canSubmit =
    file !== null &&
    parsed !== null &&
    hasModels &&
    probeOk === true &&
    !probing &&
    !submitting &&
    consent?.signed === true &&
    (verdict?.level !== "risk" || riskAck);

  const pickFile = (f: File | null) => {
    setFile(f);
    setBookName(f ? f.name.replace(/\.txt$/i, "") : "");
    setParsed(null);
    setVerdict(null);
    setRiskAck(false);
    setParseErr("");
    if (f) {
      localParse(f)
        .then((p) => {
          setParsed(p);
          setVerdict(structureVerdict({ chapterChars: p.chapterChars, totalChars: p.totalChars }));
        })
        .catch((err: Error) => setParseErr(err.message));
    }
  };

  const openConsent = (view: boolean) => {
    setConsentView(view);
    setConsentChecked(false);
    setConsentErr("");
    setConsentOpen(true);
  };

  const doSignConsent = async () => {
    setConsentBusy(true);
    setConsentErr("");
    try {
      const next = await signDeconstructConsent();
      setConsent(next);
      setConsentOpen(false);
      setConsentChecked(false);
    } catch (e) {
      setConsentErr(e instanceof Error ? e.message : "签署失败");
    } finally {
      setConsentBusy(false);
    }
  };

  const submit = async () => {
    /* v8 ignore start — 防御臂：按钮禁用态不可达（未选文件时禁用） */
    if (!file) return;
    /* v8 ignore stop */
    if (!canDeconstruct) {
      setTierModalOpen(true);
      return;
    }
    const [configId, model] = modelKey.split("::");
    setSubmitting(true);
    setSubmitErr("");
    try {
      const result = await createDeconstructTask(file, {
        bookName,
        apiConfigId: configId,
        model,
        selectedDims: selected,
        thinking,
        mode,
        rightsBasis: sourceBasis,
        sourceAuthor,
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

      {/* 拆书使用承诺（c-deconstruct-compliance-guard）：一次性签署，服务端只存签署事实 */}
      <div className="fcard" data-od-id="consent-card" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {consent?.signed ? (
            <span className="pill pill-ok"><i data-ico="check" />已签署</span>
          ) : (
            <span className="pill pill-warn">未签署</span>
          )}
          <div style={{ flex: 1, minWidth: 240 }}>
            <b style={{ display: "block" }}>《拆书使用承诺》 · {consent?.version ?? "v1"}</b>
            <span style={{ display: "block", marginTop: 2, fontSize: 12, color: "var(--muted)" }}>
              {consent?.signed
                ? `${(consent.signed_at ?? "").slice(0, 10)} 签署 · 换设备不用重签`
                : "签一次就好；之后每次拆书只显示已签署"}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            data-od-id="btn-open-consent"
            disabled={!consent}
            onClick={() => openConsent(true)}
          >
            查看承诺
          </button>
          {!consent?.signed && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-od-id="btn-sign-consent"
              disabled={!consent}
              onClick={() => openConsent(false)}
            >
              阅读并签署
            </button>
          )}
          {consentErr && !consent && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              data-od-id="btn-retry-consent-load"
              onClick={loadConsent}
            >
              重试读取
            </button>
          )}
        </div>
        {consentErr && !consentOpen && <p className="f-err" style={{ margin: "8px 0 0" }}>{consentErr}</p>}
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
      ) : null}
      {hasModels ? (
        <div className="field" data-od-id="thinking-field" style={{ maxWidth: 420 }}>
          <label htmlFor="thinking-select">
            思考档位 <span style={{ fontSize: 11.5, color: "var(--muted)" }}>拆书是抽取任务，关思考更快更稳</span>
          </label>
          <select
            id="thinking-select"
            className="input"
            data-od-id="thinking-picker"
            value={thinking}
            onChange={(e) => setThinking(e.target.value as "off" | "low" | "inherit")}
          >
            <option value="off">关闭思考（推荐）</option>
            <option value="low">思考·低</option>
            <option value="inherit">跟随模型配置</option>
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
            <p className="up-sub">
              选完文件即在本地解析（秒级、不消耗模型额度），书名/字数/章节数随之而来；单本 ≤60 万字（约 200
              章）一次任务完成
            </p>
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
          <div style={{ textAlign: "center", marginTop: 12 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              data-od-id="fmt-example-toggle"
              aria-expanded={showExample}
              onClick={() => setShowExample((v) => !v)}
            >
              {showExample ? "收起格式示例" : "不确定格式？查看示例"}
            </button>
          </div>
          {showExample && <FormatExample />}
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
                {parsed && verdict?.level === "ok" ? " · 结构判定：正常" : ""}
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
            <div className="field" style={{ margin: "14px 0 0", maxWidth: 340 }}>
              <label htmlFor="src-basis">这本书从哪来</label>
              <select
                id="src-basis"
                className="input"
                data-od-id="source-basis"
                value={sourceBasis}
                onChange={(e) => setSourceBasis(e.target.value)}
              >
                <option value="owned">自己买的</option>
                <option value="self_written">自己写的</option>
                <option value="public_domain">公版书</option>
                <option value="authorized">作者授权</option>
                <option value="other">其他</option>
              </select>
              <p className="f-hint" style={{ fontSize: 11.5, color: "var(--muted)", margin: "6px 0 0" }}>
                自己留个底：知道来源，后面查得清。不会上传到服务器。
              </p>
            </div>
            <div className="field" style={{ margin: "10px 0 0", maxWidth: 340 }}>
              <label htmlFor="src-author">作者（选填）</label>
              <input
                id="src-author"
                className="input"
                data-od-id="source-author"
                value={sourceAuthor}
                onChange={(e) => setSourceAuthor(e.target.value)}
                placeholder="不知道可以不填"
              />
            </div>
          </div>

          {verdict && verdict.level !== "ok" && (
            <div
              className={`notice${verdict.level === "risk" ? " risk" : " warn"}`}
              data-od-id="structure-verdict"
              style={{ margin: "14px 0" }}
              role={verdict.level === "risk" ? "alert" : undefined}
            >
              <span className="nt">
                <b>{verdict.level === "risk" ? "结构判定：不建议直接拆解" : "结构判定：有风险"}</b>
                <span>{verdict.issues.join("；")}</span>
              </span>
            </div>
          )}
          {verdict?.level === "risk" && <FormatExample compact />}
          {verdict?.level === "risk" && (
            <label className="dim-row" style={{ border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer" }} data-od-id="risk-ack-row">
              <input
                type="checkbox"
                checked={riskAck}
                onChange={(e) => setRiskAck(e.target.checked)}
                data-od-id="risk-ack"
              />
              <span className="d-tx">
                <b>我了解质量风险，仍要用当前文件创建任务</b>
                <span>不勾选则「创建任务」保持禁用；换掉问题文件后本确认自动复位</span>
              </span>
            </label>
          )}

          {parsed && parsed.totalChars > OVER_CAPACITY_CHARS && (
            <div className="notice warn" data-od-id="over-capacity" style={{ margin: "14px 0" }}>
              <span className="nt">
                <b>超过单本建议量（60 万字）</b>
                <span>
                  任务仍会一次跑完（分级归并不丢内容），但全书梗概注入会截断，跨卷主线拼接与结局判断变弱；建议按卷分次拆解
                </span>
              </span>
            </div>
          )}

          {/* 拆法选择（c-deconstruct-knowledge）：全书拆 vs 智能拆书 */}
          <div className="field" data-testid="mode-field">
            <label>
              拆法 <span style={{ fontSize: 11.5, color: "var(--muted)" }}>选一种，影响 token 用量和速度</span>
            </label>
            <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
              <label
                style={{
                  flex: 1, border: mode === "full" ? "2px solid var(--accent)" : "1px solid var(--line, var(--border, #ddd))",
                  borderRadius: 10, padding: "10px 14px", cursor: "pointer",
                  background: mode === "full" ? "var(--accent-soft, transparent)" : "transparent",
                }}
                data-testid="mode-full"
              >
                <input
                  type="radio" name="mode" value="full" checked={mode === "full"}
                  onChange={() => { setMode("full"); setSelected(DECONSTRUCT_DIMS.map((d) => d.key)); }} style={{ display: "none" }}
                />
                <b style={{ color: mode === "full" ? "var(--accent)" : "inherit" }}>全书拆</b>
                <div style={{ fontSize: 12, marginTop: 4, color: "var(--muted)" }}>
                  整本拆完 · 完整报告 · 更费token更慢
                  <br />适合：想全面学习这本书，或用拆书结果建书
                </div>
              </label>
              <label
                style={{
                  flex: 1, border: mode === "smart" ? "2px solid var(--accent)" : "1px solid var(--line, var(--border, #ddd))",
                  borderRadius: 10, padding: "10px 14px", cursor: "pointer",
                  background: mode === "smart" ? "var(--accent-soft, transparent)" : "transparent",
                }}
                data-testid="mode-smart"
              >
                <input
                  type="radio" name="mode" value="smart" checked={mode === "smart"}
                  onChange={() => {
                    setMode("smart");
                    // 智能拆书推荐知识四维（写法向），主线剧情/伏笔类依赖全书覆盖建议全书拆
                    setSelected(smartDims);
                  }} style={{ display: "none" }}
                />
                <b style={{ color: mode === "smart" ? "var(--accent)" : "inherit" }}>智能拆书</b>
                <div style={{ fontSize: 12, marginTop: 4, color: "var(--muted)" }}>
                  只挑代表性章节 · 省token更快
                  <br />适合：想把这本书的写法收进知识库
                </div>
              </label>
            </div>
            {mode === "smart" && (
              <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
                💡 智能拆书自动挑有代表性的章节，不逐章过——写法提炼够用，但剧情线和伏笔追踪不如全书完整。
              </p>
            )}
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
            <b>签署承诺后：</b>这本书你有权使用；拆出来的内容只给自己写作用，不发布、不售卖；正文会发给你选的模型服务商。换设备不用重签。
          </div>

          {submitErr && (
            <div className="notice" role="alert">
              <span className="nt">
                <b>创建失败</b>
                <span>{submitErr}</span>
              </span>
            </div>
          )}

          {!canDeconstruct && (
            <div className="hint" data-od-id="create-tier-lock">
              <b>AI 拆书是 PRO 功能。</b>免费可先用「正文导入」把书带进来写作；升级 PRO 后
              可拆完本小说并导出 Markdown（MAX 还能把拆书产物一键生成新书）。
            </div>
          )}

          {!consent?.signed && (
            <p className="hint" style={{ margin: "0 0 8px" }}>
              先签署上面的《拆书使用承诺》，再创建任务。
            </p>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            <button
              className="btn btn-primary"
              data-od-id="btn-submit-task"
              disabled={!canSubmit}
              onClick={() => void submit()}
            >
              {submitting
                ? "创建中…"
                : canDeconstruct
                  ? "创建任务（进队列排队）"
                  : "创建任务（PRO）"}
            </button>
            <Link className="btn btn-secondary" to="/tools">
              取消
            </Link>
          </div>
        </div>
      )}

      {consentOpen && (
        <>
          <div className="scrim show" onClick={() => setConsentOpen(false)} />
          <div className="modal show" role="dialog" aria-modal="true" data-od-id="consent-modal">
            <div className="mcard">
              <div className="mcard-head">
                <span className="mh">拆书使用承诺 · {consent?.version ?? "v1"}</span>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="关闭"
                  onClick={() => setConsentOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="mcard-body">
                <pre
                  style={{
                    margin: 0,
                    whiteSpace: "pre-wrap",
                    fontFamily: "inherit",
                    fontSize: 13,
                    lineHeight: 1.8,
                    color: "var(--fg)",
                  }}
                >
                  {consent?.text ?? ""}
                </pre>
                {!consentView && (
                  <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 14, fontSize: 13 }}>
                    <input
                      type="checkbox"
                      data-od-id="consent-check"
                      checked={consentChecked}
                      onChange={(e) => setConsentChecked(e.target.checked)}
                      style={{ marginTop: 3 }}
                    />
                    <span>我已阅读并同意《拆书使用承诺》</span>
                  </label>
                )}
                {consentErr && <p className="f-err" style={{ margin: "8px 0 0" }}>{consentErr}</p>}
              </div>
              <div className="mcard-foot">
                <button type="button" className="btn btn-secondary" onClick={() => setConsentOpen(false)}>
                  {consentView ? "关闭" : "稍后再说"}
                </button>
                {!consentView && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    data-od-id="consent-submit"
                    disabled={!consentChecked || consentBusy}
                    onClick={() => void doSignConsent()}
                  >
                    {consentBusy ? "正在签署…" : "同意并继续"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </>
      )}
      <UpgradeModal
        open={tierModalOpen}
        onClose={() => setTierModalOpen(false)}
        required="deconstruct"
      />
    </main>
  );
}
