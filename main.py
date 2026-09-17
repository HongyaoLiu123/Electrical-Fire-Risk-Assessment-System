"""HTTP server entry point for the database-backed alarm analysis app."""
import csv
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, unquote, urlparse

from .analyzer import FireRiskAnalyzer
from .config import APP_DIR, SERVER_HOST, SERVER_PORT, STATIC_DIR
from .models import AnalysisResult
from .ollama_client import OllamaClient


class Handler(SimpleHTTPRequestHandler):
    """Serve static files and database analysis APIs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args):
        pass

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json({"ok": True, "status": "running"})
            return

        if path == "/api/tags":
            self._handle_tags()
            return

        if path == "/api/mysql/analyze":
            self._handle_mysql_analyze(parsed.query)
            return

        if path.startswith("/api/mysql/chart/"):
            self._handle_mysql_chart(path, parsed.query)
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/ai/series-analysis":
            self._handle_series_ai_analysis()
            return

        self._send_json({"ok": False, "error": "接口不存在"}, status=404)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}

    def _handle_series_ai_analysis(self):
        try:
            payload = self._read_json_body()
            model = str(payload.get("model") or "llama3.2:latest").strip()

            if not model:
                self._send_json({"ok": False, "error": "缺少模型名称"}, status=400)
                return

            result = OllamaClient().generate_series_analysis(payload, model)
            if not result:
                self._send_json({"ok": False, "error": "Ollama 未返回有效分析"}, status=503)
                return

            self._send_json({"ok": True, "analysis": result})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json({"ok": False, "error": str(e)}, status=500)

    def _handle_tags(self):
        try:
            client = OllamaClient()
            models = client.list_models()
            self._send_json({
                "ok": True,
                "models": models,
                "available": len(models) > 0,
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=503)

    def _handle_mysql_analyze(self, raw_query: str):
        try:
            query = parse_qs(raw_query)
            start_time = self._query_value(query, "start_time").replace("T", " ")
            end_time = self._query_value(query, "end_time").replace("T", " ")
            part_mc = self._query_value(query, "part_mc")
            keyword = self._query_value(query, "keyword")
            model = self._query_value(query, "model", "llama3.2:latest")
            use_ollama = self._query_value(query, "use_ollama", "false").lower() == "true"

            if not start_time or not end_time:
                self._send_json({"ok": False, "error": "请选择开始时间和结束时间"}, status=400)
                return

            analyzer = FireRiskAnalyzer()
            result = analyzer.analyze_mysql(
                start_time=start_time,
                end_time=end_time,
                part_mc=part_mc,
                keyword=keyword,
                model=model,
                use_ollama=use_ollama,
            )

            self._save_report(result)

            self._send_json({
                "ok": True,
                "summary": result.summary,
                "rows": [row.to_dict() for row in result.rows],
                "source": "mysql",
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json({"ok": False, "error": str(e)}, status=500)

    def _handle_mysql_chart(self, path: str, raw_query: str):
        try:
            dev_bh = unquote(path.split("/api/mysql/chart/", 1)[-1])
            query = parse_qs(raw_query)
            start_time = self._query_value(query, "start_time").replace("T", " ")
            end_time = self._query_value(query, "end_time").replace("T", " ")

            if not dev_bh:
                self._send_json({"ok": False, "error": "缺少设备编号"}, status=400)
                return

            result = FireRiskAnalyzer().get_device_timeline_mysql(
                dev_bh=dev_bh,
                start_time=start_time,
                end_time=end_time,
            )

            if not result.get("has_data"):
                self._send_json({"ok": False, "error": "该设备没有数据"}, status=404)
                return

            from .chart_service import ChartService
            stats = ChartService.generate_summary_stats(result.get("timeline", []))

            self._send_json({
                "ok": True,
                "data": {
                    "dev_bh": dev_bh,
                    "dev_name": result.get("dev_mc", dev_bh),
                    "part_mc": result.get("part_mc", ""),
                    "data_count": result.get("data_count", 0),
                    "phase_type": result.get("phase_type", "single"),
                    "stats": stats,
                    "total_energy": result.get("total_energy"),
                    "timeline": result.get("timeline", []),
                },
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json({"ok": False, "error": str(e)}, status=500)

    @staticmethod
    def _query_value(query: Dict[str, list], name: str, default: str = "") -> str:
        value = query.get(name, [default])[0]
        return value.strip() if isinstance(value, str) else default

    def _save_report(self, result: AnalysisResult):
        out_path = APP_DIR / "last_report.csv"
        fields = [
            "final_level", "ollama_model_level", "DevBH", "DevMC",
            "PartMC", "rows", "phase_type", "temp_max", "current_max",
            "voltage_min", "voltage_max", "rule_score", "leakage_max",
            "fire_hazard", "reason", "advice", "rule_flags",
        ]

        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            for row in result.rows:
                row_dict = row.to_dict()
                writer.writerow({field: row_dict.get(field, "") for field in fields})


def run_server():
    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), Handler)

    print("=" * 55)
    print("  电气火灾隐患辅助研判系统")
    print("=" * 55)
    print(f"  服务地址: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"  静态目录: {STATIC_DIR}")
    print("  数据源: MySQL device_alarm_data")
    print("  按 Ctrl+C 停止服务")
    print("=" * 55)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")


if __name__ == "__main__":
    run_server()
