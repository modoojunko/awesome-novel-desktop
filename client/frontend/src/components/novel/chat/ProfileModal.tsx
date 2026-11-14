// ProfileModal——作家画像轻量弹窗（c-writing-agent 批G 3.5 前端入口）。
// 四条件（spec §作家画像）：可查看/可编辑/可清空/可暂停——全部在本弹窗内闭环；
// agent 写入时的透明告知走对话流（profile_update 工具结果）。
// 分区：命名口味/雷点/节奏/文风（list 用换行分隔编辑）＋自由记录（整段文本）。

import { useCallback, useEffect, useState } from "react";

import Modal from "@/components/design/Modal";
import {
  clearWriterProfile,
  loadWriterProfile,
  pauseWriterProfile,
  updateWriterProfile,
} from "@/lib/chatApi";

const SECTIONS: { key: string; name: string; hint: string }[] = [
  { key: "naming", name: "命名口味", hint: "爱用的名字风格、忌讳的字（一行一条）" },
  { key: "pet_peeves", name: "雷点", hint: "讨厌的桥段、烂俗套路（一行一条）" },
  { key: "pacing", name: "节奏偏好", hint: "爽点密度、更新习惯（一段话）" },
  { key: "style", name: "文风偏好", hint: "喜欢的叙事质感（一段话）" },
  { key: "freeform", name: "自由记录", hint: "其他想让我长期记住的事（一段话）" },
];

const listToText = (v: unknown): string =>
  Array.isArray(v) ? v.map(String).join("\n") : typeof v === "string" ? v : "";
const textToList = (t: string): string[] =>
  t.split("\n").map((x) => x.trim()).filter(Boolean);

export default function ProfileModal({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  const [sections, setSections] = useState<Record<string, unknown>>({});
  const [paused, setPaused] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await loadWriterProfile(projectId);
      setSections(data.sections ?? {});
      setPaused(Boolean(data.paused));
    } catch {
      setNotice("画像读取失败，稍后再试。");
    }
  }, [projectId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const save = useCallback(
    async (updates: Record<string, unknown>) => {
      setBusy(true);
      try {
        await updateWriterProfile(projectId, updates);
        await load();
        setNotice("已保存。");
      } catch {
        setNotice("保存失败，稍后再试。");
      } finally {
        setBusy(false);
      }
    },
    [projectId, load],
  );

  const saveDrafts = useCallback(async () => {
    const updates: Record<string, unknown> = {};
    for (const s of SECTIONS) {
      const text = drafts[s.key];
      if (text === undefined) continue;
      if (s.key === "pacing" || s.key === "style" || s.key === "freeform") {
        updates[s.key] = text;
      } else {
        updates[s.key] = textToList(text);
      }
    }
    await save(updates);
  }, [drafts, save, load]);

  const clearAll = useCallback(async () => {
    setBusy(true);
    try {
      await clearWriterProfile(projectId);
      setSections({});
      setDrafts({});
      setNotice("画像已清空。");
    } catch {
      setNotice("清空失败，稍后再试。");
    } finally {
      setBusy(false);
    }
  }, [projectId]);

  const togglePause = useCallback(async () => {
    setBusy(true);
    try {
      await pauseWriterProfile(projectId, !paused);
      setPaused(!paused);
      setNotice(paused ? "画像学习已恢复。" : "画像学习已暂停（已有内容保留）。");
    } catch {
      setNotice("操作失败，稍后再试。");
    } finally {
      setBusy(false);
    }
  }, [paused]);

  const sectionText = (key: string): string => {
    if (drafts[key] !== undefined) return drafts[key];
    const v = sections[key];
    return listToText(v);
  };

  return (
    <Modal open={open} onClose={onClose} title="作家画像">
      <div className="profile-modal" data-testid="profile-modal">
        <p className="pm-hint">
          这是我长期记住的「你的口味」——起草和发散都会照着来。随时可改、可清空；
          打开「暂停学习」我就不再自动更新它。
        </p>
        {SECTIONS.map((s) => (
          <div key={s.key} className="pm-section">
            <b>{s.name}</b>
            <span className="pm-hint-s">{s.hint}</span>
            <textarea
              rows={s.key === "naming" || s.key === "pet_peeves" ? 3 : 2}
              value={sectionText(s.key)}
              onChange={(e) =>
                setDrafts((d) => ({ ...d, [s.key]: e.target.value }))
              }
              data-testid={`profile-${s.key}`}
            />
          </div>
        ))}
        <div className="pm-acts">
          <button
            type="button"
            className="cd-btn primary"
            disabled={busy}
            onClick={() => {
              const updates: Record<string, unknown> = {};
              for (const s of SECTIONS) {
                const v = drafts[s.key];
                if (v !== undefined) updates[s.key] = v;
              }
              if (Object.keys(updates).length === 0) {
                setNotice("没有改动。");
                return;
              }
              void save(updates);
            }}
          >
            保存画像
          </button>
          <button
            type="button"
            className="cd-btn"
            disabled={busy}
            onClick={() => void clearAll()}
          >
            一键清空
          </button>
          <button type="button" className="cd-btn" disabled={busy} onClick={() => void togglePause()}>
            {paused ? "恢复画像学习" : "暂停画像学习"}
          </button>
        </div>
        {notice && <p className="pm-notice">{notice}</p>}
      </div>
    </Modal>
  );
}
