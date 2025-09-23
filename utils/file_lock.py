"""Thread-safe file locking utilities for JSON operations."""
import json
import fcntl
import os
import time
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class FileLockManager:
    """Manages file locks for thread-safe operations."""
    
    _instance = None
    _lock = threading.Lock()
    _file_locks: Dict[str, threading.Lock] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._file_locks = {}
        return cls._instance
    
    def get_lock(self, filepath: str) -> threading.Lock:
        """Get or create a lock for a specific file."""
        with self._lock:
            if filepath not in self._file_locks:
                self._file_locks[filepath] = threading.Lock()
            return self._file_locks[filepath]

@contextmanager
def atomic_json_file(filepath: str, mode: str = 'r+'):
    """Context manager for atomic JSON file operations with locking."""
    lock_manager = FileLockManager()
    thread_lock = lock_manager.get_lock(filepath)
    
    with thread_lock:  # Thread-level locking
        # Ensure file exists
        Path(filepath).touch(exist_ok=True)
        
        # Open file with OS-level locking
        with open(filepath, mode) as f:
            try:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
                # Read current data
                f.seek(0)
                try:
                    data = json.load(f) if os.path.getsize(filepath) > 0 else {}
                except json.JSONDecodeError:
                    logger.warning(f"Corrupted JSON in {filepath}, starting fresh")
                    data = {}
                
                yield data
                
                # Write back atomically
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def safe_json_read(filepath: str, default: Any = None) -> Any:
    """Safely read JSON file with locking."""
    try:
        with atomic_json_file(filepath, 'r') as data:
            return data
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return default or {}

def safe_json_write(filepath: str, data: Dict[str, Any]) -> bool:
    """Safely write JSON file with locking."""
    try:
        # Create backup
        backup_path = f"{filepath}.bak"
        if os.path.exists(filepath):
            import shutil
            shutil.copy2(filepath, backup_path)
        
        with atomic_json_file(filepath, 'w') as _:
            pass  # Data is written in the context manager
        
        # Write the data using the atomic method
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        return True
    except Exception as e:
        logger.error(f"Error writing {filepath}: {e}")
        # Restore from backup
        if os.path.exists(backup_path):
            import shutil
            shutil.copy2(backup_path, filepath)
        return False