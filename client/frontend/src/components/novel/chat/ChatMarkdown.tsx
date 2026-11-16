// ChatMarkdown——助手气泡文本渲染（c-writing-agent）。
// 挂账：markdown 富渲染（react-markdown+remark-gfm）曾尝试引入——npm 依赖树
// 漂移触发 VolumeWorkspace detail.chapters 隐患＋页面白屏，回退为纯文本
// （review 判例 2026-11-15）；待 VolumeWorkspace:338 隐患根修后重引入。
export default function ChatMarkdown({ text }: { text: string }) {
  return <div className="cd-md">{text}</div>;
}
