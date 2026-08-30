"""PC 상태 조회 도구. CPU·메모리·디스크·네트워크·상위 프로세스를 확인한다."""

import os
import time

import psutil


def _disk_root():
    """현재 앱이 있는 드라이브의 루트 경로를 돌려준다 (Windows에서 '/'는 안 먹혀서)."""
    return os.path.abspath(os.sep)


# 진짜 애플리케이션이 아니라 측정값에 잡음만 더하는 프로세스들.
# System Idle Process는 '쉬고 있는 코어 시간'이라 정의상 항상 1위로 올라와 순위를 다 가려버리고,
# 이 함수를 부른 python.exe(커리마 자기 자신)는 지금 이 측정을 하느라 잠깐 CPU를 써서 자기 자신을
# 원인으로 잘못 지목하게 만든다.
_NOISE_PROCESS_NAMES = {"system idle process", "idle"}


def _top_cpu_processes(processes, limit=5):
    """미리 cpu_percent(None)로 기준점을 잡아둔 프로세스 목록에서 CPU 사용률 상위 N개를 뽑는다."""
    own_pid = os.getpid()
    results = []
    for p in processes:
        if p.pid == own_pid:
            continue
        try:
            name = p.info["name"]
            if (name or "").strip().lower() in _NOISE_PROCESS_NAMES:
                continue
            results.append({"name": name, "cpu_percent": round(p.cpu_percent(None), 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    results.sort(key=lambda r: r["cpu_percent"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# 18. system_status
# ---------------------------------------------------------------------------
def system_status():
    """CPU·메모리·디스크 사용률, 상위 CPU 사용 프로세스, 잠깐 측정한 네트워크 속도를 확인한다."""
    psutil.cpu_percent(interval=None)  # 첫 호출은 기준점만 잡고 버린다
    processes = list(psutil.process_iter(["name"]))
    for p in processes:
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    net_before = psutil.net_io_counters()

    interval = 0.5
    time.sleep(interval)

    cpu_percent = psutil.cpu_percent(interval=None)
    net_after = psutil.net_io_counters()
    sent_kbps = round((net_after.bytes_sent - net_before.bytes_sent) / 1024 / interval, 1)
    recv_kbps = round((net_after.bytes_recv - net_before.bytes_recv) / 1024 / interval, 1)

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(_disk_root())

    return {
        "cpu_percent": cpu_percent,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / 1024**3, 1),
        "memory_total_gb": round(mem.total / 1024**3, 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "network_sent_kbps": sent_kbps,
        "network_recv_kbps": recv_kbps,
        "top_processes": _top_cpu_processes(processes),
    }


system_status_tool = {
    "type": "function",
    "name": "system_status",
    "description": (
        "CPU·메모리·디스크 사용률과 상위 CPU 사용 프로세스, 지금 순간의 네트워크 속도를 확인한다. "
        "'컴퓨터가 왜 느린지', 'CPU/메모리 얼마나 쓰고 있는지' 같은 질문에 쓴다. 측정에 약 0.5초 걸린다."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
