# File System & File Management

A web-based file manager and terminal running over an isolated sandbox folder (`storage/`). Built as an OS course project to show how real operating system concepts (inode metadata via stat, estimated block allocation, internal fragmentation, path safety, and system calls) map to practical software.

Runs locally on `127.0.0.1:8000`. No build tools, external CSS/JS libraries, or database engines required.

---

## Running the Project

Double-click `run.bat` or run it from the terminal:

```cmd
.\run.bat
```

What `run.bat` does:
1. Cleans up any leftover process listening on port 8000 so the server can bind cleanly.
2. Checks for `uv` (creates `.venv` and runs `uv pip install`) or falls back to standard Python `venv`.
3. Installs the required packages: `fastapi`, `uvicorn`, and `python-multipart`.
4. Starts the backend server and opens `http://127.0.0.1:8000` in the default browser once the port is listening.

Closing the terminal window shuts down the server.

---

## Directory Structure

```
os_project_file_system_and_file_management/
├── main.py        # FastAPI app, API routing, and HTTP endpoints
├── fs.py          # Filesystem logic, safe path resolution, block allocation, tree builder
├── terminal.py    # Command parsing and dispatch for interactive terminal actions
├── index.html     # Single-page interface: sidebar tree, terminal, and file table
├── run.bat        # Bootstrap script (dependency check, port cleanup, launch)
├── storage/       # Sandbox directory where all file operations happen
│   ├── demo.py
│   ├── welcome.txt
│   └── documents/
│       └── project_notes.txt
└── README.md      # Setup and project documentation
```

---

## Features

### GUI File Manager
- Breadcrumb path navigation and one-click `..` navigation to parent folders.
- File and folder creation, file uploads, and downloads.
- Renaming and deletions, with browser confirmation before deleting anything.
- In-browser UTF-8 text file editor with save capability.
- Search bar that recursively scans names inside the sandbox.
- Properties modal showing file size, estimated 4 KB block allocation, slack space (internal fragmentation), timestamps, and permissions.

### Live Directory Tree
- Left-hand side panel showing the nested hierarchy of `storage/`.
- Highlights the current working folder.
- Clicking any directory in the tree navigates directly into it.
- Automatically reloads whenever files or folders are changed.

### Integrated Terminal
A command line right above the file table with quick action buttons:
- `mkdir <name>`: Create a directory
- `cd <path>`: Change directory (`cd ..` moves up, `cd /` returns to root)
- `touch <name>` / `create <name>`: Create an empty file
- `write <name> <text>`: Overwrite file with text
- `write <name> @<offset> <text>`: Write text at a specific byte position (`f.seek(offset)`)
- `cat <name>` / `read <name>`: Read and display file contents
- `read <name> <start> <size>`: Read a byte range from a file
- `cp <src> <dst>`: Copy a file or directory
- `mv <src> <dst>`: Move or rename an item
- `rm <name>` / `delete <name>`: Delete a file or directory
- `truncate <name> <size>`: Cut or expand file size directly via OS truncate
- `memmap`: Print a table of all files, their estimated 4 KB cluster blocks, and slack bytes
- `reset`: Wipe temporary test files and reset `storage/` back to default sample files
- `clear`: Clear the terminal log area

---

## Operating System Concepts & Notes

### 1. Inode Metadata & Permissions (`st_mode`)
- On POSIX Linux systems, permissions are stored directly in the inode across owner, group, and others (`rwxrwxrwx`).
- On Windows (NTFS), file permissions use Access Control Lists (ACLs). When Python queries `os.stat().st_mode` on Windows, only the write permission bit (`0o200`) reflects actual state (the Windows read-only file attribute). Hence, `rw-rw-rw-` vs `r--r--r--` represents whether the file has the read-only flag set.

### 2. Timestamps (`st_ctime`)
- On Windows NTFS, `st_ctime` represents the file **creation time**.
- On Linux POSIX systems, `st_ctime` represents **metadata change time** (ctime), while creation time (birth time) is stored separately as `st_birthtime` where supported.

### 3. Estimated Block Allocation & Slack Space
- Disk controllers and filesystems allocate space in discrete clusters, commonly 4096 bytes (4 KB).
- Our calculations compute physical allocation as `ceil(size / 4096) * 4096` and slack space (internal fragmentation) as `allocated - size`.
- Note: This is an estimate assuming standard 4 KB NTFS/ext4 cluster sizes. On NTFS, very small files (< 1 KB) may be stored resident inside the Master File Table (MFT) record without dedicating an external cluster.

---

## Sandbox Security (`resolve_safe_path`)

All file operations run through one path resolver in `fs.py`:

```python
def resolve_safe_path(user_path: str = "") -> Path:
    cleaned = user_path.strip().lstrip("/\\")
    resolved = (STORAGE_DIR / cleaned).resolve()
    storage_root = STORAGE_DIR.resolve()
    if resolved != storage_root and storage_root not in resolved.parents:
        raise HTTPException(status_code=400, detail="Access denied: Path is outside the sandbox.")
    return resolved
```

How it works:
1. Strips leading slashes so Python's `Path` join does not treat the input as a drive root.
2. Calls `.resolve()` to normalize all `.` and `..` segments and trace symlinks to their actual filesystem target.
3. Checks that the target is inside `storage/` or is `storage/` itself.
4. Throws HTTP 400 if a path attempts to escape the folder.

---

## Operating System Call Mappings

| Feature | Implementation in Code | Underlying OS System Call |
|---|---|---|
| Directory listing | `Path.iterdir()` / `os.scandir()` | `opendir`, `readdir` |
| Directory creation | `Path.mkdir()` | `mkdir` |
| File creation | `Path.touch()` / `open(..., 'wb')` | `open(O_CREAT)` |
| File deletion | `Path.unlink()` | `unlink` |
| Folder deletion | `shutil.rmtree()` | `rmdir` (recursive) |
| Moving / renaming | `Path.rename()` | `rename` |
| Offset write / read | `f.seek(offset)` | `lseek` |
| File truncation | `f.truncate(size)` | `truncate` |
| Metadata lookup | `os.stat()` / `Path.stat()` | `stat` |

---

## Technical Details

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Python standard library (`os`, `pathlib`, `shutil`, `datetime`).
- **Frontend:** Single `index.html` with vanilla HTML, CSS, and JavaScript (`fetch` API).
- **Network:** Bound strictly to `127.0.0.1:8000` (loopback only).
