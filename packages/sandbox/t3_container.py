"""M08 (B07) T3 硬化隔离容器沙箱适配器（无网 Docker / 可插拔 MicroVM，严格 Fail-Closed）."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any, Callable

from packages.core.contracts import SandboxTier
from packages.sandbox.models import SandboxRequest, SandboxResult
from packages.sandbox.security import sanitize_user_env, validate_workspace_path
from packages.sandbox.t2_os import _drain_stream_bounded

DaemonProbeFn = Callable[[], bool]
CommandRunnerFn = Callable[[list[str], bytes, float, int], tuple[int, str, str, bool, bool]]


class T3ContainerSandbox:
    """T3 强隔离容器沙箱适配器（默认无网硬化 Docker，零静默降级）。

    安全强化参数清单：
      - `--rm`：运行完即销毁容器；
      - `--network=none`：物理禁用网卡（当 allow_network=False）；
      - `--read-only`：根文件系统只读；
      - `--cap-drop=ALL` + `--security-opt=no-new-privileges:true`：移除所有 Linux 内核特权；
      - `--pids-limit=<N>`：防 Fork 炸弹；
      - `--memory=<M>m --memory-swap=<M>m`：物理封顶内存且禁 Swap 逃逸；
      - `--tmpfs /tmp:rw,noexec,nosuid,size=64m`：无执行权限的受限临时盘；
      - Fail-Closed：宿主机未启动守护进程且未配置显式降级策略时直接阻断，绝不在宿主裸跑！
    """

    tier: SandboxTier = SandboxTier.T3_ISOLATED_VM
    backend_name: str = "t3-docker-hardened"

    def __init__(
        self,
        *,
        docker_binary: str = "docker",
        default_image: str = "python:3.11-slim",
        offline_only: bool = True,
        allowed_roots: tuple[str | pathlib.Path, ...] = (),
        daemon_probe: DaemonProbeFn | None = None,
        command_runner: CommandRunnerFn | None = None,
    ) -> None:
        self.docker_binary = docker_binary
        self.default_image = default_image
        self.offline_only = offline_only
        self.allowed_roots = allowed_roots
        self._daemon_probe = daemon_probe
        self._command_runner = command_runner

    def is_daemon_available(self) -> bool:
        if self._daemon_probe is not None:
            return bool(self._daemon_probe())
        if shutil.which(self.docker_binary) is None:
            return False
        try:
            proc = subprocess.run(
                [self.docker_binary, "version", "--format", "{{.Server.Version}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2.5,
                check=False,
            )
            return proc.returncode == 0 and bool(proc.stdout.strip())
        except Exception:
            return False

    def healthcheck(self) -> bool:
        return self.is_daemon_available()

    def build_command(
        self,
        request: SandboxRequest,
        *,
        workspace_path: pathlib.Path,
        container_name: str,
    ) -> list[str]:
        limits = request.limits
        mount_mode = "ro" if limits.read_only_workspace else "rw"
        cpus = f"{min(max(limits.max_cpu_sec / max(limits.timeout_sec, 1.0), 0.5), 2.0):.1f}"
        cmd: list[str] = [
            self.docker_binary,
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
        ]
        if not limits.allow_network:
            cmd.append("--network=none")
        cmd.extend(
            [
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                f"--pids-limit={limits.max_pids}",
                f"--memory={limits.max_memory_mb}m",
                f"--memory-swap={limits.max_memory_mb}m",
                f"--cpus={cpus}",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--workdir",
                "/workspace",
                "-v",
                f"{workspace_path.as_posix()}:/workspace:{mount_mode}",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "PYTHONNOUSERSITE=1",
                "-e",
                "PYTHONUTF8=1",
            ]
        )
        for k, v in sorted(sanitize_user_env(request.env_vars).items()):
            cmd.extend(["-e", f"{k}={v}"])

        cmd.append(self.default_image)
        lang = request.language.strip().lower()
        if lang == "python":
            cmd.extend(["python", "-I", "-"])
        elif lang == "shell":
            cmd.extend(["sh", "-s"])
        else:
            cmd.extend(["python", "-I", "-"])
        return cmd

    def execute_request(self, request: SandboxRequest) -> SandboxResult:
        started = time.perf_counter()
        lang = request.language.strip().lower()
        if lang not in ("python", "shell"):
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=f"T3_UNSUPPORTED_LANGUAGE:{lang}",
                stderr=f"T3 容器沙箱仅支持 python / shell，已拒绝：{lang}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        if self.offline_only and request.limits.allow_network:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason="OFFLINE_NETWORK_BLOCKED",
                stderr="T3 沙箱处于全局离线锁（offline_only=True），禁止开启容器网络。",
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
                stderr=f"T3 容器挂载目录安全校验失败：{err_ws}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        temp_ctx: tempfile.TemporaryDirectory[str] | None = None
        if resolved_ws is None:
            temp_ctx = tempfile.TemporaryDirectory(prefix="hq_t3_")
            ws_path = pathlib.Path(temp_ctx.name).resolve()
        else:
            resolved_ws.mkdir(parents=True, exist_ok=True)
            ws_path = resolved_ws.resolve()

        try:
            container_name = f"hq_t3_{uuid.uuid4().hex[:12]}"
            cmd = self.build_command(
                request,
                workspace_path=ws_path,
                container_name=container_name,
            )

            if request.dry_run:
                return SandboxResult(
                    ok=True,
                    tier_requested=request.tier,
                    tier_used=self.tier,
                    exit_code=0,
                    stdout="[T3 dry_run] 硬化容器命令生成并通过安全审计。",
                    command_preview=cmd,
                    elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                    backend=f"{self.backend_name}-dry-run",
                )

            if self._command_runner is None and not self.is_daemon_available():
                return SandboxResult(
                    ok=False,
                    tier_requested=request.tier,
                    tier_used=self.tier,
                    exit_code=126,
                    blocked=True,
                    blocked_reason="T3_DAEMON_UNAVAILABLE",
                    stderr="T3 容器守护进程未运行或不可访问；遵循 Fail-Closed 原则拒绝降级至宿主裸跑。",
                    command_preview=cmd,
                    elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                    backend=self.backend_name,
                )

            code_bytes = request.code.encode("utf-8")
            if self._command_runner is not None:
                exit_code, stdout, stderr, timed_out, truncated = self._command_runner(
                    cmd,
                    code_bytes,
                    request.limits.timeout_sec,
                    request.limits.max_output_bytes,
                )
            else:
                exit_code, stdout, stderr, timed_out, truncated = self._run_docker_subprocess(
                    cmd,
                    container_name=container_name,
                    code_bytes=code_bytes,
                    timeout_sec=request.limits.timeout_sec,
                    max_output_bytes=request.limits.max_output_bytes,
                )

            return SandboxResult(
                ok=(exit_code == 0 and not timed_out),
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=int(exit_code),
                stdout=stdout,
                stderr=stderr,
                output_truncated=truncated,
                timed_out=timed_out,
                killed_reason="TIMEOUT" if timed_out else None,
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                command_preview=cmd,
                backend=self.backend_name,
            )
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()

    def _run_docker_subprocess(
        self,
        cmd: list[str],
        *,
        container_name: str,
        code_bytes: bytes,
        timeout_sec: float,
        max_output_bytes: int,
    ) -> tuple[int, str, str, bool, bool]:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        streams: dict[str, Any] = {
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        t_out = threading.Thread(
            target=_drain_stream_bounded,
            args=(proc.stdout, max_output_bytes, streams, "stdout"),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_drain_stream_bounded,
            args=(proc.stderr, max_output_bytes, streams, "stderr"),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        try:
            assert proc.stdin is not None
            proc.stdin.write(code_bytes)
            proc.stdin.close()
        except Exception:
            pass

        timed_out = False
        try:
            exit_code = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(
                [self.docker_binary, "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            proc.kill()
            exit_code = 124

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        truncated = bool(streams["stdout_truncated"] or streams["stderr_truncated"])
        return exit_code, str(streams["stdout"]), str(streams["stderr"]), timed_out, truncated
