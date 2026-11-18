import "@testing-library/jest-dom";

// c-lossless-upgrade：壳层弹窗队列是模块级全局——用例间必须清（登出同款口径），
// 否则前一个用例的 carry 条目占队，后续用例的 pack 弹窗事件全被挡
import { clearDialogQueue } from "@/lib/dialogQueue";
import { afterEach } from "vitest";
afterEach(() => {
  clearDialogQueue();
});

// prosemirror 几何查询在 jsdom 不存在（CI 实锤 unhandled error：正文编辑器异步
// scrollIntoView 落在测试收口后——target.getClientRects is not a function）。
// 补零矩形：几何调用方（singleRect）取 [0] 继续走，数值无意义但形状成立。
const zeroRects = () =>
  [{ top: 0, right: 0, bottom: 0, left: 0, width: 0, height: 0, x: 0, y: 0 }] as unknown as DOMRectList;
// prosemirror 的 target 可能是 Element／Text 节点／Document／Window——统一在原型链
// 根部（Node.prototype 罩住 Element/Text/Document）＋window 实例补零矩形
const withRects = (o: unknown) => (o as unknown as { getClientRects: () => DOMRectList });
if (typeof Node !== "undefined" && !(Node.prototype as unknown as { getClientRects?: unknown }).getClientRects) {
  withRects(Node.prototype).getClientRects = zeroRects;
}
if (typeof window !== "undefined" && !(window as unknown as { getClientRects?: unknown }).getClientRects) {
  withRects(window).getClientRects = zeroRects;
}
