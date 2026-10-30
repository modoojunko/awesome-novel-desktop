// 建书提示条（c-deconstruct-import-async 8.1）：新建的书顶部说明建书时的降级
// （截断/合并/推断），关掉即删键。落点在设定页页顶——默认面板是「题材」，
// 放世界面板里等于用户看不到。
import { useEffect, useState } from "react";
import { dismissImportNotice, getImportNotice } from "@/lib/importNotice";
import { toast } from "@/lib/toast";

export default function ImportNotice({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    void getImportNotice(projectId)
      .then((r) => {
        if (alive) setItems(r.items);
      })
      .catch(() => {
        /* 读不到就当没有：提示条是副本，不挡设定页 */
      });
    return () => {
      alive = false;
    };
  }, [projectId]);

  if (items.length === 0) return null;

  const dismiss = async () => {
    setBusy(true);
    try {
      await dismissImportNotice(projectId);
      setItems([]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "关闭提示失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="notice" data-od-id="import-notice" style={{ marginBottom: 14 }}>
      <span className="nt">
        <b>建书时的 {items.length} 条提示</b>
        <span style={{ display: "block", marginTop: 4 }}>{items.join("；")}</span>
      </span>
      <button className="btn btn-ghost btn-sm" data-od-id="btn-notice-close" disabled={busy} onClick={() => void dismiss()}>
        {busy ? "正在关闭…" : "知道了"}
      </button>
    </div>
  );
}
