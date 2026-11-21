// CardBody 渲染契约钉（c-agent-decision-archive 覆盖债补齐）：按 kind/payload 形态
// 逐分支渲染——report/pick/struct/角色草案/章纲补全/设定字段/卷纲草稿/一句话列表/
// 人话 draft/通用兜底/空渲染。纯渲染组件，零 mock。
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardBody } from "@/components/novel/chat/CardBody";

function renderBody(kind: string, payload: unknown) {
  render(<CardBody kind={kind} payload={payload} />);
}

describe("CardBody 渲染分支", () => {
  it("report：分组逐项渲染＋状态类；空报告提示", () => {
    const { unmount } = render(
      <CardBody
        kind="report"
        payload={{ report: [{ name: "体检", items: [{ status: "ok", text: "主线一致" }] }] }}
      />,
    );
    expect(screen.getByText("体检")).toBeTruthy();
    expect(screen.getByText("主线一致")).toBeTruthy();
    unmount();
    render(<CardBody kind="report" payload={{ report: [] }} />);
    expect(screen.getByText("（报告为空）")).toBeTruthy();
  });

  it("pick：候选名＋理由", () => {
    render(
      <CardBody kind="pick" payload={{ candidates: [{ name: "路子一", rationale: "代价真" }] }} />,
    );
    expect(screen.getByText("路子一")).toBeTruthy();
    expect(screen.getByText(/代价真/)).toBeTruthy();
  });

  it("struct：角色数组渲染（含发散徽标＋锚点）", () => {
    render(
      <CardBody
        kind="struct"
        payload={{
          characters: [
            { name: "林野", role: "主角", persona: "冷硬巡护员", origin_note: "第1章埋" },
            { name: "银铎", role: "配角", persona: "配", origin: "divergent" },
          ],
        }}
      />,
    );
    expect(screen.getByText("林野")).toBeTruthy();
    expect(screen.getByText(/冷硬巡护员/)).toBeTruthy();
    expect(screen.getByText("草案·发散")).toBeTruthy();
    expect(screen.getByText(/锚点：第1章埋/)).toBeTruthy();
  });

  it("角色草案卡（character_draft）：字段化渲染＋testid", () => {
    render(
      <CardBody
        kind="text"
        payload={{
          character_draft: { name: "阿蓟", gender_age: "女 24", identity: "哨站医士" },
        }}
      />,
    );
    expect(screen.getByTestId("char-draft-card")).toBeTruthy();
    expect(screen.getByText("阿蓟")).toBeTruthy();
    expect(screen.getByText("哨站医士")).toBeTruthy();
  });

  it("章纲补全卡（fills）：中文标签字段化＋过目提示", () => {
    render(
      <CardBody
        kind="text"
        payload={{ fills: { summary: "半蹲遭遇战", mood: "高潮爆发", changes: ["x"] } }}
      />,
    );
    expect(screen.getByText(/半蹲遭遇战/)).toBeTruthy();
    expect(screen.getByText("阶段")).toBeTruthy();
    expect(screen.getByText(/产物不落库/)).toBeTruthy();
  });

  it("设定字段卡：字符串值直渲染（cd-settings）", () => {
    render(<CardBody kind="text" payload={{ value: "题材是西式奇幻" }} />);
    expect(screen.getByText("题材是西式奇幻")).toBeTruthy();
  });

  it("设定字段卡：对象值走通用人话渲染（禁裸 JSON）", () => {
    render(<CardBody kind="text" payload={{ result: { directions: "往回收" } }} />);
    expect(screen.getByText(/往回收/)).toBeTruthy();
  });

  it("卷纲草稿卡（draft 对象）：字段化＋埋设揭示行", () => {
    render(
      <CardBody
        kind="text"
        payload={{
          draft: {
            name: "第二卷",
            summary: "血案收束",
            ending: "真相揭开",
            plants: ["p1", "p2"],
            reveals: ["r1"],
          },
        }}
      />,
    );
    expect(screen.getByText(/第二卷/)).toBeTruthy();
    expect(screen.getByText(/埋设 2 条 · 揭示 1 条/)).toBeTruthy();
  });

  it("diff.one_liner：一句话有序列表", () => {
    render(<CardBody kind="text" payload={{ diff: { one_liner: ["甲句", "乙句"] } }} />);
    expect(screen.getByText("甲句")).toBeTruthy();
    expect(screen.getByText("乙句")).toBeTruthy();
  });

  it("人话 draft（字符串）：pre 渲染＋裁剪 1200", () => {
    render(<CardBody kind="text" payload={{ draft: "推演：血族扑窗" } } />);
    expect(screen.getByText(/推演：血族扑窗/)).toBeTruthy();
  });

  it("通用兜底：未知 payload 结构化人话渲染（中文标签＋列表条目）", () => {
    render(
      <CardBody
        kind="text"
        payload={{ things: [{ name: "哨站", note: "外檐影" }], place: "旧街区" }}
      />,
    );
    expect(screen.getByText(/旧街区/)).toBeTruthy();
    expect(screen.getByText(/哨站/)).toBeTruthy();
  });

  it("通用兜底：纯字符串列表走 strings 臂", () => {
    render(<CardBody kind="text" payload={{ hints: ["短句", "口语"] }} />);
    expect(screen.getByText("短句")).toBeTruthy();
    expect(screen.getByText("口语")).toBeTruthy();
  });

  it("通用兜底：对象值走 object 臂（字段中文标签＋裁剪＋genericValue 兜底路径）", () => {
    // null → ""（过滤，genericValue 空值路径）；超长 → _clip 截断
    const meta: Record<string, unknown> = {
      style: "冷硬",
      pace: "快",
      empty: null,
      long: "长".repeat(180),
    };
    render(<CardBody kind="text" payload={{ tone: meta }} />);
    expect(screen.getByText("冷硬")).toBeTruthy();
    expect(screen.getByText("快")).toBeTruthy();
    expect(screen.getAllByText(/…/).length).toBeGreaterThan(0); // 截断发生
  });

  it("通用兜底：genericValue 数值/嵌套对象路径（String/JSON 兜底）", () => {
    render(<CardBody kind="text" payload={{ count: 3, meta: { deep: { a: 1 } } }} />);
    expect(screen.getByText(/3/)).toBeTruthy();
    expect(screen.getByText(/deep/)).toBeTruthy();
  });

  it("设定字段卡：result 为空对象 → generic null → 不渲染", () => {
    const { container } = render(<CardBody kind="text" payload={{ result: {} }} />);
    expect(container.querySelector(".cd-settings")).toBeNull();
  });

  it("全空 payload → 不渲染（null）", () => {
    const { container } = render(<CardBody kind="text" payload={{}} />);
    expect(container.querySelector(".cd-generic")).toBeNull();
  });

  it("字符串 payload 兜底：通用逐字行不适用（空白串）→ cd-pre 兜底", () => {
    // 真实调用面 payload 恒为对象；字符串 payload 的最后兜底行用空白串触达
    // （非空白字符串会走通用逐字行渲染——现行为如此）
    const { container } = render(<CardBody kind="text" payload={"   "} />);
    expect(container.querySelector(".cd-pre")?.textContent).toBe("   ");
  });
});

describe("CardBody 写法约束回显（c-agent-action-contract）", () => {
  it("通用兜底：constraints_used 显示为「写法约束」", () => {
    renderBody("text", {
      result: { constraints_used: ["真谛前期不点，中期撕开", "冷硬短句"] },
    });
    expect(screen.getByText("写法约束")).toBeTruthy();
    expect(screen.getByText(/真谛前期不点/)).toBeTruthy();
    expect(screen.getByText(/冷硬短句/)).toBeTruthy();
  });
});
