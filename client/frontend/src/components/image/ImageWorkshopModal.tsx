import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";
import { toast } from "@/lib/toast";
import { parseServerTime } from "@/lib/serverTime";
import { useTier, useFeature } from "@/hooks/useTier";
import ImageThumb from "./ImageThumb";
import {
  imageApi,
  type BookImageSettings, type CharacterImageSettings,
  type ImageAsset, type ImageJob, type ImageKind, type PromptPreview,
} from "@/lib/imageApi";

const STYLES = [
  { key: "ink", label: "水墨" },
  { key: "cinematic", label: "电影写实" },
  { key: "guoman", label: "国漫" },
  { key: "print", label: "木刻版画" },
  { key: "minimal", label: "极简" },
];

export interface ImageUndoState {
  assetId: string;
  token: string;
  expiresAt: number;
}

interface Props {
  open: boolean;
  novelId: string;
  kind: ImageKind;
  characterId?: string;
  characterName?: string;
  onClose: () => void;
  /** 采用/撤销/丢弃后回调；采用时带 undo 状态供宿主保存（重开工坊可续撤销） */
  onChanged: (undo?: ImageUndoState) => void | Promise<void>;
  /** 宿主保存的撤销状态（重开工坊时传入，8s 内可续撤销） */
  initialUndo?: ImageUndoState | null;
}

function remainingMs(iso?: string | null): number {
  if (!iso) return 0;
  const t = parseServerTime(iso).getTime();
  return Number.isFinite(t) ? Math.max(0, t - Date.now()) : 0;
}

