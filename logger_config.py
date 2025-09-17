import logging
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'pathname', 'process', 'processName', 'relativeCreated',
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info']:
                log_data[key] = value
        
        return json.dumps(log_data)


class ContextFilter(logging.Filter):
    """Add contextual information to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to record"""
        # Add deployment environment
        record.environment = os.getenv('ENVIRONMENT', 'development')
        
        # Add service name
        record.service = 'slackwire'
        
        # Add version (could be from git or package)
        record.version = os.getenv('APP_VERSION', '1.0.0')
        
        return True


def setup_logging(log_level: str = None, log_format: str = 'json') -> None:
    """
    Configure logging for the application
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json' or 'text')
    """
    # Determine log level
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Create file handler for errors
    error_handler = logging.FileHandler('errors.log')
    error_handler.setLevel(logging.ERROR)
    
    # Set formatter based on format type
    if log_format == 'json' and os.getenv('ENVIRONMENT') != 'development':
        # Use JSON format in production
        json_formatter = JSONFormatter()
        console_handler.setFormatter(json_formatter)
        error_handler.setFormatter(json_formatter)
        
        # Add context filter
        context_filter = ContextFilter()
        console_handler.addFilter(context_filter)
        error_handler.addFilter(context_filter)
    else:
        # Use human-readable format for development
        text_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(text_formatter)
        error_handler.setFormatter(text_formatter)
    
    # Configure root logger
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(error_handler)
    
    # Set specific loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('slack').setLevel(logging.INFO)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={log_level}, format={log_format}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with structured logging support
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Add convenience methods for structured logging
    def log_with_context(level: int, message: str, **kwargs):
        """Log with additional context fields"""
        extra = {}
        for key, value in kwargs.items():
            # Ensure values are JSON serializable
            if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                extra[key] = value
            else:
                extra[key] = str(value)
        
        logger.log(level, message, extra=extra)
    
    # Add methods to logger
    logger.info_with_context = lambda msg, **kwargs: log_with_context(logging.INFO, msg, **kwargs)
    logger.error_with_context = lambda msg, **kwargs: log_with_context(logging.ERROR, msg, **kwargs)
    logger.warning_with_context = lambda msg, **kwargs: log_with_context(logging.WARNING, msg, **kwargs)
    
    return logger