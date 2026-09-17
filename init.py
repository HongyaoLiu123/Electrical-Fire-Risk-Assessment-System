"""电气火灾隐患辅助研判应用"""
from .config import APP_DIR, STATIC_DIR, SERVER_HOST, SERVER_PORT
from .main import run_server

__version__ = "2.0.0"
__all__ = ["run_server", "APP_DIR", "STATIC_DIR", "SERVER_HOST", "SERVER_PORT"]