// PersonaModal——助手人格查看/编辑（顶栏控制中心入口，boss 拍板 2026-11-15）。
// 四字段（后端 REQUIRED_FIELDS 同源）：名字/性格人设/说话规矩/能力边界；
// 保存 fail-loud（缺字段 422 回显）；恢复默认＝删用户覆盖（回提示词包/内置）。

import { useCallback, useEffect, useState } from "react";

import Modal from "@/components/design/Modal";
import {
  clearAssistantPersona,
  loadAssistantPersona,
  updateAssistantPersona,
} from "@/lib/chatApi";

const FIELDS: { key: string; name: string; hint: string; rows: number }[] = [
  { key: "name", name: "名字", hint: "怎么称呼这个搭档", rows: 1 },
  { key: "persona", name: "性格人设", hint: "它是个什么样的搭档——直接、温和、毒舌都行", rows: 2 },
  { key: "voice_rules", name: "说话规矩", hint: "短句还是长句、口语还是书面、要不要客套", rows: 2 },
  { key: "fence_rules", name: "能力边界", hint: "只做这本书和知识库内的事——边界怎么跟作家说", rows: 3 },
];

export default function PersonaModal({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  const [identity, setIdentity] = useState<Record<string, string>>({});
  const [customized, setCustomized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await loadAssistantPersona(projectId);
      setIdentity(data.identity ?? {});
      setCustomized(Boolean(data.customized));
      setNotice("");
    } catch {
      setNotice("人格读取失败，稍后再试。");
    }
  }, [projectId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const save = useCallback(async () => {
    const missing = FIELDS.filter((f) => !(identity[f.key] ?? "").trim());
    if (missing.length) {
      setNotice(`这几栏还没填：${missing.map((f) => f.name).join("、")}`);
      return;
    }
    setBusy(true);
    try {
      const data = await updateAssistantPersona(projectId, identity);
      setIdentity(data.identity ?? identity);
      setCustomized(true);
      setNotice("已保存——下一句话开始就用新人格。");
    } catch (e) {
      setNotice((e as Error)?.message || "保存失败，稍后再试。");
    } finally {
      setBusy(false);
    }
  }, [projectId, identity]);

  const reset = useCallback(async () => {
    setBusy(true);
    try {
      await clearAssistantPersona(projectId);
      await load();
      setNotice("已恢复默认。");
    } catch {
      setNotice("恢复失败，稍后再试。");
    } finally {
      setBusy(false);
    }
  }, [projectId, load]);

  return (
    <Modal open={open} onClose={onClose} title="助手人格">
      <div className="profile-modal" data-testid="persona-modal">
        <p className="pm-hint">
          这是你的写作搭档的人设——它按这个性格跟你说话、帮你干活。
          {customized ? "当前是你的自定义版本。" : "当前是默认版本。"}
        </p>
        {FIELDS.map((f) => (
          <div key={f.key} className="pm-section">
            <b>{f.name}</b>
            <span className="pm-hint-s">{f.hint}</span>
            <textarea
              rows={f.rows}
              value={identity[f.key] ?? ""}
              onChange={(e) => setIdentity((d) => ({ ...d, [f.key]: e.target.value }))}
              data-testid={`persona-${f.key}`}
            />
          </div>
        ))}
        <div className="pm-acts">
          <button type="button" className="cd-btn primary" disabled={busy} onClick={() => void save()}>
            保存人格
          </button>
          <button type="button" className="cd-btn" disabled={busy} onClick={() => void reset()}>
            恢复默认
          </button>
        </div>
        {notice && <p className="pm-notice">{notice}</p>}
      </div>
    </Modal>
  );
}