export default function ImageWorkshopModal({
  open, novelId, kind, characterId, characterName, onClose, onChanged, initialUndo,
}: Props) {
  const { isFree } = useTier();
  const canGenerate = useFeature("image-generate");
  const fileRef = useRef<HTMLInputElement>(null);
  const [assets, setAssets] = useState<ImageAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<ImageUndoState | null>(initialUndo ?? null);
  const [tick, setTick] = useState(Date.now());
  const [bookSettings, setBookSettings] = useState<BookImageSettings | null>(null);
  const [charSettings, setCharSettings] = useState<CharacterImageSettings | null>(null);
  const [styleKey, setStyleKey] = useState("ink");
  const [coverPrompt, setCoverPrompt] = useState("");
  const [coverSeed, setCoverSeed] = useState("");
  const [avatarPrompt, setAvatarPrompt] = useState("");
  const [avatarSeed, setAvatarSeed] = useState("");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [job, setJob] = useState<ImageJob | null>(null);
  const [genErr, setGenErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await imageApi.listAssets(novelId, {
        kind, character_id: characterId, limit: 100,
      });
      setAssets(rows);
      const bs = await imageApi.getBookSettings(novelId);
      setBookSettings(bs);
      setStyleKey(bs.style_key || "ink");
      setCoverPrompt(bs.cover_prompt || "");
      setCoverSeed(bs.cover_seed == null ? "" : String(bs.cover_seed));
      if (kind === "avatar" && characterId) {
        const cs = await imageApi.getCharacterSettings(novelId, characterId);
        setCharSettings(cs);
        setAvatarPrompt(cs.avatar_prompt || "");
        setAvatarSeed(cs.seed == null ? "" : String(cs.seed));
      }
    } catch (e) {
      setError((e as Error).message || "图像加载失败");
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [novelId, kind, characterId]);

  const loadPreview = useCallback(async () => {
    setPreviewErr(null);
    try {
      const p = kind === "avatar" && characterId
        ? await imageApi.avatarPrompt(novelId, characterId)
        : await imageApi.coverPrompt(novelId);
      setPreview(p);
    } catch (e) {
      setPreviewErr((e as Error).message || "提示词预览失败");
    }
  }, [novelId, kind, characterId]);

  useEffect(() => {
    if (!open) return;
    setUndo(null);
    setPreview(null);
    setJob(null);
    setGenErr(null);
    void load();
    void loadPreview();
  }, [open, load, loadPreview]);

  // 生成任务轮询：queued/running 每 1.5s 拉一次；终态即停并刷新候选。
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void imageApi.getImageJob(job.id).then((next) => {
        if (!alive) return;
        setJob(next);
        if (next.status === "completed") {
          void load();
          void onChanged();
        }
      }).catch(() => {
        // 轮询失败不打断：下个 tick 重试；连续失败由接口层全局提示
      });
    }, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [job, load, onChanged]);

  useEffect(() => {
    if (!undo) return;
    setTick(Date.now());
    const timer = window.setInterval(() => setTick(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [undo]);

  useEffect(() => {
    if (undo && tick >= undo.expiresAt) setUndo(null);
  }, [undo, tick]);

  // 载入完成后才判定无图：避免「上传成功 → 列表刷新瞬间」仍显示空态占位
  const [loaded, setLoaded] = useState(false);
  const current = useMemo(
    () => assets.find((a) => a.status === "current" &&
      (kind === "cover" || a.character_id === characterId)),
    [assets, kind, characterId],
  );
  const candidates = useMemo(
    () => assets.filter((a) => a.status === "candidate" &&
      (kind === "cover" || a.character_id === characterId)),
    [assets, kind, characterId],
  );
  const undoSeconds = undo ? Math.ceil(Math.max(0, undo.expiresAt - tick) / 1000) : 0;

  const changed = async () => {
    await load();
    await onChanged();
  };

  const upload = async (file: File) => {
    setBusy(true);
    setUploadPct(0);
    setError(null);
    try {
      await imageApi.uploadAsset(novelId, file, kind, characterId, setUploadPct);
      toast.success("已上传候选图");
      await changed();
    } catch (e) {
      setError((e as Error).message || "上传失败");
    } finally {
      setBusy(false);
      setUploadPct(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const adopt = async (asset: ImageAsset) => {
    setBusy(true);
    try {
      const adopted = await imageApi.adoptAsset(asset.asset_id);
      let undoState: ImageUndoState | undefined;
      if (adopted.undo_token) {
        undoState = {
          assetId: adopted.asset_id,
          token: adopted.undo_token,
          expiresAt: remainingMs(adopted.undo_expires_at) + Date.now(),
        };
        setUndo(undoState);
      }
      toast.success(kind === "cover" ? "封面已更新" : "头像已更新");
      await load();
      await onChanged(undoState);
    } catch (e) {
      toast.error((e as Error).message || "采用失败");
    } finally {
      setBusy(false);
    }
  };

  const doUndo = async () => {
    if (!undo) return;
    setBusy(true);
    try {
      await imageApi.undoAsset(undo.assetId, undo.token);
      setUndo(null);
      toast.success("已撤销");
      await load();
      await onChanged();
    } catch (e) {
      toast.error((e as Error).message || "撤销失败");
    } finally {
      setBusy(false);
    }
  };

  const discard = async (asset: ImageAsset) => {
    setBusy(true);
    try {
      await imageApi.deleteAsset(asset.asset_id);
      toast.success("已丢弃候选图");
      await changed();
    } catch (e) {
      toast.error((e as Error).message || "丢弃失败");
    } finally {
      setBusy(false);
    }
  };

  const startGeneration = async (purpose: "generate" | "test") => {
    if (!canGenerate) {
      toast.info("AI 生成是 PRO 功能；上传封面/头像免费可用");
      return;
    }
    setGenErr(null);
    try {
      const createdJob = await imageApi.createImageJob(novelId, {
        kind,
        character_id: characterId,
        n: purpose === "test" ? 1 : 2,
        purpose,
      });
      setJob(createdJob);
      toast.success(purpose === "test" ? "试画已提交" : "已开始生成 2 张候选");
    } catch (e) {
      setGenErr((e as Error).message || "生成任务提交失败");
    }
  };

  const cancelGeneration = async () => {
    if (!job) return;
    try {
      setJob(await imageApi.cancelImageJob(job.id));
      toast.success("已请求取消；已生成的候选会保留");
    } catch (e) {
      toast.error((e as Error).message || "取消失败");
    }
  };

  const retryGeneration = async () => {
    if (!job) return;
    try {
      setJob(await imageApi.retryImageJob(job.id));
      setGenErr(null);
    } catch (e) {
      toast.error((e as Error).message || "重试失败");
    }
  };

  const saveSettings = async () => {
    setSavingSettings(true);
    try {
      if (kind === "cover") {
        const seed = coverSeed.trim() === "" ? null : Number(coverSeed);
        if (seed !== null && (!Number.isInteger(seed) || seed < 0)) {
          toast.error("封面种子必须是非负整数");
          return;
        }
        const next = await imageApi.patchBookSettings(novelId, {
          style_key: styleKey, cover_prompt: coverPrompt, cover_seed: seed,
        });
        setBookSettings(next);
      } else if (characterId) {
        const seed = avatarSeed.trim() === "" ? null : Number(avatarSeed);
        if (seed !== null && (!Number.isInteger(seed) || seed < 0)) {
          toast.error("头像种子必须是非负整数");
          return;
        }
        const next = await imageApi.patchCharacterSettings(novelId, characterId, {
          avatar_prompt: avatarPrompt, seed,
        });
        setCharSettings(next);
      }
      toast.success("图像设置已保存");
      await loadPreview();
    } catch (e) {
      toast.error((e as Error).message || "保存失败");
    } finally {
      setSavingSettings(false);
    }
  };

  const title = kind === "cover"
    ? `封面${characterName ? ` · ${characterName}` : ""}`
    : `角色头像${characterName ? ` · ${characterName}` : ""}`;

  return (
    <Modal open={open} onClose={onClose} title={title} width={760} locked={busy}>
      <div className="img-workshop">
        <section className="img-workshop-main">
          {error && <div className="ferr">{error}</div>}
          <div className={`img-current${kind === "avatar" ? " square" : ""}`}>
            {current ? (
              <ImageThumb asset={current} full className="img-current-img" alt="当前图" />
            ) : loaded ? (
              <div className="img-empty">
                <span>{kind === "cover" ? "还没有封面" : "还没有头像"}</span>
                <small>上传一张 JPG/PNG/WebP（≤10MB）</small>
              </div>
            ) : null}
          </div>

          <div className="img-upload-row">
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f);
              }}
            />
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              <Ico d={P.upload} size={14} /> 上传{kind === "cover" ? "封面" : "头像"}
            </button>
            <span className="img-hint">上传后可预览并选择使用；候选保留 24 小时</span>
          </div>
          {uploadPct != null && (
            <div className="img-progress" role="progressbar" aria-valuenow={uploadPct} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: `${uploadPct}%` }} />
              <span>{uploadPct < 100 ? `上传 ${uploadPct}%` : "处理中…"}</span>
            </div>
          )}

          {undo && (
            <div className="img-undo" role="status">
              <span>已更新 · {undoSeconds} 秒内可撤销</span>
              <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void doUndo()}>撤销</button>
            </div>
          )}

          <div className="img-candidates-head">
            <span>候选图</span>
            <span className="num">{candidates.length}</span>
          </div>
          {candidates.length === 0 ? (
            <p className="img-hint">还没有候选图，先上传一张。</p>
          ) : (
            <div className="img-candidates">
              {candidates.map((a) => (
                <div key={a.asset_id} className="img-candidate">
                  <div className={`img-candidate-frame${kind === "avatar" ? " square" : ""}`}>
                    <ImageThumb asset={a} className="img-candidate-img" alt="候选图" />
                  </div>
                  <div className="img-candidate-acts">
                    <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void adopt(a)}>使用</button>
                    <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void discard(a)}>丢弃</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="img-gen-note">
            <div className="img-gen-head">
              <b>AI 生成{canGenerate ? "" : "（PRO 以上）"}</b>
              {job && (
                <span className={`img-job-status ${job.status}`}>
                  {job.status === "queued" ? "排队中" :
                   job.status === "running" ? "生成中" :
                   job.status === "completed" ? `已完成 ${job.produced_count} 张` :
                   job.status === "cancelled" ? "已取消" : "失败"}
                </span>
              )}
            </div>
            {genErr && <p className="img-gen-error">{genErr}</p>}
            {job?.error_message && <p className="img-gen-error">{job.error_message}</p>}
            {job && ["queued", "running"].includes(job.status) ? (
              <div className="img-gen-running">
                <span>关闭窗口不会取消任务；可随时回来查看候选。</span>
                <button className="btn btn-secondary btn-sm" onClick={() => void cancelGeneration()}>
                  取消生成
                </button>
              </div>
            ) : (
              <div className="img-gen-acts">
                <button
                  className="btn btn-primary btn-sm"
                  disabled={!canGenerate || !!job}
                  title={canGenerate ? "按当前设置生成 2 张候选" : "PRO 以上可用；上传免费"}
                  onClick={() => void startGeneration("generate")}
                >
                  生成 2 张候选
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={!canGenerate}
                  onClick={() => void startGeneration("test")}
                >
                  试画 1 张
                </button>
                {job && ["failed", "cancelled"].includes(job.status) && (
                  <button className="btn btn-ghost btn-sm" onClick={() => void retryGeneration()}>
                    重试
                  </button>
                )}
              </div>
            )}
            {!canGenerate && (
              <span className="img-hint">免费版可上传图片；开通 PRO 后可用 AI 生成/试画/批量头像。</span>
            )}
          </div>
        </section>

        <aside className="img-workshop-side">
          <h4>{kind === "cover" ? "封面设置" : "头像设置"}</h4>
          {kind === "cover" ? (
            <>
              <label className="img-field">
                <span>画风</span>
                <select className="input" value={styleKey} onChange={(e) => setStyleKey(e.target.value)}>
                  {STYLES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </label>
              <label className="img-field">
                <span>画面描述 <small>留空则用题材/世界观做象征场景</small></span>
                <textarea className="input" rows={4} value={coverPrompt} onChange={(e) => setCoverPrompt(e.target.value)} />
              </label>
              <label className="img-field">
                <span>封面种子</span>
                <input className="input mono" inputMode="numeric" value={coverSeed} onChange={(e) => setCoverSeed(e.target.value)} placeholder="留空自动派生" />
              </label>
            </>
          ) : (
            <>
              <label className="img-field">
                <span>头像描述 <small>只写外貌/服饰，不写剧情</small></span>
                <textarea className="input" rows={4} value={avatarPrompt} onChange={(e) => setAvatarPrompt(e.target.value)} />
              </label>
              <label className="img-field">
                <span>头像种子</span>
                <input className="input mono" inputMode="numeric" value={avatarSeed} onChange={(e) => setAvatarSeed(e.target.value)} placeholder="留空自动派生" />
              </label>
            </>
          )}
          <div className="img-model-line">
            本书模型：{bookSettings?.effective_image_model || "未配置"}
            <span className="alt">（{bookSettings?.effective_source === "explicit" ? "本书绑定" : bookSettings?.effective_source === "default" ? "默认配置" : "未配置"}）</span>
          </div>
          <button className="btn btn-secondary btn-sm" disabled={savingSettings || busy} onClick={() => void saveSettings()}>
            {savingSettings ? "保存中…" : "保存设置"}
          </button>
          <div className="img-prompt">
            <div className="img-prompt-head">
              <span>提示词预览</span>
              <button className="btn btn-ghost btn-sm" onClick={() => void loadPreview()}>刷新</button>
            </div>
            {previewErr ? (
              <p className="img-hint">{previewErr}</p>
            ) : preview ? (
              <details>
                <summary>查看 prompt / negative / hash</summary>
                <pre>{preview.prompt}</pre>
                <p className="img-hint">negative：{preview.negative_prompt}</p>
                <p className="img-hint">模板 v{preview.prompt_template_version} · seed {preview.seed} · {preview.model || "模型未绑定"}</p>
                <p className="img-hint">hash：{preview.prompt_hash}</p>
              </details>
            ) : (
              <p className="img-hint">加载中…</p>
            )}
          </div>
          {isFree && <p className="img-hint">免费用户可使用上传；AI 生成需 PRO 以上。</p>}
        </aside>
      </div>
    </Modal>
  );
}
