import { beforeEach, describe, expect, it } from "vitest";
import {
  recordLoreSuggestions,
  getLoreSuggestions,
  dropLoreSuggestion,
  type PendingLore,
} from "@/lib/loreSuggestions";

describe("loreSuggestions 暂存", () => {
  beforeEach(() => sessionStorage.clear());

  it("record 写入 + 同 origin 同 key 去重", () => {
    recordLoreSuggestions("p1", "vol-1-ch-1", [
      { key: "血衣楼", value: "新势力", set: "extra" },
    ]);
    // 同章重放（归档幂等重跑）不重复
    recordLoreSuggestions("p1", "vol-1-ch-1", [
      { key: "血衣楼", value: "新势力", set: "extra" },
    ]);
    const list = getLoreSuggestions("p1");
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ key: "血衣楼", origin: "vol-1-ch-1" });
  });

  it("sessionStorage 兜底：同标签页刷新（新读）不丢", () => {
    recordLoreSuggestions("p2", "vol-2-ch-3", [
      { key: "丹阁大火", value: "三十年前", set: "history" },
    ]);
    // 直接从 sessionStorage 重读（模拟面板挂载）
    const raw = sessionStorage.getItem("lore-suggestions:p2");
    expect(raw).toContain("丹阁大火");
  });

  it("drop 只清本条，其余保留", () => {
    recordLoreSuggestions("p3", "vol-1-ch-1", [
      { key: "甲", value: "a", set: "extra" },
      { key: "乙", value: "b", set: "history" },
    ]);
    const list = getLoreSuggestions("p3") as PendingLore[];
    dropLoreSuggestion("p3", list[0]);
    const rest = getLoreSuggestions("p3");
    expect(rest).toHaveLength(1);
    expect(rest[0].key).toBe("乙");
  });
});
