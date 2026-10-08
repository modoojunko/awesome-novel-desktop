// 供应商默认值登记表＋覆盖规则纯函数（c-api-config-vendor-defaults）。
import { describe, expect, it } from "vitest";
import { applyPreset, defaultsFor, VENDOR_DEFAULTS } from "@/components/api-config/vendorDefaults";

describe("vendorDefaults 登记表", () => {
  it("DeepSeek×openai 全量登记（URL＋默认模型）；DeepSeek×anthropic 无实测端点不登记", () => {
    expect(defaultsFor("deepseek", "openai")).toEqual({
      base_url: "https://api.deepseek.com",
      model: "deepseek-v4-pro",
    });
    expect(defaultsFor("deepseek", "anthropic")).toEqual({ base_url: "", model: "" });
  });

  it("GLM 双格式各有登记 URL，模型 id 无据留空", () => {
    expect(defaultsFor("glm", "openai")).toEqual({
      base_url: "https://open.bigmodel.cn/api/paas/v4",
      model: "",
    });
    expect(defaultsFor("glm", "anthropic")).toEqual({
      base_url: "https://open.bigmodel.cn/api/anthropic",
      model: "",
    });
  });

  it("无登记值的供应商（OpenAI 兼容/中转站）与未知键返回空（不预填）", () => {
    expect(defaultsFor("openai-compat", "openai")).toEqual({ base_url: "", model: "" });
    // 中转站站方地址/模型各不相同，无据不登记（c-relay-vendor-entry 沿用登记纪律）
    expect(defaultsFor("relay", "openai")).toEqual({ base_url: "", model: "" });
    expect(defaultsFor("relay", "anthropic")).toEqual({ base_url: "", model: "" });
    expect(defaultsFor("no-such-vendor", "openai")).toEqual({ base_url: "", model: "" });
    expect(VENDOR_DEFAULTS["openai-compat"]).toBeUndefined();
    expect(VENDOR_DEFAULTS["relay"]).toBeUndefined();
  });

  it("登记表所有值非预填即空串（禁编造：无据字段必须为空）", () => {
    for (const byFormat of Object.values(VENDOR_DEFAULTS)) {
      for (const d of Object.values(byFormat || {})) {
        expect(d.base_url).not.toBe("");
        expect(typeof d.model).toBe("string");
      }
    }
  });

  it("OpenAI/Ollama 登记值含版本段（SDK 直拼路径不自补 /v1，2026-10-08 实证修正）", () => {
    expect(defaultsFor("openai", "openai").base_url).toBe("https://api.openai.com/v1");
    expect(defaultsFor("ollama", "openai").base_url).toBe("http://localhost:11434/v1");
  });
});

describe("applyPreset 覆盖规则", () => {
  const next = { base_url: "https://next.example", model: "next-model" };

  it("空字段 → 填入新登记值", () => {
    expect(applyPreset({ base_url: "", model: "" }, null, next)).toEqual(next);
    expect(applyPreset({ base_url: "", model: "" }, { base_url: "p", model: "p" }, next)).toEqual(next);
  });

  it("仍为预填值（未手改）→ 更新为新登记值", () => {
    const prev = { base_url: "https://prev.example", model: "prev-model" };
    expect(applyPreset({ ...prev }, prev, next)).toEqual(next);
  });

  it("用户手改过的字段 → 不覆盖；未手改的同批更新", () => {
    const prev = { base_url: "https://prev.example", model: "prev-model" };
    const out = applyPreset({ base_url: "https://mine.example", model: "prev-model" }, prev, next);
    expect(out).toEqual({ base_url: "https://mine.example", model: "next-model" });
  });

  it("首个选择（无已应用预填）时非空字段也不覆盖", () => {
    expect(applyPreset({ base_url: "https://mine.example", model: "" }, null, next)).toEqual({
      base_url: "https://mine.example",
      model: "next-model",
    });
  });
});
