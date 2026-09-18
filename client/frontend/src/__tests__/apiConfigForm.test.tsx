// 添加/编辑 API Key 弹窗（ApiConfigForm）契约（覆盖率专项·批 1）：
//   新建态（供应商格选择/格式锁定矩阵/URL 不预填只换占位/校验四态/提交成功失败/测试连接四分支）
//   编辑态（供应商锁定显示/密钥留空保留/掩码提示/表单随编辑目标重置）。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "@testing-library/react";
import { ApiConfigForm, type ApiConfigFormData } from "@/components/api-config/ApiConfigForm";
import type { ApiConfig } from "@/types/api-config";

const editCfg = (over: Partial<ApiConfig> = {}): ApiConfig =>
  ({
    id: "c1",
    name: "主力",
    vendor: "openai",
    base_url: "https://api.openai.com",
    api_key_masked: "sk-****9999",
    api_format: "openai",
    models: [],
    ...over,
  }) as ApiConfig;

const setField = (id: string, value: string) => fireEvent.change(document.getElementById(id)!, { target: { value } });

describe("ApiConfigForm 新建态", () => {
  it("供应商格：点选高亮 + 单格式厂锁定接口格式（ollama → openai）", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Anthropic"));
    expect(screen.getByText("Anthropic").closest("button")!.className).toContain("on");
    expect(screen.getByText("Anthropic 格式").className).toContain("on");
    expect((screen.getByText("OpenAI 格式") as HTMLButtonElement).disabled).toBe(true); // 锁定
    // 换 Ollama：锁定回 openai 格式
    fireEvent.click(screen.getByText("Ollama"));
    expect(screen.getByText("OpenAI 格式").className).toContain("on");
    // 双格式厂商：不锁定、也不重置已有格式（拍板口径：选厂商/切格式都不动输入与既有选择）
    fireEvent.click(screen.getByText("DeepSeek"));
    expect(screen.getByText("OpenAI 格式").className).toContain("on");
    expect((screen.getByText("Anthropic 格式") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByText("Anthropic 格式"));
    expect(screen.getByText("Anthropic 格式").className).toContain("on");
    expect(screen.getByText("OpenAI 格式").className).not.toContain("on");
    // 点同一个格式不产生变化（早返回分支）
    fireEvent.click(screen.getByText("Anthropic 格式"));
    expect(screen.getByText("Anthropic 格式").className).toContain("on");
  });

  it("URL 不预填：仅 placeholder 随格式变化", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    const base = () => document.getElementById("cfBase") as HTMLInputElement;
    expect(base().value).toBe("");
    expect(base().placeholder).toContain("openai.com");
    fireEvent.click(screen.getByText("Anthropic 格式"));
    expect(base().value).toBe(""); // 不预填
    expect(base().placeholder).toContain("anthropic.com");
  });

  it("校验四态：名称/供应商/Base URL/API Key（Ollama 免 Key）", async () => {
    const onSubmit = vi.fn(async (_data: ApiConfigFormData) => {});
    render(<ApiConfigForm open onSubmit={onSubmit} onCancel={vi.fn()} />);
    const submit = () => fireEvent.submit(document.getElementById("api-config-form")!);

    submit();
    expect(await screen.findByText("请输入配置名称")).toBeTruthy();
    setField("cfName", "我的配置");
    submit();
    expect(await screen.findByText("请选择供应商")).toBeTruthy();
    fireEvent.click(screen.getByText("DeepSeek"));
    submit();
    expect(await screen.findByText("请输入 Base URL")).toBeTruthy();
    setField("cfBase", "https://api.deepseek.com");
    submit();
    expect(await screen.findByText("请输入 API Key")).toBeTruthy();
    // Ollama 免 Key
    fireEvent.click(screen.getByText("Ollama"));
    submit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "我的配置",
      vendor_id: "ollama",
      base_url: "https://api.deepseek.com",
      api_key: "",
      api_format: "openai",
    });
  });

  it("Key 输入占位：Ollama 提示免 Key 且输入框禁用", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("Ollama"));
    const key = document.getElementById("cfKey") as HTMLInputElement;
    expect(key.placeholder).toBe("Ollama 不需要 API Key");
    expect(key.disabled).toBe(true);
  });

  it("提交失败：把错误信息透出到表单（Error 与非 Error 两形态）", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValueOnce(new Error("名称已被使用"))
      .mockRejectedValueOnce("plain-string");
    render(<ApiConfigForm open onSubmit={onSubmit} onCancel={vi.fn()} />);
    setField("cfName", "x");
    fireEvent.click(screen.getByText("DeepSeek"));
    setField("cfBase", "https://api.deepseek.com");
    setField("cfKey", "sk-1");
    fireEvent.submit(document.getElementById("api-config-form")!);
    expect(await screen.findByText("名称已被使用")).toBeTruthy();
    fireEvent.submit(document.getElementById("api-config-form")!);
    expect(await screen.findByText("保存失败")).toBeTruthy();
  });

  it("测试连接：无 onTest 直接返回；校验不过不测；ok+无模型带 note / ok 有模型 / 失败 / 抛错", async () => {
    // 无 onTest
    const { unmount } = render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByText("测试连接"));
    expect(screen.queryByText("连接正常")).toBeNull();
    unmount();

    const onTest = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "ok", models: [], note: "端点不提供模型列表" })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["gpt-4o"] })
      .mockResolvedValueOnce({ ok: false, status: "auth_error", error: "密钥无效" })
      .mockResolvedValueOnce({ ok: false, status: "unknown" })
      .mockRejectedValueOnce(new Error("boom"));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onTest={onTest} />);
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("请输入配置名称")).toBeTruthy(); // 校验拦住，未调用 onTest
    expect(onTest).not.toHaveBeenCalled();

    setField("cfName", "x");
    fireEvent.click(screen.getByText("DeepSeek"));
    setField("cfBase", "https://api.deepseek.com");
    setField("cfKey", "sk-1");

    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("端点不提供模型列表")).toBeTruthy();
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("连接正常")).toBeTruthy();
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("密钥无效")).toBeTruthy();
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("测试失败")).toBeTruthy(); // 失败但后端没给原因 → 兜底文案
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("测试请求失败")).toBeTruthy();
  });
});

