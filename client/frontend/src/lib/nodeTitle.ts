/**
 * 卷/章标题的序号与名称规范（单一事实源）：
 * 序号（第几卷/第几章）由程序按 DB 位置排定，用户只能编辑名称；
 * 名称即标题本身（title 只存名称，不掺序号）。
 */

const CN_DIGITS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];

/** 数字 → 中文数字（1 → 一，12 → 十二，21 → 二十一，102 → 一百二）。
 *  四位及以上回退阿拉伯数字（1000 → "1000"）——中文数字只排到百位；不回退时
 *  `CN_DIGITS[10]` 是 undefined，标签会渲染成「第undefined百…章」（P3，2026-09-18）。
 *  后端 `manuscript/render.py::cn_num` 同族同回退，改一处必须两处同改。 */
export function cnNum(n: number): string {
  if (n <= 0 || !Number.isInteger(n)) return String(n);
  if (n >= 1000) return String(n);
  if (n < 10) return CN_DIGITS[n];
  if (n < 20) return `十${n % 10 ? CN_DIGITS[n % 10] : ""}`;
  if (n < 100) {
    const tens = Math.floor(n / 10);
    const ones = n % 10;
    return `${CN_DIGITS[tens]}十${ones ? CN_DIGITS[ones] : ""}`;
  }
  const hundreds = Math.floor(n / 100);
  const rest = n % 100;
  return `${CN_DIGITS[hundreds]}百${rest ? cnNum(rest) : ""}`;
}

/** 程序默认序号形态（第3卷 / 第三卷 / 第12章 / 第一千零一章……），视为"没起过名"。
 *  字符类含 千万两（千章回退阿拉伯后，用户手输的中文千位序号同样是"没起过名"）；
 *  与后端 manuscript/render.py::_DEFAULT_TITLE_RE 逐字一致（parity 测试焊住）。 */
const DEFAULT_TITLE_RE = /^第\s*[0-9一二三四五六七八九十百千万两零]+\s*[卷章]$/;

/** title 是否只是默认序号（老数据 / 程序兜底），没有任何用户起的名称。 */
export function isDefaultTitle(
  kind: "卷" | "章",
  no: number,
  title: string | null | undefined,
): boolean {
  const t = (title ?? "").trim();
  if (!t) return true;
  return t === `第${cnNum(no)}${kind}` || t === `第${no}${kind}` || DEFAULT_TITLE_RE.test(t);
}

/** 展示标签：序号程序排死 + 可选名称 → 「第三卷 · 风起晋北」/「第5章 · 城门初见」。 */
export function nodeLabel(
  kind: "卷" | "章",
  no: number,
  title: string | null | undefined,
): string {
  const num = `第${cnNum(no)}${kind}`;
  const name = (title ?? "").trim();
  if (!name || isDefaultTitle(kind, no, title)) return num;
  return `${num} · ${name}`;
}

/** 重命名输入框预填值：只预填名称部分；默认序号形态预填空（改名 = 起个名）。 */
export function editName(
  kind: "卷" | "章",
  no: number,
  title: string | null | undefined,
): string {
  return isDefaultTitle(kind, no, title) ? "" : (title ?? "").trim();
}
