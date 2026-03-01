import contextvars
import json
import logging
from datetime import datetime

# Global ContextVar for tracing requests across async boundaries
correlation_id_ctx = contextvars.ContextVar("correlation_id", default=None)

class JsonFormatter(logging.Formatter):
    """
    Formats log records as JSON, automatically injecting the current
    ContextVar `correlation_id` into every log line.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get(),
        }
        
        # Inject standard stack traces if an exception is attached
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

def setup_logging():
    """
    Replaces the root logger's default formatter with our structured JSON Formatter.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Safely clear out any pre-existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(stream_handler)
    
    # Optional: Silence overly verbose third-party loggers here
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
