import "@testing-library/jest-dom";

// c-lossless-upgrade：壳层弹窗队列是模块级全局——用例间必须清（登出同款口径），
// 否则前一个用例的 carry 条目占队，后续用例的 pack 弹窗事件全被挡
import { clearDialogQueue } from "@/lib/dialogQueue";
// c-model-list-auto-refresh：模型清单是模块级 store——用例间重置，避免串味。
// 走无依赖的注册桥（不直接 import modelCatalog：部分用例 mock 了 lib/api，
// setup 提前实例化会把真实 request 绑死）
import { resetRegisteredModelCatalog } from "@/lib/modelCatalogReset";
import { beforeEach, afterEach } from "vitest";
beforeEach(() => {
  resetRegisteredModelCatalog();
});
afterEach(() => {
  clearDialogQueue();
});

// prosemirror 几何查询在 jsdom 不存在（CI 实锤 unhandled error：正文编辑器异步
// scrollIntoView 落在测试收口后——target.getClientRects is not a function）。
// 补零矩形：几何调用方（singleRect）取 [0] 继续走，数值无意义但形状成立。
const zeroRects = () =>
  [{ top: 0, right: 0, bottom: 0, left: 0, width: 0, height: 0, x: 0, y: 0 }] as unknown as DOMRectList;
// prosemirror 的 target 可能落在原型链任意一层（Element/Text/Document/CharacterData
// /Window）——中间层若自定义同名属性会遮蔽 Node.prototype 的补丁，霰弹式全链打上。
// 无条件覆盖：部分 jsdom 版本在原型上放 truthy 占位（非函数），守卫会让补丁跳过。
const withRects = (proto: unknown) => {
  (proto as { getClientRects?: () => DOMRectList }).getClientRects = zeroRects;
};
for (const proto of [
  Element?.prototype,
  HTMLElement?.prototype,
  Text?.prototype,
  CharacterData?.prototype,
  Document?.prototype,
  Node?.prototype,
  window,
  globalThis,
]) {
  if (proto) withRects(proto);
}
// ★真正的 target：prosemirror textRange() 返回 DOM Range——jsdom 无排版引擎，
// Range 的 getClientRects/getBoundingClientRect 都不存在（上面原型补丁罩不住）
if (typeof Range !== "undefined") {
  const rangeProto = Range.prototype as unknown as {
    getClientRects: () => DOMRectList;
    getBoundingClientRect: () => DOMRect;
  };
  rangeProto.getClientRects = zeroRects;
  rangeProto.getBoundingClientRect = () => zeroRects()[0];
}
