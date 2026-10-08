import "@testing-library/jest-dom";

// c-lossless-upgrade：壳层弹窗队列是模块级全局——用例间必须清（登出同款口径），
// 否则前一个用例的 carry 条目占队，后续用例的 pack 弹窗事件全被挡
import { clearDialogQueue } from "@/lib/dialogQueue";
import { afterEach } from "vitest";
afterEach(() => {
  clearDialogQueue();
});
