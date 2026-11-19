import os
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

BLOCK_SIZE = 4096


def resolve_safe_path(user_path: str = "") -> Path:
    cleaned = user_path.strip().lstrip("/\\")
    resolved = (STORAGE_DIR / cleaned).resolve()
    storage_root = STORAGE_DIR.resolve()

    if resolved != storage_root and storage_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Access denied: Path is outside the sandbox.")

    return resolved


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_item_info(target_path: Path) -> dict:
    stat = target_path.stat()
    is_directory = target_path.is_dir()
    rel_path = str(target_path.relative_to(STORAGE_DIR)).replace("\\", "/")
    if rel_path == ".":
        rel_path = ""

    size = stat.st_size
    if is_directory:
        blocks = 0
        allocated = 0
        slack = 0
    else:
        blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE if size > 0 else 0
        allocated = blocks * BLOCK_SIZE
        slack = allocated - size if size > 0 else 0

    mode = stat.st_mode
    is_writable = bool(mode & 0o200)
    perm_str = "rw-rw-rw-" if is_writable else "r--r--r--"

    return {
        "name": target_path.name,
        "path": rel_path,
        "type": "directory" if is_directory else "file",
        "size": "-" if is_directory else format_size(size),
        "size_bytes": 0 if is_directory else size,
        "blocks": blocks,
        "allocated_bytes": allocated,
        "slack_bytes": slack,
        "extension": "" if is_directory else target_path.suffix.lower(),
        "permissions": perm_str,
        "mode_octal": oct(mode)[-3:],
        "readonly": not is_writable,
        "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_tree(folder: Path, max_depth: int = 15, current_depth: int = 0) -> dict:
    if current_depth > max_depth:
        return {"name": folder.name, "path": "", "type": "directory", "children": []}

    folders = []
    files = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        entries = []

    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            rel = str(entry.relative_to(STORAGE_DIR)).replace("\\", "/")
            if rel == ".":
                rel = ""
            if entry.is_dir():
                folders.append(build_tree(entry, max_depth, current_depth + 1))
            else:
                files.append({"name": entry.name, "path": rel, "type": "file"})
        except OSError:
            continue

    rel_folder = str(folder.relative_to(STORAGE_DIR)).replace("\\", "/")
    if rel_folder == ".":
        rel_folder = ""
    return {
        "name": folder.name if rel_folder else "storage",
        "path": rel_folder,
        "type": "directory",
        "children": folders + files,
    }
