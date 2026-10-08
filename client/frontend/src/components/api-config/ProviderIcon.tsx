import type { ApiFormat, VendorId } from "../../types/api-config";
import { Ico, VENDOR_ICON } from "../icons";

export const VENDORS = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "glm", label: "GLM" },
  { id: "kimi", label: "Kimi" },
  { id: "qwen", label: "Qwen" },
  { id: "ollama", label: "Ollama" },
  { id: "relay", label: "中转站 API" },
  { id: "openai-compat", label: "OpenAI 兼容" },
] as const;

// 接口格式锁定矩阵（拍板 09-06）：单格式厂商锁定，双格式厂商可切换；
// 不在表内 = 双格式可选。placeholder 随格式给示例域名（openai 版含 /v1——SDK 以
// base_url 直拼路径不自补版本段，登记值/示例域名与生成调用同源，2026-10-08 修正）。
export const VENDOR_FORMAT_LOCK: Partial<Record<VendorId, ApiFormat>> = {
  openai: "openai",
  anthropic: "anthropic",
  ollama: "openai",
};

export const FORMAT_PLACEHOLDER: Record<ApiFormat, string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
};

export const VENDOR_LABELS: Record<VendorId, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  glm: "GLM",
  kimi: "Kimi",
  qwen: "Qwen",
  ollama: "Ollama",
  relay: "中转站 API",
  "openai-compat": "OpenAI 兼容",
};

/** 供应商图标（model-config.html iconSvg 原样：1.7 圆头线帽，尺寸由上下文 CSS 控制） */
export function VendorGlyph({ vendor }: { vendor: string }) {
  return <Ico d={VENDOR_ICON[vendor] || VENDOR_ICON["openai-compat"]} sw={1.7} round />;
}

/** 配置卡左上角的供应商格（.pv-icon 38px） */
export function ProviderIcon({ vendor }: { vendor: VendorId }) {
  return (
    <span className="pv-icon" title={VENDOR_LABELS[vendor] || vendor}>
      <VendorGlyph vendor={vendor} />
    </span>
  );
}
