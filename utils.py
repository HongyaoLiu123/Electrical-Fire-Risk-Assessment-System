"""通用工具函数"""
import json
import re
from typing import Optional, Any
import pandas as pd


def safe_float(value: Any) -> Optional[float]:
    """
    安全转换为浮点数

    Args:
        value: 任意值

    Returns:
        浮点数或 None
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def safe_str(value: Any, default: str = "") -> str:
    """
    安全转换为字符串

    Args:
        value: 任意值
        default: 默认值

    Returns:
        字符串
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)


def extract_rated_current(dev_type: str, type_mc: str) -> float:
    """
    从设备类型描述中提取额定电流

    Args:
        dev_type: 设备类型
        type_mc: 型号

    Returns:
        额定电流（安培），默认 63A
    """
    text = f"{safe_str(dev_type)} {safe_str(type_mc)}"

    # 匹配 -63A 或 63A 格式
    patterns = [
        r"-(\d{1,3})(?:A|/|$)",
        r"(\d{1,3})A",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))

    return 63.0


def parse_json_from_text(text: str) -> dict:
    """
    从文本中提取并解析 JSON

    Args:
        text: 包含 JSON 的文本

    Returns:
        解析后的字典
    """
    cleaned = text.strip()
    # 移除 Markdown 代码块
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # 提取 JSON 对象
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """安全除法，避免除零错误"""
    if b is None or b == 0:
        return default
    try:
        return a / b
    except (TypeError, ZeroDivisionError):
        return default



def get_risk_order(level: str) -> int:
    """获取风险等级的排序权重"""
    from .config import RISK_ORDER
    return RISK_ORDER.get(level, 9)