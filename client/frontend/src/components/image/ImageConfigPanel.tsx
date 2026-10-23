import { useCallback, useEffect, useMemo, useState } from "react";
import Modal from "@/components/design/Modal";
import { UndoToast } from "@/components/api-config/UndoToast";
import { Ico, P } from "@/components/icons";
import { toast } from "@/lib/toast";
import {
  IMAGE_PROVIDERS, imageApi, type ImageConfig, type ImageProvider,
} from "@/lib/imageApi";

function ConfigForm({
  open, config, onClose, onSaved,
}: {
  open: boolean;
  config: ImageConfig | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!config;
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<ImageProvider>("volcengine");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [modelsText, setModelsText] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(config?.name ?? "");
    setProvider(config?.provider ?? "volcengine");
    setBaseUrl(config?.base_url ?? "");
    setApiKey("");
    setDefaultModel(config?.default_model ?? "");
    setModelsText((config?.models ?? []).join("\n"));
    setIsDefault(!!config?.is_default);
    setError(null);
  }, [open, config]);

  const providerMeta = IMAGE_PROVIDERS.find((p) => p.id === provider);

  const pickProvider = (next: ImageProvider) => {
    const prev = IMAGE_PROVIDERS.find((p) => p.id === provider);
    setProvider(next);
    const meta = IMAGE_PROVIDERS.find((p) => p.id === next);
    if (!baseUrl.trim() || baseUrl === prev?.base_url) setBaseUrl(meta?.base_url ?? "");
    if (!modelsText.trim()) setModelsText((meta?.models ?? []).join("\n"));
    if (!defaultModel.trim() || defaultModel === prev?.models?.[0]) {
      setDefaultModel(meta?.models?.[0] ?? "");
    }
  };

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) { setError("配置名称不能为空"); return; }
    const models = [...new Set(
      modelsText.split(/[\n,，]+/).map((s) => s.trim()).filter(Boolean),
    )];
    const body: Record<string, unknown> = {
      name: trimmed,
      provider,
      base_url: baseUrl.trim(),
      default_model: defaultModel.trim(),
      models,
      is_default: isDefault,
    };
    // 编辑态留空 Key = 保留旧 Key（后端同语义；绝不发空串）
    if (!isEdit || apiKey.trim()) body.api_key = apiKey.trim();
    if (isEdit && config && provider !== config.provider) {
      // 换供应商必须显式确认：后端会把未随请求提交的旧 Key/Base/模型清空
      const ok = window.confirm(
        "更换供应商后，未重新填写的 Key、Base URL、模型和测试状态会被清空；绑定这本书的模型名也会清空。继续保存？",
      );
      if (!ok) return;
    }
    setSaving(true);
    setError(null);
    try {
      if (isEdit && config) await imageApi.updateConfig(config.id, body);
      else await imageApi.createConfig(body as Parameters<typeof imageApi.createConfig>[0]);
      toast.success(isEdit ? `已保存「${trimmed}」` : `已添加「${trimmed}」`);
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? "编辑图像模型" : "添加图像模型"}
      width={560}
      locked={saving}
      footer={(
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn btn-primary" onClick={() => void submit()} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </>
      )}
    >
      <div className="img-form">
        {error && <div className="ferr">{error}</div>}
        <div className="field">
          <label>供应商</label>
          <div className="vgrid img-vgrid">
            {IMAGE_PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`vbtn${provider === p.id ? " on" : ""}`}
                onClick={() => pickProvider(p.id)}
              >
                <span>{p.label}</span>
              </button>
            ))}
          </div>
          {providerMeta?.apply_url && (
            <p className="cf-hint">
              申请 Key / 查看 Base URL：<a href={providerMeta.apply_url} target="_blank" rel="noreferrer">{providerMeta.apply_url}</a>
            </p>
          )}
        </div>
        <div className="field">
          <label>配置名称</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：封面主力 · 火山" />
        </div>
        <div className="field">
          <label>Base URL</label>
          <input className="input mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://…" />
        </div>
        <div className="field">
          <label>API Key</label>
          <input className="input mono" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={isEdit ? "留空保留当前 Key" : "粘贴 API Key"} autoComplete="off" />
        </div>
        <div className="field">
          <label>默认模型</label>
          <input className="input mono" value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} placeholder="模型 id" />
        </div>
        <div className="field">
          <label>模型清单 <span className="alt">一行一个，也可逗号分隔</span></label>
          <textarea className="input" rows={3} value={modelsText} onChange={(e) => setModelsText(e.target.value)} />
        </div>
        <label className="img-check">
          <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
          设为默认图像配置（新书未单独绑定时使用）
        </label>
        <p className="cf-hint">
          连接测试 / 试画 / 拉取模型清单在后续版本开放；当前保存即可用于上传工坊。
        </p>
      </div>
    </Modal>
  );
}

