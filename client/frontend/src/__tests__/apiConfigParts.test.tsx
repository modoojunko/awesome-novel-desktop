// 密钥/供应商配置面（api-config/**）组件契约（覆盖率专项·批 1 风险优先）：
//   ProviderIcon/VendorGlyph 图标与文案兜底 · UsageStatsCard 三态与条形行 ·
//   UsagePieChart 四态（loading/空/零总量/单段/多段）· UndoToast 8s 窗口与撤销 ·
//   DeleteConfirmDialog 影响点 · MigrationBanner 迁移提示与 dismissed 记忆 ·
//   ApiConfigCard 七态徽标与测试连接四条结果分支。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProviderIcon, VendorGlyph, VENDORS, VENDOR_LABELS, VENDOR_FORMAT_LOCK, FORMAT_PLACEHOLDER } from "@/components/api-config/ProviderIcon";
import { UsageStatsCard } from "@/components/api-config/UsageStatsCard";
import { UsagePieChart } from "@/components/api-config/UsagePieChart";
import { UndoToast } from "@/components/api-config/UndoToast";
import { DeleteConfirmDialog } from "@/components/api-config/DeleteConfirmDialog";
import { MigrationBanner } from "@/components/api-config/MigrationBanner";
import { ApiConfigCard } from "@/components/api-config/ApiConfigCard";
import type { ApiConfig } from "@/types/api-config";

const cfg = (over: Partial<ApiConfig> = {}): ApiConfig =>
  ({
    id: "c1",
    name: "主线 · OpenAI",
    vendor: "openai",
    base_url: "https://api.openai.com",
    api_key_masked: "sk-****1234",
    api_format: "openai",
    models: ["gpt-4o", "gpt-4o-mini"],
    last_test_status: "ok",
    ...over,
  }) as ApiConfig;

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("ProviderIcon / VendorGlyph", () => {
  it("八家供应商表与标签齐全，图标按 vendor 取、未知回退 openai-compat", () => {
    expect(VENDORS.map((v) => v.id)).toContain("openai-compat");
    expect(VENDOR_LABELS.anthropic).toBe("Anthropic");
    expect(VENDOR_FORMAT_LOCK.anthropic).toBe("anthropic");
    expect(FORMAT_PLACEHOLDER.anthropic).toContain("anthropic.com");
    render(
      <>
        <VendorGlyph vendor="deepseek" />
        <VendorGlyph vendor="不存在的厂商" />
        <ProviderIcon vendor={"glm" as ApiConfig["vendor"]} />
      </>,
    );
    expect(document.querySelectorAll("svg").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTitle("GLM")).toBeTruthy();
  });

  it("未知标签时 title 回落原始 id", () => {
    render(<ProviderIcon vendor={"weird" as ApiConfig["vendor"]} />);
    expect(screen.getByTitle("weird")).toBeTruthy();
  });
});

describe("UsageStatsCard", () => {
  const data = {
    total_all_time: 12345,
    total_this_month: 678,
    total_today: 9,
    by_config: [
      { config_id: "c1", config_name: "主线", tokens: 100 },
      { config_id: "c2", config_name: "", tokens: 50 },
    ],
  } as never;

  it("有数据：三块统计 + 条形行（空名回落 id、宽度按占比）", () => {
    render(<UsageStatsCard data={data} updatedLabel="刚刚" />);
    expect(screen.getByText("用量统计")).toBeTruthy();
    expect(screen.getByText(/最近更新：刚刚/)).toBeTruthy();
    expect(screen.getByText("12,345")).toBeTruthy(); // zh-CN 千分位
    expect(screen.getByText("主线")).toBeTruthy();
    expect(screen.getByText("c2")).toBeTruthy(); // config_name 空 → 回落 id
    const bars = [...document.querySelectorAll(".usage-row .bar i")].map((e) => (e as HTMLElement).style.width);
    expect(bars).toEqual(["100%", "50%"]);
  });

  it("loading：全部占位「—」且不出条形行", () => {
    render(<UsageStatsCard data={data} loading />);
    expect(document.querySelectorAll(".stat .v").length).toBe(3);
    expect([...document.querySelectorAll(".stat .v")].every((e) => e.textContent === "—")).toBe(true);
    expect(document.querySelector(".usage-rows")).toBeNull();
    expect(screen.getByText(/最近更新：—/)).toBeTruthy();
  });

  it("data 为 null：统计缺值显示「—」、无条形行", () => {
    render(<UsageStatsCard data={null} />);
    expect([...document.querySelectorAll(".stat .v")].every((e) => e.textContent === "—")).toBe(true);
    expect(document.querySelector(".usage-rows")).toBeNull();
    expect(screen.getByText(/最近更新：—/)).toBeTruthy();
  });
});

