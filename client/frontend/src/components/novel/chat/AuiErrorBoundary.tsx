// AuiErrorBoundary——ChatAnywhere 渲染崩溃兜底（c-agent-chat-memory 批6）。
// 渲染异常降级为对话内错误提示＋「重试」入口（重试＝重置边界态，children 重新
// 挂载→Aui2Dock 重新装载历史），SHALL NOT 白屏拖垮工作台。
import { Component, type PropsWithChildren } from "react";

export class AuiErrorBoundary extends Component<
  PropsWithChildren,
  { hasError: boolean; msg: string }
> {
  constructor(props: PropsWithChildren) {
    super(props);
    this.state = { hasError: false, msg: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, msg: error.message?.slice(0, 200) ?? "" };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, color: "#999" }} data-testid="aui2-error-boundary">
          <p>助手加载出错：</p>
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{this.state.msg}</pre>
          <button
            type="button"
            className="cd-btn"
            data-testid="aui2-error-retry"
            onClick={() => this.setState({ hasError: false, msg: "" })}
          >
            重试
          </button>
          <p style={{ fontSize: 12 }}>点重试重新装载；不行就刷新页面。</p>
        </div>
      );
    }
    return this.props.children;
  }
}
