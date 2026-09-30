import type { ApiConfig } from "../../types/api-config";
import Modal from "../design/Modal";

interface DeleteConfirmDialogProps {
  config: ApiConfig;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  deleting?: boolean;
  /** 定制尾注（缺省＝通用「引用它的书将回退」口径；朱雀等无引用配置传专属说明） */
  note?: string;
}

/** 删除确认（model-config.html modalDelete 原样：影响盘点红 chips + 可撤销提示） */
export function DeleteConfirmDialog({ config, onConfirm, onCancel, deleting, note }: DeleteConfirmDialogProps) {
  const models = config.models || [];
  const inventory: string[] = [];
  if (models.length) inventory.push(`模型 ${models.length} 个`);

  return (
    <Modal
      open
      onClose={onCancel}
      locked={deleting}
      width={460}
      title="删除配置"
      footer={
        <>
          <button className="btn btn-secondary" onClick={onCancel} disabled={deleting}>
            取消
          </button>
          <button className="btn btn-danger" onClick={() => void onConfirm()} disabled={deleting}>
            确认删除
          </button>
        </>
      }
    >
      <p style={{ margin: 0, fontSize: "13.5px", lineHeight: 1.7 }}>
        确定删除配置 <b>「{config.name}」</b>？
      </p>
      {inventory.length > 0 && (
        <div className="del-inventory">
          <span className="inv-title">删除影响</span>
          {inventory.map((x) => (
            <span key={x} className="inv-chip">
              {x}
            </span>
          ))}
        </div>
      )}
      <p style={{ margin: "8px 0 0", fontSize: "12.5px", color: "var(--muted)" }}>
        {note ?? "删除后引用它的书将回退到「未配置」状态，此操作可撤销。"}
      </p>
    </Modal>
  );
}