export default function ImageConfigPanel() {
  const [configs, setConfigs] = useState<ImageConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [edit, setEdit] = useState<ImageConfig | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ImageConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [undoTarget, setUndoTarget] = useState<ImageConfig | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setConfigs(await imageApi.listConfigs(includeDeleted));
    } catch (e) {
      setError((e as Error).message || "加载图像配置失败");
    } finally {
      setLoading(false);
    }
  }, [includeDeleted]);

  useEffect(() => { void load(); }, [load]);

  const active = useMemo(() => configs.filter((c) => c.status === "active"), [configs]);

  const remove = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const result = await imageApi.deleteConfig(deleteTarget.id);
      setUndoTarget(deleteTarget);
      setDeleteTarget(null);
      await load();
      if (result.affected_book_count) {
        toast.info(`已删除，并解开 ${result.affected_book_count} 本书的绑定`);
      }
    } catch (e) {
      toast.error((e as Error).message || "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const restore = async (cfg: ImageConfig) => {
    try {
      await imageApi.restoreConfig(cfg.id);
      toast.success(`已恢复「${cfg.name}」`);
      await load();
    } catch (e) {
      toast.error((e as Error).message || "恢复失败");
    }
  };

  return (
    <div className="img-cfg-panel">
      <div className="notice">
        <Ico d={P.info} sw={1.8} />
        <span>
          图像模型与写作模型分开管理；Key 只用于封面/头像。<b>免费用户可上传</b>，
          AI 生成将在后续版本开放。
        </span>
      </div>

      <div className="img-cfg-toolbar">
        <span className="img-cfg-count">{active.length} 个启用配置</span>
        <label className="img-check">
          <input
            type="checkbox"
            checked={includeDeleted}
            onChange={(e) => setIncludeDeleted(e.target.checked)}
          />
          显示已删除
        </label>
        <button className="btn btn-primary btn-sm" onClick={() => { setEdit(null); setFormOpen(true); }}>
          <Ico d={P.plus} size={13} /> 添加图像模型
        </button>
      </div>

      {loading ? (
        <div className="cards">
          {[1, 2].map((i) => <div key={i} className="card-skeleton" />)}
        </div>
      ) : error ? (
        <div className="empty">
          <div className="serif">图像配置加载失败</div>
          <p>{error}</p>
          <button className="btn btn-secondary btn-sm" onClick={() => void load()}>重新加载</button>
        </div>
      ) : configs.length === 0 ? (
        <div className="empty">
          <div className="serif">还没有图像模型配置</div>
          <p>添加一个后，封面/头像上传仍可用；生成能力将在后续版本接入。</p>
        </div>
      ) : (
        <div className="cards">
          {configs.map((c) => (
            <div key={c.id} className={`cfg-card${c.status === "deleted" ? " img-cfg-deleted" : ""}`}>
              <div className="cfg-top">
                <div className="pv-icon img-pv-icon">{c.provider.slice(0, 1).toUpperCase()}</div>
                <div className="id">
                  <div className="nm">{c.name}</div>
                  <div className="url">{c.base_url || "（未填 Base URL）"}</div>
                </div>
                {c.is_default && <span className="b ok">默认</span>}
                {c.status === "deleted" && <span className="b muted">已删除</span>}
              </div>
              <div className="keyline">{c.api_key_masked || "（未填 Key）"}</div>
              <div className="models">
                {c.models.slice(0, 5).map((m) => <span key={m} className="m-chip">{m}</span>)}
                {c.models.length > 5 && <span className="m-chip more">+{c.models.length - 5}</span>}
              </div>
              <div className="cfg-foot">
                <span className="res">{IMAGE_PROVIDERS.find((p) => p.id === c.provider)?.label || c.provider}</span>
                <div className="cfg-acts">
                  {c.status === "deleted" ? (
                    <button className="btn btn-ghost btn-sm" onClick={() => void restore(c)}>恢复</button>
                  ) : (
                    <>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setEdit(c); setFormOpen(true); }}>编辑</button>
                      <button className="btn btn-ghost btn-sm img-danger" onClick={() => setDeleteTarget(c)}>删除</button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfigForm
        open={formOpen}
        config={edit}
        onClose={() => { setFormOpen(false); setEdit(null); }}
        onSaved={() => void load()}
      />

      {deleteTarget && (
        <Modal
          open
          onClose={() => setDeleteTarget(null)}
          title="删除图像模型"
          width={440}
          locked={deleting}
          footer={(
            <>
              <button className="btn btn-secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>取消</button>
              <button className="btn btn-danger" onClick={() => void remove()} disabled={deleting}>
                {deleting ? "删除中…" : "删除"}
              </button>
            </>
          )}
        >
          <p className="img-del-note">
            删除「{deleteTarget.name}」后，绑定这本书的图像配置会被解开（Key 不会删除，可在已删除列表恢复）。
          </p>
        </Modal>
      )}

      {undoTarget && (
        <UndoToast
          configName={undoTarget.name}
          onUndo={async () => {
            await imageApi.restoreConfig(undoTarget.id);
            setUndoTarget(null);
            await load();
          }}
          onExpire={() => setUndoTarget(null)}
        />
      )}
    </div>
  );
}
