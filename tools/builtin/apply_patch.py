from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from tools.base import (
    FileDiff,
    Tool,
    ToolConfirmation,
    ToolInvocation,
    ToolKind,
    ToolResult,
)
from utils.paths import ensure_parent_directory, resolve_path


@dataclass
class MultiFileDiff:
    """A bundle of per-file diffs that quacks like a single FileDiff.

    The agent event layer and TUI only call ``to_diff()`` on a result/confirmation
    diff, so this duck-types FileDiff while carrying many files at once.
    """

    diffs: list[FileDiff]

    def to_diff(self) -> str:
        return "\n".join(d.to_diff() for d in self.diffs)


class PatchEdit(BaseModel):
    path: str = Field(
        ...,
        description="Path to the file to edit (relative to working directory or absolute).",
    )
    old_string: str = Field(
        "",
        description="Exact text to find and replace (whitespace-sensitive). Leave empty to create a new file.",
    )
    new_string: str = Field(
        "",
        description="Replacement text. For a new file this is the full file content. May be empty to delete text.",
    )
    replace_all: bool = Field(
        False,
        description="Replace all occurrences of old_string in this file (default: false).",
    )


class ApplyPatchParams(BaseModel):
    edits: list[PatchEdit] = Field(
        ...,
        min_length=1,
        description="List of edits to apply atomically across one or more files.",
    )


@dataclass
class _PlannedFile:
    path: Path
    original: str
    new_content: str
    existed: bool
    replaced: int


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = (
        "Apply multiple file edits in a single atomic operation across 2+ files. "
        "Each edit replaces old_string with new_string in the given file "
        "(use an empty old_string to create a new file). Multiple edits may target "
        "the same file and are applied in order. If ANY edit fails to apply, NO files "
        "are written. Prefer this over multiple `edit` calls when changing several files."
    )
    kind = ToolKind.WRITE
    schema = ApplyPatchParams

    def _plan(
        self, invocation: ToolInvocation
    ) -> tuple[dict[Path, _PlannedFile], str | None]:
        """Dry-run the edits against an in-memory working copy.

        Returns (planned_files_by_path, error). On error, planned is partial and
        must not be written.
        """
        params = ApplyPatchParams(**invocation.params)
        planned: dict[Path, _PlannedFile] = {}

        for index, edit in enumerate(params.edits):
            try:
                path = resolve_path(invocation.cwd, edit.path)
            except ValueError as e:
                return planned, f"edit {index} ({edit.path}): {e}"

            if path not in planned:
                existed = path.exists()
                if existed and not path.is_file():
                    return planned, f"edit {index} ({edit.path}): not a file"
                original = path.read_text(encoding="utf-8") if existed else ""
                planned[path] = _PlannedFile(
                    path=path,
                    original=original,
                    new_content=original if existed else "",
                    existed=existed,
                    replaced=0,
                )

            pf = planned[path]
            content = pf.new_content
            is_fresh_create = not pf.existed and pf.replaced == 0

            if is_fresh_create and not content:
                # Creating a brand-new file: old_string must be empty.
                if edit.old_string:
                    return (
                        planned,
                        f"edit {index} ({edit.path}): file does not exist; "
                        "use an empty old_string to create it",
                    )
                pf.new_content = edit.new_string
                pf.replaced += 1
                continue

            if not edit.old_string:
                return (
                    planned,
                    f"edit {index} ({edit.path}): old_string is empty but file already "
                    "has content; provide old_string to edit or use write_file to overwrite",
                )

            occurrences = content.count(edit.old_string)
            if occurrences == 0:
                return (
                    planned,
                    f"edit {index} ({edit.path}): old_string not found",
                )
            if occurrences > 1 and not edit.replace_all:
                return (
                    planned,
                    f"edit {index} ({edit.path}): old_string found {occurrences} times; "
                    "add more context for a unique match or set replace_all=true",
                )

            if edit.replace_all:
                pf.new_content = content.replace(edit.old_string, edit.new_string)
                pf.replaced += occurrences
            else:
                pf.new_content = content.replace(edit.old_string, edit.new_string, 1)
                pf.replaced += 1

        return planned, None

    def _diffs(self, planned: dict[Path, _PlannedFile]) -> list[FileDiff]:
        diffs: list[FileDiff] = []
        for pf in planned.values():
            if pf.new_content == pf.original:
                continue
            diffs.append(
                FileDiff(
                    path=pf.path,
                    old_content=pf.original,
                    new_content=pf.new_content,
                    is_new_file=not pf.existed,
                )
            )
        return diffs

    async def get_confirmation(
        self, invocation: ToolInvocation
    ) -> ToolConfirmation | None:
        planned, error = self._plan(invocation)
        diffs = self._diffs(planned)

        if error:
            description = f"apply_patch (invalid): {error}"
        else:
            file_count = len(diffs)
            description = f"Apply patch to {file_count} file(s)"

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=description,
            diff=MultiFileDiff(diffs) if diffs else None,
            affected_paths=list(planned.keys()),
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        planned, error = self._plan(invocation)
        if error:
            return ToolResult.error_result(f"Patch not applied: {error}")

        diffs = self._diffs(planned)
        if not diffs:
            return ToolResult.error_result(
                "No changes to apply (all edits produced identical content)"
            )

        # All edits validated — write atomically (best effort: validation already
        # passed for every file, so per-file IO is the only remaining failure point).
        written: list[Path] = []
        try:
            for pf in planned.values():
                if pf.new_content == pf.original:
                    continue
                if not pf.existed:
                    ensure_parent_directory(pf.path)
                pf.path.write_text(pf.new_content, encoding="utf-8")
                written.append(pf.path)
        except IOError as e:
            return ToolResult.error_result(
                f"Failed to write {len(written)} of {len(diffs)} files before error: {e}. "
                f"Files written: {', '.join(str(p) for p in written)}"
            )

        created = sum(1 for pf in planned.values() if not pf.existed)
        modified = len(diffs) - created
        summary = f"Applied patch: {modified} modified, {created} created ({len(diffs)} files)"
        lines = [summary]
        for pf in planned.values():
            if pf.new_content == pf.original:
                continue
            tag = "create" if not pf.existed else "edit"
            lines.append(f"  {tag} {pf.path} ({pf.replaced} change(s))")

        return ToolResult.success_result(
            "\n".join(lines),
            diff=MultiFileDiff(diffs),
            metadata={
                "files": len(diffs),
                "created": created,
                "modified": modified,
            },
        )
