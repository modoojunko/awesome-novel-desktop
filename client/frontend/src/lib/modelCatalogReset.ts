// 测试隔离桥（c-model-list-auto-refresh）：模型清单 store 是模块级单例，
// 用例之间要重置。test-setup 不能直接 import modelCatalog（它依赖 lib/api，
// 而部分用例会 mock lib/api——setup 提前实例化会把真实 request 绑死），
// 改由 modelCatalog 在自己加载时注册重置函数，setup 只调这个无依赖的桥。
type ResetFn = () => void;

let resetFn: ResetFn | null = null;

export function registerModelCatalogReset(fn: ResetFn) {
  resetFn = fn;
}

export function resetRegisteredModelCatalog() {
  resetFn?.();
}
