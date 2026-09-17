#!/usr/bin/env python
"""项目启动入口"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from app.main import run_server

if __name__ == "__main__":
    run_server()