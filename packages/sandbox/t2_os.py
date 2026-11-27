"""M08 (B07) T2 OS 原生受限子进程沙箱（Windows Job Object + POSIX rlimit + PEP 578 C 级审计钩子）."""

from __future__ import annotations

import ctypes
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from packages.core.contracts import SandboxTier
from packages.governance.evidence import DEFAULT_SENSITIVE_KEYWORDS
from packages.sandbox.models import SandboxRequest, SandboxResult
from packages.sandbox.security import sanitize_user_env, validate_workspace_path

# 在独立隔离子进程（python -I -B）内部运行的不可移除 C 级审计与路径/写配额守卫引导器
_T2_CHILD_BOOTSTRAP = r'''
import builtins
import io
import json
import os
import pathlib
import sys
import traceback

# 预先导入常见安全纯标准库，确保审计钩子启用后正常代码平滑运行
import base64, collections, csv, datetime, decimal, fractions, functools, hashlib, itertools, math, re, statistics  # noqa: E401, F401

payload = json.loads(sys.stdin.read())
sys.stdin = io.StringIO("")

CODE = payload["code"]
WORKSPACE = os.path.realpath(payload["workspace"])
ALLOW_NETWORK = bool(payload["allow_network"])
READ_ONLY = bool(payload["read_only"])
MAX_MEMORY_MB = int(payload["max_memory_mb"])
MAX_CPU_SEC = float(payload["max_cpu_sec"])
MAX_WRITE_FILES = int(payload["max_write_files"])
MAX_WRITE_BYTES = int(payload["max_write_bytes"])
SENSITIVE_KEYWORDS = tuple(k.replace("\\", "/").lower() for k in payload["sensitive_keywords"])

os.chdir(WORKSPACE)

# 清理 sys.path，仅保留标准库与工作区，严禁读取宿主项目代码
def _norm(p: str) -> str:
    return os.path.realpath(p).replace("\\", "/").rstrip("/").lower()

WORKSPACE_NORM = _norm(WORKSPACE)
_stdlib_candidates = [
    sys.prefix,
    sys.base_prefix,
    sys.exec_prefix,
    sys.base_exec_prefix,
    os.path.dirname(os.__file__),
]
STDLIB_ROOTS = tuple(sorted({_norm(p) for p in _stdlib_candidates if p}))
sys.path = [p for p in sys.path if p and any(_norm(p) == r or _norm(p).startswith(r + "/") for r in STDLIB_ROOTS)]
sys.path.insert(0, WORKSPACE)

# POSIX 内核级资源限额（Linux CI / macOS）
if os.name == "posix":
    try:
        import resource

        cpu_lim = max(1, int(MAX_CPU_SEC) + 1)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_lim, cpu_lim))
        fsize_lim = max(4096, MAX_WRITE_BYTES) if MAX_WRITE_BYTES > 0 else 0
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_lim, fsize_lim))
        # Linux RLIMIT_AS 计入虚拟地址映射，为 Python 解释器预留基础地址空间
        as_mb = max(MAX_MEMORY_MB, 192)
        as_bytes = as_mb * 1024 * 1024
        soft_as, hard_as = resource.getrlimit(resource.RLIMIT_AS)
        if hard_as in (-1, getattr(resource, "RLIM_INFINITY", -1)) or as_bytes <= hard_as:
            resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
    except Exception:
        pass

def _is_under(norm_path: str, root: str) -> bool:
    return norm_path == root or norm_path.startswith(root + "/")

def _resolve_norm(raw_path, *, relative_to: str | None = None) -> tuple[str, str]:
    if isinstance(raw_path, bytes):
        raw_str = raw_path.decode("utf-8", errors="replace")
    else:
        raw_str = os.fspath(raw_path)
    raw_norm = raw_str.replace("\\", "/").lower()
    base = relative_to or os.getcwd()
    joined = raw_str if os.path.isabs(raw_str) else os.path.join(base, raw_str)
    real = os.path.realpath(joined)
    real_norm = real.replace("\\", "/").rstrip("/").lower()
    return raw_norm, real_norm

def _check_sensitive(raw_norm: str, real_norm: str) -> None:
    for kw in SENSITIVE_KEYWORDS:
        if kw in raw_norm or kw in real_norm:
            raise PermissionError(f"[HQ_SANDBOX_BLOCKED] sensitive path forbidden: {kw}")

def _check_workspace_write(raw_path, *, relative_to: str | None = None, allow_root: bool = True) -> str:
    if READ_ONLY:
        raise PermissionError("[HQ_SANDBOX_BLOCKED] write forbidden on read-only workspace")
    raw_norm, real_norm = _resolve_norm(raw_path, relative_to=relative_to)
    _check_sensitive(raw_norm, real_norm)
    if not _is_under(real_norm, WORKSPACE_NORM):
        raise PermissionError(f"[HQ_SANDBOX_BLOCKED] write outside workspace forbidden: {raw_norm}")
    if not allow_root and real_norm == WORKSPACE_NORM:
        raise PermissionError("[HQ_SANDBOX_BLOCKED] cannot remove sandbox workspace root")
    return real_norm

def _check_read(raw_path) -> str:
    raw_norm, real_norm = _resolve_norm(raw_path)
    _check_sensitive(raw_norm, real_norm)
    if _is_under(real_norm, WORKSPACE_NORM):
        return real_norm
    for root in STDLIB_ROOTS:
        if _is_under(real_norm, root):
            return real_norm
    raise PermissionError(f"[HQ_SANDBOX_BLOCKED] read outside workspace forbidden: {raw_norm}")

_write_state = {"files": set(), "bytes": 0}
_orig_open = builtins.open

class _QuotaFileWrapper:
    """包装写入文件句柄，跨平台精确限制单次与累计写入字节配额。"""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, data):
        size = len(data.encode("utf-8", errors="replace")) if isinstance(data, str) else len(data)
        if _write_state["bytes"] + size > MAX_WRITE_BYTES:
            raise PermissionError(f"[HQ_SANDBOX_BLOCKED] disk write byte quota exceeded ({MAX_WRITE_BYTES} bytes)")
        _write_state["bytes"] += size
        return self._wrapped.write(data)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._wrapped.__exit__(exc_type, exc, tb)

def _guarded_open(file, mode="r", *args, **kwargs):
    f = _orig_open(file, mode, *args, **kwargs)
    if any(ch in str(mode) for ch in ("w", "a", "x", "+")):
        return _QuotaFileWrapper(f)
    return f

builtins.open = _guarded_open
io.open = _guarded_open

_orig_os_write = os.write

def _guarded_os_write(fd, data):
    if fd not in (1, 2):
        size = len(data)
        if _write_state["bytes"] + size > MAX_WRITE_BYTES:
            raise PermissionError(f"[HQ_SANDBOX_BLOCKED] disk write byte quota exceeded ({MAX_WRITE_BYTES} bytes)")
        _write_state["bytes"] += size
    return _orig_os_write(fd, data)

os.write = _guarded_os_write

# 进程/网络/FFI 阻塞集合（PEP 578 sys.addaudithook 在 CPython C 层执行，无法被用户代码移除）
_BLOCKED_PROC_EVENTS = frozenset({
    "subprocess.Popen",
    "os.system",
    "os.posix_spawn",
    "os.fork",
    "os.forkpty",
    "os.exec",
    "os.spawn",
    "os.startfile",
    "os.kill",
    "pty.fork",
    "pty.spawn",
    "webbrowser.open",
})

_BLOCKED_NET_EVENTS = frozenset({
    "socket.__new__",
    "socket.connect",
    "socket.bind",
    "socket.getaddrinfo",
    "socket.gethostbyname",
    "socket.gethostbyaddr",
    "socket.getnameinfo",
    "socket.sethostname",
    "urllib.Request",
    "http.client.connect",
    "ftplib.connect",
    "smtplib.connect",
    "telnetlib.Telnet",
})

_WRITE_O_FLAGS = (
    getattr(os, "O_WRONLY", 1)
    | getattr(os, "O_RDWR", 2)
    | getattr(os, "O_CREAT", 64)
    | getattr(os, "O_TRUNC", 512)
    | getattr(os, "O_APPEND", 1024)
)

def _hq_audit_hook(event: str, args: tuple) -> None:
    if event in _BLOCKED_PROC_EVENTS:
        raise PermissionError(f"[HQ_SANDBOX_BLOCKED] process/shell execution forbidden: {event}")

    if event.startswith("ctypes.") or event.startswith("winreg.") or event.startswith("msvcrt."):
        raise PermissionError(f"[HQ_SANDBOX_BLOCKED] native FFI/registry escape forbidden: {event}")

    if not ALLOW_NETWORK and event in _BLOCKED_NET_EVENTS:
        raise PermissionError(f"[HQ_SANDBOX_BLOCKED] offline network wall blocked: {event}")

    if event == "open":
        path, mode, flags = args[0], args[1], args[2]
        if isinstance(path, int):
            if path not in (0, 1, 2):
                raise PermissionError(f"[HQ_SANDBOX_BLOCKED] raw fd open forbidden: {path}")
            return
        is_write = False
        if isinstance(mode, str) and any(ch in mode for ch in ("w", "a", "x", "+")):
            is_write = True
        if isinstance(flags, int) and (flags & _WRITE_O_FLAGS) != 0:
            is_write = True

        if is_write:
            real_norm = _check_workspace_write(path)
            if real_norm not in _write_state["files"]:
                if len(_write_state["files"]) >= MAX_WRITE_FILES:
                    raise PermissionError(f"[HQ_SANDBOX_BLOCKED] max write files quota exceeded ({MAX_WRITE_FILES})")
                _write_state["files"].add(real_norm)
        else:
            _check_read(path)
        return

    if event in ("os.listdir", "os.scandir"):
        target = args[0] if args and args[0] is not None else os.getcwd()
        if not isinstance(target, int):
            _check_read(target)
        return

    if event == "os.chdir":
        target = args[0]
        if not isinstance(target, int):
            _check_read(target)
            _, real_norm = _resolve_norm(target)
            if not _is_under(real_norm, WORKSPACE_NORM):
                raise PermissionError(f"[HQ_SANDBOX_BLOCKED] chdir outside workspace forbidden: {target}")
        return

    if event in ("os.remove", "os.unlink", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate"):
        if args and args[0] is not None and not isinstance(args[0], int):
            _check_workspace_write(args[0], allow_root=(event == "os.mkdir"))
        return

    if event in ("os.rename", "os.replace", "shutil.copyfile", "shutil.move"):
        if len(args) >= 2:
            _check_workspace_write(args[0], allow_root=False)
            _check_workspace_write(args[1], allow_root=False)
        return

    if event == "shutil.rmtree":
        if args and args[0] is not None:
            _check_workspace_write(args[0], allow_root=False)
        return

    if event in ("os.symlink", "os.link"):
        if len(args) >= 2:
            src, dst = args[0], args[1]
            dst_norm = _check_workspace_write(dst, allow_root=False)
            # 解析符号链接目标相对于链接所在目录的真实落点，严防指向工作区外
            dst_parent = os.path.dirname(os.path.realpath(os.fspath(dst)))
            _check_workspace_write(src, relative_to=dst_parent, allow_root=True)
        return

sys.addaudithook(_hq_audit_hook)

user_globals = {"__name__": "__main__", "__builtins__": builtins}
try:
    exec(compile(CODE, "<huiqiao_t2_sandbox>", "exec"), user_globals, user_globals)
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    sys.exit(code)
except BaseException as exc:
    sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
    if isinstance(exc, PermissionError):
        sys.exit(126)
    if isinstance(exc, MemoryError):
        sys.exit(137)
    sys.exit(1)
'''


