import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import {
  importOwnParse,
  importOwnPersist,
  type ImportOwnParseResult,
  type ImportOwnVolumeRange,
} from "@/lib/api";
import { toast } from "@/lib/toast";

interface ImportNovelModalProps {
  open: boolean;
  onClose: () => void;
  onImported: (novelId: string) => void;
  /** 书架已满（免费档达到 max_projects）：第 3 步直接禁用创建 */
  quotaFull?: boolean;
}

type Step = 1 | 2 | 3;

const SAMPLE = `第一卷 风起
第1章 开端
张三出门买药，顺路打听城里的消息。暮色四合，他加快了脚步。

第2章 遇敌
李四拦在巷口，一言不合便动了手。刀光一闪，张三侧身避过。
`;

function rangeText(v: ImportOwnVolumeRange) {
  return `第 ${v.chapter_from}–${v.chapter_to} 章 · ${v.chapter_to - v.chapter_from + 1} 章`;
}

function copyVolumes(vols: ImportOwnVolumeRange[]): ImportOwnVolumeRange[] {
  return vols.map((v) => ({ ...v }));
}

/** 补前置/缺口「正文」卷：parser 若在若干章后才出现第一个卷标题，仍能通过连续覆盖校验。 */
function seedVolumes(vols: ImportOwnVolumeRange[], total: number): ImportOwnVolumeRange[] {
  if (!vols.length) return [];
  const out: ImportOwnVolumeRange[] = [];
  let expected = 1;
  for (const v of vols) {
    if (v.chapter_from > expected) {
      out.push({ title: "正文", chapter_from: expected, chapter_to: v.chapter_from - 1 });
    }
    out.push({ ...v });
    expected = Math.max(expected, v.chapter_to + 1);
  }
  if (expected <= total) out.push({ title: "正文", chapter_from: expected, chapter_to: total });
  return out;
}

