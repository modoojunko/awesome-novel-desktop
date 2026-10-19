import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImportNovelModal from "@/components/novel/ImportNovelModal";
import { importOwnParse, importOwnPersist } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    importOwnParse: vi.fn(),
    importOwnPersist: vi.fn(),
  };
});

const parsed = {
  import_id: "imp-1",
  title: "长夜灯",
  filename: "长夜灯.txt",
  encoding: "utf-8-sig",
  char_count: 1200,
  chapter_count: 2,
  volumes: [{ title: "风起", chapter_from: 1, chapter_to: 2 }],
  chapters: [
    { source_no: 1, title: "开端", title_raw: "第1章 开端", volume_title: "风起" },
    { source_no: 2, title: "遇敌", title_raw: "第2章 遇敌", volume_title: "风起" },
  ],
  warnings: [],
  risk: { level: "ok" as const, issues: [], chapter_count: 2, avg_chapter_chars: 600 },
  parser_version: "textparse-2026-10.1",
  source_sha256: "x",
};

function pickFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File(["第1章 开端\n张三。\n第2章 遇敌\n李四。\n"], "长夜灯.txt", { type: "text/plain" })] },
  });
}

describe("ImportNovelModal（A 路三步向导）", () => {
  beforeEach(() => {
    vi.mocked(importOwnParse).mockReset();
    vi.mocked(importOwnPersist).mockReset();
  });

  it("选文件 → 确认卷章（可撤销不导入）→ 直接导入", async () => {
    vi.mocked(importOwnParse).mockResolvedValue(parsed);
    vi.mocked(importOwnPersist).mockResolvedValue({ id: "book-1", name: "长夜灯" });
    const onImported = vi.fn();
    render(<ImportNovelModal open onClose={() => {}} onImported={onImported} />);

    pickFile();
    await waitFor(() => expect(importOwnParse).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/长夜灯.txt · utf-8-sig/)).toBeTruthy();

    fireEvent.click(screen.getByText("下一步：确认卷章"));
    expect(await screen.findByText("书目录 · 按章切分")).toBeTruthy();
    expect(screen.getByText("第1章 开端")).toBeTruthy();

    fireEvent.click(screen.getAllByText("不导入")[0]);
    expect(await screen.findByText(/已不导入第 1 章/)).toBeTruthy();
    fireEvent.click(screen.getByText("撤销"));
    expect(screen.queryByText(/已不导入第 1 章/)).toBeNull();

    fireEvent.click(screen.getByText("下一步：导入方式"));
    expect(await screen.findByText("直接导入（只带正文）")).toBeTruthy();
    fireEvent.click(screen.getByText("创建并开始写作"));

    await waitFor(() => expect(importOwnPersist).toHaveBeenCalledTimes(1));
    const body = vi.mocked(importOwnPersist).mock.calls[0][0];
    expect(body.import_id).toBe("imp-1");
    expect(body.name).toBe("长夜灯");
    expect(body.volumes).toEqual([{ title: "风起", chapter_from: 1, chapter_to: 2 }]);
    expect(body.excluded_source_nos).toEqual([]);
    expect(onImported).toHaveBeenCalledWith("book-1");
  });

  it("解析失败后同一文件可再次选择并重试", async () => {
    vi.mocked(importOwnParse)
      .mockRejectedValueOnce(new Error("云端服务暂时不可用，请稍后重试"))
      .mockResolvedValueOnce(parsed);
    render(<ImportNovelModal open onClose={() => {}} onImported={() => {}} />);

    const file = new File(["第1章 开端\n张三。\n"], "长夜灯.txt", { type: "text/plain" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText(/云端服务暂时不可用/)).toBeTruthy();

    // 处理器清空 input.value，同一 File 重选仍会触发 change。
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(importOwnParse).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/长夜灯.txt · utf-8-sig/)).toBeTruthy();
  });

  it("忽略中间章：排除号与重排后的卷范围逐字段正确", async () => {
    vi.mocked(importOwnParse).mockResolvedValue({
      ...parsed,
      chapter_count: 3,
      volumes: [{ title: "风起", chapter_from: 1, chapter_to: 3 }],
      chapters: [
        { source_no: 1, title: "开端", title_raw: "第1章 开端", volume_title: "风起" },
        { source_no: 2, title: "遇敌", title_raw: "第2章 遇敌", volume_title: "风起" },
        { source_no: 3, title: "收束", title_raw: "第3章 收束", volume_title: "风起" },
      ],
      risk: { level: "ok", issues: [], chapter_count: 3, avg_chapter_chars: 600 },
    });
    vi.mocked(importOwnPersist).mockResolvedValue({ id: "book-1", name: "长夜灯" });
    render(<ImportNovelModal open onClose={() => {}} onImported={() => {}} />);

    pickFile();
    await waitFor(() => expect(importOwnParse).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("下一步：确认卷章"));
    await screen.findByText("书目录 · 按章切分");
    fireEvent.click(screen.getAllByText("不导入")[1]);
    await screen.findByText(/已不导入第 2 章/);

    fireEvent.click(screen.getByText("下一步：导入方式"));
    fireEvent.click(await screen.findByText("创建并开始写作"));
    await waitFor(() => expect(importOwnPersist).toHaveBeenCalledTimes(1));
    const body = vi.mocked(importOwnPersist).mock.calls[0][0];
    expect(body.excluded_source_nos).toEqual([2]);
    expect(body.volumes).toEqual([{ title: "风起", chapter_from: 1, chapter_to: 2 }]);
  });

  it("首个卷标题晚于前几章：自动补前置正文卷，结构可继续", async () => {
    vi.mocked(importOwnParse).mockResolvedValue({
      ...parsed,
      chapter_count: 3,
      volumes: [{ title: "风起", chapter_from: 3, chapter_to: 3 }],
      chapters: [
        { source_no: 1, title: "一", title_raw: "第1章 一", volume_title: "" },
        { source_no: 2, title: "二", title_raw: "第2章 二", volume_title: "" },
        { source_no: 3, title: "三", title_raw: "第3章 三", volume_title: "风起" },
      ],
      risk: { level: "ok", issues: [], chapter_count: 3, avg_chapter_chars: 10 },
    });
    render(<ImportNovelModal open onClose={() => {}} onImported={() => {}} />);
    pickFile();
    await waitFor(() => expect(importOwnParse).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("下一步：确认卷章"));
    expect(await screen.findByDisplayValue("正文")).toBeTruthy();
    expect(screen.getByRole("button", { name: "下一步：导入方式" })).toBeEnabled();
  });

  it("risk 必须勾选才能继续；quotaFull 禁用创建", async () => {
    vi.mocked(importOwnParse).mockResolvedValue({
      ...parsed,
      risk: { level: "risk", issues: ["未识别到章标题"], chapter_count: 2, avg_chapter_chars: 600 },
    });
    render(<ImportNovelModal open onClose={() => {}} onImported={() => {}} quotaFull />);
    pickFile();
    await waitFor(() => expect(importOwnParse).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("下一步：确认卷章"));
    await screen.findByText("书目录 · 按章切分");
    const next = screen.getByText("下一步：导入方式") as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/我了解质量风险/));
    await waitFor(() => expect(next.disabled).toBe(false));
    fireEvent.click(next);
    await screen.findByText("直接导入（只带正文）");
    expect((screen.getByText("创建并开始写作") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("书架已满")).toBeTruthy();
  });
});
