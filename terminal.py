import os
import shutil
from pathlib import Path
from fs import STORAGE_DIR, BLOCK_SIZE, resolve_safe_path


def create_file(current_dir: str, args: list) -> tuple[str, str]:
    if not args:
        return ("Error: Missing file name.", current_dir)
    target = resolve_safe_path(f"{current_dir}/{args[0]}")
    if target.exists():
        return (f"Error: '{args[0]}' already exists.", current_dir)
    target.touch()
    return (f"Created '{args[0]}'.", current_dir)


def delete_item(current_dir: str, args: list) -> tuple[str, str]:
    if not args:
        return ("Error: Missing name to delete.", current_dir)
    target = resolve_safe_path(f"{current_dir}/{args[0]}")
    if not target.exists():
        return (f"Error: '{args[0]}' does not exist.", current_dir)
    if target == STORAGE_DIR.resolve():
        return ("Error: Cannot delete root storage folder.", current_dir)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return (f"Deleted '{args[0]}'.", current_dir)


def make_folder(current_dir: str, args: list) -> tuple[str, str]:
    if not args:
        return ("Error: Missing folder name.", current_dir)
    target = resolve_safe_path(f"{current_dir}/{args[0]}")
    if target.exists():
        return (f"Error: Folder '{args[0]}' already exists.", current_dir)
    target.mkdir()
    return (f"Created folder '{args[0]}'.", current_dir)


def change_folder(current_dir: str, args: list) -> tuple[str, str]:
    if not args or args[0] in ("/", "~"):
        return ("Moved to root folder.", "")
    target_arg = args[0]
    if target_arg == "..":
        parts = [p for p in current_dir.split("/") if p]
        new_path = "/".join(parts[:-1]) if parts else ""
        return (f"Moved to '{new_path or 'root'}'.", new_path)
    target = resolve_safe_path(f"{current_dir}/{target_arg}")
    if not target.exists():
        return (f"Error: Folder '{target_arg}' does not exist.", current_dir)
    if not target.is_dir():
        return (f"Error: '{target_arg}' is not a folder.", current_dir)
    rel = str(target.relative_to(STORAGE_DIR)).replace("\\", "/")
    if rel == ".":
        rel = ""
    return (f"Moved to '{rel or 'root'}'.", rel)


def move_item(current_dir: str, args: list) -> tuple[str, str]:
    if len(args) < 2:
        return ("Error: Missing arguments. Usage: mv <source> <target>", current_dir)
    src = resolve_safe_path(f"{current_dir}/{args[0]}")
    if not src.exists():
        return (f"Error: Source '{args[0]}' does not exist.", current_dir)
    if src == STORAGE_DIR.resolve():
        return ("Error: Cannot move root storage.", current_dir)

    dst = resolve_safe_path(f"{current_dir}/{args[1]}")
    if dst.is_dir() and src.parent != dst:
        dst = dst / src.name
    if dst.exists():
        return (f"Error: Destination '{args[1]}' already exists.", current_dir)

    src.rename(dst)
    return (f"Moved '{args[0]}' to '{args[1]}'.", current_dir)


def copy_item(current_dir: str, args: list) -> tuple[str, str]:
    if len(args) < 2:
        return ("Error: Missing arguments. Usage: cp <source> <target>", current_dir)
    src = resolve_safe_path(f"{current_dir}/{args[0]}")
    if not src.exists():
        return (f"Error: Source '{args[0]}' does not exist.", current_dir)
    if src == STORAGE_DIR.resolve():
        return ("Error: Cannot copy root storage.", current_dir)

    dst = resolve_safe_path(f"{current_dir}/{args[1]}")
    if dst.is_dir() and src.parent != dst:
        dst = dst / src.name
    if dst.exists():
        return (f"Error: Destination '{args[1]}' already exists.", current_dir)

    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return (f"Copied '{args[0]}' to '{args[1]}'.", current_dir)


def write_to_file(current_dir: str, args: list) -> tuple[str, str]:
    if len(args) < 2:
        return ("Error: Missing arguments. Usage: write <name> <text> or write <name> @<offset> <text>", current_dir)
    name = args[0]
    target = resolve_safe_path(f"{current_dir}/{name}")
    if target.exists() and target.is_dir():
        return ("Error: Cannot write to a folder.", current_dir)

    if args[1].startswith("@"):
        offset_val = args[1][1:]
        if not offset_val.isdigit():
            return ("Error: Offset must be a positive number.", current_dir)
        offset = int(offset_val)
        text = " ".join(args[2:])
        if not target.exists():
            target.touch()
        with open(target, "r+b") as f:
            f.seek(offset)
            f.write(text.encode("utf-8"))
        return (f"Wrote {len(text)} bytes to '{name}' at offset {offset}.", current_dir)
    else:
        text = " ".join(args[1:])
        target.write_text(text, encoding="utf-8")
        return (f"Wrote {len(text)} bytes to '{name}'.", current_dir)


