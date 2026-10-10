// c-char-batch-import：BatchAddModal 行为测试——预览状态徽标、就地编辑重算、
// 确认回调载荷、停批回显剩余行、草稿保留（弹层关开不丢）。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import BatchAddModal from "@/components/novel/settings/BatchAddModal";
import type { BatchRow } from "@/lib/characterImport";

function csvFile(content: string): File {
  const bytes = new TextEncoder().encode(content);
  const f = new File([bytes as unknown as BlobPart], "名单.csv", { type: "text/csv" });
  Object.defineProperty(f, "arrayBuffer", { value: async () => bytes.buffer.slice(0) });
  return f;
}

function setup(overrides: Partial<{ hasProtagonist: boolean; existingNames: string[] }> = {}) {
  const onSubmit = vi.fn(async (rows: BatchRow[]) => ({
    created: rows.length,
    skipped: 0,
    createdIds: rows.map((_, i) => `new${i}`),
  }));
  const onClose = vi.fn();
  const onToast = vi.fn();
  const ui = render(
    <BatchAddModal
      open
      existingNames={new Set(overrides.existingNames ?? ["苏晚"])}
      hasProtagonist={overrides.hasProtagonist ?? true}
      onClose={onClose}
      onToast={onToast}
      onSubmit={onSubmit}
    />,
  );
  return { onSubmit, onClose, onToast, ...ui };
}

async function upload(content: string) {
  const input = screen.getByTestId("char-batch-file-input");
  await waitFor(async () => {
    fireEvent.change(input, { target: { files: [csvFile(content)] } });
  });
}

const CSV = "\ufeff名字*,类型,一句话人设,别名(用·分隔)\n" +
  "示例-韩十三,配角,锅炉工,老韩头\n" +
  "苏晚,主角,灯语专家,二副\n" +
  "白芷,配角,药铺学徒,芷丫头";