describe("UsagePieChart", () => {
  it("loading 呈灰环；空数组与零总量都显「暂无用量数据」", () => {
    const { unmount } = render(<UsagePieChart data={[]} loading />);
    expect(document.querySelector("circle stroke, svg circle")).toBeTruthy();
    unmount();
    render(<UsagePieChart data={[]} />);
    expect(screen.getByText("暂无用量数据")).toBeTruthy();
  });

  it("零总量：同样走空态文案", () => {
    render(<UsagePieChart data={[{ model: "gpt-4o", tokens: 0 }]} />);
    expect(screen.getByText("暂无用量数据")).toBeTruthy();
  });

  it("单段：整圆 + 模型名与总量（不带百分比）", () => {
    render(<UsagePieChart data={[{ model: "gpt-4o", tokens: 1234 }]} />);
    expect(screen.getByText("gpt-4o")).toBeTruthy();
    expect(screen.getByText("1,234")).toBeTruthy();
    expect(document.querySelectorAll("svg circle").length).toBe(1);
  });

  it("多段：每段一圆 + 图例百分比与总量", () => {
    render(
      <UsagePieChart
        data={[
          { model: "a", tokens: 75 },
          { model: "b", tokens: 25 },
        ]}
      />,
    );
    expect(document.querySelectorAll("svg circle").length).toBe(2);
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
  });
});

describe("UndoToast", () => {
  it("呈配置名；点撤销 → onUndo 后立即 onExpire，按钮进入恢复中态", async () => {
    let release: (() => void) | undefined;
    const onUndo = vi.fn(() => new Promise<void>((res) => (release = res)));
    const onExpire = vi.fn();
    render(<UndoToast configName="旧配置" onUndo={onUndo} onExpire={onExpire} />);
    expect(screen.getByText(/已删除「旧配置」/)).toBeTruthy();
    fireEvent.click(screen.getByText("撤销"));
    expect(screen.getByText("恢复中…")).toBeTruthy();
    expect(onUndo).toHaveBeenCalledTimes(1);
    await act(async () => release?.());
    await waitFor(() => expect(onExpire).toHaveBeenCalledTimes(1));
  });

  it("窗口到期：先淡出再触发 onExpire（duration=0 走完 0/300ms 两拍）", async () => {
    const onExpire = vi.fn();
    render(<UndoToast configName="x" onUndo={vi.fn(async () => {})} onExpire={onExpire} duration={0} />);
    await waitFor(() => expect(onExpire).toHaveBeenCalledTimes(1), { timeout: 2000 });
    const toast = document.querySelector(".toast") as HTMLElement;
    expect(toast.style.opacity).toBe("0"); // 淡出标记
  });
});

