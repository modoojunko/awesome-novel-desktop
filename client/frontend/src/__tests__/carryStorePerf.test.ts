import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));

import {
  archiveCarryCandidates,
  hasCarryActionable,
  refreshCarry,
  resetCarryStoreForTests,
} from "@/lib/carryStore";
import type { LegacyStatus } from "@/hooks/useLegacyDb";

/** 候选快照按需刷新＋归档动作（c-carry-candidates-perf）。
 *
 * 口径（db-generation delta）：快照无待办（无未带回且未抑制的可搬运候选）时，
 * 会话内挂载自动刷新跳过请求；用户动作/搬运终局 force 绕过并按新快照重判。
 * 归档＝POST /archive 后强制拉新（归档件退出候选清单）。 */

function status(cands: Array<Record<string, unknown>>): LegacyStatus {
  return { candidates: cands, quarantined: [], current_version: "0.25" } as unknown as LegacyStatus;
}

const pending = { filename: "a.db", stamp: "s", recommended: true, unreadable: false,
                  book_count: 1, carried: false, suppressed: false };
const carried = { ...pending, filename: "b.db", carried: true, suppressed: true };

function ok(data: unknown) {
  return { code: 0, data };
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  resetCarryStoreForTests();
});

describe("候选快照按需刷新（c-carry-candidates-perf）", () => {
  it("无待办快照：会话内挂载自动刷新跳过请求；用户动作/force 绕过", async () => {
    getMock.mockResolvedValue(ok(status([{ ...carried }])));
    await refreshCarry({ auto: true });            // 首拉：无快照必拉
    expect(getMock).toHaveBeenCalledTimes(1);
    await refreshCarry({ auto: true });            // 无待办 → 跳过
    expect(getMock).toHaveBeenCalledTimes(1);
    await refreshCarry();                          // 用户动作（账户菜单）恒拉新
    expect(getMock).toHaveBeenCalledTimes(2);
    await refreshCarry({ auto: true, force: true });
    expect(getMock).toHaveBeenCalledTimes(3);
  });

  it("有待办快照：auto 不降频（挂载继续拉新）", async () => {
    getMock.mockResolvedValue(ok(status([{ ...pending }])));
    await refreshCarry({ auto: true });
    await refreshCarry({ auto: true });
    expect(getMock).toHaveBeenCalledTimes(2);
    expect(hasCarryActionable(status([{ ...pending }]))).toBe(true);
  });

  it("拉取失败：降频标记保持原值，后续挂载仍拉（不吞提醒路径）", async () => {
    getMock.mockRejectedValueOnce(new Error("x"));
    await refreshCarry({ auto: true });            // 失败 → 标记不变（初始未置位）
    getMock.mockResolvedValue(ok(status([{ ...pending }])));
    await refreshCarry({ auto: true });
    expect(getMock).toHaveBeenCalledTimes(2);
    expect(hasCarryActionable(status([{ ...pending }]))).toBe(true);
  });

  it("搬运终局 force 刷新后按新快照重判降频", async () => {
    getMock.mockResolvedValue(ok(status([{ ...pending }])));
    await refreshCarry({ auto: true });
    expect(getMock).toHaveBeenCalledTimes(1);
    getMock.mockResolvedValue(ok(status([{ ...carried }])));
    await refreshCarry({ force: true });           // pollOnce done 回调
    expect(getMock).toHaveBeenCalledTimes(2);
    await refreshCarry({ auto: true });            // 新快照无待办 → 跳过
    expect(getMock).toHaveBeenCalledTimes(2);
    expect(hasCarryActionable(status([{ ...carried }]))).toBe(false);
  });
});

describe("归档动作（c-carry-candidates-perf）", () => {
  it("POST /archive 后强制拉新，返回归档名清单", async () => {
    postMock.mockResolvedValue(ok({ archived: ["b.db"], refused: [] }));
    getMock.mockResolvedValue(ok(status([{ ...carried }])));
    const archived = await archiveCarryCandidates(["b.db"]);
    expect(archived).toEqual(["b.db"]);
    const call = postMock.mock.calls.find((c) => String(c[0]).includes("/archive"));
    expect(call).toBeTruthy();
    expect((call![1] as { filenames: string[] }).filenames).toEqual(["b.db"]);
    expect(getMock).toHaveBeenCalledTimes(1);      // force 拉新
  });

  it("后端拒绝（refused）不进归档名清单；拉新照常", async () => {
    postMock.mockResolvedValue(ok({ archived: [], refused: ["x.db"] }));
    getMock.mockResolvedValue(ok(status([{ ...carried }])));
    const archived = await archiveCarryCandidates(["x.db"]);
    expect(archived).toEqual([]);
    expect(getMock).toHaveBeenCalledTimes(1);
  });
});