describe("BatchAddModal", () => {
  it("空态：解析提示＋确认键禁用", () => {
    setup();
    expect(screen.getByText(/点「下载模版」/)).toBeTruthy();
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("上传后逐行出状态：示例行防呆/库内重名跳过/有效行带徽标；确认键按有效行数启用", async () => {
    setup();
    await upload(CSV);
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(3));
    expect(screen.getByTestId("char-batch-status-1").textContent).toBe("示例行，不导入");
    // 苏晚与库内重名：重名判定先于主角约束 → 跳过
    expect(screen.getByTestId("char-batch-status-2").textContent).toBe("已有同名，跳过");
    expect(screen.getByTestId("char-batch-status-3").textContent).toContain("将新建");
    expect(screen.getByTestId("char-batch-count").textContent).toContain("建 1 张");
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(false);
  });

  it("批内选两个主角（库内无主角）→ 双双标红禁确认", async () => {
    setup({ existingNames: [] });
    await upload("\ufeff名字*,类型\n甲,主角\n乙,主角\n丙,配角");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(3));
    expect(screen.getByTestId("char-batch-status-1").textContent).toBe("每书一位主角");
    expect(screen.getByTestId("char-batch-status-2").textContent).toBe("每书一位主角");
    expect(screen.getByTestId("char-batch-status-3").textContent).toContain("将新建");
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("确认：只上抛有效行（携别名/档案），成功后关弹层＋清草稿", async () => {
    const { onSubmit, onClose } = setup({ hasProtagonist: false, existingNames: [] });
    await upload(CSV);
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(3));
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const sent = onSubmit.mock.calls[0][0] as BatchRow[];
    expect(sent).toHaveLength(2); // 示例行被滤掉
    const suwan = sent.find((r) => r.name === "苏晚");
    expect(suwan).toMatchObject({ name: "苏晚", role: "主角", persona: "灯语专家" });
    expect(suwan?.aliases).toEqual(["二副"]);
    // 草稿清空：重开后预览为空态
    expect(screen.getByText(/点「下载模版」/)).toBeTruthy();
  });

  it("停批：failMsg 红条＋剩余行留在预览可重试，弹层不关", async () => {
    const onSubmit = vi.fn(async (rows: BatchRow[]) => ({
      created: 1,
      skipped: 0,
      createdIds: ["new0"],
      failMsg: "已建 1/2——「乙」失败：网络抖动",
      remaining: rows.slice(1),
    }));
    const onClose = vi.fn();
    render(
      <BatchAddModal
        open
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={onClose}
        onToast={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    await upload("\ufeff名字*,类型\n甲,配角\n乙,配角");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(2));
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() => expect(screen.getByTestId("char-batch-fail").textContent).toContain("已建 1/2"));
    expect(onClose).not.toHaveBeenCalled();
    // 剩余行回预览：只剩乙一行可重试
    expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1);
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(false);
  });

  it("就地改名字即时重算状态（改掉重名→将新建）", async () => {
    setup({ hasProtagonist: false });
    await upload("\ufeff名字*,类型\n苏晚,配角,x");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1));
    expect(screen.getByTestId("char-batch-status-1").textContent).toBe("已有同名，跳过");
    const nameInput = screen.getByLabelText("第 1 行名字") as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "苏晚晚" } });
    await waitFor(() => expect(screen.getByTestId("char-batch-status-1").textContent).toContain("将新建"));
  });

  it("就地改类型即时重算（配角→主角＋库内已有主角→标红）", async () => {
    setup();
    await upload("\ufeff名字*,类型\n白芷,配角,x");
    await waitFor(() => expect(screen.getByTestId("char-batch-status-1").textContent).toContain("将新建"));
    fireEvent.change(screen.getByLabelText("第 1 行类型"), { target: { value: "主角" } });
    await waitFor(() => expect(screen.getByTestId("char-batch-status-1").textContent).toBe("每书一位主角"));
  });

  it("就地改人设写回行数据（确认时上抛）", async () => {
    const onSubmit = vi.fn(async (rows: BatchRow[]) => ({
      created: rows.length,
      skipped: 0,
      createdIds: rows.map((_, i) => `new${i}`),
    }));
    render(
      <BatchAddModal
        open
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={vi.fn()}
        onToast={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    await upload("\ufeff名字*,类型\n甲,配角");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("第 1 行人设"), { target: { value: "补一句人设" } });
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect((onSubmit.mock.calls[0][0] as BatchRow[])[0].persona).toBe("补一句人设");
  });

  it("删行：× 去掉该行后重算", async () => {
    setup({ existingNames: [] });
    await upload("\ufeff名字*,类型\n甲,配角\n乙,配角");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(2));
    fireEvent.click(screen.getByLabelText("去掉第 1 行"));
    expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1);
    expect((screen.getByLabelText("第 1 行名字") as HTMLInputElement).value).toBe("乙");
  });

  it("解析失败：红条出现且确认禁用", async () => {
    setup();
    await upload("类型,性别\n配角,女");
    await waitFor(() => expect(screen.getByTestId("char-batch-parse-err").textContent).toContain("名字"));
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("草稿保留：弹层关再开，预览行还在", async () => {
    const { rerender } = render(
      <BatchAddModal
        open
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={vi.fn()}
        onToast={vi.fn()}
        onSubmit={vi.fn(async (rows) => ({ created: rows.length, skipped: 0, createdIds: [] }))}
      />,
    );
    await upload("\ufeff名字*,类型\n甲,配角");
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1));
    rerender(
      <BatchAddModal
        open={false}
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={vi.fn()}
        onToast={vi.fn()}
        onSubmit={vi.fn(async (rows) => ({ created: rows.length, skipped: 0, createdIds: [] }))}
      />,
    );
    rerender(
      <BatchAddModal
        open
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={vi.fn()}
        onToast={vi.fn()}
        onSubmit={vi.fn(async (rows) => ({ created: rows.length, skipped: 0, createdIds: [] }))}
      />,
    );
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1));
  });
});

describe("BatchAddModal 提交拒绝", () => {
  it("onSubmit 整体拒绝（如建卡前保存队列网络失败）：红条＋行保留＋不关弹层", async () => {
    const onSubmit = vi.fn(async () => {
      throw new Error("自动保存失败——请检查网络后重试");
    });
    const onClose = vi.fn();
    render(
      <BatchAddModal
        open
        existingNames={new Set()}
        hasProtagonist={false}
        onClose={onClose}
        onToast={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    const input = screen.getByTestId("char-batch-file-input");
    const bytes = new TextEncoder().encode("\ufeff名字*,类型\n甲,配角");
    const f = new File([bytes as unknown as BlobPart], "名单.csv", { type: "text/csv" });
    Object.defineProperty(f, "arrayBuffer", { value: async () => bytes.buffer.slice(0) });
    await waitFor(async () => {
      fireEvent.change(input, { target: { files: [f] } });
    });
    await waitFor(() => expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1));
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("char-batch-fail").textContent).toContain("自动保存失败"),
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getAllByTestId("char-batch-row")).toHaveLength(1);
    // busy 复位：确认键可再点
    expect((screen.getByTestId("char-batch-confirm") as HTMLButtonElement).disabled).toBe(false);
  });
});
