"""数据模型定义"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class DeviceStats:
    """设备统计信息"""
    # 设备基本信息
    dev_bh: str = ""
    dev_mc: str = ""
    type_mc: str = ""
    part_mc: str = ""
    address: str = ""
    status: str = ""
    rated_current: float = 63.0

    # 数据统计
    rows: int = 0
    data_days: str = ""

    # 相数（新增）
    phase_type: str = "single"  # 'single' 或 'three'

    # 电气参数
    temp_max: Optional[float] = None
    temp_avg: Optional[float] = None
    temp_latest: Optional[float] = None
    current_max: Optional[float] = None
    current_avg: Optional[float] = None
    voltage_min: Optional[float] = None
    voltage_max: Optional[float] = None
    voltage_avg: Optional[float] = None
    temp_max_time: str = ""
    current_max_time: str = ""
    voltage_min_time: str = ""
    voltage_max_time: str = ""
    high_temp_count: int = 0
    high_current_count: int = 0
    leakage_max: Optional[float] = None
    leakage_avg: Optional[float] = None
    leakage_max_time: str = ""
    high_leakage_count: int = 0

    # 数据质量
    missing_temp_ratio: float = 1.0
    missing_current_ratio: float = 1.0

    # 规则分析结果
    rule_score: int = 0
    rule_level: str = "正常"
    rule_flags: List[str] = field(default_factory=list)

    # Ollama 分析结果
    ollama_level: str = ""
    analysis_source: str = "rule"
    analysis_error: str = ""
    extreme_points: List[Dict[str, Any]] = field(default_factory=list)
    trend_summary: List[Dict[str, Any]] = field(default_factory=list)
    fire_hazard: str = ""
    reason: str = ""
    advice: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "final_level": self.rule_level,
            "ollama_model_level": self.ollama_level,
            "analysis_source": self.analysis_source,
            "analysis_error": self.analysis_error,
            "extreme_points": self.extreme_points,
            "trend_summary": self.trend_summary,
            "DevBH": self.dev_bh,
            "DevMC": self.dev_mc,
            "TypeMC": self.type_mc,
            "PartMC": self.part_mc,
            "Address": self.address,
            "rows": self.rows,
            "phase_type": self.phase_type,  # 新增
            "temp_max": self.temp_max,
            "current_max": self.current_max,
            "voltage_min": self.voltage_min,
            "voltage_max": self.voltage_max,
            "rule_score": self.rule_score,
            "fire_hazard": self.fire_hazard,
            "reason": self.reason,
            "advice": self.advice,
            "rule_flags": "；".join(self.rule_flags),
            "temp_max_time": self.temp_max_time,
            "current_max_time": self.current_max_time,
            "voltage_min_time": self.voltage_min_time,
            "voltage_max_time": self.voltage_max_time,
            "high_temp_count": self.high_temp_count,
            "high_current_count": self.high_current_count,
            "leakage_max": self.leakage_max,
            "leakage_avg": self.leakage_avg,
            "leakage_max_time": self.leakage_max_time,
            "high_leakage_count": self.high_leakage_count,
        }


@dataclass
class AnalysisResult:
    """分析结果"""
    summary: Dict[str, Any]
    rows: List[DeviceStats]
    raw_responses: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "summary": self.summary,
            "rows": [row.to_dict() for row in self.rows],
            "rawResponses": self.raw_responses,
        }