// AI 辅助·检测族（ai-check / fill-gaps / refine）前端契约测试：
// - ogPatchFromFills：后端 fills → OgForm 补丁（白名单外/已退役键丢弃、行列表拼接）
// - GAP_TO_FILL_KEY：缺口标签键与后端白名单键的映射全覆盖（c-og-slim-v2 两项必填）
// - lib 包装：端点路径与出入参（runAiCheck / fillOutlineGaps / refinePrompt / 采纳保存）
import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_OG_FORM,
  GAP_TO_FILL_KEY,
  ogGaps,
  ogPatchFromFills,
  REQ_FIELDS,
} from "@/components/novel/workbench/chapterForm";

const apiState = vi.hoisted(() => ({
  post: vi.fn(),
  put: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

describe("ogPatchFromFills（后端 fills → 章纲表单补丁）", () => {
  it("字符串/行列表两类各自落位；白名单外与已退役键丢弃", () => {
    const patch = ogPatchFromFills({
      summary: "渡口夜谈",
      characters: ["林晚"],
      changes: ["主角与师父决裂"],
      prohibitions: ["不得提前揭开玉佩来历"],
      mood: "紧张",
      // 已退役键（c-og-slim-v2）：给到了也必须丢弃
      key_points: ["上船", "  ", "验货"],
      location: "临江渡口",
      time: "入夜",
      strategy: "顺着章纲推进",
      detail: "把悬念压在货箱上",
      segments: [{ summary: "上船", target_words: 900 }],
      bogus: "不该出现",
      empty_text: "   ",
    });
    expect(patch).toEqual({
      summary: "渡口夜谈",
      chars: "林晚",
      changes: "主角与师父决裂",
      ban: "不得提前揭开玉佩来历",
      mood: "紧张",
    });
  });

  it("段落规划等退役键不给补丁（补缺产出一律丢弃）", () => {
    expect(ogPatchFromFills({ segments: [] })).toEqual({});
    expect(
      ogPatchFromFills({ segments: [{ summary: "夜谈", target_words: 800 }] }),
    ).toEqual({});
    expect(ogPatchFromFills({ location: "渡口", perspective_guidance: "贴主角" })).toEqual({});
  });

  it("空输入 → 空补丁（不覆盖既有表单）", () => {
    expect(ogPatchFromFills({})).toEqual({});
    expect(ogPatchFromFills({ summary: "", key_points: [] })).toEqual({});
  });

  it("补丁可直接合入 OgForm 并补齐必填缺口（两项全补＝无缺口）", () => {
    const fills = {
      changes: ["拿到货单"],
      mood: "紧张",
    };
    const form = { ...EMPTY_OG_FORM, ...ogPatchFromFills(fills) };
    expect(ogGaps(form)).toEqual([]);
  });
});

describe("GAP_TO_FILL_KEY（缺口 → 后端白名单键）", () => {
  it("两项必填全部有映射，且键在后端白名单口径内（c-og-slim-v2）", () => {
    const backendKeys = new Set([
      "summary",
      "characters",
      "changes",
      "prohibitions",
      "mood",
    ]);
    for (const { key } of REQ_FIELDS) {
      const fillKey = GAP_TO_FILL_KEY[key];
      expect(fillKey, `缺 ${key} 的映射`).toBeTruthy();
      expect(backendKeys.has(fillKey)).toBe(true);
    }
  });
});

describe("lib 包装端点契约", () => {
  it("runAiCheck/fillOutlineGaps/refinePrompt/保存 走各自端点", async () => {
    const {
      runAiCheck,
      fillOutlineGaps,
      refinePrompt,
      saveWritePrompt,
    } = await import("@/lib/aiCheck");

    apiState.post.mockResolvedValueOnce({
      findings: [{ title: "第3段", detail: "人称漂移" }],
    });
    const findings = await runAiCheck("p1", "vol-1-ch-2", "style_consistency");
    expect(apiState.post).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-2/ai-check",
      { kind: "style_consistency" },
    );
    expect(findings).toEqual([{ title: "第3段", detail: "人称漂移" }]);

    apiState.post.mockResolvedValueOnce({ fills: { mood: "紧张" } });
    const fills = await fillOutlineGaps("p1", "vol-1-ch-2", ["mood"]);
    expect(apiState.post).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-2/outline/fill-gaps",
      { missing: ["mood"] },
    );
    expect(fills).toEqual({ mood: "紧张" });

    apiState.post.mockResolvedValueOnce({ prompt: "修订后的提示词" });
    const prompt = await refinePrompt("p1", "vol-1-ch-2", "negative", "原稿");
    expect(apiState.post).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-2/write/prompt/refine",
      { mode: "negative", current_prompt: "原稿" },
    );
    expect(prompt).toBe("修订后的提示词");

    apiState.put.mockResolvedValueOnce({});
    await saveWritePrompt("p1", "vol-1-ch-2", "采纳稿");
    expect(apiState.put).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-2/prompts/write",
      { content: "采纳稿" },
    );
  });

  it("runAiCheck 后端空数组 → 空 findings（不抛）", async () => {
    const { runAiCheck } = await import("@/lib/aiCheck");
    apiState.post.mockResolvedValueOnce({});
    expect(await runAiCheck("p1", "vol-1-ch-2", "hooks_conflict")).toEqual([]);
  });
});
