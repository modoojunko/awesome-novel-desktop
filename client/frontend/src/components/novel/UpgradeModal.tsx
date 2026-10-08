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

/** PRO 档权益（book.html benefit 三行逐字复刻） */
const PRO_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "AI 生成正文（流式输出）",
    desc: "工具栏「AI 生成正文」→ 提示词由设定与章纲自动组装、可编辑 → 流式写入正文。",
  },
  {
    icon: ICON_BOOK,
    stroke: true,
    title: "设定作为 AI 上下文",
    desc: "6 项世界观设定（题材/简介/世界/风格/伏笔/角色）参与提示词组装。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "卷/章高级字段",
    desc: "结构模板、冲突阶梯、剧情条目、情绪设计——作为生成上下文与创作规范。",
  },
];

/** 标准档权益（口径＝四档矩阵：AI 管流程——卷规划/拆章/章纲/体检/设定域，正文自己写） */
const STANDARD_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "大纲到章纲的 AI 流程",
    desc: "卷规划（铺空缺）、拆下一章三方向、章纲抽卡与补缺——落笔前的这一段交给 AI。",
  },
  {
    icon: ICON_BOOK,
    stroke: true,
    title: "体检与自检",
    desc: "卷体检、章自检、与卷纲冲突检测：只给判断与建议，不代笔。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "设定域 AI 与文风建议",
    desc: "人物、世界、简介、题材一次拟一稿，采纳才写入；文风建议随章给调整项。",
  },
];

/** MAX 档权益（＝PRO 之上的三件 MAX 专属能力，文案沿用各处既有一句口径） */
const MAX_BENEFITS: Benefit[] = [
  {
    icon: ICON_STAR,
    title: "剧情推演 · 按回合走一遍",
    desc: "先定走法再逐步推演；走法可收进本章剧情条目。",
  },
  {
    icon: ICON_BOOK,
    stroke: true,
    title: "去AI味",
    desc: "选中段落去掉机器腔，对照预览后替换。",
  },
  {
    icon: ICON_SHIELD,
    stroke: true,
    title: "文风蒸馏",
    desc: "交 3,000–10,000 字你认可的样本，AI 学出六行基线。",
  },
];

/** 各档权益与标题（标题逐档写全，避免「升级PRO」这类空格/字距问题） */
const TIER_PITCH: Record<TierKey, { title: string; rows: Benefit[] }> = {
  free: { title: "升级 PRO · 解锁 AI 能力", rows: PRO_BENEFITS },
  standard: { title: "升级标准 · 解锁 AI 能力", rows: STANDARD_BENEFITS },
  pro: { title: "升级 PRO · 解锁 AI 能力", rows: PRO_BENEFITS },
  max: { title: "升级 MAX · 解锁剧情推演与去 AI 味", rows: MAX_BENEFITS },
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
