"""图表统计服务"""
from typing import List, Dict, Any


class ChartService:
    """图表统计服务"""

    @staticmethod
    def detect_phase_type(data: List[Dict[str, Any]]) -> str:
        names = [item.get("name", "") for item in data]

        has_three = any(
            name.startswith(("TB", "TC", "IB", "IC", "UB", "UC"))
            for name in names
        )

        return "three" if has_three else "single"

    @staticmethod
    def generate_summary_stats(data: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats = {}

        for item in data:
            key = item.get("type")

            if not key:
                continue

            if key not in stats:
                stats[key] = []

            stats[key].append({
                "name": item.get("name", ""),
                "max": item.get("max"),
                "min": item.get("min"),
                "avg": item.get("avg"),
                "count": item.get("count", 0),
                "total": item.get("total"),
            })

        phase_type = ChartService.detect_phase_type(data)

        stats["_phase_type"] = phase_type
        stats["_phase_label"] = "三相电" if phase_type == "three" else "单相电"

        return stats