describe("ApiConfigForm 编辑态", () => {
  it("供应商锁定为只读展示，且点选逻辑不生效；标题与按钮文案切编辑态", () => {
    render(<ApiConfigForm open config={editCfg()} onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    expect(screen.getByText("编辑配置")).toBeTruthy();
    expect(screen.getByText("保存")).toBeTruthy();
    expect(document.querySelector(".vfix")).toBeTruthy();
    expect(document.querySelector(".vgrid")).toBeNull();
    expect(document.querySelector(".vfix")!.textContent).toContain("OpenAI");
  });

  it("密钥留空保留：编辑态不填 Key 也能提交，占位与掩码提示齐备", async () => {
    const onSubmit = vi.fn(async (_data: ApiConfigFormData) => {});
    render(<ApiConfigForm open config={editCfg()} onSubmit={onSubmit} onCancel={vi.fn()} />);
    const key = document.getElementById("cfKey") as HTMLInputElement;
    expect(key.placeholder).toBe("留空则保留当前密钥");
    expect(screen.getByText(/当前密钥：sk-\*\*\*\*9999/)).toBeTruthy();
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: "主力", api_key: "" });
  });

  it("编辑态仍可切接口格式（格式按钮可点，双格式厂商）", () => {
    render(
      <ApiConfigForm
        open
        config={editCfg({ vendor: "deepseek", api_format: "openai" })}
        onSubmit={vi.fn(async () => {})}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Anthropic 格式"));
    expect(screen.getByText("Anthropic 格式").className).toContain("on");
    fireEvent.click(screen.getByText("OpenAI 格式"));
    expect(screen.getByText("OpenAI 格式").className).toContain("on");
  });

  it("测试连接返回不带 models 字段：按空列表 + note 判定", async () => {
    const onTest = vi.fn(async () => ({ ok: true, status: "ok", note: "端点未返回模型列表" }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onTest={onTest} />);
    setField("cfName", "x");
    fireEvent.click(screen.getByText("DeepSeek"));
    setField("cfBase", "https://api.deepseek.com");
    setField("cfKey", "sk-1");
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText("端点未返回模型列表")).toBeTruthy();
  });

  it("表单随编辑目标重置：换 config → 字段刷新、错误与测试结果清空、Key 清空", async () => {
    const onTest = vi.fn(async () => ({ ok: false, status: "auth_error", error: "密钥无效" }));
    const { rerender } = render(
      <ApiConfigForm open config={editCfg()} onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onTest={onTest} />,
    );
    setField("cfKey", "sk-typed");
    fireEvent.click(screen.getByText("测试连接"));
    await screen.findByText("密钥无效");
    // 切到另一份配置（formKey 变化 → 渲染期重置）
    rerender(
      <ApiConfigForm
        open
        config={editCfg({ id: "c2", name: "备用", base_url: "https://api.anthropic.com", vendor: "anthropic", api_format: "anthropic" })}
        onSubmit={vi.fn(async () => {})}
        onCancel={vi.fn()}
        onTest={onTest}
      />,
    );
    expect((document.getElementById("cfName") as HTMLInputElement).value).toBe("备用");
    expect((document.getElementById("cfBase") as HTMLInputElement).value).toBe("https://api.anthropic.com");
    expect((document.getElementById("cfKey") as HTMLInputElement).value).toBe("");
    expect(screen.queryByText("密钥无效")).toBeNull();
    rerender(<ApiConfigForm open config={null} onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    expect((document.getElementById("cfName") as HTMLInputElement).value).toBe(""); // 新建态重置
    expect(document.querySelector(".vgrid")).toBeTruthy();
  });
});
