"""Hủy khảo sát đang chạy: giao diện gửi mã công việc (job) khi bắt đầu, và gọi /api/cancel để dừng.
Các nguồn gọi cancel.sleep() giữa các yêu cầu nên dừng được trong vòng vài giây."""
import contextvars, threading, time

class Cancelled(BaseException):      # BaseException: để các khối "except Exception" của nguồn không nuốt mất lệnh hủy
    pass

_current = contextvars.ContextVar("llp_job", default="")
_cancelled: set[str] = set()
_lock = threading.Lock()

def start(job: str):
    """Đặt job cho luồng đang xử lý yêu cầu; trả về token để gọi finish()."""
    return _current.set(job or "")

def finish(token, job: str):
    _current.reset(token)
    with _lock:
        _cancelled.discard(job)

def cancel(job: str):
    if job:
        with _lock:
            _cancelled.add(job)

def is_cancelled() -> bool:
    j = _current.get()
    with _lock:
        return bool(j) and j in _cancelled

def check():
    if is_cancelled():
        raise Cancelled()

def sleep(seconds: float):
    check()
    time.sleep(seconds)
    check()
