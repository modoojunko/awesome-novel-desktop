"""assistant 包——对话式写作 agent（c-writing-agent）。

模块：router（SSE 端点）/loop（动作循环）/actions（协议解析）/tools（封闭工具
注册表）/write_gate（授权梯度，批B）/context（三层上下文）/compact（历史压缩，
移植自 OpenWorker MIT）/profile（作家画像，批C）/identity（助手身份，批D）
/session_store（会话持久化）。
"""
