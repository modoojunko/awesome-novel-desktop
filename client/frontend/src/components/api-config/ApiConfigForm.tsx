import { useState } from "react";
import type { ApiConfig } from "../../types/api-config";
import Modal from "../design/Modal";
import { Ico, P } from "../icons";
import { FORMAT_PLACEHOLDER, VENDOR_FORMAT_LOCK, VENDORS, VENDOR_LABELS, VendorGlyph } from "./ProviderIcon";
import type { ApiFormat } from "../../types/api-config";

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
}

export interface ApiConfigFormData {
  name: string;
  vendor_id: string;
  base_url: string;
  api_key: string;
  api_format: ApiFormat;
}

/** 添加/编辑配置弹窗（model-config.html modalConfig 原样：520px（ADJUSTMENTS 登记加宽）、vgrid 供应商格、编辑态 vfix） */
export function ApiConfigForm({ open, config, onSubmit, onCancel, onTest }: ApiConfigFormProps) {
  const isEdit = !!config;
  const [name, setName] = useState(config?.name || "");
  const [vendorId, setVendorId] = useState(config?.vendor || "");
  const [apiFormat, setApiFormat] = useState<ApiFormat>(config?.api_format || "openai");
  const [baseUrl, setBaseUrl] = useState(config?.base_url || "");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 弹窗常挂载（Modal 退场动画需要），切换编辑目标/重开新建时在渲染期重置表单
  const formKey = config?.id ?? "new";
  const [trackedKey, setTrackedKey] = useState(formKey);
  if (formKey !== trackedKey) {
    setTrackedKey(formKey);
    setName(config?.name || "");
    setVendorId(config?.vendor || "");
    setApiFormat(config?.api_format || "openai");
    setBaseUrl(config?.base_url || "");
    setApiKey("");
    setError(null);
    setTestResult(null);
  }

  // 接口格式锁定矩阵：单格式厂商锁定（openai/anthropic/ollama），双格式可切换
  const formatLock = VENDOR_FORMAT_LOCK[vendorId as keyof typeof VENDOR_FORMAT_LOCK];

  // 拍板（09-06）：URL 不预填——选供应商、切格式都不改动输入框，仅联动格式与占位
  const handleVendorSelect = (id: string) => {
    if (isEdit) return;
    setVendorId(id);
    const lock = VENDOR_FORMAT_LOCK[id as keyof typeof VENDOR_FORMAT_LOCK];
    if (lock) setApiFormat(lock);
    setTestResult(null);
  };

  const handleFormatSelect = (fmt: ApiFormat) => {
    if (formatLock || fmt === apiFormat) return;
    setApiFormat(fmt);
    setTestResult(null);
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
        api_key: apiKey,
        api_format: apiFormat,
      });
      const noModels = r.ok && (r.models ?? []).length === 0 && !!r.note;
      setTestResult({
        ok: r.ok,
        message: r.ok ? (noModels ? r.note! : "连接正常") : r.error || "测试失败",
      });
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
      await onSubmit({ name: name.trim(), vendor_id: vendorId, base_url: baseUrl.trim(), api_key: apiKey, api_format: apiFormat });
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
            placeholder={FORMAT_PLACEHOLDER[apiFormat]}
            disabled={saving}
          />
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
            placeholder={keyPlaceholder}
            disabled={saving || vendorId === "ollama"}
          />
          {isEdit && config?.api_key_masked && (
            <span className="alt">当前密钥：{config.api_key_masked}</span>
          )}
        </div>
        {testResult && (
          <div className={"tresult " + (testResult.ok ? "ok" : "bad")}>{testResult.message}</div>
        )}
      </form>
    </Modal>
  );
}
