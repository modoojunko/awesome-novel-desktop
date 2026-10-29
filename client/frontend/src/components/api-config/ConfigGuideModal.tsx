/**
 * 配置指南弹窗（c-modelconfig-help-guide）：
 * 按接口格式三类（OpenAI 格式｜Anthropic 格式｜Google 系）组织的配置步骤手册。
 * 固定尺寸 880×760（拍板 10-29：不随视口缩放、不随页签切换跳尺寸），内容超高内部滚动。
 * 文案＝产品文案终稿（docs/design-c/drafts/…-配置步骤指南-原型.html 逐字），作家语汇
 * 无实现词汇（协议/SDK/端点/探针等，测试黑名单钉住）；领 Key 地址表数据化便于复核。
 */
import { useEffect, useState } from "react";
import Modal from "../design/Modal";

export type GuideTab = "openai" | "anthropic" | "google";

/** 供应商方块 id → 指南页签（两处入口共用的定位单源）。 */
export function guideTabForVendor(vendorId: string | null | undefined): GuideTab {
  if (vendorId === "anthropic" || vendorId === "opencode-go-claude") return "anthropic";
  if (vendorId === "gemini") return "google";
  return "openai";
}

const GUIDE_TABS: Array<{ id: GuideTab; label: string }> = [
  { id: "openai", label: "OpenAI 格式" },
  { id: "anthropic", label: "Anthropic 格式" },
  { id: "google", label: "Google 系" },
];

/** 领 Key 速查表（OpenAI 格式页签）：发布前随实现 PR 人工复核过一遍（入口会改版）。 */
const OPENAI_KEY_SOURCES: Array<{ name: string; url: string }> = [
  { name: "OpenAI", url: "platform.openai.com" },
  { name: "DeepSeek", url: "platform.deepseek.com" },
  { name: "GLM", url: "open.bigmodel.cn" },
  { name: "Kimi", url: "platform.moonshot.cn" },
  { name: "Qwen", url: "阿里云百炼 · bailian.console.aliyun.com" },
  { name: "豆包", url: "火山方舟 · console.volcengine.com/ark" },
  { name: "Ollama", url: "本机运行，无需 Key" },
  { name: "OpenCode Go", url: "opencode.ai（订阅制，一把 Key 全家用）" },
];

interface GuideStep {
  title: string;
  body: string[];
}

interface GuideFaq {
  q: string;
  a: string;
}

interface GuideContent {
  /** 适用范围 chips（与供应商方块命名逐字一致） */
  scope: string[];
  /** 一句定位说明 */
  intro: string;
  steps: GuideStep[];
  faqs: GuideFaq[];
}