describe("DeleteConfirmDialog", () => {
  it("有模型：影响点 chips 呈现；取消/确认接线与 deleting 锁定", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn(async () => {});
    const { rerender } = render(<DeleteConfirmDialog config={cfg()} onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByText("删除影响")).toBeTruthy();
    expect(screen.getByText("模型 2 个")).toBeTruthy();
    fireEvent.click(screen.getByText("确认删除"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("取消"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(<DeleteConfirmDialog config={cfg()} onConfirm={onConfirm} onCancel={onCancel} deleting />);
    expect((screen.getByText("确认删除") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("取消") as HTMLButtonElement).disabled).toBe(true);
  });

  it("无模型 / models 字段缺失：都不渲染影响区", () => {
    const { unmount } = render(
      <DeleteConfirmDialog config={cfg({ models: [] })} onConfirm={vi.fn(async () => {})} onCancel={vi.fn()} />,
    );
    expect(screen.queryByText("删除影响")).toBeNull();
    unmount();
    render(
      <DeleteConfirmDialog
        config={{ ...cfg(), models: undefined } as never}
        onConfirm={vi.fn(async () => {})}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("删除影响")).toBeNull();
  });
});

describe("MigrationBanner", () => {
  it("迁移未完成且未 dismissed：呈现提示；「知道了」写记忆并隐藏", async () => {
    render(<MigrationBanner migrationCompleted={false} />);
    expect(await screen.findByText(/已升级为多配置方式/)).toBeTruthy();
    fireEvent.click(screen.getByText("知道了"));
    await waitFor(() => expect(screen.queryByText(/已升级为多配置方式/)).toBeNull());
    expect(localStorage.getItem("migration_banner_dismissed")).toBe("1");
  });

  it("已 dismissed：重挂不再出现", async () => {
    localStorage.setItem("migration_banner_dismissed", "1");
    render(<MigrationBanner migrationCompleted={false} />);
    await waitFor(() => expect(document.querySelector(".notice")).toBeNull());
  });

  it("迁移已完成：不出提示", async () => {
    render(<MigrationBanner migrationCompleted />);
    await waitFor(() => expect(document.querySelector(".notice")).toBeNull());
  });

  it("「去查看」但列表不存在：静默不炸", async () => {
    document.getElementById("api-config-list")?.remove();
    render(<MigrationBanner migrationCompleted={false} />);
    fireEvent.click(await screen.findByText("去查看"));
    expect(screen.getByText("去查看")).toBeTruthy();
  });

  it("「去查看」滚动到配置列表（列表在时）", async () => {
    const target = document.createElement("div");
    target.id = "api-config-list";
    const scrollIntoView = vi.fn();
    target.scrollIntoView = scrollIntoView;
    document.body.appendChild(target);
    render(<MigrationBanner migrationCompleted={false} />);
    fireEvent.click(await screen.findByText("去查看"));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    target.remove();
  });
});

describe("ApiConfigCard", () => {
  it("七态徽标与边框：逐态映射（含未知态回落未测试）", () => {
    const cases: Array<[ApiConfig["last_test_status"], string, string]> = [
      ["ok", "连接正常", ""],
      ["auth_error", "认证失败", "b-err"],
      ["timeout", "连接超时", "b-warn"],
      ["network_error", "网络错误", "b-warn"],
      ["rate_limited", "频率限制", "b-muted"],
      ["unknown", "未知", "b-muted"],
      ["something_new" as ApiConfig["last_test_status"], "未测试", ""],
    ];
    for (const [status, label, border] of cases) {
      const { unmount } = render(
        <ApiConfigCard
          config={cfg({ last_test_status: status, models: [] })}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onTest={vi.fn()}
        />,
      );
      const card = document.querySelector(".cfg-card") as HTMLElement;
      expect(screen.getByText(label)).toBeTruthy();
      expect(card.className).toContain(border);
      unmount();
    }
  });

  it("无 base_url / 无密钥 / 超 5 模型：兜底文案与 +N 计数", () => {
    render(
      <ApiConfigCard
        config={cfg({
          base_url: "",
          api_key_masked: "",
          models: ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
        })}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onTest={vi.fn()}
      />,
    );
    expect(screen.getByText("（本地）")).toBeTruthy();
    expect(screen.getByText("（无需 API Key）")).toBeTruthy();
    expect(screen.getByText("+2")).toBeTruthy();
  });

  it("测试连接四分支：失败带原因 / 失败无原因 / 成功无模型带说明 / 成功有模型清空结果", async () => {
    const onTest = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: "auth_error", error: "密钥无效" })
      .mockResolvedValueOnce({ ok: false, status: "unknown" })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: [], note: "端点不提供模型列表" })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["gpt-4o"] });
    render(<ApiConfigCard config={cfg({ models: [] })} onEdit={vi.fn()} onDelete={vi.fn()} onTest={onTest} />);
    const btn = screen.getByText("测试连接");

    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("密钥无效")).toBeTruthy());
    expect(document.querySelector(".res.bad")).toBeTruthy();

    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("测试失败")).toBeTruthy());

    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("端点不提供模型列表")).toBeTruthy());

    fireEvent.click(btn);
    await waitFor(() => expect(document.querySelector(".res")!.textContent).toBe(""));
  });

  it("缺字段兜底：last_test_status / models 都缺失时按未测试与空列表处理", () => {
    render(
      <ApiConfigCard
        config={{ ...cfg(), last_test_status: undefined, models: undefined } as never}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onTest={vi.fn()}
      />,
    );
    expect(screen.getByText("未测试")).toBeTruthy();
    expect(document.querySelectorAll(".m-chip").length).toBe(0);
  });

  it("测试返回不带 models 时按配置里的模型列表判断（?? 回落臂）", async () => {
    const withModels = vi.fn(async () => ({ ok: true, status: "ok", note: "端点不提供模型列表" }));
    const { unmount } = render(
      <ApiConfigCard config={cfg({ models: ["gpt-4o"] })} onEdit={vi.fn()} onDelete={vi.fn()} onTest={withModels} />,
    );
    fireEvent.click(screen.getByText("测试连接"));
    await waitFor(() => expect(document.querySelector(".res")!.textContent).toBe("")); // 有模型 → 不显示 note
    unmount();
    // 配置也没有模型 + 无 note → 同样清空（note 假臂）
    const noModelsNoNote = vi.fn(async () => ({ ok: true, status: "ok" }));
    render(
      <ApiConfigCard
        config={{ ...cfg(), models: undefined } as never}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onTest={noModelsNoNote}
      />,
    );
    fireEvent.click(screen.getByText("测试连接"));
    await waitFor(() => expect(document.querySelector(".res")!.textContent).toBe(""));
  });

  it("测试连接抛错：呈现「测试请求失败」", async () => {
    const onTest = vi.fn(async () => {
      throw new Error("boom");
    });
    render(<ApiConfigCard config={cfg()} onEdit={vi.fn()} onDelete={vi.fn()} onTest={onTest} />);
    fireEvent.click(screen.getByText("测试连接"));
    await waitFor(() => expect(screen.getByText("测试请求失败")).toBeTruthy());
  });

  it("编辑/删除按钮把配置回传调用方", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<ApiConfigCard config={cfg()} onEdit={onEdit} onDelete={onDelete} onTest={vi.fn()} />);
    fireEvent.click(screen.getByText("编辑"));
    fireEvent.click(screen.getByText("删除"));
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
    expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
  });
});
