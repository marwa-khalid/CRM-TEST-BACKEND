# appflow/logger.py
import logging

# Configure root logger to INFO level to reduce verbosity
logging.basicConfig(level=logging.INFO)

# Set specific loggers to reduce DEBUG noise
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("pdf2image").setLevel(logging.WARNING)

# Application logger
logger = logging.getLogger("auth_app")
logger.setLevel(logging.INFO)
