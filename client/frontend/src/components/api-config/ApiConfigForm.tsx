import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ApiConfig, ApiFormat } from "../../types/api-config";
import Modal from "../design/Modal";
import { Ico, P } from "../icons";
import { FORMAT_PLACEHOLDER, VENDOR_FORMAT_LOCK, VENDORS, VENDOR_LABELS, VendorGlyph } from "./ProviderIcon";
import { applyPreset, defaultsFor, type PrefillFields } from "./vendorDefaults";

interface ApiConfigFormProps {
  open: boolean;
  config?: ApiConfig | null; // 有值 = 编辑态
  onSubmit: (data: ApiConfigFormData) => Promise<void>;
  onCancel: () => void;
  onTest?: (data: ApiConfigFormData) => Promise<{
    ok: boolean;
    status: string;
    error?: string;
    note?: string;
    models?: string[];
  }>;
  /** 只拉清单轻探针（c-api-config-auto-models）：Key 失焦/参数变更时自动拉模型清单。 */
  onFetchModels?: (data: {
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: ApiFormat;
  }) => Promise<{
    ok: boolean;
    status?: string;
    models?: string[] | null;
    candidates?: string[];
    note?: string;
    error?: string;
  }>;
}

export interface ApiConfigFormData {
  name: string;
  vendor_id: string;
  base_url: string;
  model: string;
  api_key: string;
  api_format: ApiFormat;
}

