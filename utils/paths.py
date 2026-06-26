from pathlib import Path


def is_path_within_base(path: str | Path, base: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def resolve_path(
    base: str | Path,
    path: str | Path,
    *,
    enforce_within_base: bool = True,
) -> Path:
    base_path = Path(base).resolve()
    input_path = Path(path).expanduser()
    if input_path.is_absolute():
        resolved = input_path.resolve()
    else:
        resolved = (base_path / input_path).resolve()

    if enforce_within_base and not is_path_within_base(resolved, base_path):
        raise ValueError(f"Path escapes workspace: {path}")

    return resolved


def display_path_rel_to_cwd(path: str, cwd: Path | None) -> str:
    try:
        p = Path(path)
    except Exception:
        return path

    if cwd:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            pass

    return str(p)


def ensure_parent_directory(path: str | Path) -> Path:
    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def is_binary_file(path: str | Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False
