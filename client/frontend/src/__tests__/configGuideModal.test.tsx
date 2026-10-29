// 配置指南弹窗（c-modelconfig-help-guide）组件契约：
//   三页签渲染与切换（面板互斥、弹窗不关）· guideTabForVendor 映射矩阵 ·
//   文案黑名单（作家语汇纪律，无实现词汇）· 领 Key 地址表 8 家 ·
//   initialTab 打开时定位（两处入口共用单源）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ConfigGuideModal, { guideTabForVendor } from "@/components/api-config/ConfigGuideModal";

afterEach(() => {
  // 不手动清 document.body：Modal portal 由 RTL 卸载路径收尾，手动 wipe 会让
  // removeChild 踩不到父节点（NotFoundError）
  vi.clearAllMocks();
});

describe("guideTabForVendor", () => {
  it("映射矩阵：anthropic 系→anthropic、gemini→google、其余→openai", () => {
    expect(guideTabForVendor("anthropic")).toBe("anthropic");
    expect(guideTabForVendor("opencode-go-claude")).toBe("anthropic");
    expect(guideTabForVendor("gemini")).toBe("google");
    expect(guideTabForVendor("openai")).toBe("openai");
    expect(guideTabForVendor("deepseek")).toBe("openai");
    expect(guideTabForVendor("opencode-go-chat")).toBe("openai");
    expect(guideTabForVendor("openai-compat")).toBe("openai");
    expect(guideTabForVendor("doubao")).toBe("openai");
    expect(guideTabForVendor("")).toBe("openai");
    expect(guideTabForVendor(null)).toBe("openai");
    expect(guideTabForVendor(undefined)).toBe("openai");
  });
});

describe("ConfigGuideModal", () => {
  it("三页签切换：面板内容跟随、弹窗保持打开", () => {
    render(<ConfigGuideModal open onClose={vi.fn()} />);
    // 弹窗渲染进 document.body（Modal portal）
    expect(screen.getByText("配置指南")).toBeTruthy();
    expect(screen.getByText("大多数国内外服务商都用这一格式，不确定就先按它配。")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 格式" }));
    expect(screen.getByText("Anthropic 的 Claude 系模型，以及提供「Claude 兼容」地址的中转站。")).toBeTruthy();
    expect(screen.queryByText("大多数国内外服务商都用这一格式，不确定就先按它配。")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Google 系" }));
    expect(screen.getByText(/Google 的 Gemini 模型/)).toBeTruthy();
    // 弹窗仍在（页签切换不关闭）
    expect(screen.getByText("配置指南")).toBeTruthy();
  });

  it("四步骨架与常见问题在三页签均在位（关键文案逐字）", () => {
    render(<ConfigGuideModal open onClose={vi.fn()} />);
    for (const tabLabel of ["OpenAI 格式", "Anthropic 格式", "Google 系"]) {
      fireEvent.click(screen.getByRole("button", { name: tabLabel }));
      // 「测试连接」与导语「领 Key → 选方块贴 Key → 测试连接」的加粗撞文本——存在即可
      expect(screen.getAllByText("测试连接").length).toBeGreaterThan(0);
      expect(screen.getByText("领 API Key")).toBeTruthy();
      expect(screen.getByText("常见问题")).toBeTruthy();
    }
  });

  it("OpenAI 页签含领 Key 速查表 8 家", () => {
    render(<ConfigGuideModal open onClose={vi.fn()} />);
    for (const name of ["OpenAI", "DeepSeek", "GLM", "Kimi", "Qwen", "豆包", "Ollama", "OpenCode Go"]) {
      // 同名文本会与 chips/步骤撞车（如「OpenAI」chip×「OpenAI 格式」页签），存在即可
      expect(screen.getAllByText(name, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("platform.deepseek.com")).toBeTruthy();
  });

  it("initialTab 定位：打开即落在指定页签（弹窗内入口按供应商定位）", () => {
    render(<ConfigGuideModal open onClose={vi.fn()} initialTab="google" />);
    expect(screen.getByText(/Google 的 Gemini 模型/)).toBeTruthy();
  });

  it("关闭回调：点关闭钮触发 onClose", () => {
    const onClose = vi.fn();
    render(<ConfigGuideModal open onClose={onClose} />);
    fireEvent.click(document.querySelector(".mcard-head .x") as HTMLElement);
    expect(onClose).toHaveBeenCalled();
  });

  it("文案黑名单：可见文案无实现词汇（作家语汇纪律）", () => {
    render(<ConfigGuideModal open onClose={vi.fn()} />);
    const visible = () => {
      // Modal portal 到 body，不在 RTL container 里——查 document
      const el = document.querySelector(".guide-body") as HTMLElement;
      expect(el).toBeTruthy();
      return el.textContent || "";
    };
    const banned = ["协议", "SDK", "端点", "探针", "兼容层", "wire", "vendor"];
    for (const tabLabel of ["OpenAI 格式", "Anthropic 格式", "Google 系"]) {
      fireEvent.click(screen.getByRole("button", { name: tabLabel }));
      const text = visible();
      for (const b of banned) {
        expect(text.includes(b), `可见文案含实现词汇「${b}」`).toBe(false);
      }
    }
  });
});