class _WindowsJobSandbox:
    """Windows 原生 Job Object 内核隔离封装（内存上限 + 进程数上限 + 关闭即灭进程树）。"""

    def __init__(self, *, max_memory_mb: int, max_pids: int) -> None:
        self.handle: int | None = None
        if sys.platform != "win32":
            return
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return

            class _IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32),
                ]

            class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
            JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
            JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
            JobObjectExtendedLimitInformation = 9

            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            mem_bytes = max(32, max_memory_mb) * 1024 * 1024
            info.BasicLimitInformation.LimitFlags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                | JOB_OBJECT_LIMIT_JOB_MEMORY
                | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            )
            info.BasicLimitInformation.ActiveProcessLimit = max(1, max_pids)
            info.ProcessMemoryLimit = mem_bytes
            info.JobMemoryLimit = mem_bytes

            kernel32.SetInformationJobObject.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_uint32,
            ]
            kernel32.SetInformationJobObject.restype = ctypes.c_int
            ok = kernel32.SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if ok:
                self.handle = job
            else:
                kernel32.CloseHandle(job)
        except Exception:
            self.handle = None

    def assign(self, pid: int) -> bool:
        if not self.handle or sys.platform != "win32":
            return False
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_ALL_ACCESS = 0x1F0FFF
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            proc_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, 0, pid)
            if not proc_handle:
                return False
            try:
                kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                kernel32.AssignProcessToJobObject.restype = ctypes.c_int
                return bool(kernel32.AssignProcessToJobObject(self.handle, proc_handle))
            finally:
                kernel32.CloseHandle(proc_handle)
        except Exception:
            return False

    def terminate_and_close(self) -> None:
        if not self.handle or sys.platform != "win32":
            return
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.TerminateJobObject(self.handle, 1)
            kernel32.CloseHandle(self.handle)
        except Exception:
            pass
        finally:
            self.handle = None


