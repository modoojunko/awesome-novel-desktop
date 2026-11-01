// 角色原型渲染（c-kb-character）：kb_entries（角色设定）payload → 建卡预填字段。
// 映射口径：archetype＝persona 一句；档案三格 look/background/speech；认知三格 w1/s1/v1。
// 其余 payload 键（relation_slot/arc）本期不进建卡预填（逐格白名单外）。
import type { KbEntry } from "@/lib/kbApi";

export interface PrototypeRender {
  /** 原型句＝persona（建卡必落；payload 校验保证非空） */
  persona: string;
  dossier: Partial<Record<"look" | "background" | "speech", string>>;
  cog: Partial<Record<"w1" | "s1" | "v1", string>>;
}

const DOSSIER_KEYS = ["look", "background", "speech"] as const;
const COG_KEYS = ["w1", "s1", "v1"] as const;

export function renderPrototype(payload: Record<string, unknown>): PrototypeRender {
  const s = (k: string): string => (typeof payload[k] === "string" ? (payload[k] as string).trim() : "");
  const persona = s("archetype");
  const dossier: PrototypeRender["dossier"] = {};
  for (const k of DOSSIER_KEYS) {
    const v = s(k);
    if (v) dossier[k] = v;
  }
  const cog: PrototypeRender["cog"] = {};
  for (const k of COG_KEYS) {
    const v = s(k);
    if (v) cog[k] = v;
  }
  return { persona, dossier, cog };
}

export function prototypeOf(e: Pick<KbEntry, "payload">): PrototypeRender {
  return renderPrototype((e.payload ?? {}) as Record<string, unknown>);
}
