/** 「朱雀 AI 检测」配置面板（c-zhuque-ai-detect：模型配置页第二页签）。
 *
 *  单 Key 槽位（后端 vendor="zhuque" 专用端点，作者只粘贴 Key）；两态：
 *  未配置（Key 输入＋三步引导）／已配置（掩码/更换/删除/测试连接/显示开关）。
 *  独立取数（/api/v1/zhuque/*），不串 useApiConfigs（那是大模型多配置体系）。
 *  文案口径：MAX 会员权益（试用不含）＋活动额度引用式表述（以腾讯云为准）。
 *  词汇：panel/panel-h/pill/notice（.pg-config 域）＋新增 zg 系与 zq-toggle-row。 */
import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";
import { getZhuqueShow, setZhuqueShow } from "@/lib/prefs";
import { toast } from "@/lib/toast";

interface ZqStatus {
  configured: boolean;
  api_key_masked?: string;
  last_test_status?: string | null;
  last_test_error?: string | null;
  last_tested_at?: string | null;
}

const CONSOLE_KEY_URL =
  "https://console.cloud.tencent.com/edgeone/makers?tab=models&subTab=apikey";
const CONSOLE_USAGE_URL =
  "https://console.cloud.tencent.com/edgeone/makers?tab=models&subTab=overview";

