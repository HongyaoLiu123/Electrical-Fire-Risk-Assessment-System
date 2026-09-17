"""Ollama API 客户端"""
import json
from typing import List, Dict, Any, Optional
from urllib import request
from .config import OLLAMA_URL, OLLAMA_TIMEOUT
from .models import DeviceStats
from .utils import parse_json_from_text


class OllamaClient:
    """Ollama API 客户端"""

    def __init__(self, base_url: str = OLLAMA_URL, timeout: int = OLLAMA_TIMEOUT):
        """
        初始化 Ollama 客户端

        Args:
            base_url: Ollama API 地址
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def list_models(self) -> List[Dict[str, Any]]:
        """
        获取可用模型列表

        Returns:
            模型列表，如果请求失败则返回空列表
        """
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except Exception:
            return []

    def is_available(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(self, stats: DeviceStats, model: str) -> Optional[Dict[str, str]]:
        """
        调用 Ollama 生成分析建议

        Args:
            stats: 设备统计信息
            model: 模型名称

        Returns:
            包含 risk_level, fire_hazard, reason, advice 的字典
        """
        prompt = self._build_prompt(stats)

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 8192,
            },
        }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "").strip()
                if not response_text:
                    return None
                return parse_json_from_text(response_text)
        except Exception:
            return None

    def generate_series_analysis(self, payload: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        """Generate AI analysis for one chart series."""
        prompt = self._build_series_analysis_prompt(payload)
        request_payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096,
            },
        }

        body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "").strip()
                if not response_text:
                    return None
                return parse_json_from_text(response_text)
        except Exception:
            return None

    def _build_series_analysis_prompt(self, payload: Dict[str, Any]) -> str:
        """Build prompt for one parameter chart analysis."""
        series_json = json.dumps(payload, ensure_ascii=False, indent=2)
        return f"""你是电气消防安全巡检辅助分析助手。请根据单个设备参数曲线的统计摘要，生成更像人工巡检报告的分析结论。

要求：
1. 只输出 JSON，不要输出 Markdown
2. conclusion_lines 输出 3-5 条，适合放在网页“分析结论”列表中
3. advice 输出 1 段巡检建议，要求具体、可执行
4. 结合阈值、extreme_points、最大值、平均值、异常次数、异常占比和出现时间分析
5. 如果存在 extreme_points，必须判断它更像瞬时冲击、持续异常还是采集噪声，并提醒现场复核
6. 必须结合 trend_summary 判断整体趋势：持续上升、持续下降、周期波动、短时冲击、危险点集中出现等
7. 对危险情况和极端情况要放在结论前两条重点说明，并给出专业指导，不要只写“继续观察”
8. 如果数据正常，也要说明为什么判断为正常，并给出后续关注点
9. 不要夸大风险，这是辅助研判，不替代现场检测

曲线统计数据：
{series_json}

请严格输出如下 JSON：
{{
  "summary": "一句话概括该参数运行情况",
  "conclusion_lines": [
    "结论1",
    "结论2",
    "结论3"
  ],
  "advice": "现场巡检建议"
}}"""

    def _build_prompt(self, stats: DeviceStats) -> str:
        """
        构建提示词

        Args:
            stats: 设备统计信息

        Returns:
            提示词字符串
        """
        return f"""你是电气消防安全巡检助手。请根据本次提供的电参量统计摘要，判断是否存在火灾隐患，并给出简短建议。

要求：
1. 只输出 JSON，不要输出 Markdown 或其他格式
2. risk_level 只能是 "高"、"中"、"低"、"正常" 之一
3. fire_hazard 说明是否存在火灾隐患
4. reason 写 150-250 字，结合温度、电流、电压、剩余电流和规则标志分析
5. advice 写 200-350 字，给出现场巡检重点、可能原因和处理建议
6. 不要只说“继续观察”，要给出可执行检查项
7. 这是辅助研判，不替代现场检测
8. 如果 extreme_points 不为空，必须说明这些极端点可能是真实故障、负载突变或采集噪声，并给出复核建议
9. 必须结合 trend_summary 分析数据变化趋势，对持续上升、持续下降、波动扩大、突变回落等情况给出判断
10. 对危险趋势和极端点要优先分析，并给出专业现场指导：检查部位、可能原因、处置优先级、复测方式
11. fire_hazard 必须说明危险源来自哪里，例如温度、剩余电流、电流、电压、趋势变化或采集异常
12. reason 必须写出危险/极端数据的具体时间、数值、设备位置或区域；如果当前安全，也要根据 trend_summary 判断是否存在隐患苗头

设备与规则摘要：
{{
    "DevBH": "{stats.dev_bh}",
    "DevMC": "{stats.dev_mc}",
    "PartMC": "{stats.part_mc}",
    "Address": "{stats.address}",
    "rows": {stats.rows},
    "temp_max": {stats.temp_max or "null"},
    "temp_avg": {stats.temp_avg or "null"},
    "temp_latest": {stats.temp_latest or "null"},
    "current_max": {stats.current_max or "null"},
    "current_avg": {stats.current_avg or "null"},
    "leakage_max": {stats.leakage_max or "null"},
    "leakage_avg": {stats.leakage_avg or "null"},
    "high_leakage_count": {stats.high_leakage_count},
    "temp_max_time": "{stats.temp_max_time}",
    "current_max_time": "{stats.current_max_time}",
    "voltage_min_time": "{stats.voltage_min_time}",
    "voltage_max_time": "{stats.voltage_max_time}",
    "high_temp_count": {stats.high_temp_count},
    "high_current_count": {stats.high_current_count},
    "voltage_min": {stats.voltage_min or "null"},
    "voltage_max": {stats.voltage_max or "null"},
    "voltage_avg": {stats.voltage_avg or "null"},
    "rule_level": "{stats.rule_level}",
    "rule_flags": {stats.rule_flags},
    "extreme_points": {json.dumps(stats.extreme_points, ensure_ascii=False)},
    "trend_summary": {json.dumps(stats.trend_summary, ensure_ascii=False)}
}}

请按以下格式输出 JSON：
{{
    "risk_level": "高/中/低/正常",
    "fire_hazard": "一句话说明火灾隐患情况，必须包含危险源来自哪个参数或趋势",
    "danger_source": "危险源来源，例如TC温度、剩余电流、IA电流、电压波动、趋势变化或采集异常",
    "reason": "详细原因分析，结合温度、电流、电压、负载率、剩余电流、趋势、极端点、时间和地点",
    "advice": "详细巡检建议，包括检查部位、可能原因、处理优先级和后续监测建议"
}}"""