/** 添加/编辑配置弹窗（model-config.html modalConfig 原样：520px（ADJUSTMENTS 登记加宽）、vgrid 供应商格、编辑态 vfix） */
export function ApiConfigForm({ open, config, onSubmit, onCancel, onTest, onFetchModels }: ApiConfigFormProps) {
  const isEdit = !!config;
  const [name, setName] = useState(config?.name || "");
  const [vendorId, setVendorId] = useState(config?.vendor || "");
  const [apiFormat, setApiFormat] = useState<ApiFormat>(config?.api_format || "openai");
  const [baseUrl, setBaseUrl] = useState(config?.base_url || "");
  const [modelName, setModelName] = useState("");
  const [apiKey, setApiKey] = useState("");
  // 模型清单自动拉取（c-api-config-auto-models）
  const [modelList, setModelList] = useState<string[]>([]);
  const [modelCandidates, setModelCandidates] = useState<string[]>([]);
  const [modelNote, setModelNote] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchErr, setFetchErr] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  // 当前已应用的预填值（手改判定基准）
  const lastPresetRef = useRef<PrefillFields | null>(null);
  // 用户手选/手填标记：自动默认选中（清单首项）不覆盖手选值
  const modelPickedRef = useRef(false);
  // 模型值镜像（评审 P0：applyAutoSelect 的守卫在 await 恢复后读到的是过期闭包 state，
  // 在途响应会覆盖用户刚手填的值——守卫一律读 ref）
  const modelNameRef = useRef("");
  // 在途请求去重：序号丢弃过期响应（参数已变的旧响应不落地）
  const fetchSeqRef = useRef(0);
  // 最近一次成功拉取的参数指纹：同参数重复触发（如再次失焦）不重拉
  const lastFetchRef = useRef("");
  // 弹层 portal 节点（评审 P1：Modal 的 .mcard overflow 会裁剪卡内浮层，照 Modal 自身
  // 先例 portal 到 body；滚动/resize 重锚，外点用 pointerdown 关）
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** 模型值单一写口：state 与 ref 镜像同步（异步回调里守卫/判定读 ref 不踩闭包过期值）。 */
  const setModel = (v: string) => {
    modelNameRef.current = v;
    setModelName(v);
  };

  // 弹窗常挂载（Modal 退场动画需要），切换编辑目标/重开新建时在渲染期重置表单
  const formKey = config?.id ?? "new";
  const [trackedKey, setTrackedKey] = useState(formKey);
  if (formKey !== trackedKey) {
    setTrackedKey(formKey);
    setName(config?.name || "");
    setVendorId(config?.vendor || "");
    setApiFormat(config?.api_format || "openai");
    setBaseUrl(config?.base_url || "");
    setModel("");
    setApiKey("");
    setError(null);
    setTestResult(null);
    lastPresetRef.current = null;
    setModelList([]);
    setModelCandidates([]);
    setModelNote(null);
    setFetchErr(null);
    setFetching(false);
    setPickerOpen(false);
    setPanelPos(null);
    modelPickedRef.current = false;
    fetchSeqRef.current += 1; // 在途响应作废
    lastFetchRef.current = ""; // 拉取指纹随表单重置
  }

  // 接口格式锁定矩阵：单格式厂商锁定（openai/anthropic/ollama），双格式可切换
  const formatLock = VENDOR_FORMAT_LOCK[vendorId as keyof typeof VENDOR_FORMAT_LOCK];

  // 2026-10-05 拍板：选已知供应商预填 Base URL＋模型名称（空或仍为预填值才覆盖、
  // 手改不劫持）；登记值见 vendorDefaults（取代 09-06「URL 不预填」）
  // 2026-10-07：模型值参与覆盖判定的只有手选/手填值——自动拉取默认选中的值（清单首项）
  // 不算手改，切供应商时随之更新（modelPickedRef 区分）
  const prefillTo = (vendor: string, fmt: ApiFormat) => {
    const next = defaultsFor(vendor, fmt);
    const out = applyPreset(
      { base_url: baseUrl.trim(), model: modelPickedRef.current ? modelNameRef.current.trim() : "" },
      lastPresetRef.current,
      next,
    );
    setBaseUrl(out.base_url);
    setModel(out.model);
    lastPresetRef.current = next;
    return out;
  };

  /** 默认选中（2026-10-07 二次拍板「默认选第一个就好，不评估价值」）：清单首项，
   *  登记默认模型不优先（预填值只作清单到位前的初值）。手选/手填（非空）不覆盖——
   *  守卫读 modelNameRef（评审 P0：读闭包 state 会在途覆盖用户刚手填的值）。 */
  const applyAutoSelect = (models: string[]) => {
    if (models.length === 0) return;
    if (modelPickedRef.current && modelNameRef.current.trim()) return;
    setModel(models[0]);
  };

  /** 只拉清单轻探针：precondition 不满足时静默跳过；同参数成功后不重复拉（force 重拉）。 */
  const runFetchModels = async (
    params: { vendor_id: string; base_url: string; api_key: string; api_format: ApiFormat },
    opts?: { force?: boolean },
  ) => {
    if (isEdit || !onFetchModels) return;
    if (!params.vendor_id || !params.base_url.trim()) return;
    /* v8 ignore start -- 防御分支：调用点（失焦/切换）均已前置校验，非 ollama 且空 Key 到不了这里 */
    if (params.vendor_id !== "ollama" && !params.api_key.trim()) return;
    /* v8 ignore stop */
    const fp = `${params.vendor_id}|${params.base_url.trim()}|${params.api_key}|${params.api_format}`;
    if (!opts?.force && fp === lastFetchRef.current) return;
    lastFetchRef.current = fp;
    const seq = ++fetchSeqRef.current;
    setFetching(true);
    setFetchErr(null);
    try {
      const r = await onFetchModels(params);
      if (seq !== fetchSeqRef.current) return; // 过期响应：参数已变，丢弃
      if (r.ok) {
        const models = r.models ?? [];
        setModelList(models);
        setModelCandidates(r.candidates ?? []);
        setModelNote(r.note ?? null);
        applyAutoSelect(models);
      } else {
        lastFetchRef.current = ""; // 失败允许原参数重试
        setFetchErr(r.error || "模型清单获取失败");
      }
    } catch {
      if (seq !== fetchSeqRef.current) return;
      lastFetchRef.current = "";
      setFetchErr("模型清单获取失败");
    } finally {
      if (seq === fetchSeqRef.current) setFetching(false);
    }
  };

  /** 供应商/格式切换：旧端点的清单/候选/说明全部作废（含在途响应——评审 P1：
   *  只清 state 不作废在途请求，旧供应商的响应会在无新请求顶替时照常落地）；
   *  拉取指纹一并作废——切回同参数供应商时清单已被清空，须重拉而不是被指纹挡掉。 */
  const invalidateModelList = () => {
    setModelList([]);
    setModelCandidates([]);
    setModelNote(null);
    setFetchErr(null);
    setFetching(false); // 在途请求被作废后无人清 fetching（评审整改补），就地复位
    lastFetchRef.current = "";
    fetchSeqRef.current += 1; // 在途旧响应作废
  };

  const curFetchParams = () => ({
    vendor_id: vendorId,
    base_url: baseUrl.trim(),
    api_key: apiKey,
    api_format: apiFormat,
  });

  const handleVendorSelect = (id: string) => {
    /* v8 ignore start -- 防御分支：编辑态不渲染 .vgrid（改渲染 .vfix），无触发路径 */
    if (isEdit) return;
    /* v8 ignore stop */
    setVendorId(id);
    const lock = VENDOR_FORMAT_LOCK[id as keyof typeof VENDOR_FORMAT_LOCK];
    const fmt = lock ?? apiFormat;
    if (lock) setApiFormat(lock);
    setTestResult(null);
    invalidateModelList();
    const out = prefillTo(id, fmt);
    // Key 已填（或 ollama 免 Key）即按新供应商重拉清单（预填的 base 同步生效）
    if (apiKey.trim() || id === "ollama") {
      void runFetchModels({ vendor_id: id, base_url: out.base_url, api_key: apiKey, api_format: fmt });
    }
  };

  const handleFormatSelect = (fmt: ApiFormat) => {
    if (formatLock || fmt === apiFormat) return;
    setApiFormat(fmt);
    setTestResult(null);
    invalidateModelList();
    const out = prefillTo(vendorId, fmt);
    if (apiKey.trim() || vendorId === "ollama") {
      void runFetchModels({ vendor_id: vendorId, base_url: out.base_url, api_key: apiKey, api_format: fmt });
    }
  };

  const validate = (): string | null => {
    if (!name.trim()) return "请输入配置名称";
    if (!vendorId) return "请选择供应商";
    if (!baseUrl.trim()) return "请输入 Base URL";
    // 编辑态留空 = 保留当前密钥；Ollama 本地模型免 Key
    if (vendorId !== "ollama" && !isEdit && !apiKey.trim()) return "请输入 API Key";
    return null;
  };

  const handleTest = async () => {
    const err = validate();
    setError(err);
    if (err || !onTest) return;
    setTesting(true);
    setTestResult(null);
    try {
      const r = await onTest({
        name: name.trim(),
        vendor_id: vendorId,
        base_url: baseUrl.trim(),
        model: modelName.trim(),
        api_key: apiKey,
        api_format: apiFormat,
      });
      const noModels = r.ok && (r.models ?? []).length === 0 && !!r.note;
      setTestResult({
        ok: r.ok,
        message: r.ok ? (noModels ? r.note! : "连接正常") : r.error || "测试失败",
      });
      // 双保险：测试连接拉回的清单同步刷新选择器——失败信封也带清单（后端自恢复口径），
      // 连接失败但清单真实时仍更新选项让用户能改选；同时清旧失败态并写同参指纹（评审 P2）
      if ((r.models ?? []).length > 0) {
        setModelList(r.models!);
        setModelCandidates([]);
        setModelNote(null);
        setFetchErr(null);
        lastFetchRef.current = `${vendorId}|${baseUrl.trim()}|${apiKey}|${apiFormat}`;
        if (r.ok) applyAutoSelect(r.models!);
      }
    } catch {
      setTestResult({ ok: false, message: "测试请求失败" });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    setError(err);
    if (err) return;
    setSaving(true);
    try {
      await onSubmit({ name: name.trim(), vendor_id: vendorId, base_url: baseUrl.trim(), model: modelName.trim(), api_key: apiKey, api_format: apiFormat });
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const keyPlaceholder =
    vendorId === "ollama"
      ? "Ollama 不需要 API Key"
      : isEdit
        ? "留空则保留当前密钥"
        : "sk-...";

  // ── 模型选择器（组合框：输入框即搜索框；清单来自轻探针自动拉取） ──────────────
  const modelFilter = modelName.trim().toLowerCase();
  const filteredModels = modelList.filter((m) => m.toLowerCase().includes(modelFilter));

  const pickModel = (m: string) => {
    setModel(m);
    modelPickedRef.current = true;
    setPickerOpen(false);
  };

  const onModelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return; // IME 组合期方向键/Enter 归输入法选词（评审 P2）
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !pickerOpen) {
      setPickerOpen(true);
      return;
    }
    if (!pickerOpen) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, filteredModels.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      // 弹层开着且有可选项：Enter＝选中（吞掉，防止触发表单提交）；无匹配则放行为手填值。
      // cursor 钳位到过滤后区间（onChange 已重置，防越界兜底）
      const pick = filteredModels[Math.min(cursor, filteredModels.length - 1)];
      if (pick) {
        e.preventDefault();
        pickModel(pick);
      }
    } else if (e.key === "Escape") {
      // 只收弹层，不把整个表单弹窗一起关掉（Modal 在 window 上听 Esc——评审 P1）
      e.stopPropagation();
      setPickerOpen(false);
    }
  };

  const metaTone = fetching ? "" : fetchErr || (!modelList.length && modelNote) ? "warn" : modelList.length ? "ok" : "";
  const metaText = fetching
    ? "正在获取模型清单…"
    : fetchErr
      ? "清单获取失败"
      : modelList.length
        ? `已拉到 ${modelList.length} 个模型`
        : modelNote
          ? "无模型清单"
          : "";

  // 弹层定位（评审 P1：portal 出 .mcard 滚动容器后用 fixed 锚输入框矩形；
  // 随滚动/resize 重锚，近视口底缘向上翻转——266≈弹层最大高＋边距）
  useEffect(() => {
    if (!pickerOpen) return;
    const anchor = () => {
      const el = document.getElementById("cfModel");
      /* v8 ignore start -- 防御分支：卸载竞态下滚动回调时输入框已不在文档 */
      if (!el) return;
      /* v8 ignore stop */
      const r = el.getBoundingClientRect();
      const belowFits = r.bottom + 6 + 266 <= window.innerHeight;
      setPanelPos({
        top: belowFits ? r.bottom + 6 : Math.max(8, r.top - 6 - 266),
        left: r.left,
        width: r.width,
      });
    };
    anchor();
    window.addEventListener("scroll", anchor, true);
    window.addEventListener("resize", anchor);
    return () => {
      window.removeEventListener("scroll", anchor, true);
      window.removeEventListener("resize", anchor);
    };
  }, [pickerOpen]);

  // 外点关闭：pointerdown 落在输入框与弹层之外即收起（点非聚焦区域不触发 blur，旧
  // relatedTarget 方案关不掉——评审 P1）；弹层内部 mousedown 已整体 preventDefault 不抢焦点
  useEffect(() => {
    if (!pickerOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (document.getElementById("cfModel")?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      setPickerOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [pickerOpen]);

  return (
    <Modal
      open={open}
      onClose={onCancel}
      locked={saving}
      width={520}
      title={isEdit ? "编辑配置" : "添加 API Key"}
      footer={
        <>
          <button
            className="btn btn-secondary"
            type="button"
            onClick={handleTest}
            disabled={testing || saving}
          >
            {testing ? (
              <>
                <Ico d={P.spinner} sw={2.4} className="spin" />
                测试中…
              </>
            ) : (
              "测试连接"
            )}
          </button>
          <button className="btn btn-secondary" type="button" onClick={onCancel} disabled={saving}>
            取消
          </button>
          <button className="btn btn-primary" type="submit" form="api-config-form" disabled={saving}>
            {isEdit ? "保存" : "保存并测试连接"}
          </button>
        </>
      }
    >
      <form id="api-config-form" onSubmit={handleSubmit}>
        {error && <div className="ferr">{error}</div>}
        <div className="field">
          <label htmlFor="cfName">
            配置名称 <span className="req">*</span>
          </label>
          <input
            className="input"
            id="cfName"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：主线 · OpenAI"
            maxLength={30}
            disabled={saving}
          />
        </div>
        <div className="field">
          <label>供应商</label>
          {!isEdit ? (
            <div className="vgrid">
              {VENDORS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className={"vbtn" + (vendorId === v.id ? " on" : "")}
                  aria-pressed={vendorId === v.id}
                  onClick={() => handleVendorSelect(v.id)}
                >
                  <VendorGlyph vendor={v.id} />
                  <span>{v.label}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="vfix">
              <VendorGlyph vendor={config!.vendor} />
              <span>{VENDOR_LABELS[config!.vendor]}</span>
            </div>
          )}
        </div>
        <div className="field">
          <div className="label-row">
            <label htmlFor="cfBase">
              Base URL <span className="req">*</span>
            </label>
            <div className={"seg" + (formatLock ? " lock" : "")} role="group" aria-label="接口格式">
              <button
                type="button"
                className={apiFormat === "openai" ? "on" : ""}
                disabled={!!formatLock && formatLock !== "openai"}
                aria-pressed={apiFormat === "openai"}
                onClick={() => handleFormatSelect("openai")}
              >
                OpenAI 格式
              </button>
              <button
                type="button"
                className={apiFormat === "anthropic" ? "on" : ""}
                disabled={!!formatLock && formatLock !== "anthropic"}
                aria-pressed={apiFormat === "anthropic"}
                onClick={() => handleFormatSelect("anthropic")}
              >
                Anthropic 格式
              </button>
            </div>
          </div>
          <input
            className="input mono"
            id="cfBase"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            onBlur={() => {
              // Base URL 敲定即拉清单（ollama 免 Key 的主触发点；其他供应商 Key 已填时同样生效）
              if (!isEdit && baseUrl.trim() && (vendorId === "ollama" || apiKey.trim())) {
                void runFetchModels(curFetchParams());
              }
            }}
            placeholder={FORMAT_PLACEHOLDER[apiFormat]}
            disabled={saving}
          />
          {vendorId === "openai-compat" && (
            <p className="cf-hint">
              未列厂商（如 Google Gemini）走 OpenAI 兼容模版：Gemini 官方兼容地址{" "}
              <code>https://generativelanguage.googleapis.com/v1beta/openai/</code>
              （配 Gemini API Key）。该类地址可能拉不到模型清单，手填模型 id（如
              gemini-2.5-pro）即可；国外厂商也可把 Base URL 填成反代/转发服务地址
              （OpenAI、Anthropic 等按钮同样支持改地址指向反代）。
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="cfKey">API Key</label>
          <input
            className="input mono"
            id="cfKey"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onBlur={() => {
              // Key 失焦且非空＝自动拉清单的主触发点（2026-10-07 拍板：配完 Key 自动弹清单）
              if (!isEdit && vendorId !== "ollama" && apiKey.trim()) {
                void runFetchModels(curFetchParams());
              }
            }}
            placeholder={keyPlaceholder}
            disabled={saving || vendorId === "ollama"}
          />
          {isEdit && config?.api_key_masked && (
            <span className="alt">当前密钥：{config.api_key_masked}</span>
          )}
        </div>
        {!isEdit && (
          <div className="field">
            <div className="label-row">
              <label htmlFor="cfModel">模型名称</label>
              {metaText && (
                <span className={"mp-meta" + (metaTone ? ` ${metaTone}` : "")}>{metaText}</span>
              )}
            </div>
            <div className="mp-wrap">
              <input
                className="input mono"
                id="cfModel"
                role="combobox"
                aria-expanded={pickerOpen}
                aria-controls="cf-model-list"
                aria-autocomplete="list"
                aria-activedescendant={pickerOpen && filteredModels.length ? `cf-model-opt-${cursor}` : undefined}
                autoComplete="off"
                spellCheck={false}
                value={modelName}
                onChange={(e) => {
                  setModel(e.target.value);
                  modelPickedRef.current = true; // 手填＝手选：默认选中不再覆盖
                  setPickerOpen(true);
                  setCursor(0);
                }}
                onFocus={() => setPickerOpen(true)}
                onClick={() => setPickerOpen(true)} // 选中后焦点仍在输入框，再点可重开弹层（评审 P2）
                onKeyDown={onModelKeyDown}
                placeholder={
                  vendorId === "ollama"
                    ? "选定后自动列出本地模型；也可手动输入"
                    : "填 Key 后自动获取清单；也可直接输入模型 id"
                }
                disabled={saving}
              />
              {fetchErr && !fetching && (
                <div className="mp-err" role="alert">
                  <span>{fetchErr}</span>
                  <button
                    type="button"
                    className="mp-retry"
                    onClick={() => void runFetchModels(curFetchParams(), { force: true })}
                  >
                    重新拉取
                  </button>
                </div>
              )}
              {pickerOpen &&
                panelPos &&
                createPortal(
                  <div
                    className="mp-panel"
                    id="cf-model-list"
                    role="listbox"
                    aria-label="模型清单"
                    ref={panelRef}
                    style={{ position: "fixed", top: panelPos.top, left: panelPos.left, width: panelPos.width, zIndex: 70 }}
                    onMouseDown={(e) => e.preventDefault()} // 滚动条/说明区拖点不抢焦点不误关（评审 P1）
                  >
                    {modelNote && <div className="mp-note">{modelNote}</div>}
                    {modelCandidates.length > 0 && (
                      <div className="mp-chips">
                        {modelCandidates.map((c) => (
                          <button
                            key={c}
                            type="button"
                            className="mp-cap"
                            tabIndex={-1}
                            onClick={() => pickModel(c)}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                    )}
                    {fetching && <div className="mp-empty">正在获取模型清单…</div>}
                    {!fetching && filteredModels.length === 0 && (
                      <div className="mp-empty">
                        {modelList.length > 0
                          ? "没有匹配的模型 id，换个词试试"
                          : fetchErr
                            ? "清单拉取失败——可手填模型 id，或点「重新拉取」"
                            : modelNote
                              ? "暂无模型清单——可手动填模型 id（说明见上）"
                              : "暂无模型清单——填好 Key 后自动获取"}
                      </div>
                    )}
                    {!fetching && filteredModels.length > 0 && (
                      <ul className="mp-list">
                        {filteredModels.map((m, i) => (
                          <li key={m}>
                            <button
                              type="button"
                              role="option"
                              id={`cf-model-opt-${i}`}
                              aria-selected={m === modelName}
                              tabIndex={-1}
                              className={"mp-item" + (i === cursor ? " cur" : "") + (m === modelName ? " on" : "")}
                              onMouseEnter={() => setCursor(i)}
                              onClick={() => pickModel(m)}
                            >
                              {m}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>,
                  document.body,
                )}
            </div>
          </div>
        )}
        {testResult && (
          <div className={"tresult " + (testResult.ok ? "ok" : "bad")}>{testResult.message}</div>
        )}
      </form>
    </Modal>
  );
}
