/**
 * 恢复导入弹窗（backup-restore UX 稿四步：选包→预览→恢复中→完成）。
 * 部分成功=成功主叙事，失败是明细；密钥全程掩码（敏感四层 L4）。
 * 桥接 pick_open_file 选包；parse 预览；persist 逐书原子落库+配置恢复+智能挂回。
 */
import { useState } from "react";
import Modal from "@/components/design/Modal";
import { api, errMessage } from "@/lib/api";
import { getUsername } from "@/lib/auth";
import { BRAND } from "@/lib/brand";

interface ParseBook {
  name: string;
  path: string;
  source_zip: string;
}
interface ParseData {
  books: ParseBook[];
  config: {
    format_version?: number;
    user?: { display_name?: string; api_key?: string; api_base_url?: string; api_model?: string };
    api_configs?: { name: string; api_key: string; models?: string | null }[];
  } | null;
  warnings: string[];
  schema_version: number | null;
}
interface PersistSummary {
  results: { book_id: string; status: string }[];
  warnings: string[];
  reattach: { mode: string; attached: number };
}

type Step = "pick" | "preview" | "working" | "done";

async function pickZip(): Promise<string | null> {
  const bridge = (window as unknown as { pywebview?: { api?: { pick_open_file: (t?: string[]) => Promise<string[]> } } }).pywebview?.api;
  if (!bridge) return null; // 无壳环境（调用方负责提示）
  const files = await bridge.pick_open_file(["zip 文件 (*.zip)", "All files (*)"]);
  return files?.[0] ?? null;
}

