import type { ApiFormat, VendorId } from "../../types/api-config";

/**
 * 供应商默认值登记表（c-api-config-vendor-defaults，2026-10-05 拍板：
 * 选已知供应商预填 Base URL＋模型名称，用户只填 Key——取代 2026-09-06「URL 不预填」）。
 * 键＝供应商×接口格式；登记纪律＝有据才登记（实测或官方文档核对），无据字段留空、禁编造；
 * 「OpenAI 兼容」等无登记值的供应商不预填。与后端 connection.py VENDOR_MODEL_CANDIDATES
 * 同族（那边是探针兜底候选，登记值变更两处对齐）。
 */
export interface VendorDefault {
  base_url: string;
  model: string;
}

export const VENDOR_DEFAULTS: Partial<Record<VendorId, Partial<Record<ApiFormat, VendorDefault>>>> = {
  // OpenAI/Ollama 2026-10-08 实证修正（c-api-config-foreign-vendors）；2026-10-09 随
  // c-relay-base-normalize 更新理由：SDK 侧对 openai 格式 base 已有同源版本段归一兜底
  // （裸域名补 /v1），登记值仍须含版本段以显式表达实际请求地址（OpenAI 官方 /v1；
  // Ollama 官方 README 同款 /v1；后端 tags 探针会剥尾 /v1）
  openai: { openai: { base_url: "https://api.openai.com/v1", model: "" } },
  anthropic: { anthropic: { base_url: "https://api.anthropic.com", model: "" } },
  // DeepSeek 首批全量（URL 与模型均有实测在案）；×anthropic 无实测端点（实测 404）不登记
  deepseek: {
    openai: {
      base_url: "https://api.deepseek.com",
      model: "deepseek-v4-pro",
    },
  },
  glm: {
    openai: { base_url: "https://open.bigmodel.cn/api/paas/v4", model: "" },
    anthropic: { base_url: "https://open.bigmodel.cn/api/anthropic", model: "" },
  },
  kimi: { openai: { base_url: "https://api.moonshot.cn/v1", model: "" } },
  qwen: { openai: { base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "" } },
  ollama: { openai: { base_url: "http://localhost:11434/v1", model: "" } },
};

const EMPTY_DEFAULT: VendorDefault = { base_url: "", model: "" };

/** 该「供应商×接口格式」的登记值；无登记值返回空（不预填）。 */
export function defaultsFor(vendor: string, format: ApiFormat): VendorDefault {
  const d = VENDOR_DEFAULTS[vendor as VendorId]?.[format];
  return d ? { ...d } : { ...EMPTY_DEFAULT };
}

export interface PrefillFields {
  base_url: string;
  model: string;
}

/**
 * 覆盖规则：字段为空、或仍等于已应用的预填值（用户未手改）时更新为新登记值；
 * 用户手改过的字段不被覆盖。
 */
export function applyPreset(
  current: PrefillFields,
  prevPreset: PrefillFields | null,
  next: PrefillFields,
): PrefillFields {
  const out: PrefillFields = { base_url: current.base_url, model: current.model };
  for (const k of ["base_url", "model"] as const) {
    if (current[k] === "" || (prevPreset !== null && current[k] === prevPreset[k])) {
      out[k] = next[k];
    }
  }
  return out;
}
