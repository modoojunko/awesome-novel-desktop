/** 朱雀检测指纹（c-zhuque-ai-detect）：与后端 zhuque/segmentation.py 同一管道。
 *
 *  换行归一（\r\n|\r → \n）→ NBSP（\u00a0）→ 空格 → 按非空段切分 → 各段 trim
 *  → \n join → sha256（hex）。NBSP 归一必须保留：粘贴 Word/网页会把真实
 *  U+00A0 插进编辑器文档，漏掉这步会让粘贴章「检测结果返回瞬间即过期」。
 *  sha256 走 Web Crypto（async）。 */

export function normalizeProse(text: string): string {
  return (text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/\u00a0/g, " ");
}

export function splitParagraphs(text: string): string[] {
  return normalizeProse(text)
    .split("\n")
    .map((seg) => seg.trim())
    .filter((seg) => seg.length > 0);
}

export function canonicalText(text: string): string {
  return splitParagraphs(text).join("\n");
}

export async function fingerprint(text: string): Promise<string> {
  const data = new TextEncoder().encode(canonicalText(text));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