def _drain_stream_bounded(stream: Any, max_bytes: int, result_holder: dict[str, Any], key: str) -> None:
    """在后台线程中以有界上限读取管道，防止 10MB+ 输出洪水撑爆或死锁父进程。"""
    chunks: list[bytes] = []
    collected = 0
    truncated = False
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if collected < max_bytes:
                remaining = max_bytes - collected
                if len(chunk) <= remaining:
                    chunks.append(chunk)
                    collected += len(chunk)
                else:
                    chunks.append(chunk[:remaining])
                    collected += remaining
                    truncated = True
            else:
                truncated = True
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass
    result_holder[key] = b"".join(chunks).decode("utf-8", errors="replace")
    result_holder[f"{key}_truncated"] = truncated


def _kill_process_tree(proc: subprocess.Popen[bytes], job: _WindowsJobSandbox | None = None) -> None:
    """跨平台彻底击杀子进程及全部派生进程树，不留孤儿。"""
    if job is not None and job.handle:
        job.terminate_and_close()
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _build_clean_child_env(workspace: pathlib.Path, extra_env: dict[str, str]) -> dict[str, str]:
    """从零构建子进程环境变量，绝不继承宿主 os.environ 中的任何私钥/Token。"""
    env: dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(workspace),
        "USERPROFILE": str(workspace),
        "TEMP": str(workspace),
        "TMP": str(workspace),
        "NO_PROXY": "*",
        "HTTP_PROXY": "http://127.0.0.1:0",
        "HTTPS_PROXY": "http://127.0.0.1:0",
    }
    if sys.platform == "win32":
        # Windows 进程加载系统基础 DLL 所需的极小非敏感变量
        for k in ("SYSTEMROOT", "WINDIR"):
            if k in os.environ:
                env[k] = os.environ[k]
    else:
        env["PATH"] = "/usr/bin:/bin"
        env["LC_ALL"] = "C.UTF-8"
        env["LANG"] = "C.UTF-8"

    env.update(sanitize_user_env(extra_env))
    return env


