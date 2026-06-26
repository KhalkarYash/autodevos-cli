import asyncio
import os
from pathlib import Path
import signal
import sys
from safety.approval import is_dangerous_command
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
import fnmatch
from utils.paths import resolve_path

_LOGIN_SHELLS = frozenset({"bash", "zsh", "fish"})


class ShellParams(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    timeout: int = Field(
        120, ge=1, le=600, description="Timeout in seconds (default: 120)"
    )
    cwd: str | None = Field(None, description="Working directory for the command")


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = "Execute a shell command. Use this for running system commands, scripts and CLI tools."

    schema = ShellParams

    async def get_confirmation(
        self, invocation: ToolInvocation
    ) -> ToolConfirmation | None:
        params = ShellParams(**invocation.params)

        if is_dangerous_command(params.command):
            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Execute (BLOCKED): {params.command}",
                command=params.command,
                is_dangerous=True,
            )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute: {params.command}",
            command=params.command,
            is_dangerous=False,
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)

        if is_dangerous_command(params.command):
            return ToolResult.error_result(
                f"Command blocked for safety: {params.command}",
                metadata={"blocked": True},
            )

        if params.cwd:
            try:
                cwd = resolve_path(invocation.cwd, params.cwd)
            except ValueError as e:
                return ToolResult.error_result(str(e))
        else:
            cwd = invocation.cwd

        if not cwd.exists():
            return ToolResult.error_result(f"Working directory doesn't exist: {cwd}")

        env = self._build_environment()
        shell_cmd = self._get_shell_command(params.command)

        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=params.timeout,
            )
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
            return ToolResult.error_result(f"Command timed out after {params.timeout}s")

        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")
        exit_code = process.returncode

        output = ""
        if stdout.strip():
            output += stdout.rstrip()

        if stderr.strip():
            output += "\n--- stderr ---\n"
            output += stderr.rstrip()

        if exit_code != 0:
            output += f"\nExit code: {exit_code}"

        if len(output) > 100 * 1024:
            output = output[: 100 * 1024] + "\n... [output truncated]"

        return ToolResult(
            success=exit_code == 0,
            output=output,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code,
        )

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()

        shell_environment = self.config.shell_environment

        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove = [
                    k for k in env.keys() if fnmatch.fnmatch(k.upper(), pattern.upper())
                ]

                for k in keys_to_remove:
                    del env[k]

        if shell_environment.set_vars:
            env.update(shell_environment.set_vars)

        self._augment_path(env)

        return env

    def _get_shell_command(self, command: str) -> list[str]:
        if sys.platform == "win32":
            return ["cmd.exe", "/c", command]

        shell = os.environ.get("SHELL", "")
        if not shell or not Path(shell).is_file():
            shell = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"

        # Login shell loads nvm/fnm/homebrew paths from the user's profile.
        if Path(shell).name in _LOGIN_SHELLS:
            return [shell, "-lc", command]
        return [shell, "-c", command]

    @staticmethod
    def _resolve_nvm_node_bin(home: Path) -> Path | None:
        nvm_dir = home / ".nvm"
        default_file = nvm_dir / "alias" / "default"
        if not default_file.is_file():
            return None

        version = default_file.read_text().strip()
        versions_dir = nvm_dir / "versions" / "node"
        if version.startswith("v"):
            node_bin = versions_dir / version / "bin"
            return node_bin if node_bin.is_dir() else None

        matches = sorted(
            (
                v
                for v in versions_dir.iterdir()
                if v.is_dir() and v.name.startswith(f"v{version}")
            ),
            key=lambda p: p.name,
        )
        if not matches:
            return None
        node_bin = matches[-1] / "bin"
        return node_bin if node_bin.is_dir() else None

    def _augment_path(self, env: dict[str, str]) -> None:
        """Prepend common dev-tool directories when they are missing from PATH."""
        home = env.get("HOME")
        if not home:
            return

        home_path = Path(home)
        candidates: list[Path] = []

        if sys.platform == "darwin":
            candidates.extend([Path("/opt/homebrew/bin"), Path("/usr/local/bin")])

        candidates.extend([
            home_path / ".local" / "bin",
            home_path / ".cargo" / "bin",
            home_path / ".bun" / "bin",
            home_path / ".volta" / "bin",
            home_path / ".asdf" / "shims",
            home_path / ".local" / "share" / "mise" / "shims",
            home_path / ".pyenv" / "shims",
            home_path / ".local" / "share" / "fnm" / "aliases" / "default" / "bin",
        ])

        nvm_node_bin = self._resolve_nvm_node_bin(home_path)
        if nvm_node_bin is not None:
            candidates.append(nvm_node_bin)

        existing = env.get("PATH", "")
        existing_parts = existing.split(":") if existing else []
        prepended: list[str] = []
        for candidate in candidates:
            path_str = str(candidate)
            if (
                candidate.is_dir()
                and path_str not in existing_parts
                and path_str not in prepended
            ):
                prepended.append(path_str)

        if prepended:
            env["PATH"] = ":".join(prepended + ([existing] if existing else []))
