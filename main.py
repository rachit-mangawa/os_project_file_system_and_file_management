import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from fs import BASE_DIR, STORAGE_DIR, resolve_safe_path, get_item_info, build_tree
from terminal import COMMANDS

app = FastAPI(title="File System & File Management")


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

    try:
        target.rename(destination)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot rename item: {e.strerror or str(e)}")
    return {"message": "Item renamed successfully."}


@app.post("/api/delete")
def api_delete_item(req: DeleteRequest):
    target = resolve_safe_path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Item not found.")
    if target == STORAGE_DIR.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the root storage folder.")

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot delete item: {e.strerror or str(e)}")

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
