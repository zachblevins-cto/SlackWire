"""Ensure only one instance of the bot runs at a time."""
import os
import sys
import fcntl
import atexit
import signal
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SingleInstance:
    """Ensures only one instance of the application runs."""
    
    def __init__(self, lock_file: str = "/tmp/slackwire.lock"):
        self.lock_file = lock_file
        self.lock_fd = None
        
    def __enter__(self):
        """Acquire exclusive lock."""
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            
            # Register cleanup handlers
            atexit.register(self.cleanup)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            
            logger.info(f"Acquired single instance lock (PID: {os.getpid()})")
            return self
            
        except IOError:
            # Another instance is running
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())
                logger.error(f"Another instance is already running (PID: {pid})")
            except:
                logger.error("Another instance is already running")
            
            sys.exit(1)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock on exit."""
        self.cleanup()
    
    def cleanup(self):
        """Clean up lock file and file descriptor."""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_fd = None
            except:
                pass
        
        try:
            os.unlink(self.lock_file)
            logger.info("Released single instance lock")
        except:
            pass
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.cleanup()
        sys.exit(0)
    
    def is_running(self) -> bool:
        """Check if another instance is running."""
        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())
                
            # Check if process exists
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                # Process doesn't exist, remove stale lock
                os.unlink(self.lock_file)
                return False
                
        except (FileNotFoundError, ValueError):
            return False