const GUIDE_CONTENT: Record<GuideTab, GuideContent> = {
  openai: {
    scope: ["OpenAI", "DeepSeek", "GLM", "Kimi", "Qwen", "豆包 · 火山方舟", "Ollama（本地）", "OpenCode Go · 通用", "OpenAI 兼容"],
    intro: "大多数国内外服务商都用这一格式，不确定就先按它配。",
    steps: [
      {
        title: "领 API Key",
        body: ["到服务商的开放平台注册并创建一个 API Key（部分平台要先充值或领额度再能用）："],
      },
      {
        title: "选方块、贴 Key",
        body: [
          "点「添加 API Key」，在方块区点对应服务商：地址已经帮你填好，起个名字、贴上 Key 即可。中转站选「OpenAI 兼容」方块，地址照抄服务商给的。",
        ],
      },
      {
        title: "选模型",
        body: ["贴上 Key 后模型清单会自动到位，选一个就行；没拉到清单就照服务商文档手填模型 id（如 deepseek-v4-pro）。"],
      },
      {
        title: "测试连接",
        body: ["点「测试连接」，看到「连接正常」就能保存使用。"],
      },
    ],
    faqs: [
      { q: "提示鉴权失败或 401", a: "Key 抄错、带了空格，或账户没充值、没开额度——回服务商后台核对。" },
      { q: "地址报 404", a: "官方服务商别改预填地址；中转站严格照抄它文档里「接口地址」一截，一般到 /v1 为止。" },
      { q: "拉不到模型清单", a: "不影响使用，手填模型 id 即可——部分服务商不提供清单。" },
    ],
  },
  anthropic: {
    scope: ["Anthropic", "OpenCode Go · Claude 系", "Claude 兼容中转"],
    intro: "Anthropic 的 Claude 系模型，以及提供「Claude 兼容」地址的中转站。",
    steps: [
      {
        title: "领 API Key",
        body: ["Anthropic 在 console.anthropic.com 创建（需要国际网络并绑定支付）；中转站的 Key 由服务商直接发给你。"],
      },
      {
        title: "选方块、贴 Key",
        body: [
          "官方选「Anthropic」方块（地址已预填）；Claude 兼容中转选「OpenAI 兼容」方块，把接口格式切到「Anthropic 格式」，地址照抄服务商给的。",
        ],
      },
      {
        title: "填模型 id",
        body: ["这类服务常不提供模型清单，直接手填（如 claude-sonnet-5），应用也会给出常用候选。"],
      },
      {
        title: "测试连接",
        body: ["看到「连接正常」就能保存使用。"],
      },
    ],
    faqs: [
      { q: "地址填到哪一截", a: "填到域名即可，版本段由系统自动补；误带了也会自动剥掉。" },
      { q: "开了「思考模式」就报错", a: "部分 Claude 兼容服务不支持思考参数，先关掉思考模式再测。" },
      { q: "鉴权失败或 401", a: "回服务商后台核对 Key 与余额。" },
    ],
  },
  google: {
    scope: ["Gemini（官方）", "带 Gemini 的中转"],
    intro: "Google 的 Gemini 模型。官方提供了「OpenAI 兼容」入口，在应用里按 OpenAI 格式配置即可。",
    steps: [
      {
        title: "领 API Key",
        body: ["到 Google AI Studio（aistudio.google.com/apikey）创建，有免费额度；需要能访问 Google 的网络。"],
      },
      {
        title: "选方块、贴 Key",
        body: ["选「Gemini」方块：Google 官方兼容地址已预填，接口格式保持「OpenAI 格式」，贴上 Key 即可。"],
      },
      {
        title: "选模型",
        body: ["清单拉得到就选；拉不到就照 AI Studio 的模型列表手填模型 id。"],
      },
      {
        title: "测试连接",
        body: ["看到「连接正常」就能保存使用。"],
      },
    ],
    faqs: [
      { q: "一直超时、连不上", a: "你的网络到 Google 不通——换有国际网络的线路，或改用带 Gemini 的中转服务（按「OpenAI 格式」页签的方式配置）。" },
      { q: "思考模式关不掉", a: "部分 Gemini 型号始终会思考，「关闭」只对 Flash 系生效（表单里也有同样提示）。" },
      { q: "模型 id 报「不存在」", a: "以 AI Studio 的模型列表为准，逐字复制。" },
    ],
  },
};

export default function ConfigGuideModal({
  open,
  onClose,
  initialTab,
}: {
  open: boolean;
  onClose: () => void;
  initialTab?: GuideTab;
}) {
  const [tab, setTab] = useState<GuideTab>(initialTab ?? "openai");

  // 打开时按入口定位页签；切换 initialTab（入口携带不同供应商）即时跟随
  useEffect(() => {
    if (open && initialTab) setTab(initialTab);
  }, [open, initialTab]);

  const c = GUIDE_CONTENT[tab];

  return (
    <Modal open={open} onClose={onClose} title="配置指南" width={880}>
      <div className="guide-body">
        <p className="guide-lead">
          三步把一个 AI 服务接进爱小说：<b>领 Key</b> → <b>选方块贴 Key</b> → <b>测试连接</b>
          。按服务商使用的接口格式分三类，选一类照着做：
        </p>
        <div className="seg guide-tabs" role="group" aria-label="接口格式分类">
          {GUIDE_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={tab === t.id ? "on" : ""}
              aria-pressed={tab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <p className="guide-scope-intro">
          这一类包括：
          {c.scope.map((s) => (
            <span key={s} className="guide-chip">
              {s}
            </span>
          ))}
        </p>
        <p className="guide-intro">{c.intro}</p>

        <ol className="guide-steps">
          {c.steps.map((s, i) => (
            <li key={s.title} className="guide-step">
              <i>{i + 1}</i>
              <div>
                <b>{s.title}</b>
                {s.body.map((p) => (
                  <p key={p.slice(0, 18)}>{p}</p>
                ))}
                {tab === "openai" && s.title === "领 API Key" && (
                  <div className="guide-kv">
                    {OPENAI_KEY_SOURCES.map((k) => (
                      <div key={k.name} className="guide-kv-row">
                        <b>{k.name}</b>
                        <code>{k.url}</code>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>

        <details className="guide-faq">
          <summary>常见问题</summary>
          <div className="guide-qa">
            {c.faqs.map((f) => (
              <div key={f.q}>
                <b>{f.q}</b>
                <p>{f.a}</p>
              </div>
            ))}
          </div>
        </details>
      </div>
    </Modal>
  );
}
