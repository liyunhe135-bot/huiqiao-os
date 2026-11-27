"""M08 (B07) T1 轻量级纯计算沙箱（AST 门禁 + 步数/超时/内存防炸弹插桩 + 可选 wasmtime）."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import time
from typing import Any

from packages.core.contracts import SandboxTier
from packages.sandbox.models import SandboxRequest, SandboxResult
from packages.sandbox.security import T1_ALLOWED_IMPORTS, analyze_t1_python_ast


class _T1TimeoutError(BaseException):
    """内部不可被用户 except Exception 吞掉的超时/步数中止信号。"""


class _T1MemoryError(BaseException):
    """内部不可被用户 except Exception 吞掉的内存炸弹中止信号。"""


class _BoundedOutputBuffer:
    """严格有界的 stdout 收集器，防止打印洪水炸弹撑爆宿主内存。"""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._chunks: list[str] = []
        self._byte_len = 0
        self.truncated = False

    def write(self, text: str) -> None:
        if self.truncated or not text:
            return
        encoded = text.encode("utf-8", errors="replace")
        remaining = self.max_bytes - self._byte_len
        if len(encoded) <= remaining:
            self._chunks.append(text)
            self._byte_len += len(encoded)
        else:
            if remaining > 0:
                clipped = encoded[:remaining].decode("utf-8", errors="ignore")
                self._chunks.append(clipped)
                self._byte_len += len(clipped.encode("utf-8"))
            self.truncated = True

    def getvalue(self) -> str:
        return "".join(self._chunks)


class _LoopAndResourceGuard(ast.NodeTransformer):
    """在 AST 层对循环、推导式、函数体、乘方与序列乘法自动注入安全护栏。"""

    def _tick_stmt(self) -> ast.Expr:
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_hq_tick", ctx=ast.Load()),
                args=[],
                keywords=[],
            )
        )

    def visit_While(self, node: ast.While) -> ast.AST:
        self.generic_visit(node)
        node.body = [self._tick_stmt(), *node.body]
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        self.generic_visit(node)
        node.iter = ast.Call(
            func=ast.Name(id="_hq_iter", ctx=ast.Load()),
            args=[node.iter],
            keywords=[],
        )
        node.body = [self._tick_stmt(), *node.body]
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        node.body = [self._tick_stmt(), *node.body]
        return node

    def visit_comprehension(self, node: ast.comprehension) -> ast.AST:
        self.generic_visit(node)
        node.iter = ast.Call(
            func=ast.Name(id="_hq_iter", ctx=ast.Load()),
            args=[node.iter],
            keywords=[],
        )
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Pow):
            return ast.Call(
                func=ast.Name(id="_hq_pow", ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        if isinstance(node.op, ast.Mult):
            return ast.Call(
                func=ast.Name(id="_hq_mul", ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[],
            )
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Pow):
            load_target = ast.Name(id=node.target.id, ctx=ast.Load()) if isinstance(node.target, ast.Name) else None
            if load_target is not None:
                return ast.Assign(
                    targets=[node.target],
                    value=ast.Call(
                        func=ast.Name(id="_hq_pow", ctx=ast.Load()),
                        args=[load_target, node.value],
                        keywords=[],
                    ),
                )
        if isinstance(node.op, ast.Mult):
            load_target = ast.Name(id=node.target.id, ctx=ast.Load()) if isinstance(node.target, ast.Name) else None
            if load_target is not None:
                return ast.Assign(
                    targets=[node.target],
                    value=ast.Call(
                        func=ast.Name(id="_hq_mul", ctx=ast.Load()),
                        args=[load_target, node.value],
                        keywords=[],
                    ),
                )
        return node


class T1WasmLightSandbox:
    """T1 轻量纯计算沙箱（零文件、零网络、零子进程，<50ms 启动）。

    - 对 Python 纯计算脚本：采用强 AST 静态白名单 + 运行时步数/超时/内存插桩执行；
    - 对 WASM 字节码：自动检测本机可选 `wasmtime` 运行时（未安装时 Fail-Closed）。
    """

    tier: SandboxTier = SandboxTier.T1_WASM
    backend_name: str = "t1-restricted-ast"

    def __init__(self, *, max_steps_per_sec: int = 250_000) -> None:
        self.max_steps_per_sec = max_steps_per_sec
        self._has_wasmtime = importlib.util.find_spec("wasmtime") is not None

    def healthcheck(self) -> bool:
        return True

    def execute_request(self, request: SandboxRequest) -> SandboxResult:
        started = time.perf_counter()
        lang = request.language.strip().lower()

        if request.limits.allow_network:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason="T1_NETWORK_FORBIDDEN",
                stderr="T1 轻量纯计算沙箱物理禁网，不允许开启 allow_network。",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        if lang == "wasm":
            return self._execute_wasm(request, started)

        if lang != "python":
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=f"T1_UNSUPPORTED_LANGUAGE:{lang}",
                stderr=f"T1 沙箱仅支持 python / wasm 纯计算，已拒绝语言：{lang}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )

        violations = analyze_t1_python_ast(request.code)
        if violations:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=f"T1_AST_BLOCKED:{violations[0]}",
                stderr=f"T1 静态安全门禁拦截：{'; '.join(violations[:5])}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
                metadata={"violations": violations},
            )

        if request.dry_run:
            return SandboxResult(
                ok=True,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=0,
                stdout="[T1 dry_run] AST 静态门禁通过。",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=f"{self.backend_name}-dry-run",
            )

        return self._execute_python_ast(request, started)

    def _execute_wasm(self, request: SandboxRequest, started: float) -> SandboxResult:
        if not self._has_wasmtime:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                blocked=True,
                blocked_reason="WASM_RUNTIME_UNAVAILABLE",
                stderr="本机未安装 wasmtime，T1 WASM 执行遵循 Fail-Closed 拒绝降级。",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend="t1-wasmtime",
            )
        # 若环境安装了 wasmtime，执行带 fuel 限额的零能力 WASM 模块（WAT 文本）
        try:
            import wasmtime  # type: ignore[import-not-found]

            cfg = wasmtime.Config()
            cfg.consume_fuel = True
            engine = wasmtime.Engine(cfg)
            store = wasmtime.Store(engine)
            store.set_fuel(int(max(10_000, request.limits.timeout_sec * 1_000_000)))
            module = wasmtime.Module(engine, request.code)
            instance = wasmtime.Instance(store, module, [])
            exports = instance.exports(store)
            out_val = ""
            if "main" in exports:
                res = exports["main"](store)
                out_val = "" if res is None else str(res)
            return SandboxResult(
                ok=True,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=0,
                stdout=out_val,
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend="t1-wasmtime",
            )
        except Exception as exc:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=1,
                stderr=f"T1 WASM 执行失败: {type(exc).__name__}: {exc}",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend="t1-wasmtime",
            )

    def _execute_python_ast(self, request: SandboxRequest, started: float) -> SandboxResult:
        limits = request.limits
        deadline = time.monotonic() + limits.timeout_sec
        max_steps = int(max(50_000, limits.timeout_sec * self.max_steps_per_sec))
        max_alloc_bytes = limits.max_memory_mb * 1024 * 1024
        # 对纯计算单对象分配设置严厉上限，防止瞬时炸穿宿主 RAM
        hard_object_cap = min(max_alloc_bytes, 64 * 1024 * 1024)
        out_buf = _BoundedOutputBuffer(limits.max_output_bytes)

        state = {"steps": 0, "alloc_bytes": 0}

        def _hq_tick() -> None:
            state["steps"] += 1
            if state["steps"] > max_steps:
                raise _T1TimeoutError(f"T1_STEP_LIMIT_EXCEEDED:{max_steps}")
            if (state["steps"] & 255) == 0 and time.monotonic() > deadline:
                raise _T1TimeoutError(f"T1_TIMEOUT:{limits.timeout_sec}s")

        def _hq_iter(iterable: Any) -> Any:
            for item in iterable:
                _hq_tick()
                yield item

        def _hq_charge_mem(estimated_bytes: int) -> None:
            if estimated_bytes < 0:
                return
            state["alloc_bytes"] += estimated_bytes
            if estimated_bytes > hard_object_cap or state["alloc_bytes"] > max_alloc_bytes:
                raise _T1MemoryError(
                    f"T1_MEMORY_LIMIT_EXCEEDED: limit={limits.max_memory_mb}MB"
                )

        def _hq_pow(base: Any, exp: Any, mod: Any = None) -> Any:
            _hq_tick()
            if mod is not None:
                return pow(base, exp, mod)
            if isinstance(exp, (int, float)) and isinstance(base, (int, float)):
                if abs(exp) > 10_000 and abs(base) > 1:
                    raise _T1MemoryError("T1_EXPONENT_BOMB_BLOCKED")
            return base ** exp

        def _hq_mul(left: Any, right: Any) -> Any:
            _hq_tick()
            seq_types = (str, bytes, bytearray, list, tuple)
            if isinstance(left, seq_types) and isinstance(right, int):
                est = len(left) * max(0, right) * (8 if isinstance(left, (list, tuple)) else 1)
                _hq_charge_mem(est)
            elif isinstance(right, seq_types) and isinstance(left, int):
                est = len(right) * max(0, left) * (8 if isinstance(right, (list, tuple)) else 1)
                _hq_charge_mem(est)
            return left * right

        def _safe_print(*args: Any, sep: str = " ", end: str = "\n") -> None:
            _hq_tick()
            text = sep.join(str(a) for a in args) + end
            out_buf.write(text)

        def _safe_range(*args: Any) -> Any:
            r = range(*args)
            if len(r) > 2_000_000:
                raise _T1TimeoutError("T1_RANGE_BOMB_BLOCKED")
            return _hq_iter(r)

        def _safe_bytearray(*args: Any, **kwargs: Any) -> bytearray:
            if args and isinstance(args[0], int):
                _hq_charge_mem(args[0])
            elif args and hasattr(args[0], "__len__"):
                _hq_charge_mem(len(args[0]))
            return bytearray(*args, **kwargs)

        def _safe_bytes(*args: Any, **kwargs: Any) -> bytes:
            if args and isinstance(args[0], int):
                _hq_charge_mem(args[0])
            elif args and hasattr(args[0], "__len__"):
                _hq_charge_mem(len(args[0]))
            return bytes(*args, **kwargs)

        def _safe_import(
            name: str,
            globals_: Any = None,
            locals_: Any = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if level != 0:
                raise PermissionError("T1_RELATIVE_IMPORT_FORBIDDEN")
            root = name.split(".")[0]
            if root not in T1_ALLOWED_IMPORTS:
                raise PermissionError(f"T1_FORBIDDEN_IMPORT:{name}")
            return importlib.import_module(name)

        safe_builtins: dict[str, Any] = {
            "abs": abs,
            "all": all,
            "any": any,
            "ascii": ascii,
            "bin": bin,
            "bool": bool,
            "bytearray": _safe_bytearray,
            "bytes": _safe_bytes,
            "chr": chr,
            "complex": complex,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "hash": hash,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": _hq_iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": _hq_pow,
            "print": _safe_print,
            "range": _safe_range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
            "__import__": _safe_import,
            # 安全异常类型
            "AssertionError": AssertionError,
            "Exception": Exception,
            "IndexError": IndexError,
            "KeyError": KeyError,
            "MemoryError": MemoryError,
            "OverflowError": OverflowError,
            "PermissionError": PermissionError,
            "RuntimeError": RuntimeError,
            "StopIteration": StopIteration,
            "TypeError": TypeError,
            "ValueError": ValueError,
            "ZeroDivisionError": ZeroDivisionError,
        }

        tree = ast.parse(request.code, mode="exec")
        guarded_tree = _LoopAndResourceGuard().visit(tree)
        ast.fix_missing_locations(guarded_tree)
        compiled = compile(guarded_tree, "<huiqiao_t1_sandbox>", "exec")

        exec_globals: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "_hq_tick": _hq_tick,
            "_hq_iter": _hq_iter,
            "_hq_pow": _hq_pow,
            "_hq_mul": _hq_mul,
        }

        try:
            exec(compiled, exec_globals, exec_globals)  # noqa: S102
            return SandboxResult(
                ok=True,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=0,
                stdout=out_buf.getvalue(),
                output_truncated=out_buf.truncated,
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )
        except _T1TimeoutError as exc:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=124,
                stdout=out_buf.getvalue(),
                stderr=str(exc),
                output_truncated=out_buf.truncated,
                timed_out=True,
                killed_reason="TIMEOUT",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )
        except (_T1MemoryError, MemoryError) as exc:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=137,
                stdout=out_buf.getvalue(),
                stderr=str(exc),
                output_truncated=out_buf.truncated,
                blocked=True,
                blocked_reason="MEMORY_LIMIT_EXCEEDED",
                killed_reason="MEMORY_LIMIT",
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )
        except PermissionError as exc:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=126,
                stdout=out_buf.getvalue(),
                stderr=str(exc),
                output_truncated=out_buf.truncated,
                blocked=True,
                blocked_reason=str(exc),
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )
        except Exception as exc:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=self.tier,
                exit_code=1,
                stdout=out_buf.getvalue(),
                stderr=f"{type(exc).__name__}: {exc}",
                output_truncated=out_buf.truncated,
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
                backend=self.backend_name,
            )
