import os
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="File System & File Management")

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

BLOCK_SIZE = 4096


class CreateFolderRequest(BaseModel):
    path: str = ""
    name: str


class RenameRequest(BaseModel):
    path: str
    new_name: str


class DeleteRequest(BaseModel):
    path: str


class SaveTextRequest(BaseModel):
    path: str
    content: str


class CommandRequest(BaseModel):
    current_path: str = ""
    command: str = ""


def resolve_safe_path(user_path: str = "") -> Path:
    # Strip slashes to avoid joining treating user input as absolute root
    cleaned = user_path.strip().lstrip("/\\")
    resolved = (STORAGE_DIR / cleaned).resolve()

    # Block directory traversal (..) and symlink escapes outside the storage sandbox
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


def build_tree(folder: Path) -> dict:
    folders = []
    files = []
    for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel = str(entry.relative_to(STORAGE_DIR)).replace("\\", "/")
        if rel == ".":
            rel = ""
        if entry.is_dir():
            folders.append(build_tree(entry))
        else:
            files.append({"name": entry.name, "path": rel, "type": "file"})

    rel_folder = str(folder.relative_to(STORAGE_DIR)).replace("\\", "/")
    if rel_folder == ".":
        rel_folder = ""
    return {
        "name": folder.name if rel_folder else "storage",
        "path": rel_folder,
        "type": "directory",
        "children": folders + files,
    }


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


@app.get("/")
def serve_ui():
    index_file = BASE_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found.")
    return FileResponse(index_file)


@app.get("/tree")
def get_tree():
    return build_tree(STORAGE_DIR)


@app.post("/run")
def run_command(req: CommandRequest):
    raw = req.command.strip()
    if not raw:
        return {"output": "", "current_path": req.current_path}

    parts = raw.split()
    cmd = parts[0].lower()
    args = parts[1:]

    handler = COMMANDS.get(cmd)
    if not handler:
        return {
            "output": f"Unknown command: '{cmd}'. Available: mkdir, cd, touch/create, write, read/cat, cp, mv, rm/delete, truncate, memmap, reset",
            "current_path": req.current_path,
        }

    try:
        output_text, new_path = handler(req.current_path, args)
        return {"output": output_text, "current_path": new_path}
    except HTTPException as error:
        return {"output": f"Error: {error.detail}", "current_path": req.current_path}
    except Exception as error:
        return {"output": f"Error: {str(error)}", "current_path": req.current_path}


@app.get("/api/list")
def list_folder(path: str = ""):
    target = resolve_safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Folder does not exist.")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Requested path is not a folder.")

    items = [get_item_info(child) for child in target.iterdir()]
    items.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))

    rel_path = str(target.relative_to(STORAGE_DIR)).replace("\\", "/")
    if rel_path == ".":
        rel_path = ""

    return {"current_path": rel_path, "items": items}


@app.post("/api/folder")
def create_folder(req: CreateFolderRequest):
    folder_name = req.name.strip()
    if not folder_name or "/" in folder_name or "\\" in folder_name:
        raise HTTPException(status_code=400, detail="Invalid folder name.")

    target = resolve_safe_path(f"{req.path}/{folder_name}")
    if target.exists():
        raise HTTPException(status_code=400, detail="An item with this name already exists.")

    target.mkdir()
    return {"message": "Folder created successfully."}


@app.post("/api/upload")
def upload_file(path: str = Form(""), file: UploadFile = File(...)):
    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    target = resolve_safe_path(f"{path}/{filename}")
    with open(target, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "File uploaded successfully."}


@app.get("/api/download")
def download_file(path: str):
    target = resolve_safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(target, filename=target.name)


@app.post("/api/rename")
def rename_item(req: RenameRequest):
    new_name = req.new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        raise HTTPException(status_code=400, detail="Invalid new name.")

    target = resolve_safe_path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
    if target == STORAGE_DIR.resolve():
        raise HTTPException(status_code=400, detail="Cannot rename the root storage folder.")

    destination = target.parent / new_name
    resolve_safe_path(str(destination.relative_to(STORAGE_DIR)))

    if destination.exists():
        raise HTTPException(status_code=400, detail="An item with the new name already exists.")

    target.rename(destination)
    return {"message": "Item renamed successfully."}


@app.post("/api/delete")
def api_delete_item(req: DeleteRequest):
    target = resolve_safe_path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
    if target == STORAGE_DIR.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the root storage folder.")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"message": "Deleted successfully."}


@app.get("/api/read")
def read_text_file(path: str):
    target = resolve_safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        content = target.read_text(encoding="utf-8")
        return {"content": content, "name": target.name}
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Cannot open file: not a UTF-8 text file.")


@app.post("/api/save")
def save_text_file(req: SaveTextRequest):
    target = resolve_safe_path(req.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        target.write_text(req.content, encoding="utf-8")
        return {"message": "File saved successfully."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(error)}")


@app.get("/api/search")
def search_items(q: str):
    query = q.strip().lower()
    if not query:
        return {"results": []}

    results = []
    for root, dirs, files in os.walk(STORAGE_DIR):
        for name in dirs + files:
            if query in name.lower():
                full_path = Path(root) / name
                results.append(get_item_info(full_path))

    return {"results": results}


@app.get("/api/properties")
def get_properties(path: str):
    target = resolve_safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")

    info = get_item_info(target)
    info["full_path"] = str(target)
    return info


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
