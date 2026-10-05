#!/usr/bin/env node
// 朱雀 classify 桩（zhuque.spec e2e 专用）：POST /v1/providers/zhuque-text/classify
// 按请求 text 的段落回显段对象 {text,label,confidence}（c-zhuque-seg-align 契约：
// 段 text 按响应序拼接==请求规范化文本）；第 2 段标疑似（label 2）供正文标注断言。
// 供隔离栈后端 ZHUQUE_API_BASE=http://host.docker.internal:45875 指向。
import http from "node:http";

const PORT = 45875;
http
  .createServer((req, res) => {
    if (req.method === "POST" && req.url?.includes("/classify")) {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        let paras = [];
        try {
          const parsed = JSON.parse(raw || "{}");
          paras = String(parsed.text ?? "").split(/\n+/).filter((t) => t.trim());
        } catch { /* 按空段回 */ }
        const labels = [0, 2, 0];
        const segs = paras.map((t, i) => ({
          text: t,
          label: labels[i % labels.length],
          confidence: 0.9,
        }));
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            status: "success",
            labels_ratio: { "0": 0.67, "1": 0.0, "2": 0.33 },
            softmax_confidence: 0.91,
            segment_labels: segs,
            makers_models_usage: { usage: 12 },
          }),
        );
      });
      return;
    }
    res.writeHead(404); res.end("{}");
  })
  .listen(PORT, () => console.log(`zhuque classify stub :${PORT}`));