/** A 路导入：①选文件 ②确认卷章（连续切分/不导入）③直接导入。 */
export default function ImportNovelModal({
  open,
  onClose,
  onImported,
  quotaFull = false,
}: ImportNovelModalProps) {
  const [step, setStep] = useState<Step>(1);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parsed, setParsed] = useState<ImportOwnParseResult | null>(null);
  const [volumes, setVolumes] = useState<ImportOwnVolumeRange[]>([]);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [name, setName] = useState("");
  const [riskAck, setRiskAck] = useState(false);
  const [error, setError] = useState("");
  const [lastExcluded, setLastExcluded] = useState<{
    volumes: ImportOwnVolumeRange[];
    excluded: Set<number>;
    sourceNo: number;
  } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const importTokenRef = useRef<string>(crypto.randomUUID());
  const lastShaRef = useRef<string>("");
  const splitRef = useRef<HTMLInputElement>(null);
  const [splitNo, setSplitNo] = useState("");
  const parseAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => parseAbortRef.current?.abort(), []);

  const reset = useCallback(() => {
    parseAbortRef.current?.abort();
    parseAbortRef.current = null;
    setStep(1);
    setParsing(false);
    setSaving(false);
    setParsed(null);
    setVolumes([]);
    setExcluded(new Set());
    setName("");
    setRiskAck(false);
    setError("");
    setLastExcluded(null);
    setSplitNo("");
    lastShaRef.current = "";
    importTokenRef.current = crypto.randomUUID();
  }, []);

  const handleClose = useCallback(() => {
    if (saving) return;
    reset();
    onClose();
  }, [saving, reset, onClose]);

  const activeChapters = useMemo(
    () => (parsed ? parsed.chapters.filter((c) => !excluded.has(c.source_no)) : []),
    [parsed, excluded],
  );
  const activeCount = activeChapters.length;
  const displayNo = useCallback(
    (sourceNo: number) => {
      const i = activeChapters.findIndex((c) => c.source_no === sourceNo);
      return i < 0 ? 0 : i + 1;
    },
    [activeChapters],
  );
  const sourceAt = useCallback(
    (activeNo: number) => activeChapters[activeNo - 1],
    [activeChapters],
  );

  const valid = useMemo(() => {
    if (!activeCount || !volumes.length || volumes[0].chapter_from !== 1) return false;
    if (volumes[volumes.length - 1].chapter_to !== activeCount) return false;
    for (let i = 0; i < volumes.length; i++) {
      if (volumes[i].chapter_to < volumes[i].chapter_from) return false;
      if (i > 0 && volumes[i].chapter_from !== volumes[i - 1].chapter_to + 1) return false;
    }
    return true;
  }, [activeCount, volumes]);

  const riskReady = parsed?.risk.level !== "risk" || riskAck;

  const splitNoValid = useMemo(() => {
    const n = parseInt(splitNo, 10);
    return Number.isFinite(n) && n >= 1 && n < activeCount &&
      volumes.some((v) => n >= v.chapter_from && n < v.chapter_to);
  }, [splitNo, activeCount, volumes]);

  const handleFile = useCallback(async (file: File) => {
    setError("");
    // 换文件先清旧 manifest，失败时也不让旧数据被下一步带走。
    setParsed(null);
    setVolumes([]);
    setExcluded(new Set());
    setName("");
    setRiskAck(false);
    setLastExcluded(null);
    setSplitNo("");
    if (!file.name.toLowerCase().endsWith(".txt")) {
      setError("第一期只支持 .txt 文件");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError("文件大小超过 50MB 限制");
      return;
    }
    parseAbortRef.current?.abort();
    const controller = new AbortController();
    parseAbortRef.current = controller;
    setParsing(true);
    try {
      const data = await importOwnParse(file, controller.signal);
      if (controller.signal.aborted) return;
      // 同一文件重试沿用 token（响应丢失可幂等）；换了文件必须换 token，避免命中上一本。
      if (lastShaRef.current && lastShaRef.current !== data.source_sha256) {
        importTokenRef.current = crypto.randomUUID();
      }
      lastShaRef.current = data.source_sha256;
      setParsed(data);
      setVolumes(seedVolumes(data.volumes, data.chapter_count));
      setName(data.title || file.name.replace(/\.txt$/i, "") || "未命名作品");
      setRiskAck(false);
      setExcluded(new Set());
      setLastExcluded(null);
      if (data.risk.level === "risk") {
        setError("");
      }
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : "解析失败，请检查文件格式");
    } finally {
      if (parseAbortRef.current === controller) {
        parseAbortRef.current = null;
        setParsing(false);
      }
    }
  }, []);

  const rebuildAfterExclude = useCallback(
    (sourceNo: number) => {
      if (!sourceAt(1)) return;
      const oldActive = activeChapters.map((c) => c.source_no);
      const oldVols = copyVolumes(volumes);
      setLastExcluded({ volumes: oldVols, excluded: new Set(excluded), sourceNo });
      const nextExcluded = new Set(excluded);
      nextExcluded.add(sourceNo);
      const nextActive = (parsed?.chapters ?? [])
        .filter((c) => !nextExcluded.has(c.source_no))
        .map((c) => c.source_no);
      const nextVols: ImportOwnVolumeRange[] = [];
      oldVols.forEach((v) => {
        const members: number[] = [];
        for (let i = v.chapter_from; i <= v.chapter_to; i++) {
          const src = oldActive[i - 1];
          if (src !== sourceNo) members.push(src);
        }
        if (!members.length) return;
        nextVols.push({
          title: v.title,
          chapter_from: nextActive.indexOf(members[0]) + 1,
          chapter_to: nextActive.indexOf(members[members.length - 1]) + 1,
        });
      });
      setExcluded(nextExcluded);
      setVolumes(nextVols);
    },
    [activeChapters, excluded, parsed, sourceAt, volumes],
  );

  const undoExclude = useCallback(() => {
    if (!lastExcluded) return;
    setVolumes(copyVolumes(lastExcluded.volumes));
    setExcluded(new Set(lastExcluded.excluded));
    setLastExcluded(null);
  }, [lastExcluded]);

  const addVolume = useCallback(() => {
    const m = activeCount;
    if (!m) return;
    if (!volumes.length) {
      setVolumes([{ title: "正文", chapter_from: 1, chapter_to: m }]);
      return;
    }
    // 已有卷时不再自动对半劈最大卷（ADJUSTMENTS 2026-10-20）：分卷只走
    // 「在第N章后分卷」，点「+ 新增卷」聚焦分卷输入框，切哪里由作者指定。
    splitRef.current?.focus();
  }, [activeCount, volumes]);

  const splitAt = useCallback(() => {
    const n = parseInt(splitNo, 10);
    if (!n || n < 1 || n >= activeCount) return;
    const i = volumes.findIndex((v) => n >= v.chapter_from && n < v.chapter_to);
    if (i < 0) return;
    const v = volumes[i];
    const next = copyVolumes(volumes);
    next.splice(i, 1,
      { title: v.title, chapter_from: v.chapter_from, chapter_to: n },
      { title: "", chapter_from: n + 1, chapter_to: v.chapter_to },
    );
    setVolumes(next);
    setSplitNo("");
  }, [activeCount, volumes, splitNo]);

  const shift = useCallback((i: number, delta: -1 | 1) => {
    const next = copyVolumes(volumes);
    const v = next[i];
    const nv = next[i + 1];
    if (!v || !nv) return;
    if (delta < 0) {
      if (v.chapter_to - v.chapter_from + 1 <= 1) return;
      v.chapter_to -= 1;
      nv.chapter_from -= 1;
    } else {
      if (nv.chapter_to - nv.chapter_from + 1 <= 1) return;
      v.chapter_to += 1;
      nv.chapter_from += 1;
    }
    setVolumes(next);
  }, [volumes]);

  const merge = useCallback((i: number) => {
    const next = copyVolumes(volumes);
    if (!next[i] || !next[i + 1]) return;
    next[i].chapter_to = next[i + 1].chapter_to;
    next.splice(i + 1, 1);
    setVolumes(next);
  }, [volumes]);

  const handleNext = useCallback(async () => {
    setError("");
    if (step === 1) {
      if (!parsed) {
        setError("先选择一个 .txt 文件并检查格式");
        return;
      }
      setStep(2);
      return;
    }
    if (step === 2) {
      if (!valid) {
        setError("分卷需要覆盖全部章、每卷至少 1 章");
        return;
      }
      setStep(3);
      return;
    }
    if (!parsed || quotaFull) return;
    setSaving(true);
    try {
      const result = await importOwnPersist({
        import_id: parsed.import_id,
        name: name.trim() || parsed.title || "未命名作品",
        volumes,
        import_token: importTokenRef.current,
        excluded_source_nos: [...excluded],
      });
      toast.success(`《${result.name}》已建好，开始写下一章`);
      reset();
      onImported(result.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败，请重试");
    } finally {
      setSaving(false);
    }
  }, [step, parsed, valid, quotaFull, name, volumes, excluded, reset, onImported]);

  const downloadSample = useCallback(() => {
    const blob = new Blob([SAMPLE], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "导入示例.txt";
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const risk = parsed?.risk;
  const nextLabel =
    step === 1 ? "下一步：确认卷章" : step === 2 ? "下一步：导入方式" : "创建并开始写作";

  return (
    <Modal
      open={open}
      onClose={handleClose}
      locked={saving}
      title="导入我的书"
      width={960}
      footer={
        <>
          {step > 1 && (
            <button className="btn btn-secondary" onClick={() => setStep((s) => (s - 1) as Step)} disabled={saving}>
              上一步
            </button>
          )}
          <button className="btn btn-secondary" onClick={handleClose} disabled={saving}>
            取消
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void handleNext()}
            disabled={
              parsing || saving ||
              (step === 1 && !parsed) ||
              (step === 2 && (!valid || !riskReady)) ||
              (step === 3 && quotaFull)
            }
          >
            {saving ? "正在建书…" : nextLabel}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", gap: 8, marginBottom: 14, fontSize: 12.5, color: "var(--muted)" }}>
        <span style={{ color: step === 1 ? "var(--accent-strong)" : undefined }}>① 选文件</span>
        <span>→</span>
        <span style={{ color: step === 2 ? "var(--accent-strong)" : undefined }}>② 确认卷章</span>
        <span>→</span>
        <span style={{ color: step === 3 ? "var(--accent-strong)" : undefined }}>③ 导入方式</span>
      </div>

      {error && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          <span className="nt"><b>还没有完成</b><span>{error}</span></span>
        </div>
      )}

      {step === 1 && (
        <div>
          <div className="notice info" style={{ marginBottom: 12 }}>
            <span className="nt">
              <b>第一期只支持 .txt</b>
              <span>一册一个文件，≤50MB，不限字数；UTF-8 / GBK / Big5 自动识别。md / docx / epub 暂不支持。</span>
            </span>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,text/plain"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                // 清空 value：同一文件解析失败后重选才会再次触发 change。
                e.target.value = "";
                if (f) void handleFile(f);
              }}
            />
            <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={parsing}>
              {parsing ? "正在检查…" : "选择 .txt 文件"}
            </button>
            <button className="btn btn-secondary" onClick={downloadSample}>
              下载示例 .txt
            </button>
            {parsed && (
              <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
                {parsed.filename} · {parsed.encoding} · {parsed.char_count.toLocaleString()} 字 · {parsed.chapter_count} 章
              </span>
            )}
          </div>
          <div className="panel" style={{ padding: "12px 14px", marginBottom: 12 }}>
            <b>文档格式要求</b>
            <ul style={{ margin: "6px 0 8px 18px", padding: 0, fontSize: 12.5, lineHeight: 1.8 }}>
              <li>章标题独占一行：第X章 / 第X回 / 第X节，行内不跟正文；卷标题同理（可不分卷）。</li>
              <li>纯文本 .txt，用记事本或写作软件「另存为 .txt」；不要带 Word 自动编号。</li>
              <li>建议删除目录页——目录行可能被误认为章标题。</li>
            </ul>
            <pre style={{ margin: 0, padding: 10, background: "var(--fg-soft)", borderRadius: 8, fontSize: 12, overflow: "auto" }}>
              {SAMPLE}
            </pre>
          </div>
          {risk && risk.level !== "ok" && (
            <div className={`notice ${risk.level === "risk" ? "warn" : "warn"}`}>
              <span className="nt">
                <b>{risk.level === "risk" ? "结构风险：几乎无法拆分" : "格式检查通过，有需要注意的地方"}</b>
                <span>{risk.issues.join("；") || "可以继续，拆书质量可能下降。"}</span>
                {risk.level === "risk" && (
                  <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                    <input type="checkbox" checked={riskAck} onChange={(e) => setRiskAck(e.target.checked)} />
                    我了解质量风险，仍要导入
                  </label>
                )}
              </span>
            </div>
          )}
          {risk?.level === "warn" && (
            <div className="hint" style={{ marginTop: 8 }}>{risk.issues.join("；")}</div>
          )}
        </div>
      )}

      {step === 2 && parsed && (
        <div>
          {lastExcluded && (
            <div className="notice info" style={{ marginBottom: 10 }}>
              <span className="nt">
                <span>已不导入第 {lastExcluded.sourceNo} 章；后面的章会按顺序补上。</span>
                <button className="btn btn-ghost btn-sm" onClick={undoExclude}>撤销</button>
              </span>
            </div>
          )}
          {risk?.level !== "ok" && risk && (
            <div className="notice warn" style={{ marginBottom: 10 }}>
              <span className="nt">
                <b>{risk.level === "risk" ? "结构风险：几乎无法拆分" : "有需要注意的地方"}</b>
                <span>{risk.issues.join("；") || "可以继续，拆书质量可能下降。"}</span>
                {risk.level === "risk" && (
                  <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                    <input type="checkbox" checked={riskAck} onChange={(e) => setRiskAck(e.target.checked)} />
                    我了解质量风险，仍要导入
                  </label>
                )}
              </span>
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <p style={{ margin: "0 0 6px", fontSize: 12.5, color: "var(--muted)" }}>
                扫描结果 · {activeCount} 章{excluded.size ? ` · 已忽略 ${excluded.size}` : ""}
              </p>
              <div style={{ maxHeight: 360, overflow: "auto", border: "1px solid var(--border)", borderRadius: 8, padding: 8 }}>
                {parsed.chapters.map((c) => {
                  const ex = excluded.has(c.source_no);
                  const dn = displayNo(c.source_no);
                  return (
                    <div key={c.source_no} style={{ display: "flex", gap: 8, padding: "3px 4px", fontSize: 12, opacity: ex ? 0.5 : 1 }}>
                      <span style={{ width: 24, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>{ex ? "—" : String(dn).padStart(2, "0")}</span>
                      <span style={{ textDecoration: ex ? "line-through" : undefined }}>
                        {c.volume_title ? `${c.volume_title} · ` : ""}第{ex ? c.source_no : dn}章 {c.title}{ex ? "（已忽略）" : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <p style={{ margin: "0 0 6px", fontSize: 12.5, color: "var(--muted)" }}>书目录 · 按章切分</p>
                <button className="btn btn-ghost btn-sm" onClick={addVolume}>+ 新增卷</button>
              </div>
              <div style={{ maxHeight: 360, overflow: "auto", border: "1px solid var(--border)", borderRadius: 8, padding: 8 }}>
                {!volumes.length && (
                  <p className="hint" style={{ margin: 0 }}>右侧还是空的。点「+ 新增卷」得到一卷「正文」，再在第 X 章后分卷。</p>
                )}
                {volumes.map((v, i) => (
                  <div key={`vol-${i}`} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 8, marginBottom: 8 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>第{i + 1}卷</span>
                      <input
                        className="input"
                        style={{ height: 26, fontSize: 12, flex: 1 }}
                        value={v.title}
                        placeholder="卷名（可选）"
                        onChange={(e) => {
                          const next = copyVolumes(volumes);
                          next[i].title = e.target.value;
                          setVolumes(next);
                        }}
                      />
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>
                      <span style={{ flex: 1 }}>{rangeText(v)}</span>
                      {i < volumes.length - 1 && v.chapter_to - v.chapter_from + 1 > 1 && (
                        <button className="btn btn-ghost btn-sm" onClick={() => shift(i, -1)}>◀ 少一章</button>
                      )}
                      {i < volumes.length - 1 && volumes[i + 1].chapter_to - volumes[i + 1].chapter_from + 1 > 1 && (
                        <button className="btn btn-ghost btn-sm" onClick={() => shift(i, 1)}>多一章 ▶</button>
                      )}
                      {i < volumes.length - 1 && (
                        <button className="btn btn-ghost btn-sm" onClick={() => merge(i)}>合并</button>
                      )}
                    </div>
                    {Array.from({ length: v.chapter_to - v.chapter_from + 1 }, (_, k) => {
                      const activeNo = v.chapter_from + k;
                      const src = sourceAt(activeNo);
                      if (!src) return null;
                      return (
                        <div key={activeNo} style={{ display: "flex", gap: 8, alignItems: "center", padding: "2px 0 2px 20px", fontSize: 12 }}>
                          <span style={{ width: 22, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>{String(activeNo).padStart(2, "0")}</span>
                          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            第{activeNo}章 {src.title}
                          </span>
                          <button className="btn btn-ghost btn-sm" onClick={() => rebuildAfterExclude(src.source_no)}>不导入</button>
                        </div>
                      );
                    })}
                  </div>
                ))}
                {volumes.length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 11.5, color: "var(--muted)" }}>在第</span>
                      <input
                        ref={splitRef}
                        className="input"
                        type="number"
                        min={1}
                        max={activeCount}
                        placeholder="如：34"
                        value={splitNo}
                        onChange={(e) => setSplitNo(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && splitNoValid) splitAt();
                        }}
                        style={{ width: 64, height: 26, fontSize: 12 }}
                      />
                      <span style={{ fontSize: 11.5, color: "var(--muted)" }}>章后分卷</span>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={splitAt}
                        disabled={!splitNoValid}
                      >
                        分卷
                      </button>
                    </div>
                    <p style={{ margin: "6px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
                      案例：输入 34 点「分卷」→ 第 1–34 章留在本卷，第 35 章起归入新的一卷。分卷永远按你输入的章号切，不会自动拆。
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {step === 3 && parsed && (
        <div>
          <p className="hint" style={{ marginTop: 0 }}>
            已确认结构：{volumes.length} 卷 {activeCount} 章 · {parsed.char_count.toLocaleString()} 字
          </p>
          {quotaFull && (
            <div className="notice warn" style={{ marginBottom: 12 }}>
              <span className="nt">
                <b>书架已满</b>
                <span>开书前需要先归档或删除一本，或升级套餐。关闭后会丢失本次解析；腾出空位后可重新导入。</span>
                <button className="btn btn-secondary btn-sm" onClick={onClose}>去书架腾位置</button>
              </span>
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div className="panel" style={{ padding: 14 }}>
              <b style={{ fontSize: 15 }}>直接导入（只带正文）</b>
              <p style={{ margin: "6px 0 10px", fontSize: 12.5, color: "var(--muted)" }}>
                立即建书；卷/章/正文就位，设定留空（简介自动识别）。<b>0 token · 只在本机处理，不要求配置 Key。</b>
              </p>
              <p style={{ margin: "0 0 6px", fontSize: 12.5 }}>
                代价：伏笔/钩子/设定变化不会带过来；之后只能手动补设定，不含逐章 AI 补齐。
              </p>
              <div className="field">
                <label>书名 <span className="opt">· 默认取解析书名，可改</span></label>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            </div>
            <div className="panel" style={{ padding: 14, opacity: 0.65 }}>
              <b style={{ fontSize: 15 }}>AI 拆书补充设定</b>{' '}
              <span className="pill">即将开放</span>
              <p style={{ margin: "6px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
                当前版本先支持直接导入；拆书补设定会在后续版本开放，不影响本次导入与续写。
              </p>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
