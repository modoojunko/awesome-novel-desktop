// 归档卡三段进度条（c-ops-archive-stages）：状态矩阵与文案。
// 提取段=archiveJob 态；确认段=dossier GET progress（归档卡常驻拉取）；完成段=archived。
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ArchiveStages, { useElapsedSec } from "@/components/novel/workbench/ArchiveStages";

describe("ArchiveStages 三段进度", () => {
  it("提取中：段1 active 带已运行秒数，确认/完成未点亮", () => {
    render(
      <ArchiveStages extract="active" elapsedSec={42} confirmLabel={null} done={false} />,
    );
    const strip = screen.getByTestId("archive-stages");
    expect(strip.textContent).toContain("提取中");
    expect(strip.textContent).toContain("已 42 秒");
    expect(strip.textContent).toContain("确认");
    const active = strip.querySelector(".is-active")!;
    expect(active.textContent).toContain("提取中");
    expect(strip.querySelectorAll(".is-done")).toHaveLength(0);
  });

  it("已归档有提案：提取✓＋待确认 N 条 active＋完成✓", () => {
    render(
      <ArchiveStages
        extract="done"
        confirmLabel="待确认 3 条"
        confirmActive
        done
      />,
    );
    const strip = screen.getByTestId("archive-stages");
    expect(strip.textContent).toContain("待确认 3 条");
    const actives = strip.querySelectorAll(".is-active");
    expect(actives).toHaveLength(1);
    expect(actives[0].textContent).toContain("确认");
    expect(strip.querySelectorAll(".is-done")).toHaveLength(2);
  });

  it("提案全处理完：确认段转 done；提取失败：段1 fail 红标", () => {
    const { rerender } = render(
      <ArchiveStages extract="done" confirmLabel="提案已处理" done />,
    );
    const strip = screen.getByTestId("archive-stages");
    expect(strip.textContent).toContain("提案已处理");
    expect(strip.querySelectorAll(".is-done")).toHaveLength(3);
    rerender(<ArchiveStages extract="fail" confirmLabel={null} done={false} />);
    expect(strip.querySelector(".is-fail")!.textContent).toContain("失败");
  });

  it("跳过提取：段1 标未提取（skip 态）", () => {
    render(<ArchiveStages extract="skip" confirmLabel={null} done />);
    expect(screen.getByTestId("archive-stages").textContent).toContain("未提取");
  });
});

describe("useElapsedSec", () => {
  it("active 时按 startedAt 走秒；非 active/无起点恒 0", () => {
    const started = Date.now() - 5_000;
    const Host = ({ at, active }: { at: number | undefined; active: boolean }) => {
      const sec = useElapsedSec(at, active);
      return <span data-testid="elapsed">{sec}</span>;
    };
    const { rerender } = render(<Host at={started} active />);
    expect(Number(screen.getByTestId("elapsed").textContent)).toBeGreaterThanOrEqual(4);
    rerender(<Host at={started} active={false} />);
    expect(screen.getByTestId("elapsed").textContent).toBe("0");
    rerender(<Host at={undefined} active />);
    expect(screen.getByTestId("elapsed").textContent).toBe("0");
  });
});