export default function RestoreModal({
  open,
  onClose,
  onGoConfig,
}: {
  open: boolean;
  onClose: () => void;
  /** 完成（或用户想手动选配置）时关掉弹窗并跳配置区 */
  onGoConfig: () => void;
}) {
  const [step, setStep] = useState<Step>("pick");
  const [assetsPath, setAssetsPath] = useState<string | null>(null);
  const [configPath, setConfigPath] = useState<string | null>(null);
  const [parseData, setParseData] = useState<ParseData | null>(null);
  const [existingNames, setExistingNames] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  /** 错误块标题：解析与恢复失败共用同一块，文案不能固定成「解析失败」（评审 P2） */
  const [errTitle, setErrTitle] = useState("解析失败");
  const [summary, setSummary] = useState<PersistSummary | null>(null);

  const paths = [assetsPath, configPath].filter((p): p is string => !!p);

  const pick = async (slot: "assets" | "config") => {
    const path = await pickZip();
    if (!path) return;
    if (slot === "assets") setAssetsPath(path);
    else setConfigPath(path);
    if (error) setError(null);
  };

  const toPreview = async () => {
    setError(null);
    try {
      // 走 api 封装（自动带 Authorization；裸 fetch 曾致 401，与下载成稿同一缺陷）
      const d = await api.post("/backup/import/parse", { paths });
      setParseData(d.data);
      // 同名书副本标记：对照现有书目（解析与恢复之间的确认信息）
      try {
        // quiet：可选富化（失败已被显式吞掉）＝静默预取，401 不得踢出用户
        const list = await api.get("/novels", { quiet: true });
        const names: string[] = Array.isArray(list)
          ? list.map((b: { name?: string }) => b.name ?? "")
          : [];
        setExistingNames(new Set(names));
      } catch {
        // 书清单拿不到就不标重名，不阻断恢复
      }
      setStep("preview");
    } catch (e) {
      setErrTitle("解析失败");
      setError(errMessage(e, "备份包解析失败，请确认选择的是本应用导出的文件"));
    }
  };

  const confirmRestore = async () => {
    setError(null);
    setStep("working");
    try {
      const d = await api.post("/backup/import/persist", {
        paths,
        include_config: !!configPath,
      });
      setSummary(d.data);
      setStep("done");
    } catch (e) {
      // 留在预览步：错误块在 preview 分支渲染（旧码回 pick 且标签固定「解析失败」，两处都不对）
      setErrTitle("恢复失败");
      setError(errMessage(e, "恢复失败，请重试"));
      setStep("preview");
    }
  };

  const account = parseData?.config?.user?.display_name || "";
  const me = getUsername() || "";
  const accountMismatch = !!account && !!me && account !== me;
  const okCount = summary?.results.filter((r) => r.status === "ok").length ?? 0;
  const failedList = summary?.results.filter((r) => r.status !== "ok") ?? [];

  const startDisabled = !assetsPath && !configPath;

  return (
    <Modal
      open={open}
      onClose={() => {
        /* v8 ignore start -- 防御分支：locked={step === "working"} 已让 Modal 在恢复中
           拒绝一切关闭路径（遮罩/Esc/X），这里只是二道保险 */
        if (step !== "working") onClose();
        /* v8 ignore stop */
      }}
      title="恢复备份"
      locked={step === "working"}
      width={480}
    >
      {step === "pick" && (
        <div>
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--muted)" }}>
            选择备份包文件（至少一项）。恢复会新增书与配置，不覆盖、不删除现有内容。
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            <Slot
              label="作品备份包"
              hint={`${BRAND.name}-备份-日期.zip 或《书名》-作品包`}
              path={assetsPath}
              onPick={() => pick("assets")}
            />
            <Slot
              label="账号与模型配置包（可选）"
              hint={`${BRAND.name}-备份-配置-日期.zip`}
              path={configPath}
              onPick={() => pick("config")}
            />
            {/* B/S 模式兜底：无原生文件弹窗时手动输入路径（桌面版也可用） */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                className="input"
                placeholder="或输入文件完整路径（浏览器模式）"
                style={{ flex: 1, fontSize: 12.5 }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const v = (e.target as HTMLInputElement).value.trim();
                    if (v) { setAssetsPath(v); setError(null); }
                  }
                }}
              />
              <button
                className="btn btn-sm"
                onClick={(e) => {
                  const input = (e.target as HTMLElement).previousElementSibling as HTMLInputElement;
                  const v = input?.value?.trim();
                  if (v) { setAssetsPath(v); setError(null); }
                }}
              >
                填入作品包
              </button>
            </div>
          </div>
          {error && (
            <div role="alert" style={{ marginTop: 12 }}>
              <span className="pill pill-err">{errTitle}</span>
              <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6, wordBreak: "break-all" }}>{error}</div>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary btn-sm" onClick={onClose}>
              取消
            </button>
            <button className="btn btn-primary btn-sm" disabled={startDisabled} onClick={toPreview}>
              下一步
            </button>
          </div>
        </div>
      )}

      {step === "preview" && parseData && (
        <div>
          {parseData.books.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                作品（{parseData.books.length} 本）
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                {parseData.books.map((b) => (
                  <div key={b.path} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <span>《{b.name}》</span>
                    {existingNames.has(b.name) && <span className="pill pill-warn">与现有书目重名·将以副本恢复</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {parseData.config && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                模型配置（{parseData.config.api_configs?.length ?? 0} 项）
              </div>
              <div style={{ display: "grid", gap: 4 }}>
                {(parseData.config.api_configs ?? []).map((c) => (
                  <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <span>{c.name}</span>
                    <span style={{ color: "var(--muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{c.api_key}</span>
                  </div>
                ))}
              </div>
              {accountMismatch && (
                <div style={{ fontSize: 12.5, color: "var(--warn)", marginTop: 6 }}>
                  备份来自账号「{account}」（当前：{me}），配置仍会作为副本恢复。
                </div>
              )}
            </div>
          )}
          {parseData.warnings.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              {parseData.warnings.map((w) => (
                <div key={w} style={{ fontSize: 12.5, color: "var(--warn)", marginTop: 4 }}>
                  {w}
                </div>
              ))}
            </div>
          )}
          {error && (
            <div role="alert" style={{ marginBottom: 12 }}>
              <span className="pill pill-err">{errTitle}</span>
              <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6, wordBreak: "break-all" }}>{error}</div>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setStep("pick")}>
              上一步
            </button>
            <button className="btn btn-primary btn-sm" onClick={confirmRestore}>
              确认恢复
            </button>
          </div>
        </div>
      )}

      {step === "working" && (
        <div style={{ textAlign: "center", padding: "24px 0" }}>
          <div className="serif" style={{ fontSize: 22, marginBottom: 8 }}>
            恢复中…
          </div>
          <div style={{ fontSize: 13, color: "var(--muted)" }}>正在逐本恢复，请勿关闭窗口</div>
        </div>
      )}

      {step === "done" && summary && (
        <div>
          {okCount > 0 ? (
            <div className="serif" style={{ fontSize: 19, marginBottom: 8 }}>
              已恢复 {okCount} 本书
            </div>
          ) : (
            <div className="serif" style={{ fontSize: 19, marginBottom: 8 }}>
              模型配置已恢复
            </div>
          )}
          {summary.reattach.attached > 0 ? (
            <span className="pill pill-ok">模型配置已接回（{summary.reattach.attached} 本）</span>
          ) : (
            <span className="pill pill-warn">模型配置待选择</span>
          )}
          {failedList.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {failedList.map((f) => (
                <div key={f.book_id} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                  <span className="pill pill-err">失败</span>
                  <span style={{ fontSize: 12.5 }}>{f.book_id}</span>
                </div>
              ))}
            </div>
          )}
          {summary.warnings.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {summary.warnings.map((w) => (
                <div key={w} style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
                  {w}
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                onClose();
                onGoConfig();
              }}
            >
              去检查模型配置
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                setStep("pick");
                onClose();
              }}
            >
              完成
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Slot({
  label,
  hint,
  path,
  onPick,
}: {
  label: string;
  hint: string;
  path: string | null;
  onPick: () => void;
}) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "10px 12px" }}>
      <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{hint}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        <button className="btn btn-secondary btn-sm" onClick={onPick}>
          选择文件
        </button>
        {path && (
          <span style={{ fontSize: 12, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {path}
          </span>
        )}
      </div>
    </div>
  );
}
