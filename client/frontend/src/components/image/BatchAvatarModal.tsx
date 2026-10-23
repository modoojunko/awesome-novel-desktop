import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/design/Modal";
import { toast } from "@/lib/toast";
import { useFeature } from "@/hooks/useTier";
import { imageApi, type ImageJob } from "@/lib/imageApi";

export interface BatchCharacter {
  id: string;
  name: string;
  hasAvatar: boolean;
}

interface Props {
  open: boolean;
  novelId: string;
  characters: BatchCharacter[];
  onClose: () => void;
  onChanged: () => void | Promise<void>;
}

const STATE_LABEL: Record<string, string> = {
  pending: "排队",
  running: "生成中",
  completed: "完成",
  failed: "失败",
  cancelled: "已取消",
  cancelled_billed: "已取消（已计费）",
};

export default function BatchAvatarModal({
  open, novelId, characters, onClose, onChanged,
}: Props) {
  const canGenerate = useFeature("image-generate");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(characters.map((c) => c.id)));
  const [job, setJob] = useState<ImageJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelected(new Set(characters.filter((c) => !c.hasAvatar).map((c) => c.id)));
    setJob(null);
    setError(null);
  }, [open, characters]);

  const running = !!job && ["queued", "running"].includes(job.status);

  useEffect(() => {
    if (!job || !running) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void imageApi.getImageJob(job.id).then((next) => {
        if (!alive) return;
        setJob(next);
        if (next.status === "completed") void onChanged();
      }).catch(() => {
        // 轮询失败下个 tick 重试；接口层负责全局网络提示
      });
    }, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [job, running, onChanged]);

  const itemStates = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of job?.items || []) map.set(item.character_id, item.status);
    return map;
  }, [job]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const start = async () => {
    if (!canGenerate) {
      toast.info("批量头像是 PRO 功能；单个头像可免费上传");
      return;
    }
    if (!selected.size) {
      toast.info("先选择至少一个角色");
      return;
    }
    setError(null);
    try {
      setJob(await imageApi.createAvatarBatch(novelId, [...selected]));
      toast.success(`已提交 ${selected.size} 个角色的头像生成`);
    } catch (e) {
      setError((e as Error).message || "批量任务提交失败");
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      setJob(await imageApi.cancelImageJob(job.id));
      toast.success("已请求取消；已生成的候选会保留");
    } catch (e) {
      toast.error((e as Error).message || "取消失败");
    }
  };

  // 取消/失败后原地重排同一任务（已完成 item 保留，只补未完成的部分）。
  const retry = async () => {
    if (!job) return;
    try {
      setJob(await imageApi.retryImageJob(job.id));
      setError(null);
      toast.success("已重新排队");
    } catch (e) {
      toast.error((e as Error).message || "重试失败");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="批量生成头像"
      width={620}
      footer={(
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            {running ? "后台运行" : "关闭"}
          </button>
          {running ? (
            <button className="btn btn-danger" onClick={() => void cancel()}>取消生成</button>
          ) : (
            <button
              className="btn btn-primary"
              disabled={!canGenerate || !selected.size}
              onClick={() => void start()}
            >
              生成 {selected.size} 个头像
            </button>
          )}
        </>
      )}
    >
      <div className="img-batch">
        <p className="img-hint">
          按角色卡白名单逐个生成一张头像候选；已生成的候选不会因取消丢失，可在角色页逐一采用。
          {!canGenerate && " 批量生成是 PRO 功能；免费版可逐个上传头像。"}
        </p>
        {error && <div className="ferr">{error}</div>}
        {job?.error_message && <div className="ferr">{job.error_message}</div>}
        <div className="img-batch-list">
          {characters.map((c) => {
            const state = itemStates.get(c.id) || (job ? "pending" : c.hasAvatar ? "已有头像" : "待选择");
            return (
              <label key={c.id} className="img-batch-row">
                <input
                  type="checkbox"
                  disabled={running}
                  checked={selected.has(c.id)}
                  onChange={() => toggle(c.id)}
                />
                <span className="nm">{c.name || "未命名"}</span>
                <span className={`img-batch-state ${state}`}>{STATE_LABEL[state] || state}</span>
              </label>
            );
          })}
        </div>
        {job && (
          <div className="img-gen-head">
            <span className="img-hint">
              任务状态：{STATE_LABEL[job.status] || job.status} · 已生成 {job.produced_count} 张
            </span>
            <span className={`img-job-status ${job.status}`}>{job.status}</span>
            {["failed", "cancelled"].includes(job.status) && (
              <button className="btn btn-ghost btn-sm" onClick={() => void retry()}>
                重试
              </button>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