export default function ZhuquePanel() {
  const [status, setStatus] = useState<ZqStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [keyDraft, setKeyDraft] = useState("");
  const [replacing, setReplacing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [show, setShow] = useState(getZhuqueShow);

  const refresh = useCallback(async () => {
    try {
      setStatus(await request<ZqStatus>("/v1/zhuque/config", { quiet: true }));
    } catch {
      setStatus({ configured: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveAndTest = useCallback(async () => {
    const key = keyDraft.trim();
    if (!key || saving) return;
    setSaving(true);
    try {
      const st = await request<ZqStatus>("/v1/zhuque/config", {
        method: "PUT",
        body: JSON.stringify({ api_key: key }),
      });
      setStatus(st);
      setKeyDraft("");
      setReplacing(false);
      const t = await request<{ ok: boolean; error: string | null }>("/v1/zhuque/test", {
        method: "POST",
      });
      await refresh();
      if (t.ok) toast.success("已保存 · 连接正常");
      else toast.error(`已保存 · ${t.error || "连接失败，请检查 Key"}`);
    } catch (e) {
      toast.error((e as Error).message || "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  }, [keyDraft, saving, refresh]);

  const runTest = useCallback(async () => {
    if (testing) return;
    setTesting(true);
    try {
      const t = await request<{ ok: boolean; error: string | null }>("/v1/zhuque/test", {
        method: "POST",
      });
      await refresh();
      if (t.ok) toast.success("连接正常");
      else toast.error(t.error || "连接失败，请重试");
    } catch (e) {
      toast.error((e as Error).message || "测试失败，请重试");
    } finally {
      setTesting(false);
    }
  }, [testing, refresh]);

  const removeKey = useCallback(async () => {
    if (!window.confirm("删除后工作台将不可用朱雀检测（可重新粘贴恢复），确定删除？")) return;
    try {
      await request("/v1/zhuque/config", { method: "DELETE" });
      await refresh();
      toast.success("已删除朱雀 Key");
    } catch (e) {
      toast.error((e as Error).message || "删除失败，请重试");
    }
  }, [refresh]);

  const toggleShow = useCallback(() => {
    const next = !show;
    setShow(next);
    setZhuqueShow(next);
  }, [show]);

  if (loading) return <p className="opt">查询中…</p>;

  const configured = !!status?.configured;
  const keyRow = (inputId: string) => (
    <div className="zg-keyrow" data-od-id="zhuque-key-row">
      <input
        id={inputId}
        className="input"
        type="password"
        placeholder="粘贴 EdgeOne Makers API Key"
        value={keyDraft}
        onChange={(e) => setKeyDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void saveAndTest();
        }}
      />
      <button className="btn btn-primary" disabled={!keyDraft.trim() || saving} onClick={() => void saveAndTest()}>
        {saving ? "保存中…" : "保存并测试"}
      </button>
    </div>
  );

  return (
    <div data-setting-key="zhuque-detect">
      <div className="notice" data-od-id="zhuque-notice">
        <span>
          朱雀是<b>腾讯的 AI 生成内容检测</b>：把整章正文送去测一测「像不像 AI 写的」，按段落给出
          置信度。<b>MAX 会员权益</b>（试用不含）；需自备腾讯云 Key，<b>每月 50 万 token 免费额度</b>
          （活动口径，以腾讯云为准）。
        </span>
      </div>

      <div className="panel" data-od-id="zhuque-card">
        <div className="panel-h">
          <h2>
            朱雀 AI 检测 <span className="pill">zhuque-text · 文本检测</span>
          </h2>
          <span className={`pill ${configured ? "pill-ok" : ""} pill-status`}>
            {configured ? "✓ 已配置" : "未配置"}
          </span>
        </div>

        {configured ? (
          <>
            <div className="zg-keyrow" data-od-id="zhuque-key-masked-row">
              <input className="input" type="password" value={status!.api_key_masked || "••••"} disabled readOnly />
              {!replacing && (
                <button className="btn btn-secondary" onClick={() => setReplacing(true)}>
                  更换 Key
                </button>
              )}
            </div>
            {replacing && keyRow("zhuque-key-replace")}
            <div className="zg-stats">
              <div className="st">
                <b>
                  {status!.last_tested_at
                    ? new Date(status!.last_tested_at).toLocaleString("zh-CN", { hour12: false })
                    : "—"}
                </b>
                <span>上次连接测试</span>
              </div>
              <div className="st">
                <b>50 万 token / 月</b>
                <span>免费额度（以腾讯云控制台为准）</span>
              </div>
              <div className="st">
                <b>
                  <a className="lnk" href={CONSOLE_USAGE_URL} target="_blank" rel="noreferrer">
                    查看用量 ↗
                  </a>
                </b>
                <span>Makers 概览 · 模型用量总览</span>
              </div>
            </div>
            <div className="zq-toggle-row" data-od-id="zhuque-show-toggle">
              <div className="tt">
                <b>在写作台显示朱雀检测</b>
                <span>
                  开＝右栏出现「朱雀 AI 检测」入口，检测后章标题区显示占比结果、正文行带标注；
                  关＝两处都不出现，不影响已配好的 Key。对所有书生效。
                </span>
              </div>
              <button
                className="switch-btn"
                role="switch"
                aria-checked={show}
                aria-label="在写作台显示朱雀检测"
                data-od-id="zhuque-show-switch"
                onClick={toggleShow}
              >
                <span className="sw-track" />
                <span className="sw-knob" />
              </button>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button className="btn btn-secondary btn-sm" disabled={testing} onClick={() => void runTest()}>
                {testing ? "测试中…" : "测试连接"}
              </button>
              <button className="btn btn-ghost btn-sm" style={{ color: "var(--err)" }} onClick={() => void removeKey()}>
                删除 Key
              </button>
            </div>
          </>
        ) : (
          <>
            {keyRow("zhuque-key-input")}
            <span style={{ fontSize: 12, color: "var(--muted)", marginTop: 8, display: "block" }}>
              Key 只存在本机，检测时随请求发送给腾讯；泄露可在控制台重建网关作废。每台设备需单独配置。
            </span>
          </>
        )}
      </div>

      <div className="panel" data-od-id="zhuque-howto">
        <div className="panel-h">
          <h2 style={{ fontSize: 14 }}>如何获取 Key</h2>
          <span className="pill">个人身份即可 · 不需企业资质</span>
        </div>
        <ol className="zg-flow">
          <li><span><b>注册腾讯云</b>并完成个人实名认证（身份证，几分钟，一次性）</span></li>
          <li>
            <span>
              打开 <b>EdgeOne 控制台 → Makers → Models → API Key</b>，点「创建 API Key」并复制
            </span>
          </li>
          <li><span>回到这里粘贴保存，保存后会自动测一次连接（消耗极少额度）</span></li>
        </ol>
        <div style={{ display: "flex", gap: 16, marginTop: 12 }}>
          <a className="lnk" href={CONSOLE_KEY_URL} target="_blank" rel="noreferrer">
            打开 EdgeOne 控制台 ↗
          </a>
          <a className="lnk" href="https://matrix.tencent.com/ai-detect/" target="_blank" rel="noreferrer">
            先去朱雀网页版免费试用 ↗
          </a>
        </div>
      </div>

      <div className="notice warn" data-od-id="zhuque-privacy">
        <span>
          <b>隐私提示</b>：检测会把<b>整章正文发送到腾讯朱雀服务</b>做判定，本机不参与打分。
          介意送稿的章节请不要使用。检测结果为概率参考，非任何平台的判定标准。
        </span>
      </div>
    </div>
  );
}
