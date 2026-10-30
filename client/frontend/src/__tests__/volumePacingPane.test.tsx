/** 卷节奏页签面板（c-volume-pacing）：两态/预填/保存失效的组件级测试。
 *  mock volumePacingApi（数据形状照后端 normalize_pacing_config 输出）。 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getVolume = vi.fn();
const saveVolume = vi.fn();

vi.mock("@/lib/volumePacingApi", () => ({
  volumePacingApi: {
    getVolume: (...a: unknown[]) => getVolume(...a),
    saveVolume: (...a: unknown[]) => saveVolume(...a),
    plan: vi.fn(),
    tailor: vi.fn(),
    polish: vi.fn(),
  },
}));

import VolumePacingPane from "@/components/novel/workbench/VolumePacingPane";

const PRESETS = [
  {
    key: "upgrade",
    label: "升级套路",
    sub: "遇麻烦 → 解决 → 变强",
    steps_len: 3,
    warn_len: 6,
    hint: "3–5 章最稳；拖过 5 章，读者会等疲。",
    steps: [
      { n: "遇麻烦", t: "一个主角眼下对付不了的麻烦当场砸下来；第一段剧情里，金手指露头。" },
      { n: "用金手指解决", t: "真刀真枪把麻烦解掉——怎么出手、付出什么、局面怎么松，都写实。" },
      { n: "变强收尾", t: "变强落到实处（境界、家底、名分），交代下一步；结尾埋下一段的新麻烦。" },
    ],
    ch1_extra: "开场即危机，金手指当场觉醒，世界观跟着剧情带出来——前三章内给到第一个爽点。",
  },
  {
    key: "case",
    label: "破案套路",
    sub: "案发 → 查案 → 反转",
    steps_len: 12,
    warn_len: 16,
    hint: "一案一段剧情；收案别拖过 15 章。",
    steps: [
      { n: "案发", t: "案子当场发生，利害落到主角头上；不写背景铺陈。" },
      { n: "查案", t: "现场和证物过一遍手，抓住第一条线头。" },
      { n: "锁定嫌疑人", t: "圈出两三个可疑的人，个个有动机。" },
      { n: "层层排查", t: "线索排掉又翻起来；中途至少认错一次方向。" },
      { n: "真相反转", t: "真凶落定，和开头想的不一样；余波一句话收。" },
    ],
    ch1_extra: "第 1 章：案子必须当场发生。",
  },
];

const PREFILL = {
  preset: "upgrade",
  steps: PRESETS[0].steps.map((s) => ({ ...s })),
  steps_len: 3,
  ch1_extra_on: true,
  ch1_extra: PRESETS[0].ch1_extra,
  planned: false,
};

function props(
  overrides: Partial<{ onChanged: () => void; chapterTarget: number | null }> = {},
) {
  return {
    projectId: "p1",
    volumeRef: "vol-1",
    volumeNo: 1,
    chapterTarget: "chapterTarget" in overrides ? overrides.chapterTarget! : 40,
    onChanged: overrides.onChanged ?? vi.fn(),
    onDirtyChange: vi.fn(),
  };
}

beforeEach(() => {
  getVolume.mockReset();
  saveVolume.mockReset().mockResolvedValue({ config: PREFILL });
});

describe("VolumePacingPane · 查看态", () => {
  it("未配置卷按预填展示（未排），体量行给段表口径", async () => {
    getVolume.mockResolvedValue({
      config: null,
      prefill: PREFILL,
      source: "genre",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    expect(await screen.findByText("升级套路")).toBeInTheDocument();
    expect(screen.getByText(/未排/)).toBeInTheDocument();
    expect(screen.getByText(/约 13 段/)).toBeInTheDocument();
  });

  it("已排卷显示已排状态", async () => {
    getVolume.mockResolvedValue({
      config: { ...PREFILL, planned: true },
      prefill: { ...PREFILL, planned: true },
      source: "volume",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    expect(await screen.findByText(/已排/)).toBeInTheDocument();
  });
});

describe("VolumePacingPane · 编辑态", () => {
  it("进编辑即以当前生效配置初始化 draft（三步可见，P1 回归钉）", async () => {
    getVolume.mockResolvedValue({
      config: null,
      prefill: PREFILL,
      source: "genre",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    expect(await screen.findByDisplayValue("遇麻烦")).toBeInTheDocument();
    expect(screen.getByDisplayValue("用金手指解决")).toBeInTheDocument();
    expect(screen.getByDisplayValue("变强收尾")).toBeInTheDocument();
  });

  it("保存＝PUT 卷配置（真实变更→planned 失效置 false）并触发 onChanged（P2 回归钉）", async () => {
    const onChanged = vi.fn();
    getVolume.mockResolvedValue({
      config: { ...PREFILL, planned: true },
      prefill: { ...PREFILL, planned: true },
      source: "volume",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props({ onChanged })} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    // 真实变更（段长 3→5）后才允许保存，且 planned 失效
    fireEvent.change(await screen.findByLabelText("一段剧情讲几章"), {
      target: { value: "5" },
    });
    const saveBtn = await screen.findByRole("button", { name: "保存" });
    await waitFor(() => expect(saveBtn).not.toBeDisabled());
    fireEvent.click(saveBtn);
    await waitFor(() => expect(saveVolume).toHaveBeenCalled());
    const body = saveVolume.mock.calls[0]?.[2];
    expect(body?.planned).toBe(false);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("零改动保存保留已排（保存键禁用，planned 不被打掉）", async () => {
    getVolume.mockResolvedValue({
      config: { ...PREFILL, planned: true },
      prefill: { ...PREFILL, planned: true },
      source: "volume",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    const saveBtn = await screen.findByRole("button", { name: "保存" });
    expect(saveBtn).toBeDisabled(); // 零改动＝不可保存，「已排」天然保留
    fireEvent.click(saveBtn);
    expect(saveVolume).not.toHaveBeenCalled();
  });

  it("一段剧情超拖线出黄牌", async () => {
    getVolume.mockResolvedValue({
      config: null,
      prefill: { ...PREFILL, steps_len: 7 },
      source: "genre",
      book_default: null,
      plan: { target: 40, steps_len: 7, n: 5, rem: 5, last_from: 36, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    expect(screen.getAllByText(/读者会等疲/).length).toBeGreaterThan(0);
  });

  it("编辑态上抛 onEditingChange（进编辑 true／取消 false）", async () => {
    getVolume.mockResolvedValue({
      config: { ...PREFILL, planned: true },
      prefill: { ...PREFILL, planned: true },
      source: "volume",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    const onEditingChange = vi.fn();
    render(
      <VolumePacingPane
        {...props()}
        onEditingChange={onEditingChange}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    await waitFor(() => expect(onEditingChange).toHaveBeenLastCalledWith(true));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(onEditingChange).toHaveBeenLastCalledWith(false));
  });

  it("切换套路重置步表与每段几章", async () => {
    getVolume.mockResolvedValue({
      config: null,
      prefill: PREFILL,
      source: "genre",
      book_default: null,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
      presets: PRESETS,
      theme: "仙侠/修真",
      sub_genre: "凡人流",
    });
    render(<VolumePacingPane {...props()} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    fireEvent.click(screen.getByRole("button", { name: /破案套路/ }));
    expect(await screen.findByDisplayValue("案发")).toBeInTheDocument();
    expect(screen.getByDisplayValue("12")).toBeInTheDocument();
  });
});

// ── c-pacing-effectiveness：来源/是否照它走/出口 ─────────────────────────
const BOOK = {
  preset: "case",
  steps: PRESETS[1].steps.map((s) => ({ ...s })),
  steps_len: 4,
  ch1_extra_on: false,
  ch1_extra: "",
  planned: false,
};
const VOL = { ...PREFILL, planned: true };

function withResult(extra: Record<string, unknown>) {
  return getVolume.mockResolvedValue({
    config: null,
    prefill: PREFILL,
    source: "genre",
    effective: null,
    effective_source: null,
    config_present: false,
    config_invalid: false,
    book_default: null,
    plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
    presets: PRESETS,
    theme: "仙侠/修真",
    sub_genre: "凡人流",
    ...extra,
  });
}

describe("VolumePacingPane · 节奏会不会照它走（c-pacing-effectiveness）", () => {
  it("仅题材预填：标明没存到本卷，一键保存写预填（planned=false）", async () => {
    const onChanged = vi.fn();
    withResult({});
    render(<VolumePacingPane {...props({ onChanged })} />);
    expect(await screen.findByTestId("pacing-source")).toHaveTextContent(
      "题材默认 · 还没存到这一卷",
    );
    fireEvent.click(screen.getByTestId("pacing-save-prefill"));
    await waitFor(() => expect(saveVolume).toHaveBeenCalled());
    const body = saveVolume.mock.calls[0]?.[2];
    expect(body).toMatchObject({ preset: "upgrade", steps_len: 3, planned: false });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("书默认生效：标全书默认＋给改为本卷设置；上一卷建议不冒充", async () => {
    withResult({
      effective: BOOK,
      effective_source: "book",
      prefill: PREFILL,
      source: "prev",
      book_default: { preset: "case", steps_len: 4 },
      plan: { target: 40, steps_len: 4, n: 10, rem: 0, last_from: 37, last_to: 40 },
    });
    render(<VolumePacingPane {...props()} />);
    expect(await screen.findByTestId("pacing-source")).toHaveTextContent(
      "全书默认 · 拆章会照它走",
    );
    expect(screen.getByTestId("pacing-prev-suggest")).toHaveTextContent(
      "之前某一卷的设置（3 章）还没存到这一卷",
    );
    expect(screen.queryByTestId("pacing-save-prefill")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("pacing-freeze-book"));
    await waitFor(() => expect(saveVolume).toHaveBeenCalled());
    expect(saveVolume.mock.calls[0]?.[2]).toMatchObject({ preset: "case", steps_len: 4 });
  });

  it("本卷设置：已存即承诺四个下游；无出口", async () => {
    withResult({
      config: VOL,
      effective: VOL,
      effective_source: "volume",
      source: "volume",
      config_present: true,
      plan: { target: 40, steps_len: 3, n: 13, rem: 1, last_from: 37, last_to: 40 },
    });
    render(<VolumePacingPane {...props()} />);
    expect(await screen.findByTestId("pacing-source")).toHaveTextContent(
      "本卷设置 · 拆章会照它走",
    );
    expect(screen.getByTestId("pacing-promise")).toHaveTextContent(
      "拆章、剧情、推演、正文都照这张表来",
    );
    expect(screen.queryByTestId("pacing-save-prefill")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pacing-freeze-book")).not.toBeInTheDocument();
  });

  it("有配置但没填章数目标：不承诺照它走", async () => {
    withResult({
      config: VOL,
      effective: VOL,
      effective_source: "volume",
      source: "volume",
      config_present: true,
      plan: { target: 0, steps_len: 3, n: 1, rem: 0, last_from: 1, last_to: 0 },
    });
    render(<VolumePacingPane {...props({ chapterTarget: null })} />);
    expect(await screen.findByTestId("pacing-source")).toHaveTextContent(
      "填上本卷章数目标后",
    );
    expect(screen.getByTestId("pacing-promise")).not.toHaveTextContent(
      "都照这张表来",
    );
  });

  it("配置读不出来：说读不出来，不说没存；不给保存预填出口", async () => {
    withResult({ config_invalid: true, config_present: true });
    render(<VolumePacingPane {...props()} />);
    expect(await screen.findByTestId("pacing-source")).toHaveTextContent(
      "本卷设置读不出来 · 请重新保存",
    );
    expect(screen.queryByTestId("pacing-save-prefill")).not.toBeInTheDocument();
  });

  it("书默认生效时进编辑：零改动不脏（基线取 effective，不取预填）", async () => {
    withResult({
      effective: BOOK,
      effective_source: "book",
      prefill: PREFILL,
      source: "prev",
      plan: { target: 40, steps_len: 4, n: 10, rem: 0, last_from: 37, last_to: 40 },
    });
    render(<VolumePacingPane {...props()} />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑节奏" }));
    const saveBtn = await screen.findByRole("button", { name: "保存" });
    expect(saveBtn).toBeDisabled();
  });
});