def read_from_file(current_dir: str, args: list) -> tuple[str, str]:
    if not args:
        return ("Error: Missing file name.", current_dir)
    target = resolve_safe_path(f"{current_dir}/{args[0]}")
    if not target.exists():
        return (f"Error: File '{args[0]}' not found.", current_dir)
    if target.is_dir():
        return ("Error: Cannot read a folder.", current_dir)

    if len(args) >= 3:
        if not (args[1].isdigit() and args[2].isdigit()):
            return ("Error: Start and size must be positive numbers.", current_dir)
        start, size = int(args[1]), int(args[2])
        with open(target, "rb") as f:
            f.seek(start)
            data = f.read(size)
        try:
            return (data.decode("utf-8"), current_dir)
        except UnicodeDecodeError:
            return (str(data), current_dir)
    else:
        try:
            content = target.read_text(encoding="utf-8")
            return (content if content else "(empty file)", current_dir)
        except UnicodeDecodeError:
            return ("Error: File is binary and cannot be displayed as UTF-8 text.", current_dir)


def truncate_file(current_dir: str, args: list) -> tuple[str, str]:
    if len(args) < 2:
        return ("Error: Missing size. Usage: truncate <name> <max_size>", current_dir)
    name, size_val = args[0], args[1]
    if not size_val.isdigit():
        return ("Error: max_size must be a number.", current_dir)
    max_size = int(size_val)
    target = resolve_safe_path(f"{current_dir}/{name}")
    if not target.exists() or not target.is_file():
        return (f"Error: File '{name}' not found.", current_dir)

    with open(target, "r+b") as f:
        f.truncate(max_size)
    return (f"Truncated '{name}' to {max_size} bytes.", current_dir)


def usage_map(current_dir: str, args: list) -> tuple[str, str]:
    total_files = 0
    total_folders = 0
    total_bytes = 0
    total_blocks = 0
    total_slack = 0
    rows = []

    for root, dirs, files in os.walk(STORAGE_DIR):
        total_folders += len(dirs)
        for filename in files:
            file_path = Path(root) / filename
            size = file_path.stat().st_size
            blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE if size > 0 else 0
            allocated = blocks * BLOCK_SIZE
            slack = allocated - size if size > 0 else 0
            rel_path = str(file_path.relative_to(STORAGE_DIR)).replace("\\", "/")
            total_files += 1
            total_bytes += size
            total_blocks += blocks
            total_slack += slack
            rows.append((rel_path, size, blocks, slack))

    divider = "-" * 76
    header = f"{'PATH':<34} {'SIZE (B)':<10} {'BLOCKS (4KB)':<14} {'SLACK/WASTE':<14}"
    body = "\n".join(f"{r[0]:<34} {r[1]:<10} {r[2]:<14} {r[3]:<14}" for r in rows)
    summary = (
        f"{divider}\n"
        f"Totals: {total_files} files, {total_folders} folders | "
        f"{total_bytes} bytes logical | {total_blocks * BLOCK_SIZE} bytes allocated ({total_blocks} blocks) | "
        f"{total_slack} bytes slack waste\n"
        f"(Estimated assuming standard 4 KB filesystem cluster blocks)"
    )
    return (f"Storage Block Usage Map (estimated 4 KB units)\n{divider}\n{header}\n{divider}\n{body}\n{summary}", current_dir)


def reset_sandbox(current_dir: str, args: list) -> tuple[str, str]:
    for item in STORAGE_DIR.iterdir():
        if item.name == "documents":
            for sub in item.iterdir():
                if sub.name != "project_notes.txt":
                    if sub.is_dir():
                        shutil.rmtree(sub)
                    else:
                        sub.unlink()
        elif item.name not in ("demo.py", "welcome.txt"):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    return ("Storage sandbox reset to initial sample state.", "")


COMMANDS = {
    "create": create_file,
    "touch": create_file,
    "delete": delete_item,
    "rm": delete_item,
    "mkdir": make_folder,
    "cd": change_folder,
    "mv": move_item,
    "move": move_item,
    "cp": copy_item,
    "copy": copy_item,
    "write": write_to_file,
    "read": read_from_file,
    "cat": read_from_file,
    "truncate": truncate_file,
    "memmap": usage_map,
    "reset": reset_sandbox,
    "clean": reset_sandbox,
    "clear": lambda cur, args: ("__CLEAR__", cur),
}
