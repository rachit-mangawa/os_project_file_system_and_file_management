# File System & File Management

A lightweight web-based file manager and terminal interface demonstrating operating system file management concepts over an isolated disk sandbox (`storage/`).

Built for the 7th Semester OS course project. Runs entirely on `127.0.0.1:8000` with zero cloud dependencies, build tools, or frontend frameworks.

---

## Quick Start (Windows)

Double-click `run.bat` or execute in PowerShell / Command Prompt:

```cmd
.\run.bat
```

`run.bat` handles everything:
1. Clears any stale process holding port `8000` to avoid bind conflicts (`Errno 10048`).
2. Detects `uv` (or falls back to standard Python `venv`).
3. Installs backend dependencies (`fastapi`, `uvicorn`, `python-multipart`).
4. Launches the server and opens `http://127.0.0.1:8000` in your default browser.

---

## Project Structure

```
project_work/
├── main.py        # Single-file backend (FastAPI, os, pathlib, shutil)
├── index.html     # Single-file frontend (Vanilla HTML5, CSS3, ES6 JS)
├── run.bat        # Automated one-click bootstrap script
├── storage/       # Active sandbox directory (sample files included)
│   ├── demo.py
│   ├── welcome.txt
│   └── documents/
│       └── project_notes.txt
├── README.md      # Project overview and run guide
└── report.md      # Complete OS technical report and viva defense guide
```

---

## Core Features

### 1. GUI File Manager
- **Directory Navigation:** Breadcrumb trail and parent (`..`) navigation.
- **File CRUD:** Create folder, upload file, download file, rename, and delete (with UI confirmation).
- **In-Browser Text Editor:** Open, edit, and save UTF-8 text and script files directly.
- **Search:** Case-insensitive recursive name search across the entire sandbox.
- **Properties & Metadata Inspector:** Inspects logical file size, physical disk allocation, internal fragmentation (slack space), POSIX permissions, octal modes, timestamps, and full system paths via `os.stat()`.

### 2. Live Directory Tree (Side Panel)
- Live recursive tree of `storage/` separating folders (`📁`) and files (`📄`).
- Highlights active directory; clicking any folder changes directory.
- Refreshes automatically on every file change.

### 3. Integrated Terminal & CLI
Interactive command bar supporting bash-like operations with Tab autocompletion:
- `mkdir <name>` — Create directory (`os.mkdir`).
- `cd <path>` — Change working directory (`cd ..` moves up, `cd /` returns to root).
- `touch <name>` / `create <name>` — Create an empty file (`Path.touch`).
- `write <name> <text>` — Overwrite file content with text.
- `write <name> @<offset> <text>` — Low-level write at a specific byte offset (`f.seek(offset)`).
- `cat <name>` / `read <name>` — Output entire file.
- `read <name> <start> <size>` — Sliced byte read (`f.seek(start)`, `f.read(size)`).
- `cp <src> <dst>` — Copy file (`shutil.copy2`) or directory tree (`shutil.copytree`).
- `mv <src> <dst>` — Move or rename (`Path.rename`).
- `rm <name>` / `delete <name>` — Remove file (`unlink`) or directory (`shutil.rmtree`).
- `truncate <name> <max_size>` — Adjust file size directly (`f.truncate(max_size)`).
- `memmap` — Displays block allocation table (4 KB cluster units) and internal fragmentation summary.
- `reset` — Purges temporary files and restores `storage/` to initial sample state.
- `clear` — Clears terminal log output.

---

## Security: Sandbox Enforcement

All incoming paths pass through `resolve_safe_path()`:
```python
def resolve_safe_path(user_path: str = "") -> Path:
    cleaned = user_path.strip().lstrip("/\\")
    resolved = (STORAGE_DIR / cleaned).resolve()
    storage_root = STORAGE_DIR.resolve()
    if resolved != storage_root and storage_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Access denied: Path is outside the sandbox.")
    return resolved
```
1. Strips leading slashes so `Path / user_input` does not treat input as a filesystem root.
2. Canonicalizes `..`, `.`, and resolves symlinks to their physical disk target via `Path.resolve()`.
3. Verifies that `storage/` is an ancestor of the target.
4. Throws an HTTP 400 error immediately if traversal is detected.

---

## OS Concepts Implemented

| OS Concept | Implementation | Underlying OS Call |
|---|---|---|
| **Hierarchical Directory Tree** | Recursive traversal (`build_tree`) | `opendir`, `readdir` |
| **Directory Navigation** | Breadcrumb navigation and `cd` | Directory lookup |
| **File Deletion** | File removal vs recursive tree removal | `unlink`, `rmdir` |
| **Byte-Level I/O & Seek** | Offset writes and slice reads | `lseek`, `read`, `write` |
| **File Truncation** | Direct size reduction/expansion | `truncate` |
| **Cluster Allocation** | Calculating 4 KB units (`(size + 4095) // 4096`) | File system block sizing |
| **Internal Fragmentation** | Slack space = `allocated_bytes - size` | Cluster tail slack |
| **Metadata Extraction** | File attributes and timestamps | `stat` / `fstat` |
| **Protection & Modes** | Read-only flag on Windows, octal permissions | `st_mode` bitmask |

---

## Tech Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, standard library (`os`, `pathlib`, `shutil`, `datetime`).
- **Frontend:** Single `index.html` with vanilla HTML5, CSS3, and ES6 JavaScript (`fetch` API). No external CDNs, npm packages, or build dependencies.
