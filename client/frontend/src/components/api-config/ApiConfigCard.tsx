import { useState } from "react";
import type { ApiConfig } from "../../types/api-config";
import { ProviderIcon } from "./ProviderIcon";

interface ApiConfigCardProps {
  config: ApiConfig;
  onEdit: (config: ApiConfig) => void;
  onDelete: (config: ApiConfig) => void;
  onTest: (config: ApiConfig) => Promise<{
    ok: boolean;
    status: string;
    error?: string;
    note?: string;
    models?: string[];
  }>;
}

/** 七态徽标（model-config.html STATUS 原样） */
const STATUS: Record<string, { label: string; cls: string }> = {
  ok: { label: "连接正常", cls: "ok" },
  auth_error: { label: "认证失败", cls: "err" },
  timeout: { label: "连接超时", cls: "warn" },
  network_error: { label: "网络错误", cls: "warn" },
  rate_limited: { label: "频率限制", cls: "muted" },
  unknown: { label: "未知", cls: "muted" },
  untested: { label: "未测试", cls: "muted" },
};
const CARD_BORDER: Record<string, string> = {
  auth_error: "b-err",
  timeout: "b-warn",
  network_error: "b-warn",
  rate_limited: "b-muted",
  unknown: "b-muted",
};

export function ApiConfigCard({ config, onEdit, onDelete, onTest }: ApiConfigCardProps) {
  const status = config.last_test_status ?? "untested";
  const st = STATUS[status] || STATUS.untested;
  const [testing, setTesting] = useState(false);
  const [res, setRes] = useState<{ text: string; bad?: boolean } | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setRes({ text: "测试中…" });
    try {
      const r = await onTest(config);
      if (!r.ok) {
        setRes({ text: r.error || "测试失败", bad: true });
      } else if ((r.models ?? config.models ?? []).length === 0 && r.note) {
        // 连接正常但端点不提供模型列表 → 说明原因（否则用户以为「读不到」）
        setRes({ text: r.note });
      } else {
        setRes(null);
      }
    } catch {
      setRes({ text: "测试请求失败", bad: true });
    } finally {
      setTesting(false);
    }
  };

  const models = config.models || [];

  return (
    <div className={"cfg-card " + (CARD_BORDER[status] || "")}>
      <div className="cfg-top">
        <ProviderIcon vendor={config.vendor} />
        <div className="id">
          <div className="nm">{config.name}</div>
          <div className="url">{config.base_url || "（本地）"}</div>
        </div>
        <span className={"b " + st.cls}>{st.label}</span>
      </div>
      <div className="keyline">{config.api_key_masked || "（无需 API Key）"}</div>
      <div className="models">
        {models.slice(0, 5).map((m) => (
          <span key={m} className="m-chip">
            {m}
          </span>
        ))}
        {models.length > 5 && <span className="m-chip more">+{models.length - 5}</span>}
      </div>
      <div className="cfg-foot">
        <span className={"res" + (res?.bad ? " bad" : "")}>{res?.text || ""}</span>
        <div className="cfg-acts">
          <button className="btn btn-ghost btn-sm" onClick={handleTest} disabled={testing}>
            测试连接
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => onEdit(config)}>
            编辑
          </button>
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: "var(--err)" }}
            onClick={() => onDelete(config)}
          >
            删除
          </button>
        </div>
      </div>
    </div>
  );
}
