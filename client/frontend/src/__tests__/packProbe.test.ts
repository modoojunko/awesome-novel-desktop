// c-pack-modal-dismiss：引导弹窗关闭记忆存取（packProbe 关闭记忆段）——
// 单 key JSON 读写、首装标记装上自愈清除、暂不更新版本锚、坏 JSON/写失败容错。
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearPackInstallDismissed,
  readPackDismissal,
  writePackInstallDismissed,
  writePackUpdateDismissed,
} from "@/lib/packProbe";

describe("引导弹窗关闭记忆（c-pack-modal-dismiss）", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("空存储读出空对象；写入后读回同形", () => {
    expect(readPackDismissal()).toEqual({});
    writePackInstallDismissed();
    expect(readPackDismissal()).toEqual({ install: true });
  });

  it("首装与暂不更新两字段共存互不覆盖", () => {
    writePackInstallDismissed();
    writePackUpdateDismissed("6");
    expect(readPackDismissal()).toEqual({ install: true, updateVersion: "6" });
    writePackUpdateDismissed("7");
    expect(readPackDismissal()).toEqual({ install: true, updateVersion: "7" });
  });

  it("清除首装标记保留版本锚；无标记时清除是无操作", () => {
    writePackInstallDismissed();
    writePackUpdateDismissed("6");
    clearPackInstallDismissed();
    expect(readPackDismissal()).toEqual({ updateVersion: "6" });
    clearPackInstallDismissed();
    expect(readPackDismissal()).toEqual({ updateVersion: "6" });
  });

  it("坏 JSON／非对象 JSON 容错读出空对象", () => {
    window.localStorage.setItem("pack-modal-dismissed", "{oops");
    expect(readPackDismissal()).toEqual({});
    window.localStorage.setItem("pack-modal-dismissed", '"str"');
    expect(readPackDismissal()).toEqual({});
  });

  it("写失败静默不抛（隐私模式形态）", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => writePackInstallDismissed()).not.toThrow();
    spy.mockRestore();
  });
});
