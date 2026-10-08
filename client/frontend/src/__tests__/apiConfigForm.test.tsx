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

  it("编辑态 Key 失焦不触发自动拉取（编辑态无模型选择器）", () => {
    const onFetchModels = vi.fn(async (_d: unknown) => ({ ok: false, status: "ok", models: [] }));
    render(
      <ApiConfigForm
        open
        config={editCfg()}
        onSubmit={vi.fn(async () => {})}
        onCancel={vi.fn()}
        onFetchModels={onFetchModels}
      />,
    );
    fireEvent.change(document.getElementById("cfKey")!, { target: { value: "sk-typed" } });
    fireEvent.blur(document.getElementById("cfKey")!);
    expect(onFetchModels).not.toHaveBeenCalled();
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

  it("默认选中清单首项（2026-10-07 二次拍板「默认选第一个，不评估价值」——登记默认不优先）", async () => {
    const onFetchModels = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["deepseek-flash", "deepseek-v4-pro"] })
      .mockResolvedValueOnce({ ok: true, status: "ok", models: ["deepseek-v4-pro"] });
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("DeepSeek"));
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-v4-pro"); // 预填初值
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-flash"),
    ); // 登记默认 ∈ 清单也不优先——严格选清单首项
    // 清 Key 后切走再切回（中间不拉取）；回切即重拉，首项为 v4-pro → 选中它
    setField("cfKey", "");
    fireEvent.click(screen.getByText("GLM"));
    setField("cfKey", "sk-1");
    fireEvent.click(screen.getByText("DeepSeek"));
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("deepseek-v4-pro"),
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

  it("OpenAI 兼容：显示兼容模版引导文案（Gemini 兼容地址/手填模型 id/指向中转站按钮），他商不显示", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    // 默认 OpenAI：无引导
    expect(screen.queryByText(/generativelanguage\.googleapis\.com/)).toBeNull();
    fireEvent.click(screen.getByText("OpenAI 兼容"));
    const hint = screen.getByText(/未列厂商（如 Google Gemini）走 OpenAI 兼容模版/);
    expect(hint.textContent).toContain("https://generativelanguage.googleapis.com/v1beta/openai/");
    expect(hint.textContent).toContain("手填模型 id");
    expect(hint.textContent).toContain("中转站 API"); // 反代/转发口径收编进中转站按钮（c-relay-vendor-entry）
  });

  it("中转站 API：显示中转站口径引导（/v1 填法/403 分组权限手填），他商不显示", () => {
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} />);
    expect(screen.queryByText(/中转站\/转发 API：Base URL 填站方给的接口地址/)).toBeNull();
    fireEvent.click(screen.getByText("中转站 API"));
    const hint = screen.getByText(/中转站\/转发 API：Base URL 填站方给的接口地址/);
    expect(hint.textContent).toContain("/v1");
    expect(hint.textContent).toContain("403");
    expect(hint.textContent).toContain("手填模型 id");
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
      base_url: "http://localhost:11434/v1", // 登记值含版本段（2026-10-08 修正）；后端 tags 探针剥尾 /v1
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

  it("在途拉取期间手填不被迟到响应覆盖（评审 P0：守卫读闭包过期 state 曾把它清掉）", async () => {
    let resolveFetch: (v: { ok: boolean; status: string; models: string[] }) => void = () => {};
    const pending = new Promise<{ ok: boolean; status: string; models: string[] }>((res) => {
      resolveFetch = res;
    });
    const onFetchModels = vi.fn(async () => pending);
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey(); // 慢端点在途（最长 10s 超时窗口）
    setField("cfModel", "my-model"); // 用户立刻手填（onChange 置手选标记）
    resolveFetch({ ok: true, status: "ok", models: ["kimi-k3", "kimi-k2.7-code"] }); // 响应迟到
    await waitFor(() => expect(screen.getByText("已拉到 2 个模型")).toBeTruthy()); // 清单照常落地
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("my-model"); // 手填值不被覆盖
  });

  it("Esc 只收弹层不关表单弹窗（评审 P1：Modal 在 window 上听 Esc）", async () => {
    const onFetchModels = vi.fn(async () => ({ ok: true, status: "ok", models: ["m-1", "m-2"] }));
    const onCancel = vi.fn();
    render(
      <ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={onCancel} onFetchModels={onFetchModels} />,
    );
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() =>
      expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("m-1"),
    );
    const input = document.getElementById("cfModel") as HTMLInputElement;
    fireEvent.focus(input);
    expect(document.querySelector(".mp-panel")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(document.querySelector(".mp-panel")).toBeNull(); // 弹层收起
    expect(onCancel).not.toHaveBeenCalled(); // 表单弹窗不跟着关
  });

  it("供应商切换作废在途请求：清 Key 后切走，旧响应不落地且拉取态复位", async () => {
    let rejectFirst: () => void = () => {};
    const pending = new Promise<{ ok: boolean; status: string; models: string[] }>((_, rej) => {
      // 用 reject 形态钉 catch 内的作废判（seq 已变 → 不落地任何状态）
      rejectFirst = () => rej(new Error("stale"));
    });
    const onFetchModels = vi.fn(async () => pending);
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey(); // Kimi 在途
    await screen.findByText("正在获取模型清单…");
    setField("cfKey", ""); // 清 Key → 切供应商不再发新请求顶替
    fireEvent.click(screen.getByText("GLM"));
    rejectFirst(); // 旧响应（失败形态）迟到
    await Promise.resolve();
    // 旧供应商清单/默认选中不落地；拉取态已复位（不卡「正在获取…」、无失败提示）
    expect(screen.queryByText("正在获取模型清单…")).toBeNull();
    expect(screen.queryByText("重新拉取")).toBeNull();
    expect((document.getElementById("cfModel") as HTMLInputElement).value).toBe("");
  });
});

