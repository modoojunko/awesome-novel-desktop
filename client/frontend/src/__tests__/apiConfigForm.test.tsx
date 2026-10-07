// 添加/编辑 API Key 弹窗（ApiConfigForm）契约（覆盖率专项·批 1）：
//   新建态（供应商格选择/格式锁定矩阵/供应商默认值预填〔2026-10-05 拍板反转「URL 不预填」〕/
//   校验四态/提交成功失败/测试连接四分支）
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

  it("预填：选 DeepSeek 自动填 Base URL＋模型名称，只填 Key 即可提交", async () => {
    const onSubmit = vi.fn(async (_data: ApiConfigFormData) => {});
    render(<ApiConfigForm open onSubmit={onSubmit} onCancel={vi.fn()} />);
    const base = () => document.getElementById("cfBase") as HTMLInputElement;
    const model = () => document.getElementById("cfModel") as HTMLInputElement;
    expect(base().value).toBe("");
    expect(model().value).toBe("");
    fireEvent.click(screen.getByText("DeepSeek"));
    expect(base().value).toBe("https://api.deepseek.com");
    expect(model().value).toBe("deepseek-v4-pro");
    setField("cfName", "写作");
    setField("cfKey", "sk-1");
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "写作",
      vendor_id: "deepseek",
      base_url: "https://api.deepseek.com",
      model: "deepseek-v4-pro",
      api_key: "sk-1",
      api_format: "openai",
    });
  });

  it("手改不覆盖：手改的 Base URL 切供应商保持用户值；未手改的模型名照常随供应商更新", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    const base = () => document.getElementById("cfBase") as HTMLInputElement;
    const model = () => document.getElementById("cfModel") as HTMLInputElement;
    fireEvent.click(screen.getByText("DeepSeek"));
    setField("cfBase", "https://mine.example/v1"); // 手改
    fireEvent.click(screen.getByText("GLM"));
    expect(base().value).toBe("https://mine.example/v1"); // 手改字段不被覆盖
    expect(model().value).toBe(""); // 未手改 → 随 GLM 登记值（模型 id 无据留空）
    fireEvent.click(screen.getByText("DeepSeek"));
    expect(base().value).toBe("https://mine.example/v1"); // 仍不被覆盖
    expect(model().value).toBe("deepseek-v4-pro"); // 模型名仍是预填态 → 随供应商更新
    setField("cfModel", "my-model"); // 手改模型名
    fireEvent.click(screen.getByText("GLM"));
    expect(model().value).toBe("my-model"); // 手改的模型名同样不被覆盖
  });

  it("无登记值不预填：OpenAI 兼容留空；切格式按「供应商×格式」登记值更新（GLM 双地址）", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    const base = () => document.getElementById("cfBase") as HTMLInputElement;
    const model = () => document.getElementById("cfModel") as HTMLInputElement;
    fireEvent.click(screen.getByText("OpenAI 兼容"));
    expect(base().value).toBe("");
    expect(model().value).toBe("");
    fireEvent.click(screen.getByText("GLM"));
    expect(base().value).toBe("https://open.bigmodel.cn/api/paas/v4");
    expect(model().value).toBe(""); // 模型 id 无据留空
    fireEvent.click(screen.getByText("Anthropic 格式"));
    expect(base().value).toBe("https://open.bigmodel.cn/api/anthropic");
    fireEvent.click(screen.getByText("OpenAI 格式"));
    expect(base().value).toBe("https://open.bigmodel.cn/api/paas/v4");
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
    // 无登记值供应商（OpenAI 兼容）不预填 → Base URL 仍必填
    fireEvent.click(screen.getByText("OpenAI 兼容"));
    submit();
    expect(await screen.findByText("请输入 Base URL")).toBeTruthy();
    setField("cfBase", "https://api.deepseek.com");
    submit();
    expect(await screen.findByText("请输入 API Key")).toBeTruthy();
    // Ollama 免 Key（预填的 localhost 不覆盖手填 URL）
    fireEvent.click(screen.getByText("Ollama"));
    submit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "我的配置",
      vendor_id: "ollama",
      base_url: "https://api.deepseek.com",
      model: "",
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
    // 模型名称＝创建表单一级字段，编辑态不渲染（沿用已存值，不施加预填）
    expect(document.getElementById("cfModel")).toBeNull();
  });

  it("编辑态留空：表单提交空串（**省略字段是页面层职责**，见 ApiKeyConfigPage 用例），占位与掩码提示齐备", async () => {
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

  it("密钥输入不泄漏：密码框 + 关自动填充 + 明文不进 DOM 文本", () => {
    render(<ApiConfigForm open config={editCfg()} onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    const key = document.getElementById("cfKey") as HTMLInputElement;
    expect(key.type).toBe("password");
    expect(key.getAttribute("autocomplete")).toBe("off");
    fireEvent.change(key, { target: { value: "sk-typed-secret" } });
    expect(key.value).toBe("sk-typed-secret"); // 只存在于输入框
    expect(document.body.textContent).not.toContain("sk-typed-secret"); // 不进任何文本节点
    expect(document.body.textContent).toContain("sk-****9999"); // 展示的是掩码
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

describe("ApiConfigForm 模型清单自动拉取（c-api-config-auto-models）", () => {
  const blurKey = () => fireEvent.blur(document.getElementById("cfKey")!);

  it("Key 失焦自动拉清单：无登记默认的供应商默认选首项；同参数重复失焦不重拉", async () => {
    const onFetchModels = vi.fn(async () => ({
      ok: true,
      status: "ok",
      models: ["kimi-k3", "kimi-k2.7-code"],
    }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    // 字段顺序拍板（2026-10-07）：Base URL → API Key → 模型（模型垫底，紧接 Key 失焦拉清单的动线）
    const [b, k, m] = ["cfBase", "cfKey", "cfModel"].map((id) => document.getElementById(id)!);
    expect(b.compareDocumentPosition(k) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(k.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("kimi-k3"),
    );
    expect(await screen.findByText("已拉到 2 个模型")).toBeTruthy();
    expect(onFetchModels).toHaveBeenCalledTimes(1);
    expect(onFetchModels).toHaveBeenCalledWith({
      vendor_id: "kimi",
      base_url: "https://api.moonshot.cn/v1",
      api_key: "sk-1",
      api_format: "openai",
    });
    // 同参数再次失焦：指纹去重，不重复拉
    blurKey();
    await Promise.resolve();
    expect(onFetchModels).toHaveBeenCalledTimes(1);
  });

  it("登记默认模型在清单内优先选中；不在清单内退清单首项", async () => {
    const onFetchModels = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["deepseek-flash", "deepseek-v4-pro"] })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["deepseek-flash"] });
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("DeepSeek"));
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-v4-pro"); // 预填初值
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-v4-pro"),
    ); // 登记默认 ∈ 清单 → 保持登记值（不取首项 flash）
    // 清 Key 后切走再切回（中间不拉取）；回切即重拉，清单不再含登记默认 → 退首项
    setField("cfKey", "");
    fireEvent.click(screen.getByText("GLM"));
    setField("cfKey", "sk-1");
    fireEvent.click(screen.getByText("DeepSeek"));
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-flash"),
    );
  });

  it("无清单端点：空清单＋候选 chips＋说明，点 chip 选中；手填兜底仍可提交", async () => {
    const onSubmit = vi.fn(async (_data: ApiConfigFormData) => {});
    const onFetchModels = vi.fn(async () => ({
      ok: true,
      status: "ok",
      models: [],
      candidates: ["glm-5.3", "glm-5.3-flash"],
      note: "该端点不提供模型列表（Anthropic 兼容端点常见）——可手动填模型 id",
    }));
    render(<ApiConfigForm open onSubmit={onSubmit} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("GLM"));
    fireEvent.click(screen.getByText("Anthropic 格式"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    expect(await screen.findByText("无模型清单")).toBeTruthy(); // 不点开弹层也可见「无清单」态
    // 聚焦模型框弹层：说明＋候选 chips 可见，点 chip 选中
    fireEvent.focus(document.getElementById("cfModel")!);
    expect(screen.getByRole("listbox", { name: "模型清单" })).toBeTruthy();
    expect(screen.getByText(/不提供模型列表/)).toBeTruthy();
    fireEvent.click(screen.getByText("glm-5.3"));
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("glm-5.3");
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ model: "glm-5.3" });
  });

  it("拉取失败不阻塞：失败提示＋「重新拉取」出口，手填模型仍可保存；重拉刷新清单但不覆盖手填", async () => {
    const onSubmit = vi.fn(async (_data: ApiConfigFormData) => {});
    const onFetchModels = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: "auth_error", error: "认证失败 (HTTP 401)" })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["m-1"] });
    render(<ApiConfigForm open onSubmit={onSubmit} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-bad");
    blurKey();
    expect(await screen.findByText("认证失败 (HTTP 401)")).toBeTruthy();
    expect(screen.getByText("重新拉取")).toBeTruthy();
    // 手填不受失败影响，可保存
    setField("cfModel", "my-model");
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ model: "my-model" });
    // 「重新拉取」强制重拉：清单刷新（元信息更新），手填值保持不被覆盖
    fireEvent.click(screen.getByText("重新拉取"));
    expect(await screen.findByText("已拉到 1 个模型")).toBeTruthy();
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("my-model");
  });

  it("测试连接拉回清单同步刷新选择器（双保险）；手选值不被覆盖", async () => {
    const onTest = vi.fn(async () => ({ ok: true, status: "ok", models: ["gpt-4o", "gpt-4o-mini"] }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onTest={onTest} />);
    setField("cfName", "x");
    fireEvent.click(screen.getByText("OpenAI"));
    setField("cfKey", "sk-1");
    fireEvent.click(screen.getByText("测试连接"));
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("gpt-4o"),
    ); // 无登记默认 → 清单首项
    expect(await screen.findByText("已拉到 2 个模型")).toBeTruthy();
    // 手选后再次测试：清单刷新但手选值保持
    setField("cfModel", "gpt-4o-mini");
    fireEvent.click(screen.getByText("测试连接"));
    await waitFor(() => expect(onTest).toHaveBeenCalledTimes(2));
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("gpt-4o-mini");
  });

  it("弹层键盘交互：聚焦展开、输入过滤、ArrowDown＋Enter 选中、Esc 收起", async () => {
    const onFetchModels = vi.fn(async () => ({
      ok: true,
      status: "ok",
      models: ["qwen3.6-plus", "qwen3.6-max", "qwen3.6-flash"],
    }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Qwen"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("qwen3.6-plus"),
    );
    const input = document.getElementById("cfModel") as HTMLInputElement;
    fireEvent.focus(input);
    // 输入过滤（组合框语义：输入即搜索）
    fireEvent.change(input, { target: { value: "max" } });
    expect(screen.queryByText("qwen3.6-plus")).toBeNull();
    expect(screen.getByText("qwen3.6-max")).toBeTruthy();
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input.value).toBe("qwen3.6-max");
    expect(document.querySelector(".mp-panel")).toBeNull(); // 选中后收起
    // 重新展开后 Esc 收起
    fireEvent.focus(input);
    expect(document.querySelector(".mp-panel")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(document.querySelector(".mp-panel")).toBeNull();
  });

  it("Ollama 免 Key：选供应商即拉本地清单并默认选首项", async () => {
    const onFetchModels = vi.fn(async () => ({
      ok: true,
      status: "ok",
      models: ["llama3:8b"],
    }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Ollama"));
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("llama3:8b"),
    );
    expect(onFetchModels).toHaveBeenCalledWith({
      vendor_id: "ollama",
      base_url: "http://localhost:11434",
      api_key: "",
      api_format: "openai",
    });
  });

  it("在途过期响应丢弃：换供应商后旧清单响应不落地", async () => {
    let resolveFirst: (v: { ok: boolean; status: string; models: string[] }) => void = () => {};
    const first = new Promise<{ ok: boolean; status: string; models: string[] }>((res) => {
      resolveFirst = res;
    });
    const onFetchModels = vi.fn().mockImplementationOnce(() => first).mockResolvedValueOnce({
      ok: true,
      status: "ok",
      models: ["glm-5.3"],
    });
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey(); // Kimi 在途
    fireEvent.click(screen.getByText("GLM")); // 参数已变 → 序号作废 Kimi 响应，立即拉 GLM
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("glm-5.3"),
    );
    resolveFirst({ ok: true, status: "ok", models: ["kimi-k3"] }); // 过期响应迟到
    await Promise.resolve();
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("glm-5.3"); // 不被覆盖
  });
});
