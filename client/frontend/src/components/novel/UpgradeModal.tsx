// 升级 PRO 弹窗（book.html #modalUpgrade 复刻）：benefit 三行逐字复刻。
// 产品化（ADJUSTMENTS）：确认升级 = 跳 S端 门户开通页（新标签），非演示态就地转 PRO。
import { useState } from "react";
import Modal from "@/components/design/Modal";
import { fetchPortalUrl, isSafeExternalUrl } from "@/lib/portal";
import { toast } from "@/lib/toast";

export default function UpgradeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [jumping, setJumping] = useState(false);

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
      title="升级 PRO · 解锁 AI 能力"
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
        不改变现有操作路径，同一本书内解锁：
      </p>
      <div className="benefit-row">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z" />
        </svg>
        <div>
          <b>AI 生成正文（流式输出）</b>
          <p>工具栏「AI 生成正文」→ 提示词由设定与章纲自动组装、可编辑 → 流式写入正文。</p>
        </div>
      </div>
      <div className="benefit-row">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 19.5A2.5 2.5 0 016.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
        </svg>
        <div>
          <b>设定作为 AI 上下文</b>
          <p>6 项世界观设定（题材/简介/世界/风格/伏笔/角色）参与提示词组装。</p>
        </div>
      </div>
      <div className="benefit-row">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 3l7 4v5c0 4.5-3 8-7 9-4-1-7-4.5-7-9V7l7-4z" />
          <path d="M9.5 12l2 2 3.5-4" />
        </svg>
        <div>
          <b>卷/章高级字段</b>
          <p>结构模板、冲突阶梯、剧情条目、情绪设计——作为生成上下文与创作规范。</p>
        </div>
      </div>
    </Modal>
  );
}