describe("ApiConfigForm 模型选择器覆盖补齐（CI 全局 100% 覆盖率门禁）", () => {
  const blurKey = () => fireEvent.blur(document.getElementById("cfKey")!);
  const blurBase = () => fireEvent.blur(document.getElementById("cfBase")!);
  const input = () => document.getElementById("cfModel") as HTMLInputElement;
  const panel = () => document.querySelector(".mp-panel") as HTMLElement | null;

  async function setupFetched(onFetchModels: (data: any) => Promise<any>, models = ["m-1", "m-2", "m-3"]) {
    render(
      <ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />,
    );
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() => expect(input().value).toBe(models[0]));
    return models;
  }

  it("拉取信封兜底三态：ok 不带 models→空清单；ok:false 不带 error→兜底文案；reject→catch 兜底", async () => {
    const onFetchModels = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "ok" }) // models 缺失 → ?? [] 空清单
      .mockResolvedValueOnce({ ok: false, status: "unknown" }) // error 缺失 → 兜底文案
      .mockRejectedValueOnce(new Error("net"));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    blurKey();
    await waitFor(() => expect(onFetchModels).toHaveBeenCalledTimes(1));
    expect(input().value).toBe(""); // 空清单不默认选中
    setField("cfKey", "sk-2"); // 指纹含 Key → 换 Key 重拉
    blurKey();
    expect(await screen.findByText("模型清单获取失败")).toBeTruthy();
    setField("cfKey", "sk-3");
    blurKey();
    expect(await screen.findByText("重新拉取")).toBeTruthy(); // reject 同走兜底
  });

  it("切格式重拉：GLM＋Key 已填，切 Anthropic 格式即按新格式参数拉", async () => {
    const onFetchModels = vi.fn(async () => ({ ok: true, status: "ok", models: ["glm-5.3"] }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />);
    fireEvent.click(screen.getByText("GLM"));
    setField("cfName", "x");
    setField("cfKey", "sk-1");
    fireEvent.click(screen.getByText("Anthropic 格式"));
    await waitFor(() => expect(input().value).toBe("glm-5.3"));
    expect(onFetchModels).toHaveBeenLastCalledWith({
      vendor_id: "glm",
      base_url: "https://open.bigmodel.cn/api/anthropic",
      api_key: "sk-1",
      api_format: "anthropic",
    });
  });

  it("Base URL 失焦触发：Key 空非 ollama 不拉；Key 已填则拉；Ollama 免 Key 亦触发", async () => {
    const onFetchModels = vi.fn(async () => ({ ok: true, status: "ok", models: ["m-1"] }));
    const { unmount } = render(
      <ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchModels} />,
    );
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfName", "x");
    blurBase(); // Key 空 → 不拉
    await Promise.resolve();
    expect(onFetchModels).not.toHaveBeenCalled();
    setField("cfKey", "sk-1");
    blurBase(); // Key 已填 → 拉
    await waitFor(() => expect(onFetchModels).toHaveBeenCalledTimes(1));
    unmount();

    const onFetchOllama = vi.fn(async () => ({ ok: true, status: "ok", models: ["llama3:8b"] }));
    render(
      <ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onFetchModels={onFetchOllama} />,
    );
    fireEvent.click(screen.getByText("Ollama")); // 免 Key 即拉（同参数）
    await waitFor(() => expect(onFetchOllama).toHaveBeenCalledTimes(1));
    blurBase(); // 同参数指纹去重，不重复拉（但触发路径已执行）
    await Promise.resolve();
    expect(onFetchOllama).toHaveBeenCalledTimes(1);
  });

  it("键盘补齐：IME 组合期放行；关态 Enter 早退；关态方向键开层；ArrowUp 上移；开态他键不动作", async () => {
    await setupFetched(async () => ({ ok: true, status: "ok", models: ["m-1", "m-2", "m-3"] }));
    fireEvent.focus(input());
    expect(panel()).toBeTruthy();
    // IME 组合期 Enter：早退——不开不选不关（面板保持、值不变）
    fireEvent.keyDown(input(), { key: "Enter", isComposing: true });
    expect(panel()).toBeTruthy();
    expect(input().value).toBe("m-1");
    // 开态他键（非方向/Enter/Esc）：落空不动作
    fireEvent.keyDown(input(), { key: "z" });
    expect(panel()).toBeTruthy();
    // 开态 Enter 无匹配：不选不吞（手填值原样保留，真实浏览器放行隐式提交）
    fireEvent.change(input(), { target: { value: "no-such-model" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(panel()).toBeTruthy();
    expect(input().value).toBe("no-such-model");
    // 清空过滤词 → 全量三项（组合框按当前值过滤，不清空则方向键被钳位）
    fireEvent.change(input(), { target: { value: "" } });
    expect(document.querySelectorAll(".mp-item").length).toBe(3);
    // Esc 收起（stopPropagation 只关弹层）
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(panel()).toBeNull();
    // 关态 Enter：早退（不选中；真实浏览器里由此放行原生隐式提交，jsdom 不模拟）
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(panel()).toBeNull();
    expect(input().value).toBe("");
    // 关态 ArrowDown → 开层
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(panel()).toBeTruthy();
    // ArrowDown×2 后 ArrowUp：光标钳位往返
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(input().getAttribute("aria-activedescendant")).toBe("cf-model-opt-2");
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    expect(input().getAttribute("aria-activedescendant")).toBe("cf-model-opt-1");
  });

  it("列表直点与选中态高亮：当前值即过滤词时 on 臂；全量列表 mouseEnter 移光标＋click 直选", async () => {
    await setupFetched(async () => ({ ok: true, status: "ok", models: ["q-a", "q-b", "q-c"] }), ["q-a", "q-b", "q-c"]);
    fireEvent.focus(input()); // 过滤词＝当前值 q-a → 列表＝[q-a]，命中 on 臂
    const cur = document.querySelectorAll(".mp-item")[0];
    expect(cur.className).toContain("on");
    fireEvent.mouseEnter(cur);
    fireEvent.click(cur); // 列表项直选
    expect(panel()).toBeNull();
    expect(input().value).toBe("q-a");
    fireEvent.focus(input());
    fireEvent.change(input(), { target: { value: "" } }); // 清空过滤 → 全量
    const items = document.querySelectorAll(".mp-item");
    expect(items.length).toBe(3);
    fireEvent.mouseEnter(items[2]);
    expect(input().getAttribute("aria-activedescendant")).toBe("cf-model-opt-2");
    fireEvent.click(items[1]);
    expect(input().value).toBe("q-b");
    expect(panel()).toBeNull();
  });

  it("选中后再点输入框重开弹层；外点收起；弹层内 pointerdown/mousedown 不误关", async () => {
    await setupFetched(async () => ({ ok: true, status: "ok", models: ["m-1", "m-2"] }));
    fireEvent.focus(input());
    fireEvent.keyDown(input(), { key: "Enter" }); // 选中首项后收起（焦点仍在输入框）
    expect(panel()).toBeNull();
    fireEvent.click(input()); // 再点重开（onClick 臂）
    expect(panel()).toBeTruthy();
    // 弹层内 pointerdown/mousedown（滚动条拖点）：不关
    fireEvent.pointerDown(panel()!);
    fireEvent.mouseDown(panel()!);
    expect(panel()).toBeTruthy();
    // 输入框内 pointerdown：不关
    fireEvent.pointerDown(input());
    expect(panel()).toBeTruthy();
    // 外点（body）：收起
    fireEvent.pointerDown(document.body);
    expect(panel()).toBeNull();
  });

  it("弹层定位：近视口底缘向上翻转（flip 臂，fixed top 兜底 8px）", async () => {
    await setupFetched(async () => ({ ok: true, status: "ok", models: ["m-1"] }));
    const original = window.innerHeight;
    Object.defineProperty(window, "innerHeight", { value: 40, configurable: true });
    try {
      fireEvent.focus(input());
      await waitFor(() => expect(panel()).toBeTruthy());
      expect(panel()!.style.top).toBe("8px"); // jsdom 输入框矩形为 0 → 翻转臂取下限
    } finally {
      Object.defineProperty(window, "innerHeight", { value: original, configurable: true });
    }
  });

  it("测试连接失败信封带清单：选项刷新但不自动改选（失败也可改选正确模型）", async () => {
    const onTest = vi.fn(async () => ({
      ok: false,
      status: "unknown",
      error: "探针被拒（所试模型 m-bad）",
      models: ["m-1", "m-2"],
    }));
    render(<ApiConfigForm open onSubmit={vi.fn(async () => {})} onCancel={vi.fn()} onTest={onTest} />);
    setField("cfName", "x");
    fireEvent.click(screen.getByText("Kimi"));
    setField("cfKey", "sk-1");
    setField("cfModel", "m-bad"); // 手填错 id
    fireEvent.click(screen.getByText("测试连接"));
    expect(await screen.findByText(/探针被拒/)).toBeTruthy();
    expect(await screen.findByText("已拉到 2 个模型")).toBeTruthy(); // 失败信封清单照常刷新
    expect(input().value).toBe("m-bad"); // 不自动改选（手填值保留），用户可从列表改选
  });
});
