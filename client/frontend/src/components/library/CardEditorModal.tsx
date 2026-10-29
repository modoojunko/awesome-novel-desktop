// 库卡编辑/新建弹窗（c-character-library）：全字段（认知各格直取共享常量，禁手抄）＋
// 书源卡「从《书》同步最新设定」＋AI 随机只碰名字与年龄＋删除（显式确认，明示复制语义）。
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import Modal from "@/components/design/Modal";
import LibraryAvatar from "@/components/library/LibraryAvatar";
import { COG_LAYERS, DOSSIER_FIELDS, ROLES } from "@/lib/characterModel";
import {
  clearLibraryAvatarCache,
  createLibraryCard,
  deleteLibraryCard,
  randomLibraryName,
  syncCardFromBook,
  updateLibraryCard,
  type LibraryCard,
  type LibraryCardInput,
} from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";

const KINDS = ["亲人", "朋友", "挚友", "小弟", "下人", "长辈", "敌人", "其他"] as const;

interface Props {
  open: boolean;
  card: LibraryCard | null;
  onClose: () => void;
}

function blank(): LibraryCardInput {
  return {
    name: "",
    aliases: [],
    role: "配角",
    genre: "",
    kind: "其他",
    persona: "",
    dossier: {},
    cog: {},
  };
}

function fromCard(card: LibraryCard): LibraryCardInput {
  return {
    name: card.name,
    aliases: [...(card.aliases || [])],
    role: card.role,
    genre: card.genre,
    kind: card.kind || "其他",
    persona: card.persona,
    dossier: { ...(card.dossier || {}) },
    cog: { ...(card.cog || {}) },
  };
}

/** 把 30 个认知格摊平成「层名 → 格」清单（渲染用；键名直接来自共享常量） */
export function cogFieldList(): { key: string; label: string }[] {
  return COG_LAYERS.flatMap((layer) =>
    layer.fields.map((f) => ({ key: f.k, label: `${layer.name} · ${f.label}` })),
  );
}

