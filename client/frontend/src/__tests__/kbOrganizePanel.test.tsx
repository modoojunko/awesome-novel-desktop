// 知识整理面板接线测试（c-kb-organize 批D）：状态行/手动触发/待确认清单渲染/
// 关系生效·否决·这条不对/建议采纳·忽略/错误兜底。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  status: vi.fn(),
  findings: vi.fn(),
  run: vi.fn(),
  adoptFinding: vi.fn(),
  ignoreFinding: vi.fn(),
  adoptRelation: vi.fn(),
  rejectRelation: vi.fn(),
  relationFeedback: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, organize: api } };
});

import KbOrganizePanel from "@/components/tools/KbOrganizePanel";

const STATUS = {
  genre: "玄幻",
  running: false,
  last_run: {
    id: "r1", status: "completed", started_at: "2026-11-01T00:00:00",
    finished_at: "2026-11-01T00:01:00", entries_scanned: 4,
    relations_added: 2, error: "",
  },
  pending_relations: 1,
  proposed_findings: 1,
};

const LIST = {
  relations: [
    {
      id: "rel-1", rel_type: "applies_to", from_id: "a", to_id: "b",
      from_title: "打斗手法", to_title: "短句文风",
      confidence: 0.7, note: "打斗适用", evidence: "第3章",
    },
    {
      id: "rel-2", rel_type: "mystery_kind", from_id: "c", to_id: "d",
      from_title: "未知类型", to_title: "缺省臂",
      confidence: 0.5, note: "", evidence: "",
    },
  ],
  findings: [{
    id: "find-1", kind: "merge" as const, subject_id: "a", subject2_id: "b",
    subject_title: "洛九歌", payload: { reason: "同来源（疑似双出口平行条目）" },
  }],
  counts: { relations: 1, findings: 1 },
};

