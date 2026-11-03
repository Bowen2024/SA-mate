"""Shared project-state lock and durable file helpers.

The lock coordinates fusion tools that update project metadata or artifacts.
It does not replace operating-system sandboxing and does not authorize callers.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import tempfile


LOCK_NAME = ".project-state.lock"
JOURNAL_NAME = ".project-state-transaction.json"
JOURNAL_LIMIT = 8 * 1024 * 1024


def _write_all(descriptor, raw):
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise OSError("文件写入未取得进展")
        offset += written


def _directory_fsync(directory):
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def exclusive_lock(path, message, payload=None):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ValueError(message) from error
    try:
        raw = (json.dumps(payload or {}, ensure_ascii=False) + "\n").encode("utf-8")
        _write_all(descriptor, raw)
        os.fsync(descriptor)
        locked = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        yield path
    finally:
        try:
            current = os.lstat(path)
        except FileNotFoundError:
            raise RuntimeError(f"写入锁在操作期间丢失：{path.name}")
        if not stat.S_ISREG(current.st_mode) or (
            current.st_dev, current.st_ino
        ) != (locked.st_dev, locked.st_ino):
            raise RuntimeError(f"写入锁在操作期间被替换：{path.name}")
        path.unlink()


def project_state_lock(root, operation):
    return exclusive_lock(
        root / LOCK_NAME,
        "项目状态写入锁已存在；先核对在途操作，不自动删除锁",
        {"operation": operation, "pid": os.getpid()},
    )


def atomic_replace(path, raw):
    if path.is_symlink():
        raise ValueError(f"不允许替换软链：{path.name}")
    existing_mode = None
    if path.exists():
        existing = path.stat()
        if not path.is_file() or existing.st_nlink != 1:
            raise ValueError(f"目标不是独立普通文件：{path.name}")
        existing_mode = stat.S_IMODE(existing.st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            if existing_mode is not None:
                os.fchmod(stream.fileno(), existing_mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _directory_fsync(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_journal(root, value):
    path = root / JOURNAL_NAME
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(raw) > JOURNAL_LIMIT:
        raise ValueError("恢复事务超过 8 MiB 限制")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ValueError("存在未完成的成果索引事务；先由 Main 恢复，不开始新写入") from error
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _directory_fsync(root)
    return path


def read_journal(root):
    path = root / JOURNAL_NAME
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("恢复事务缺失或不是独立普通文件")
    with path.open("rb") as stream:
        raw = stream.read(JOURNAL_LIMIT + 1)
    if len(raw) > JOURNAL_LIMIT:
        raise ValueError("恢复事务超过 8 MiB 限制")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("恢复事务不是有效 UTF-8 JSON") from error
    return path, value


def remove_journal(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("不删除异常恢复事务文件")
    parent = path.parent
    path.unlink()
    _directory_fsync(parent)