export default function CardEditorModal({ open, card, onClose }: Props) {
  const qc = useQueryClient();
  const isNew = card === null;
  const [form, setForm] = useState<LibraryCardInput>(blank);
  const [seededFor, setSeededFor] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  
  // 打开时按卡初始化；关闭即清播种标记——取消后再开同一张卡回到卡上原值
  const seedKey = open ? card?.id ?? "__new__" : "";
  if (!open && seededFor) setSeededFor("");
  if (open && seedKey !== seededFor) {
    setSeededFor(seedKey);
    setForm(card ? fromCard(card) : blank());
    setConfirmDel(false);
  }

  const cogFields = useMemo(cogFieldList, []);
  const filledCog = useMemo(
    () => Object.values(form.cog).filter((v) => String(v || "").trim()).length,
    [form.cog],
  );

  const set = <K extends keyof LibraryCardInput>(key: K, value: LibraryCardInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const setCell = (bucket: "dossier" | "cog", key: string, value: string) =>
    setForm((f) => ({ ...f, [bucket]: { ...f[bucket], [key]: value } }));

  const onAI = async () => {
    try {
      const picked = await randomLibraryName(String(form.dossier?.gender || "男"));
      setForm((f) => ({
        ...f,
        name: picked.name,
        dossier: { ...f.dossier, age: String(picked.age) },
      }));
      toast.success(`换好了：「${picked.name}」· ${picked.age} 岁（其余格未动）`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "随机起名失败，稍后再试");
    }
  };

  const onSave = async () => {
    if (!form.name.trim()) {
      toast.error("先给角色起个名字");
      return;
    }
    setSaving(true);
    try {
      const payload: LibraryCardInput = {
        ...form,
        dossier: Object.fromEntries(Object.entries(form.dossier).filter(([, v]) => v.trim())),
        cog: Object.fromEntries(Object.entries(form.cog).filter(([, v]) => v.trim())),
      };
      if (isNew) await createLibraryCard(payload);
      else await updateLibraryCard(card!.id, payload);
      await qc.invalidateQueries({ queryKey: queryKeys.characterLibrary });
      toast.success(isNew ? `已建「${form.name}」——收进库里了` : `已保存「${form.name}」`);
      onClose();
    } catch (e) {
      // 非 Error 拒绝（字符串/异常体）走兜底文案——mock 覆盖不到所有异常形态
      /* v8 ignore next */
      toast.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    setSaving(true);
    try {
      await deleteLibraryCard(card!.id);
      await qc.invalidateQueries({ queryKey: queryKeys.characterLibrary });
      toast.success(`已删除「${card!.name}」——已经用到书里的不受影响`);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    } finally {
      setSaving(false);
    }
  };

  const onSync = async () => {
    setSaving(true);
    try {
      const fresh = await syncCardFromBook(card!.id);
      clearLibraryAvatarCache(fresh.id); // 头像字节可能已换：清该卡缓存图
      setForm(fromCard(fresh));
      await qc.invalidateQueries({ queryKey: queryKeys.characterLibrary });
      toast.success(`已把《${fresh.src.novel_name}》里的最新设定同步进库卡`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "同步失败");
    } finally {
      setSaving(false);
    }
  };

  const footer = confirmDel ? (
    <>
      <span style={{ marginRight: "auto", fontSize: 12.5, color: "var(--muted)" }}>
        只删库里的这张卡，书里已导入的不受影响
      </span>
      <button className="btn btn-secondary btn-sm" onClick={() => setConfirmDel(false)} disabled={saving}>
        取消
      </button>
      <button className="btn btn-danger btn-sm" onClick={() => void onDelete()} disabled={saving}>
        确认删除
      </button>
    </>
  ) : (
    <>
      {!isNew && (
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginRight: "auto", color: "var(--err)" }}
          onClick={() => setConfirmDel(true)}
          disabled={saving}
          data-testid="lib-delete"
        >
          删除
        </button>
      )}
      <button className="btn btn-secondary" onClick={onClose} disabled={saving}>
        取消
      </button>
      <button className="btn btn-primary" onClick={() => void onSave()} disabled={saving} data-testid="lib-save">
        {saving ? "保存中…" : "保存"}
      </button>
    </>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isNew ? "新建角色" : "编辑角色"}
      width={600}
      locked={saving}
      footer={footer}
      headExtra={
        card ? <span style={{ fontSize: 12, color: "var(--muted)" }}>{card.src.novel_name || "手建"}</span> : undefined
      }
    >
      <div style={{ maxHeight: "66vh", overflowY: "auto", paddingRight: 2 }}>
        <div className="field" style={{ display: "flex", flexDirection: "row", alignItems: "center", gap: 12 }}>
          {card ? <LibraryAvatar card={card} size="lg" /> : <span className="lib-ava lg">角</span>}
          <div style={{ flex: 1, minWidth: 0 }}>
            <label>名字</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="input"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="角色叫什么"
                style={{ flex: 1 }}
              />
              <button className="btn btn-secondary btn-sm" onClick={() => void onAI()} data-testid="lib-ai-random">
                AI 随机起名与年龄
              </button>
            </div>
            <div className="alt" style={{ marginTop: 4 }}>
              AI 随机只碰名字和年龄，其余格不动；头像随卡走（拆书收进来的先没有）
            </div>
          </div>
        </div>

        <div style={{ margin: "14px 0 6px", fontSize: 12.5, fontWeight: 600 }}>库里分类</div>
        <div style={{ display: "flex", gap: 12 }}>
          <div className="field" style={{ flex: "0 0 96px" }}>
            <label>题材</label>
            <input
              className="input"
              value={form.genre}
              onChange={(e) => set("genre", e.target.value)}
              placeholder="如：武侠"
              data-testid="lib-genre"
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>定位</label>
            <div className="seg">
              {ROLES.map((r) => (
                <button
                  key={r}
                  className={form.role === r ? "on" : ""}
                  onClick={() => set("role", r)}
                  type="button"
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>小类</label>
          <div className="seg" style={{ flexWrap: "wrap" }}>
            {KINDS.map((k) => (
              <button
                key={k}
                className={form.kind === k ? "on" : ""}
                onClick={() => set("kind", k)}
                type="button"
              >
                {k}
              </button>
            ))}
          </div>
        </div>

        <div style={{ margin: "14px 0 6px", fontSize: 12.5, fontWeight: 600 }}>一句话人设</div>
        <div className="field">
          <textarea
            className="input"
            rows={2}
            value={form.persona}
            onChange={(e) => set("persona", e.target.value)}
            placeholder="每章都会带上这张卡的这句"
          />
        </div>

        <div style={{ margin: "14px 0 6px", fontSize: 12.5, fontWeight: 600 }}>基础档案</div>
        <div className="field">
          <label>别名 · 称呼</label>
          <input
            className="input"
            value={form.aliases.join("、")}
            onChange={(e) => set("aliases", e.target.value.split(/[、,，\s]+/).filter(Boolean))}
            placeholder="顿号隔开，可留空"
          />
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
          <div className="field" style={{ flex: "0 0 84px" }}>
            <label>性别</label>
            <select
              className="input"
              aria-label="性别"
              value={form.dossier?.gender || "男"}
              onChange={(e) => setCell("dossier", "gender", e.target.value)}
            >
              <option>男</option>
              <option>女</option>
            </select>
          </div>
          <div className="field" style={{ flex: "0 0 84px" }}>
            <label>年龄</label>
            <input
              className="input"
              aria-label="年龄"
              value={form.dossier?.age || ""}
              onChange={(e) => setCell("dossier", "age", e.target.value)}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>种族</label>
            <input
              className="input"
              aria-label="种族"
              value={form.dossier?.race || ""}
              onChange={(e) => setCell("dossier", "race", e.target.value)}
            />
          </div>
        </div>
        {DOSSIER_FIELDS.filter((f) => ["faction", "look", "speech", "background"].includes(f.k)).map((f) => (
          <div className="field" key={f.k} style={{ marginTop: 10 }}>
            <label>{f.label}</label>
            {f.k === "speech" || f.k === "background" ? (
              <textarea
                className="input"
                aria-label={f.label}
                rows={2}
                value={form.dossier?.[f.k] || ""}
                onChange={(e) => setCell("dossier", f.k, e.target.value)}
              />
            ) : (
              <input
                className="input"
                aria-label={f.label}
                value={form.dossier?.[f.k] || ""}
                onChange={(e) => setCell("dossier", f.k, e.target.value)}
              />
            )}
          </div>
        ))}
        <div className="field" style={{ marginTop: 10 }}>
          <label>剧情定位</label>
          <textarea
            className="input"
            aria-label="剧情定位"
            rows={2}
            value={form.dossier?.plot || ""}
            onChange={(e) => setCell("dossier", "plot", e.target.value)}
          />
        </div>

        <details open={filledCog > 0} style={{ marginTop: 14 }}>
          <summary style={{ cursor: "pointer", fontSize: 12.5, fontWeight: 600 }}>
            认知内核（六层，与设定页同格同叫法）
          </summary>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10, marginTop: 10 }}>
            {cogFields.map((f) => (
              <div className="field" key={f.key}>
                <label>{f.label}</label>
                <input
                  className="input"
                  aria-label={f.label}
                  value={form.cog?.[f.key] || ""}
                  onChange={(e) => setCell("cog", f.key, e.target.value)}
                />
              </div>
            ))}
          </div>
        </details>

        {!isNew && card?.src.kind === "book" && (
          <div className="field" style={{ marginTop: 14 }}>
            <label>同步</label>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => void onSync()} disabled={saving}>
                <Ico d="refresh" size={13} /> 从《{card.src.novel_name}》同步最新设定
              </button>
              <span className="alt" style={{ marginTop: 0 }}>
                书里改过的点这里推回库卡；库里的小类、定位不动
              </span>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

import { Ico } from "@/components/icons";