def _snapshot_files(root: pathlib.Path) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return snap
    for p in root.rglob("*"):
        if p.is_file():
            try:
                st = p.stat()
                rel = p.relative_to(root).as_posix()
                snap[rel] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue
    return snap


class T2OsRestrictedSandbox:
    """T2 OS 原生受限子进程沙箱（跨平台 Windows 10 + Ubuntu Linux CI）。

    四层纵深隔离：
      1. 宿主环境零继承（环境变量脱敏 + 物理屏蔽外网代理）；
      2. 隔离模式启动 `python -I -B`，通过 stdin 投递代码；
      3. CPython C 级不可移除 `sys.addaudithook` 拦截网络/进程派生/FFI/越界读写/符号链接逃逸；
      4. OS 内核资源限额（Windows Job Object / POSIX rlimit）+ 有界管道读取 + 全进程树超时强杀。
    """

    tier: SandboxTier = SandboxTier.T2_OS_RESTRICTED
    backend_name: str = "t2-os-restricted-subprocess"

    def __init__(self, *, allowed_roots: tuple[str | pathlib.Path, ...] = ()) -> None:
        self.allowed_roots = allowed_roots

    def healthcheck(self) -> bool:
        return bool(sys.executable)

    def execute_request(self, request: SandboxRequest) -> SandboxResult:
        started = time.perf_counter()
        lang = request.language.strip().lower()
        if lang != "python":
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=f"T2_UNSUPPORTED_LANGUAGE:{lang}",
                stderr=f"T2 受限进程沙箱仅支持 python，已拒绝：{lang}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        ok_ws, err_ws, resolved_ws = validate_workspace_path(
            request.workspace_dir,
            allowed_roots=self.allowed_roots,
        )
        if not ok_ws:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=err_ws,
                stderr=f"T2 工作区校验失败：{err_ws}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        temp_ctx: tempfile.TemporaryDirectory[str] | None = None
        if resolved_ws is None:
            temp_ctx = tempfile.TemporaryDirectory(prefix="hq_t2_")
            ws_path = pathlib.Path(temp_ctx.name).resolve()
        else:
            resolved_ws.mkdir(parents=True, exist_ok=True)
            ws_path = resolved_ws.resolve()

        try:
            cmd = [sys.executable, "-I", "-B", "-c", _T2_CHILD_BOOTSTRAP]
            if request.dry_run:
                return SandboxResult(
                    ok=True,
                    tier_requested=request.tier,
                    tier_used=self.tier,
                    exit_code=0,
                    stdout="[T2 dry_run] 参数与工作区安全校验通过。",
                    command_preview=[sys.executable, "-I", "-B", "-c", "<t2_audit_bootstrap>"],
                    elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                    backend=f"{self.backend_name}-dry-run",
                )

            before_snap = _snapshot_files(ws_path)
            child_env = _build_clean_child_env(ws_path, request.env_vars)
            payload_bytes = json.dumps(
                {
                    "code": request.code,
                    "workspace": str(ws_path),
                    "allow_network": request.limits.allow_network,
                    "read_only": request.limits.read_only_workspace,
                    "max_memory_mb": request.limits.max_memory_mb,
                    "max_cpu_sec": request.limits.max_cpu_sec,
                    "max_write_files": request.limits.max_write_files,
                    "max_write_bytes": request.limits.max_write_bytes,
                    "sensitive_keywords": list(DEFAULT_SENSITIVE_KEYWORDS),
                },
                ensure_ascii=False,
            ).encode("utf-8")

            popen_kwargs: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": str(ws_path),
                "env": child_env,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                popen_kwargs["start_new_session"] = True

            job = _WindowsJobSandbox(
                max_memory_mb=request.limits.max_memory_mb,
                max_pids=request.limits.max_pids,
            )

            proc = subprocess.Popen(cmd, **popen_kwargs)
            job.assign(proc.pid)

            streams: dict[str, Any] = {
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
            }
            t_out = threading.Thread(
                target=_drain_stream_bounded,
                args=(proc.stdout, request.limits.max_output_bytes, streams, "stdout"),
                daemon=True,
            )
            t_err = threading.Thread(
                target=_drain_stream_bounded,
                args=(proc.stderr, request.limits.max_output_bytes, streams, "stderr"),
                daemon=True,
            )
            t_out.start()
            t_err.start()

            try:
                assert proc.stdin is not None
                proc.stdin.write(payload_bytes)
                proc.stdin.close()
            except Exception:
                pass

            timed_out = False
            killed_reason: str | None = None
            try:
                exit_code = proc.wait(timeout=request.limits.timeout_sec)
            except subprocess.TimeoutExpired:
                timed_out = True
                killed_reason = "TIMEOUT"
                _kill_process_tree(proc, job)
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
                exit_code = 124
            finally:
                job.terminate_and_close()

            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)

            stdout = str(streams["stdout"])
            stderr = str(streams["stderr"])
            output_truncated = bool(streams["stdout_truncated"] or streams["stderr_truncated"])

            blocked = False
            blocked_reason: str | None = None
            if "[HQ_SANDBOX_BLOCKED]" in stderr or exit_code == 126:
                blocked = True
                first_line = stderr.strip().splitlines()[0] if stderr.strip() else "SANDBOX_POLICY_BLOCKED"
                blocked_reason = first_line[:240]
            elif "MemoryError" in stderr or exit_code in (137, -9):
                if not timed_out:
                    blocked = True
                    blocked_reason = "MEMORY_LIMIT_EXCEEDED"
                    killed_reason = killed_reason or "MEMORY_LIMIT"

            artifacts: list[str] = []
            if resolved_ws is not None:
                after_snap = _snapshot_files(ws_path)
                for rel, meta in sorted(after_snap.items()):
                    if before_snap.get(rel) != meta:
                        artifacts.append(rel)

            return SandboxResult(
                ok=(exit_code == 0 and not timed_out and not blocked),
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=int(exit_code),
                stdout=stdout,
                stderr=stderr,
                output_truncated=output_truncated,
                timed_out=timed_out,
                blocked=blocked,
                blocked_reason=blocked_reason,
                killed_reason=killed_reason,
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                artifacts=artifacts,
                command_preview=[sys.executable, "-I", "-B", "-c", "<t2_audit_bootstrap>"],
                backend=self.backend_name,
            )
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()
