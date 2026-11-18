// dock 产物卡写回器钉（c-agent-panel-consolidate，review 补测试债）：
// - core_promise 特例：{value,note} dict 拆写两字段（review P2——原实现整 dict
//   塞 core_promise 且丢 note）；其余字段原样直写
// - 角色卡：空书第一张＝主角、非空＝配角（review P3）
// - 世界卡：双层 JSON 串剥壳存纯文本；条目格拒绝直写
// 打桩层＝@/lib/api＋@/lib/charactersApi（与 plotFlow 同款最小桩）。
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));
const charsState = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));
vi.mock("@/lib/charactersApi", () => ({ charactersApi: charsState }));

import {
  writeBackCharacter,
  writeBackSettingsField,
  writeBackWorld,
} from "@/lib/dockWriteBack";

const P = "p1";

beforeEach(() => {
  apiState.get.mockReset();
  apiState.put.mockReset();
  apiState.put.mockResolvedValue({});
  charsState.list.mockReset();
  charsState.create.mockReset();
  charsState.patch.mockReset();
  charsState.create.mockImplementation(async (_p, _n, _o) => ({ id: "new-1" }));
  charsState.patch.mockResolvedValue({});
});

describe("settings 字段卡写回", () => {
  it("core_promise {value,note} dict 拆写两字段（review P2）", async () => {
    apiState.get.mockResolvedValue({ core_promise: "", promise_note: "", forbidden_list: [] });
    await writeBackSettingsField(P, {
      stype: "genre", field: "core_promise",
      value: { value: "以弱破强", note: "读者要看到弱者翻盘" },
    });
    expect(apiState.get).toHaveBeenCalledWith(`/novels/${P}/settings/genre`);
    const putBody = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(putBody.core_promise).toBe("以弱破强");
    expect(putBody.promise_note).toBe("读者要看到弱者翻盘");
    expect(putBody.forbidden_list).toEqual([]); // 既有字段不被破坏
  });

  it("数值/数组字段原样直写（cost_ratio）", async () => {
    apiState.get.mockResolvedValue({ cost_ratio: 5 });
    await writeBackSettingsField(P, { stype: "genre", field: "cost_ratio", value: 7 });
    const putBody = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(putBody.cost_ratio).toBe(7);
  });

  it("core_promise 多看点数组：core_promise 置空、note 拼接（镜像面板多选语义）", async () => {
    apiState.get.mockResolvedValue({ core_promise: "", promise_note: "旧的句子", forbidden_list: [] });
    await writeBackSettingsField(P, {
      stype: "genre", field: "core_promise",
      value: [
        { value: "以弱破强", note: "弱者翻盘" },
        { value: "绝处逢生", note: "死里逃生" },
      ],
    });
    const putBody = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(putBody.core_promise).toBe("");
    expect(putBody.promise_note).toContain("弱者翻盘");
    expect(putBody.promise_note).toContain("死里逃生");
    expect(putBody.forbidden_list).toEqual([]);
  });

  it("单条 dict 无 note：不洗掉既有 promise_note", async () => {
    apiState.get.mockResolvedValue({ core_promise: "", promise_note: "作家已有的一段话" });
    await writeBackSettingsField(P, {
      stype: "genre", field: "core_promise", value: { value: "以弱破强" },
    });
    const putBody = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(putBody.core_promise).toBe("以弱破强");
    expect(putBody.promise_note).toBe("作家已有的一段话");
  });

  it("缺 stype/field/value 拒写", async () => {
    await expect(writeBackSettingsField(P, { stype: "genre", field: "", value: 1 })).rejects.toThrow("写入位置");
    expect(apiState.put).not.toHaveBeenCalled();
  });
});

describe("世界观卡写回", () => {
  it("文本格 merge 单 topic（双层 JSON 串剥壳）", async () => {
    apiState.get.mockResolvedValue({ stage: "灰港", power: "", factions: [] });
    await writeBackWorld(P, { topic: "power", draft: '{"value": "血源共鸣四阶"}' });
    const putBody = apiState.put.mock.calls[0][1] as Record<string, unknown>;
    expect(putBody.power).toBe("血源共鸣四阶");
    expect(putBody.stage).toBe("灰港");
  });

  it("条目格（factions）拒绝文本直写", async () => {
    apiState.get.mockResolvedValue({ factions: [] });
    await expect(writeBackWorld(P, { topic: "factions", draft: "散文草稿" })).rejects.toThrow("条目格");
  });
});

describe("角色卡写回", () => {
  it("空书第一张＝主角", async () => {
    charsState.list.mockResolvedValue({ count: 0, items: [] });
    await writeBackCharacter(P, {
      character_draft: { name: "林野", personality: "冷硬、不圣母" },
    });
    expect(charsState.create).toHaveBeenCalledWith(P, "林野", { role: "主角" });
    expect(charsState.patch).toHaveBeenCalledWith(P, "new-1", "persona", "冷硬、不圣母", 0);
  });

  it("已有卡＝配角", async () => {
    charsState.list.mockResolvedValue({ count: 1, items: [{ id: "c1" }] });
    await writeBackCharacter(P, { character_draft: { name: "阿蓟" } });
    expect(charsState.create).toHaveBeenCalledWith(P, "阿蓟", { role: "配角" });
  });

  it("无 character_draft 拒写", async () => {
    await expect(writeBackCharacter(P, {})).rejects.toThrow("角色草案");
    expect(charsState.create).not.toHaveBeenCalled();
  });
});
