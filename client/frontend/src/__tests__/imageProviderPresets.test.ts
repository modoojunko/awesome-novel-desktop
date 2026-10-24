import { describe, expect, it } from "vitest";
import { IMAGE_PROVIDERS } from "@/lib/imageApi";

// c-model-list-cap-300：火山预设头必须是在役款（/models 实测 260128 已 Retiring、
// flash-260915 在役）。预填值是作家新建配置的起点，退役款会把首发请求引向 410/404。
describe("IMAGE_PROVIDERS 火山预设", () => {
  it("首项为在役的 5-0-flash-260915，旧代次依次兜后", () => {
    const volc = IMAGE_PROVIDERS.find((p) => p.id === "volcengine");
    expect(volc).toBeDefined();
    expect(volc!.models[0]).toBe("doubao-seedream-5-0-flash-260915");
    expect(volc!.models).toContain("doubao-seedream-5-0-260128");
    expect(volc!.models).toContain("doubao-seedream-4-5-251128");
    expect(volc!.models).toContain("doubao-seedream-4-0-250828");
  });

  it("六家齐全且 id 唯一（供应商按钮的渲染契约）", () => {
    expect(IMAGE_PROVIDERS.map((p) => p.id)).toEqual([
      "volcengine", "aliyun", "zhipu", "openai", "minimax", "openai-compat",
    ]);
  });
});
