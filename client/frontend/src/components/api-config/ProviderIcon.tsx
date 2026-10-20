import type { ApiFormat, VendorId } from "../../types/api-config";
import { Ico, VENDOR_ICON } from "../icons";

/** 供应商分组页签（c-modelconfig-gemini-go）：官方厂商｜中转 · 订阅制 */
export type VendorTab = "official" | "relay";

export const VENDOR_TABS: Array<{ id: VendorTab; label: string }> = [
  { id: "official", label: "官方厂商" },
  { id: "relay", label: "中转 · 订阅制" },
];

export interface VendorEntry {
  id: VendorId;
  label: string;
  tab: VendorTab;
  /** 中转方块的第二行（如「通用」「Claude 系」）；官方厂商无副标 */
  sub?: string;
  /** 「新」角标（本期新增方块） */
  badge?: string;
}

export const VENDORS: VendorEntry[] = [
  { id: "openai", label: "OpenAI", tab: "official" },
  { id: "anthropic", label: "Anthropic", tab: "official" },
  { id: "deepseek", label: "DeepSeek", tab: "official" },
  { id: "glm", label: "GLM", tab: "official" },
  { id: "kimi", label: "Kimi", tab: "official" },
  { id: "qwen", label: "Qwen", tab: "official" },
  { id: "ollama", label: "Ollama", tab: "official" },
  { id: "gemini", label: "Gemini", tab: "official", badge: "新" },
  { id: "opencode-go-chat", label: "OpenCode Go", tab: "relay", sub: "通用", badge: "新" },
  { id: "opencode-go-claude", label: "OpenCode Go", tab: "relay", sub: "Claude 系", badge: "新" },
  { id: "openai-compat", label: "OpenAI 兼容", tab: "relay" },
];

// 接口格式锁定矩阵（拍板 09-06）：单格式厂商锁定，双格式厂商可切换；
// 不在表内 = 双格式可选。placeholder 随格式给示例域名（openai 版含 /v1——与生成调用
// 同源显式表达实际请求地址，SDK 侧另有同源版本段归一兜底，2026-10-08 修正）。
export const VENDOR_FORMAT_LOCK: Partial<Record<VendorId, ApiFormat>> = {
  openai: "openai",
  anthropic: "anthropic",
  ollama: "openai",
  gemini: "openai",
  "opencode-go-chat": "openai",
  "opencode-go-claude": "anthropic",
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
  gemini: "Gemini",
  "opencode-go-chat": "OpenCode Go · 通用",
  "opencode-go-claude": "OpenCode Go · Claude 系",
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
