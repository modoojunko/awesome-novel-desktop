# local-config-store Specification

## Purpose

本地配置文件（config.json：会话 token/档位/设备指纹/迁移期兜底 Key）的写入语义——原子写、被占用重试、半截内容容错。

## Requirements

### Requirement: 本地配置文件（config.json）的原子写与占用韧性

C端 本地会话配置 `<DATA_ROOT>/config.json` 的写入 SHALL 为原子替换（先写临时文件再 `os.replace`），
且 SHALL 满足：
- 临时文件名 SHALL 每次唯一（进程号＋随机串）——固定 tmp 名会在并发写时互踩（一方读到/搬走另一方的
  半成品，或 `os.replace` 因源文件被他人持有报错）；
- 目标文件被瞬时占用（Windows `PermissionError` / WinError 32：杀软实时扫描、他进程短暂持句柄）
  时 SHALL 做**有限次短退避重试**（约 6 次、总预算 ≤1 秒），每次失败 SHALL 留一行 warn（含尝试次数与
  错误），便于现场区分"瞬态扫描"与"长期持锁"；
- 重试仍失败 SHALL NOT 静默吞掉：MUST 抛出，且 SHALL 清理自己留下的临时文件；内存缓存 SHALL 只在
  写入成功后更新（MUST NOT 出现"文件没落盘、缓存却报成功"的漂移）。

背景（2026-10-06 现场）：`check-auth` 因该异常返回 500 一次（前端自愈重试后恢复），根因是
固定 tmp 名＋零重试把一次瞬态句柄冲突放大成用户可见的 500。

#### Scenario: 瞬时占用被重试吸收
- **WHEN** `os.replace` 第一次因 WinError 32 失败、随后句柄释放
- **THEN** 重试成功落盘、无异常外抛、warn 留痕、数据目录不留任何 `.tmp` 残件

#### Scenario: 持续占用最终报错且不留残件
- **WHEN** 目标文件在全部重试窗口内一直被占用
- **THEN** 抛出 `PermissionError`（调用方可重试/自愈），且本次写入的临时文件被清理、内存缓存不更新