beforeEach(() => {
  api.status.mockResolvedValue(STATUS);
  api.findings.mockResolvedValue(LIST);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbOrganizePanel", () => {
  it("渲染状态行与待确认清单", async () => {
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("待确认 2 项")).toBeTruthy());
    expect(screen.getByText(/扫 4 条/)).toBeTruthy();
    expect(screen.getByText(/打斗手法 → 短句文风/)).toBeTruthy();
    expect(screen.getByText(/洛九歌/)).toBeTruthy();
    expect(screen.getByText(/疑似双出口/)).toBeTruthy();
  });

  it("立即整理调用 run 并刷新", async () => {
    api.run.mockResolvedValue({ status: "completed", relations_added: 3 });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("立即整理")).toBeTruthy());
    fireEvent.click(screen.getByText("立即整理"));
    await waitFor(() => expect(api.run).toHaveBeenCalledWith("玄幻"));
    await waitFor(() => expect(screen.getByText(/新增关系 3 条/)).toBeTruthy());
    expect(api.status.mock.calls.length).toBeGreaterThanOrEqual(2); // 初始＋刷新
  });

  it("关系三操作与建议采纳忽略", async () => {
    api.adoptRelation.mockResolvedValue({ message: "关系已生效" });
    api.rejectRelation.mockResolvedValue({ message: "已否决" });
    api.relationFeedback.mockResolvedValue({ message: "已记录，下次整理会降低同类候选权重" });
    api.adoptFinding.mockResolvedValue({ message: "已合并进「洛九歌」" });
    api.ignoreFinding.mockResolvedValue({ message: "已忽略" });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("生效").length).toBeGreaterThanOrEqual(1));

    fireEvent.click(screen.getAllByText("生效")[0]);
    await waitFor(() => expect(api.adoptRelation).toHaveBeenCalledWith("rel-1"));
    fireEvent.click(screen.getAllByText("否决")[0]);
    await waitFor(() => expect(api.rejectRelation).toHaveBeenCalledWith("rel-1"));
    fireEvent.click(screen.getAllByText("这条不对")[0]);
    await waitFor(() => expect(api.relationFeedback).toHaveBeenCalledWith("rel-1"));
    await waitFor(() => expect(screen.getByText(/降低同类候选权重/)).toBeTruthy());
    fireEvent.click(screen.getAllByText("采纳")[0]);
    await waitFor(() => expect(api.adoptFinding).toHaveBeenCalledWith("find-1"));
    fireEvent.click(screen.getAllByText("忽略")[0]);
    await waitFor(() => expect(api.ignoreFinding).toHaveBeenCalledWith("find-1"));
  });

  it("空清单与错误兜底", async () => {
    api.findings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
    api.status.mockRejectedValue(new Error("加载失败"));
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("加载失败")).toBeTruthy());
    await waitFor(() => expect(screen.getByText(/没有待确认的关系/)).toBeTruthy());
    fireEvent.click(screen.getByText("立即整理"));
    api.run.mockRejectedValue(new Error("整理失败"));
    await waitFor(() => expect(screen.getAllByText(/失败/).length).toBeGreaterThanOrEqual(1));
  });

  it("run skipped 与 rejected 两臂", async () => {
    api.run.mockResolvedValueOnce({ skipped: true, message: "该题材正在整理中，稍后再看结果" });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("立即整理")).toBeTruthy());
    fireEvent.click(screen.getByText("立即整理"));
    await waitFor(() => expect(screen.getByText(/正在整理中/)).toBeTruthy());
    // 第二次：rejected
    fireEvent.click(screen.getByText("立即整理"));
    api.run.mockRejectedValueOnce(new Error("整理失败"));
    await waitFor(() => expect(screen.getByText(/整理失败/)).toBeTruthy());
  });

  it("act 操作失败臂", async () => {
    api.adoptRelation.mockRejectedValue(new Error("操作失败"));
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("生效").length).toBeGreaterThanOrEqual(1));
    const shengxiao = screen.getAllByText("生效");
    fireEvent.click(shengxiao[0]);
    await waitFor(() => expect(screen.getByText(/操作失败/)).toBeTruthy());
  });

  it("关闭按钮回调", async () => {
    const onClose = vi.fn();
    render(<KbOrganizePanel genre="玄幻" onClose={onClose} />);
    await waitFor(() => expect(screen.getByLabelText("关闭")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("KbOrganizePanel 缺省臂大扫除", () => {
  it("load catch 右臂（非 Error 无 message）", async () => {
    api.status.mockRejectedValue("raw-string");
    api.findings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("加载失败")).toBeTruthy());
  });

  it("run catch 右臂（非 Error 无 message）", async () => {
    api.run.mockRejectedValue("raw-string");
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("知识整理").parentElement).toBeTruthy());
    fireEvent.click(screen.getByText("立即整理"));
    await waitFor(() => expect(screen.getByText(/整理失败/)).toBeTruthy());
  });

  it("run skipped 无 message → warn 缺省右臂", async () => {
    api.run.mockResolvedValue({ skipped: true });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("立即整理").length).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getAllByText("立即整理")[0]);
    await waitFor(() => expect(screen.getByText(/正在整理中/)).toBeTruthy());
  });

  it("run ok 无 relations_added → ?? 缺省右臂", async () => {
    api.run.mockResolvedValue({ status: "completed" });
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("立即整理").length).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getAllByText("立即整理")[0]);
    await waitFor(() => expect(screen.getByText(/整理完成/)).toBeTruthy());
  });

  it("run reject 非 Error → err catch 右臂", async () => {
    api.run.mockRejectedValue("raw-string");
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("立即整理").length).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getAllByText("立即整理")[0]);
    await waitFor(() => expect(screen.getByText(/整理失败/)).toBeTruthy());
  });

  it("status.last_run 三态渲染（error/还没跑过/完成）", async () => {
    // 臂1：last_run=null → 「还没跑过」
    api.status.mockResolvedValue({
      genre: "玄幻", running: false, last_run: null, pending_relations: 0, proposed_findings: 0,
    });
    api.findings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
    const { unmount } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/还没跑过/)).toBeTruthy());
    unmount();
    // 臂2：last_run.status=error → 「失败」
    api.status.mockResolvedValue({
      genre: "玄幻", running: false,
      last_run: { id: "r", status: "error", started_at: "", finished_at: "",
        entries_scanned: 0, relations_added: 0, error: "boom" },
      pending_relations: 0, proposed_findings: 0,
    });
    const { unmount: u2 } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/失败/)).toBeTruthy());
    u2();
    // 臂3：completed → 「完成 · 扫 N 条」
    api.status.mockResolvedValue({
      genre: "玄幻", running: false,
      last_run: { id: "r", status: "completed", started_at: "", finished_at: "",
        entries_scanned: 2, relations_added: 1, error: "" },
      pending_relations: 0, proposed_findings: 0,
    });
    const { unmount: u3 } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/完成 · 扫 2 条/)).toBeTruthy());
    u3();
    // 臂4：未知状态（running 等）→ 原样显示状态串（#1002 后的缺省臂）
    api.status.mockResolvedValue({
      genre: "玄幻", running: true,
      last_run: { id: "r", status: "running", started_at: "", finished_at: "",
        entries_scanned: 0, relations_added: 0, error: "" },
      pending_relations: 0, proposed_findings: 0,
    });
    const { unmount: u4 } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/上次整理：running/)).toBeTruthy());
    u4();
  });

  it("act catch 右臂（非 Error 无 message）", async () => {
    api.adoptRelation.mockRejectedValue("raw");
    render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("生效").length).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getAllByText("生效")[0]);
    await waitFor(() => expect(screen.getByText(/操作失败/)).toBeTruthy());
  });

  it("last_run 渲染三态与未知 rel_type 缺省臂", async () => {
    // error 状态臂
    api.status.mockResolvedValue({
      genre: "玄幻", running: false,
      last_run: { id: "r", status: "error", started_at: "", finished_at: "",
        entries_scanned: 0, relations_added: 0, error: "boom" },
      pending_relations: 0, proposed_findings: 0,
    });
    api.findings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
    const { unmount } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("知识整理").parentElement).toBeTruthy());
    unmount();
    // completed 状态臂＋未知 rel_type 行（REL_LABEL 缺省右臂）
    api.status.mockResolvedValue({
      genre: "玄幻", running: false,
      last_run: { id: "r", status: "completed", started_at: "", finished_at: "",
        entries_scanned: 2, relations_added: 1, error: "" },
      pending_relations: 0, proposed_findings: 0,
    });
    api.findings.mockResolvedValue({ relations: [
      { id: "x", rel_type: "future_kind", from_id: "a", to_id: "b",
        from_title: "甲", to_title: "乙", confidence: 0.5, note: "", evidence: "" },
    ], findings: [], counts: { relations: 0, findings: 0 } });
    const { unmount: u2 } = render(<KbOrganizePanel genre="玄幻" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/完成 · 扫 2 条 · 新增关系 1 条/)).toBeTruthy());
    u2();
  });
});
