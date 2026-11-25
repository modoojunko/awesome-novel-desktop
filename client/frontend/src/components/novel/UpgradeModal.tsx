// 升级引导弹窗（book.html #modalUpgrade 的 PRO 版权益文案）：目标档＝**被触发能力所需档**
// （tier_required）——出口把所点那行的 feature key 传进来（如 ai-plan→标准、ai-detect→PRO）；
// 全局入口（本书偏好/账号区）不带 key，回退＝已有 PRO（含试用）出 MAX、否则出 PRO
// （免费也出 PRO：全局入口不指具体件，PRO 是正文 AI 的起点），
// 免得对已是 PRO 的作者再喊一遍「升级 PRO」。
// 产品化（ADJUSTMENTS）：确认升级 = 跳 S端 门户开通页（新标签），非演示态就地转 PRO。
import { useState, type ReactNode } from "react";
import Modal from "@/components/design/Modal";
import { useFeature, useTier } from "@/hooks/useTier";
import { FEATURES, minTierOf, tierRank, type FeatureKey, type TierKey } from "@/lib/features";
import { fetchPortalUrl, isSafeExternalUrl } from "@/lib/portal";
import { toast } from "@/lib/toast";

const ICON_STAR = (
  <path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z" />
);
const ICON_BOOK = (
  <>
    <path d="M4 19.5A2.5 2.5 0 016.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
  </>
);
const ICON_SHIELD = (
  <>
    <path d="M12 3l7 4v5c0 4.5-3 8-7 9-4-1-7-4.5-7-9V7l7-4z" />
    <path d="M9.5 12l2 2 3.5-4" />
  </>
);

interface Benefit {
  icon: ReactNode;
  stroke?: boolean;
  title: string;
  desc: string;
}

/** PRO 档权益（AI 写手） */
const PRO_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "AI 写手：规划、章纲、正文初稿",
    desc: "卷规划/拆章/章纲/人物/体检出卡你挑；正文方案卡过目后整章生成、逐行采纳。",
  },
  {
    icon: ICON_BOOK,
    stroke: true,
    title: "官方写作知识库 331 本",
    desc: "331 本 / 8197 条 / 36 题材；助理可查可引用，按题材填文风。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "AI 拆书 / 导入已有书",
    desc: "把一本书拆成世界观/人物/大纲/文风/技法，产物可导出、可收进本地知识库。",
  },
  {
    icon: ICON_STAR,
    title: "朱雀 AI 味检测 + 提示词页签",
    desc: "腾讯朱雀段落级标注（自配 Key）；写作提示词自己调。",
  },
];

/** 存量标准档权益（grandfathered）：旧标准 keys 的说明；新售不再提供 */
const STANDARD_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "存量标准会员权益",
    desc: "原标准档已停售；到期前按原权益使用，到期后可回标准（免费）或升级 PRO。",
  },
];

/** MAX 档权益（写作秘书） */
const MAX_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "人味检测 + 逐行修改指引",
    desc: "本地 19 项指标；哪句像 AI、哪段人味不够，标到行并给改法。",
  },
  {
    icon: ICON_BOOK,
    stroke: true,
    title: "AI 封面 / 头像 / 试画 / 批量头像",
    desc: "自配图像 Key；书的第一眼也交给它。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "拆书产物一键建书",
    desc: "勾选拆书里的设定/文风，直接生成一本可写的新书。",
  },
  {
    icon: ICON_STAR,
    title: "发散起草 / 剧情推演 / 文风蒸馏",
    desc: "卡文时它添人添事、演一回合、学你的文风。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "全权托管 + 5 台设备",
    desc: "本书内自动执行（硬地板仍弹卡）；5 台设备 + 飞书内测群。",
  },
];

/** 各档权益与标题 */
const TIER_PITCH: Record<TierKey, { title: string; rows: Benefit[] }> = {
  free: { title: "升级 PRO · AI 写手", rows: PRO_BENEFITS },
  standard: { title: "升级 PRO · AI 写手", rows: PRO_BENEFITS },
  pro: { title: "升级 PRO · AI 写手", rows: PRO_BENEFITS },
  max: { title: "升级 MAX · 写作秘书", rows: MAX_BENEFITS },
};

export default function UpgradeModal({
  open,
  onClose,
  required,
}: {
  open: boolean;
  onClose: () => void;
  /** 被触发能力（tier_required）：出口知道用户点的是哪一行就传进来，弹窗即出该档口径；
   *  全局入口（本书偏好/账号区）不传 → 回退：已有 PRO（含试用）出 MAX，否则出 PRO。 */
  required?: FeatureKey;
}) {
  const [jumping, setJumping] = useState(false);
  const { isStandard, isPro, isMax } = useTier();
  // 已有 ai-generate（PRO/试用同权）；ownRank 用于「已含该能力就不重复喊」的兜底
  const hasPro = useFeature("ai-generate");
  // 试用档同样含 ai-generate（PRO 同权）→ 归 2，避免对已含该能力的档位重复喊同一档
  const ownRank = isMax ? 3 : isPro || hasPro ? 2 : isStandard ? 1 : 0;
  // 防御：required 非登记 key（如误把事件对象传进来）时按「无 key」处理
  const needTier: TierKey | null =
    required && FEATURES[required] ? minTierOf(required) : null;
  const needRank = needTier ? tierRank(needTier) : 0;
  const target: TierKey = needTier && needRank > ownRank ? needTier : hasPro ? "max" : "pro";
  const pitch = TIER_PITCH[target];
  const benefits = pitch.rows;

  const handleConfirm = async () => {
    setJumping(true);
    try {
      const url = await fetchPortalUrl();
      if (isSafeExternalUrl(url)) {
        window.open(url, "_blank", "noopener,noreferrer");
        toast.success("已打开 S 端开通页，完成后刷新本页生效");
        onClose();
      } else {
        toast.error("未获取到有效的开通地址，请稍后再试");
      }
    } finally {
      setJumping(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={pitch.title}
      wbStyle
      locked={jumping}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={jumping}>
            暂不
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void handleConfirm()}
            disabled={jumping}
          >
            确认升级
          </button>
        </>
      }
    >
      <p style={{ margin: "0 0 8px", fontSize: 12.5, color: "var(--muted)" }}>
        {target === "max" ? "不改变现有操作路径，同一本书内追加解锁：" : "不改变现有操作路径，同一本书内解锁："}
      </p>
      {benefits.map((b) => (
        <div className="benefit-row" key={b.title}>
          <svg
            viewBox="0 0 24 24"
            fill={b.stroke ? "none" : "currentColor"}
            stroke={b.stroke ? "currentColor" : undefined}
            strokeWidth={b.stroke ? 1.8 : undefined}
          >
            {b.icon}
          </svg>
          <div>
            <b>{b.title}</b>
            <p>{b.desc}</p>
          </div>
        </div>
      ))}
    </Modal>
  );
}
