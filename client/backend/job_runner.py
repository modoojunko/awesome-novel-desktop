"""通用单飞后台任务骨架（c-manuscript-download PR1）。

从 backup/export.py 抽出的任务机制：全局单飞（同一时间全系统只允许一个任务在跑，
备份与成稿下载互斥）+ daemon 线程 + status 快照轮询。消费方：
- backup/export.py  —— kind=backup（整库双包）/ single（单书作品包），薄适配
- manuscript/       —— kind=download（读者成稿，md/txt/docx）

纪律（泛化负载后必须遵守）：
- 负载字段只经 set() 整值替换，禁止拿到 job dict 后就地改嵌套字段；
- status() 返回 deepcopy 快照，消费方不得修改快照内容——浅拷贝 dict(_job)
  在负载出现嵌套结构（如逐格式状态列表）后会泄漏共享可变状态。
"""

import copy
import threading

_lock = threading.Lock()
_job: dict | None = None


class JobError(Exception):
    """带归因码的任务失败（路由层转错误响应；文案面向用户）。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def classify_os_error(e: OSError) -> str:
    """OSError → 稳定错误码（backup 与 download 统一口径）。"""
    if getattr(e, "errno", None) == 28:
        return "disk_full"
    if getattr(e, "errno", None) in (13, 30):
        return "permission_denied"
    if isinstance(e, (FileNotFoundError, NotADirectoryError)) or getattr(e, "errno", None) in (2, 20):
        return "invalid_path"
    return "io_error"


def set_job(**kw) -> None:
    with _lock:
        _job.update(kw)


def phase(name: str, **kw) -> None:
    set_job(phase=name, **kw)


def status() -> dict:
    with _lock:
        return copy.deepcopy(_job) if _job else {"state": "idle"}


def running_kind() -> str | None:
    with _lock:
        return _job.get("kind") if _job and _job.get("state") == "running" else None


def start(kind: str, runner, user_id: str, **payload) -> dict | None:
    """单飞入口：已有任务在跑返回 None（路由层转 409），否则起线程并返回初始 status。"""
    global _job
    with _lock:
        if _job and _job["state"] == "running":
            return None
        _job = {
            "state": "running",
            "phase": "probe",
            "kind": kind,
            "error": None,
            **payload,
        }
    thread = threading.Thread(target=runner, args=(payload, user_id), daemon=True)
    thread.start()
    return status()


def run_thread(fn) -> None:
    """线程体兜底包装：任务线程的任何异常必须落到 status（state=error）。"""
    try:
        fn()
        set_job(state="done", phase="finalize")
    except JobError as e:
        set_job(state="error", error={"code": e.code, "message": e.message})
    except OSError as e:
        set_job(state="error", error={"code": classify_os_error(e), "message": str(e)})
    except Exception as e:  # noqa: BLE001 — 兜底：任务线程错误必须落到 status
        set_job(state="error", error={"code": "io_error", "message": str(e)})
    except BaseException as e:  # noqa: BLE001 — asyncio.run 的 CancelledError/SystemExit 会穿透上一支，
        # 不接住会留下 state=running 的死任务，单飞槽永久卡死（备份/单书/下载全锁死）
        set_job(state="error", error={"code": "cancelled", "message": f"任务被中断：{e!r}"})
