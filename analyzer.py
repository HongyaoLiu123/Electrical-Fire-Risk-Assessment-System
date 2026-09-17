"""核心分析逻辑"""
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from .repository import DataRepository

from .config import (
    CSV_ENCODINGS,
    RISK_THRESHOLDS,
    TEMP_THRESHOLDS,
    VOLTAGE_THRESHOLDS,
    VOLTAGE_COLS,
    CURRENT_COLS,
    TEMP_COLS,
    LEAKAGE_COLS,
    LEAKAGE_THRESHOLDS,
)
from .models import DeviceStats, AnalysisResult
from .utils import (
    safe_float,
    safe_str,
    extract_rated_current,
    get_risk_order,
    safe_divide,
)
from .ollama_client import OllamaClient

class FireRiskAnalyzer:
    """火灾风险分析器"""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        """
        初始化分析器

        Args:
            ollama_client: Ollama 客户端实例
        """
        self.repo = DataRepository()
        self.ollama = ollama_client or OllamaClient()

    def analyze(
            self,
            device_file: str,
            data_files: List[str],
            model: str = "llama3.2:latest",
            use_ollama: bool = True
    ) -> AnalysisResult:

        devices = self._load_device_files(device_file)
        data = self._load_data_files(data_files)

        return self._analyze_dataframe(devices, data, model, use_ollama)

    def analyze_mysql(
            self,
            start_time: str,
            end_time: str,
            part_mc: str = "",
            keyword: str = "",
            model: str = "llama3.2:latest",
            use_ollama: bool = True
    ) -> AnalysisResult:

        devices = self.repo.load_devices(
            part_mc=part_mc,
            keyword=keyword
        )

        if devices.empty:
            raise ValueError("没有查询到设备信息")

        dev_list = devices["DevBH"].dropna().astype(str).tolist()

        data = self.repo.load_data(
            start_time=start_time,
            end_time=end_time,
            dev_list=dev_list
        )

        return self._analyze_dataframe(devices, data, model, use_ollama)

    def _analyze_dataframe(
            self,
            devices: pd.DataFrame,
            data: pd.DataFrame,
            model: str,
            use_ollama: bool
    ) -> AnalysisResult:

        stats_list = self._build_stats(devices, data)

        for stats in stats_list:
            score, flags = self._score_risk(stats)
            stats.rule_score = score
            stats.rule_flags = flags
            stats.rule_level = self._risk_level(score)

        if use_ollama:
            self._call_ollama(stats_list, model)

        self._finalize(stats_list)
        self._sort_results(stats_list)

        summary = self._build_summary(stats_list, model, use_ollama)

        return AnalysisResult(
            summary=summary,
            rows=stats_list,
            raw_responses=[]
        )


    # ============================================================
    # 数据读取
    # ============================================================

    def _read_csv(self, file_path: str) -> pd.DataFrame:
        """
        读取 CSV / Excel 文件

        Args:
            file_path: 文件路径

        Returns:
            DataFrame
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = path.suffix.lower()

        # Excel 文件
        if suffix in [".xlsx", ".xls"]:
            return pd.read_excel(path, dtype=str)

        # CSV 文件
        for encoding in CSV_ENCODINGS:
            try:
                return pd.read_csv(path, dtype=str, encoding=encoding)
            except UnicodeDecodeError:
                continue

        return pd.read_csv(path, dtype=str)

    def _load_device_files(self, file_paths) -> pd.DataFrame:
        """加载多个设备文件并合并"""
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        frames = []

        for file_path in file_paths:
            if not file_path:
                continue

            df = self._read_csv(file_path)
            df.columns = [str(c).strip() for c in df.columns]
            frames.append(df)

        if not frames:
            raise ValueError("没有有效的设备文件")

        return pd.concat(frames, ignore_index=True)

    def _load_data_files(self, file_paths: List[str]) -> pd.DataFrame:
        """
        加载多个数据文件并合并

        Args:
            file_paths: 文件路径列表

        Returns:
            合并后的 DataFrame
        """
        frames = []
        for file_path in file_paths:
            if not file_path:
                continue

            df = self._read_csv(file_path)

            # 先统一去空格、小写
            df.columns = [str(c).strip().lower() for c in df.columns]

            # 再把系统关键字段改回代码里使用的名字
            df = df.rename(columns={
                "devbh": "DevBH",
                "createdate": "CreateDate",
                "happenedtime": "HappenedTime",
                "sendtime": "sendtime",
            })

            df["source_file"] = Path(file_path).name
            frames.append(df)

        if not frames:
            raise ValueError("没有有效的数据文件")

        return pd.concat(frames, ignore_index=True)

    # ============================================================
    # 统计构建
    # ============================================================

    def _build_stats(self, devices: pd.DataFrame, data: pd.DataFrame) -> List[DeviceStats]:
        """
        构建设备统计信息

        Args:
            devices: 设备 DataFrame
            data: 数据 DataFrame

        Returns:
            设备统计列表
        """
        # 转换数值列
        all_num_cols = VOLTAGE_COLS + CURRENT_COLS + TEMP_COLS + LEAKAGE_COLS + ["yg"]
        for col in all_num_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        # 获取设备信息（去重）
        device_cols = ["DevBH", "DevMC", "TypeMC", "DevType", "PartMC", "Address", "Status"]
        available_cols = [c for c in device_cols if c in devices.columns]
        device_info = devices[available_cols].drop_duplicates("DevBH")

        stats_list = []
        for _, dev in device_info.iterrows():
            dev_bh = safe_str(dev.get("DevBH"))
            subset = data[data["DevBH"] == dev_bh]

            # 检测相数
            phase_type = self._detect_phase_from_subset(subset)

            stats = DeviceStats(
                dev_bh=dev_bh,
                dev_mc=safe_str(dev.get("DevMC")),
                type_mc=safe_str(dev.get("TypeMC")),
                part_mc=safe_str(dev.get("PartMC")),
                address=safe_str(dev.get("Address")),
                status=safe_str(dev.get("Status")),
                rated_current=extract_rated_current(
                    safe_str(dev.get("DevType")),
                    safe_str(dev.get("TypeMC"))
                ),
                rows=len(subset),
                data_days=self._get_data_days(subset),
                phase_type=phase_type,  # 新增
            )

            if len(subset) > 0:
                self._extract_params(subset, stats)
                stats.extreme_points = self._detect_extreme_points(subset)
                stats.trend_summary = self._detect_trend_summary(subset)

            stats_list.append(stats)

        return stats_list

    def _get_data_days(self, subset: pd.DataFrame) -> str:
        """获取数据天数"""
        if "source_file" in subset.columns:
            days = sorted(subset["source_file"].dropna().unique().tolist())
            return ",".join(days)
        return ""

    def _extract_params(self, subset: pd.DataFrame, stats: DeviceStats):

        def get_time_value(row_index):
            for time_col in ["CreateDate", "HappenedTime", "sendtime"]:
                if time_col in subset.columns:
                    return safe_str(subset.loc[row_index, time_col])
            return ""

        """
        提取电气参数

        Args:
            subset: 设备数据子集
            stats: 统计对象（会被修改）
        """
        # 温度
        temp_cols = [c for c in TEMP_COLS if c in subset.columns]
        temps = subset[temp_cols].stack().dropna() if temp_cols else pd.Series(dtype=float)

        if len(temps) > 0:
            stats.temp_max = safe_float(temps.max())
            stats.temp_avg = safe_float(temps.mean())
            stats.high_temp_count = int((temps >= TEMP_THRESHOLDS["watch"]).sum())

            max_temp_pos = temps.idxmax()
            if isinstance(max_temp_pos, tuple):
                stats.temp_max_time = get_time_value(max_temp_pos[0])
            else:
                stats.temp_max_time = get_time_value(max_temp_pos)

        # 电流
        current_cols = [c for c in CURRENT_COLS if c in subset.columns]
        currents = subset[current_cols].stack().dropna() if current_cols else pd.Series(dtype=float)

        if len(currents) > 0:
            stats.current_max = safe_float(currents.max())
            stats.current_avg = safe_float(currents.mean())

            rating = stats.rated_current or 63.0
            stats.high_current_count = int((currents >= rating * 0.8).sum())

            max_current_pos = currents.idxmax()
            if isinstance(max_current_pos, tuple):
                stats.current_max_time = get_time_value(max_current_pos[0])
            else:
                stats.current_max_time = get_time_value(max_current_pos)

        # 电压
        voltage_cols = [c for c in VOLTAGE_COLS if c in subset.columns]
        voltages = subset[voltage_cols].stack().dropna() if voltage_cols else pd.Series(dtype=float)

        if len(voltages) > 0:
            stats.voltage_min = safe_float(voltages.min())
            stats.voltage_max = safe_float(voltages.max())
            stats.voltage_avg = safe_float(voltages.mean())

            min_voltage_pos = voltages.idxmin()
            max_voltage_pos = voltages.idxmax()

            if isinstance(min_voltage_pos, tuple):
                stats.voltage_min_time = get_time_value(min_voltage_pos[0])
            else:
                stats.voltage_min_time = get_time_value(min_voltage_pos)

            if isinstance(max_voltage_pos, tuple):
                stats.voltage_max_time = get_time_value(max_voltage_pos[0])
            else:
                stats.voltage_max_time = get_time_value(max_voltage_pos)

        # 剩余电流
        leakage_cols = [c for c in LEAKAGE_COLS if c in subset.columns]
        leakages = subset[leakage_cols].stack().dropna() if leakage_cols else pd.Series(dtype=float)

        if len(leakages) > 0:
            stats.leakage_max = safe_float(leakages.max())
            stats.leakage_avg = safe_float(leakages.mean())
            stats.high_leakage_count = int(
                (leakages >= LEAKAGE_THRESHOLDS["danger"]).sum()
            )

            max_leakage_pos = leakages.idxmax()

            if isinstance(max_leakage_pos, tuple):
                stats.leakage_max_time = get_time_value(max_leakage_pos[0])
            else:
                stats.leakage_max_time = get_time_value(max_leakage_pos)

        # 数据缺失率
        if temp_cols:
            stats.missing_temp_ratio = round(
                float(subset[temp_cols].isna().all(axis=1).mean()), 3
            )
        if current_cols:
            stats.missing_current_ratio = round(
                float(subset[current_cols].isna().all(axis=1).mean()), 3
            )

    # ============================================================
    # 相数检测
    # ============================================================



    def _detect_trend_summary(self, subset: pd.DataFrame) -> List[Dict[str, Any]]:
        """Build compact trend summaries for AI analysis."""
        if subset.empty:
            return []

        def get_time_value(row_index):
            for time_col in ["CreateDate", "HappenedTime", "sendtime"]:
                if time_col in subset.columns:
                    return safe_str(subset.loc[row_index, time_col])
            return ""

        groups = [
            ("temperature", TEMP_COLS, "温度", "℃"),
            ("current", CURRENT_COLS, "电流", "A"),
            ("voltage", VOLTAGE_COLS, "电压", "V"),
            ("leakage", LEAKAGE_COLS, "剩余电流", "mA"),
        ]
        summaries: List[Dict[str, Any]] = []

        for metric_type, cols, label, unit in groups:
            for col in [c for c in cols if c in subset.columns]:
                series = pd.to_numeric(subset[col], errors="coerce").dropna()
                if len(series) < 3:
                    continue

                first = float(series.iloc[0])
                last = float(series.iloc[-1])
                max_value = float(series.max())
                min_value = float(series.min())
                avg_value = float(series.mean())
                change = last - first
                change_ratio = safe_divide(change, abs(first), 0.0) * 100
                diffs = series.diff().dropna()
                abs_diffs = diffs.abs()
                max_step = float(abs_diffs.max()) if len(abs_diffs) else 0.0
                max_step_index = abs_diffs.idxmax() if len(abs_diffs) else series.index[-1]
                volatility = safe_divide(float(series.std(ddof=0) or 0), abs(avg_value), 0.0) * 100

                if abs(change_ratio) >= 8 or abs(change) >= max(1.0, abs(avg_value) * 0.08):
                    direction = "rising" if change > 0 else "falling"
                elif volatility >= 6 or max_step >= max(1.0, abs(avg_value) * 0.12):
                    direction = "fluctuating"
                else:
                    direction = "stable"

                concern = "normal"
                if metric_type == "temperature" and (max_value >= 60 or direction == "rising" and last >= 45):
                    concern = "danger"
                elif metric_type == "leakage" and (max_value >= 300 or direction == "rising" and last >= 200):
                    concern = "danger"
                elif metric_type == "current" and (direction == "rising" or max_step >= max(5.0, abs(avg_value) * 0.2)):
                    concern = "watch"
                elif metric_type == "voltage" and (min_value < 187 or max_value > 253 or volatility >= 4):
                    concern = "watch"
                elif direction in ("rising", "falling", "fluctuating"):
                    concern = "watch"

                summaries.append({
                    "type": metric_type,
                    "name": f"{col.upper()} {label}",
                    "unit": unit,
                    "start_time": get_time_value(series.index[0]),
                    "end_time": get_time_value(series.index[-1]),
                    "start_value": round(first, 3),
                    "end_value": round(last, 3),
                    "change": round(change, 3),
                    "change_ratio": round(change_ratio, 2),
                    "direction": direction,
                    "volatility": round(volatility, 2),
                    "max_step": round(max_step, 3),
                    "max_step_time": get_time_value(max_step_index),
                    "max_value": round(max_value, 3),
                    "min_value": round(min_value, 3),
                    "concern": concern,
                })

        summaries.sort(key=lambda item: {"danger": 0, "watch": 1, "normal": 2}.get(item["concern"], 3))
        return summaries[:12]

    def _detect_extreme_points(self, subset: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect suspicious isolated extreme points for AI review."""
        if subset.empty:
            return []

        def get_time_value(row_index):
            for time_col in ["CreateDate", "HappenedTime", "sendtime"]:
                if time_col in subset.columns:
                    return safe_str(subset.loc[row_index, time_col])
            return ""

        groups = [
            ("temperature", TEMP_COLS, "温度", "℃", 8.0),
            ("current", CURRENT_COLS, "电流", "A", 5.0),
            ("voltage", VOLTAGE_COLS, "电压", "V", 12.0),
            ("leakage", LEAKAGE_COLS, "剩余电流", "mA", 60.0),
        ]
        points: List[Dict[str, Any]] = []

        for metric_type, cols, label, unit, min_delta in groups:
            for col in [c for c in cols if c in subset.columns]:
                series = pd.to_numeric(subset[col], errors="coerce").dropna()
                if len(series) < 5:
                    continue

                median = float(series.median())
                deviation = (series - median).abs()
                mad = float(deviation.median())
                std = float(series.std(ddof=0) or 0)
                scale = 1.4826 * mad if mad > 0 else std
                if not scale or scale <= 0:
                    continue

                for row_index, value in series.items():
                    value = float(value)
                    delta = abs(value - median)
                    robust_z = delta / scale

                    if robust_z < 6 or delta < min_delta:
                        continue

                    position = subset.index.get_loc(row_index)
                    neighbor_values = []
                    for neighbor_pos in (position - 1, position + 1):
                        if 0 <= neighbor_pos < len(subset):
                            neighbor_value = pd.to_numeric(
                                pd.Series([subset.iloc[neighbor_pos].get(col)]),
                                errors="coerce"
                            ).iloc[0]
                            if pd.notna(neighbor_value):
                                neighbor_values.append(float(neighbor_value))

                    neighbor_delta = None
                    if neighbor_values:
                        neighbor_avg = sum(neighbor_values) / len(neighbor_values)
                        neighbor_delta = abs(value - neighbor_avg)

                    points.append({
                        "type": metric_type,
                        "name": f"{col.upper()} {label}",
                        "time": get_time_value(row_index),
                        "value": round(value, 3),
                        "unit": unit,
                        "median": round(median, 3),
                        "delta_from_median": round(delta, 3),
                        "neighbor_delta": round(neighbor_delta, 3) if neighbor_delta is not None else None,
                        "severity": round(robust_z, 2),
                        "reason": "该采样点与同类历史中位数偏离明显，疑似孤立极端点或瞬时异常。",
                    })

        points.sort(key=lambda item: item["severity"], reverse=True)
        return points[:8]

    def _detect_phase_from_subset(self, subset: pd.DataFrame) -> str:
        """
        从数据子集中检测设备相数

        Args:
            subset: 设备数据子集

        Returns:
            'single' 或 'three'
        """
        if len(subset) == 0:
            return 'single'

        has_b_phase = False
        has_c_phase = False

        # 检查温度列 (tb, tc)
        for col in ['tb', 'tc']:
            if col in subset.columns and subset[col].notna().any():
                if col == 'tb':
                    has_b_phase = True
                else:
                    has_c_phase = True

        # 检查电流列 (ib, ic)
        for col in ['ib', 'ic']:
            if col in subset.columns and subset[col].notna().any():
                if col == 'ib':
                    has_b_phase = True
                else:
                    has_c_phase = True

        # 检查电压列 (ub, uc)
        for col in ['ub', 'uc']:
            if col in subset.columns and subset[col].notna().any():
                if col == 'ub':
                    has_b_phase = True
                else:
                    has_c_phase = True

        return 'three' if (has_b_phase or has_c_phase) else 'single'

    def _detect_phase_from_timeline(self, data: List[Dict[str, Any]]) -> str:
        """
        从时序数据中检测设备相数

        Args:
            data: 时序数据列表

        Returns:
            'single' 或 'three'
        """
        temp_names = [d['name'] for d in data if d['type'] == 'temperature']
        current_names = [d['name'] for d in data if d['type'] == 'current']
        voltage_names = [d['name'] for d in data if d['type'] == 'voltage']

        all_names = temp_names + current_names + voltage_names

        # 检查是否有 B 相或 C 相数据
        has_b_or_c = any(
            'TB' in name or 'TC' in name or
            'IB' in name or 'IC' in name or
            'UB' in name or 'UC' in name
            for name in all_names
        )

        return 'three' if has_b_or_c else 'single'

    # ============================================================
    # 风险评分
    # ============================================================

    def _score_risk(self, stats: DeviceStats) -> Tuple[int, List[str]]:
        """
        计算风险分数和标志

        Args:
            stats: 设备统计信息

        Returns:
            (分数, 标志列表)
        """
        score = 0
        flags = []

        # --- 温度评分 ---
        if stats.temp_max is not None:
            if stats.temp_max >= TEMP_THRESHOLDS["critical"]:
                score += 45
                flags.append(f"最高温度{stats.temp_max}℃，达到严重过热区间")
            elif stats.temp_max >= TEMP_THRESHOLDS["high"]:
                score += 35
                flags.append(f"最高温度{stats.temp_max}℃，存在较高过热风险")
            elif stats.temp_max >= TEMP_THRESHOLDS["warning"]:
                score += 22
                flags.append(f"最高温度{stats.temp_max}℃，温升偏高")
            elif stats.temp_max >= TEMP_THRESHOLDS["watch"]:
                score += 10
                flags.append(f"最高温度{stats.temp_max}℃，需关注温升")
        else:
            score += 8
            flags.append("缺少温度数据，无法排除接点发热隐患")

        # 最近温度仍处于高位
        if (stats.temp_latest is not None and
                stats.temp_max is not None and
                stats.temp_latest >= TEMP_THRESHOLDS["watch"] and
                stats.temp_latest >= stats.temp_max - 2):
            score += 8
            flags.append("最近温度仍处于高位")

        # --- 电流评分 ---
        if stats.current_max is not None:
            rating = stats.rated_current or 63.0
            load_ratio = safe_divide(stats.current_max, rating)
            avg_ratio = safe_divide(stats.current_avg or 0, rating)

            if load_ratio >= 1.0:
                score += 40
                flags.append(f"最大电流{stats.current_max}A，超过估算额定电流{rating}A")
            elif load_ratio >= 0.9:
                score += 30
                flags.append(f"最大电流{stats.current_max}A，接近额定电流{rating}A")
            elif load_ratio >= 0.8 or avg_ratio >= 0.7:
                score += 15
                flags.append("负载率偏高，长时间运行可能加剧发热")
        elif stats.missing_current_ratio > 0.5:
            score += 5
            flags.append("电流数据缺失较多")

        # --- 电压评分 ---
        if stats.voltage_min is not None and stats.voltage_min < VOLTAGE_THRESHOLDS["min"]:
            score += 18
            flags.append(f"最低电压{stats.voltage_min}V，低压异常")

        if stats.voltage_max is not None and stats.voltage_max > VOLTAGE_THRESHOLDS["max"]:
            score += 18
            flags.append(f"最高电压{stats.voltage_max}V，过压异常")

        if (stats.voltage_min is not None and
                stats.voltage_max is not None and
                stats.voltage_max - stats.voltage_min > VOLTAGE_THRESHOLDS["max_fluctuation"]):
            score += 8
            flags.append("电压波动较大")

        # --- 剩余电流 ---
        if stats.leakage_max is not None:

            if stats.leakage_max > 300:
                score += 45
                flags.append(
                    f"剩余电流达到{stats.leakage_max}mA，超过300mA，存在火灾风险"
                )

            elif stats.leakage_max > 200:
                score += 20
                flags.append(
                    f"剩余电流达到{stats.leakage_max}mA，接近火灾风险"
                )

        if stats.extreme_points:
            score += min(18, 6 + len(stats.extreme_points) * 3)
            first = stats.extreme_points[0]
            flags.append(
                f"检测到{len(stats.extreme_points)}个疑似极端数据点，最高严重度点为{first.get('name')} "
                f"{first.get('value')}{first.get('unit')}，出现于{first.get('time')}"
            )

        dangerous_trends = [item for item in stats.trend_summary if item.get("concern") == "danger"]
        watch_trends = [item for item in stats.trend_summary if item.get("concern") == "watch"]
        if dangerous_trends:
            score += min(20, 8 + len(dangerous_trends) * 4)
            first = dangerous_trends[0]
            flags.append(
                f"检测到危险变化趋势：{first.get('name')}呈{first.get('direction')}趋势，"
                f"从{first.get('start_value')}{first.get('unit')}变化到{first.get('end_value')}{first.get('unit')}"
            )
        elif watch_trends:
            score += min(10, 4 + len(watch_trends) * 2)
            first = watch_trends[0]
            flags.append(
                f"检测到需关注变化趋势：{first.get('name')}呈{first.get('direction')}趋势或波动加大"
            )

        # --- 数据质量评分 ---
        if stats.rows < 3:
            score += 6
            flags.append("样本数量偏少，建议继续观测")

        if stats.missing_temp_ratio > 0.5:
            score += 6
            flags.append("温度缺失比例较高")


        # 没有异常
        if not flags:
            flags.append("本次采集数据中电气参数未见明显越限")

        return min(score, 100), flags

    def _risk_level(self, score: int) -> str:
        """
        根据分数确定风险等级

        Args:
            score: 风险分数

        Returns:
            风险等级
        """
        if score >= RISK_THRESHOLDS["high"]:
            return "高"
        if score >= RISK_THRESHOLDS["medium"]:
            return "中"
        if score >= RISK_THRESHOLDS["low"]:
            return "低"
        return "正常"

    # ============================================================
    # Ollama 调用
    # ============================================================

    def _call_ollama(self, stats_list: List[DeviceStats], model: str):
        """
        调用 Ollama 生成建议

        Args:
            stats_list: 设备统计列表（会被修改）
            model: 模型名称
        """
        # 对所有查询到的设备调用 AI；规则结果作为证据和兜底。
        target_stats = stats_list

        for stats in target_stats:
            stats.analysis_source = "ollama_failed"
            stats.analysis_error = "Ollama 未返回有效研判，已使用规则兜底。"
            try:
                result = self.ollama.generate(stats, model)
                if not result:
                    continue

                if result.get("risk_level") in ("高", "中", "低", "正常"):
                    stats.ollama_level = result.get("risk_level", "")
                danger_source = result.get("danger_source", "")
                if danger_source and result.get("fire_hazard"):
                    stats.fire_hazard = f"{result.get('fire_hazard')}（危险源：{danger_source}）"
                else:
                    stats.fire_hazard = result.get("fire_hazard", stats.fire_hazard)
                stats.reason = result.get("reason", stats.reason)
                stats.advice = result.get("advice", stats.advice)
                stats.analysis_source = "ollama"
                stats.analysis_error = ""
            except Exception as exc:
                stats.analysis_error = f"Ollama 调用失败：{exc}"

    # ============================================================
    # 结果处理
    # ============================================================

    def _finalize(self, stats_list: List[DeviceStats]):
        """
        生成最终结果

        Args:
            stats_list: 设备统计列表（会被修改）
        """
        for stats in stats_list:
            level = stats.rule_level
            flags = stats.rule_flags

            # 生成回退建议
            hazard, advice = self._fallback_advice(level, flags)

            stats.fire_hazard = stats.fire_hazard or hazard
            stats.advice = stats.advice or advice
            stats.reason = stats.reason or "；".join(flags[:4])

    def _fallback_advice(self, level: str, flags: List[str]) -> Tuple[str, str]:
        """
        生成回退建议

        Args:
            level: 风险等级
            flags: 风险标志列表

        Returns:
            (隐患描述, 建议)
        """
        if level == "高":
            hazard = "存在火灾隐患"
            advice = "建议立即安排现场复核，检查断路器端子、接线压接、负载分配和散热环境，必要时停用相关回路并整改。"
        elif level == "中":
            hazard = "存在火灾隐患"
            advice = "建议尽快巡检接线端子、负载情况和周边可燃物，连续监测温度与电流变化，确认是否需要分路或更换器件。"
        elif level == "低":
            hazard = "需关注"
            advice = "建议纳入重点观察，保持配电箱通风清洁，复查端子紧固情况，并设置温度、电流预警阈值。"
        else:
            hazard = "暂未发现明显火灾隐患"
            advice = "建议保持日常巡检和周期性紧固检查，继续采集温度、电流、电压数据。"

        return hazard, f"{advice} 主要依据：{'；'.join(flags[:4])}"

    def _sort_results(self, stats_list: List[DeviceStats]):
        """
        排序结果

        Args:
            stats_list: 设备统计列表（会被修改）
        """
        stats_list.sort(key=lambda x: (
            get_risk_order(x.rule_level),
            -x.rule_score,
            x.dev_bh
        ))

    def _build_summary(self, stats_list: List[DeviceStats], model: str, use_ollama: bool) -> Dict[str, Any]:
        """
        构建摘要信息

        Args:
            stats_list: 设备统计列表
            model: 模型名称
            use_ollama: 是否使用了 Ollama

        Returns:
            摘要字典
        """
        counts = {"高": 0, "中": 0, "低": 0, "正常": 0}
        for stats in stats_list:
            counts[stats.rule_level] = counts.get(stats.rule_level, 0) + 1

        return {
            "deviceCount": len(stats_list),
            "matchedCount": sum(1 for s in stats_list if s.rows > 0),
            "unmatchedCount": sum(1 for s in stats_list if s.rows == 0),
            "counts": counts,
            "model": model,
            "useOllama": use_ollama,
        }

    def get_device_timeline_mysql(
            self,
            dev_bh: str,
            start_time: str = None,
            end_time: str = None
    ) -> Dict[str, Any]:
        """从 MySQL 获取单个设备的时序数据用于图表展示"""

        devices = self.repo.load_devices()

        data = self.repo.load_data(
            start_time=start_time,
            end_time=end_time,
            dev_list=[dev_bh]
        )

        if data.empty:
            return {
                "dev_bh": dev_bh,
                "has_data": False,
                "message": "该设备没有数据"
            }

        all_num_cols = (
                VOLTAGE_COLS +
                CURRENT_COLS +
                TEMP_COLS +
                LEAKAGE_COLS +
                ["yg"]
        )

        for col in all_num_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        dev_data = data[data["DevBH"].astype(str) == str(dev_bh)].copy()

        if dev_data.empty:
            return {
                "dev_bh": dev_bh,
                "has_data": False,
                "message": "该设备没有数据"
            }

        dev_info = {}
        if "DevBH" in devices.columns:
            matched = devices[devices["DevBH"].astype(str) == str(dev_bh)]
            if not matched.empty:
                dev_info = matched.iloc[0]

        time_col = None
        for col in ["CreateDate", "HappenedTime", "sendtime", "collect_time"]:
            if col in dev_data.columns:
                time_col = col
                break

        if time_col:
            dev_data = dev_data.sort_values(by=[time_col]).reset_index(drop=True)
            time_labels = dev_data[time_col].astype(str).tolist()
        else:
            dev_data = dev_data.reset_index(drop=True)
            time_labels = [str(i + 1) for i in range(len(dev_data))]

        timeline = []
        total_energy = None

        def add_series(cols, name_suffix, series_type):
            for col in cols:
                if col not in dev_data.columns:
                    continue

                series = pd.to_numeric(dev_data[col], errors="coerce")
                valid = series.dropna()

                if valid.empty:
                    continue

                valid_indices = valid.index.tolist()
                valid_times = [
                    time_labels[i] for i in valid_indices
                    if i < len(time_labels)
                ]

                values = valid.tolist()

                if len(valid_times) != len(values):
                    valid_times = [str(i + 1) for i in range(len(values))]

                timeline.append({
                    "name": col.upper() + name_suffix,
                    "type": series_type,
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values))
                })

        add_series(TEMP_COLS, " 温度", "temperature")
        add_series(CURRENT_COLS, " 电流", "current")
        add_series(VOLTAGE_COLS, " 电压", "voltage")

        for col in LEAKAGE_COLS:
            if col in dev_data.columns:
                leakage = pd.to_numeric(dev_data[col], errors="coerce").dropna()
                if not leakage.empty:
                    timeline.append({
                        "name": "剩余电流",
                        "type": "leakage",
                        "data": leakage.tolist(),
                        "time_labels": [time_labels[i] for i in leakage.index.tolist()],
                        "count": len(leakage),
                        "max": safe_float(leakage.max()),
                        "min": safe_float(leakage.min()),
                        "avg": safe_float(leakage.mean())
                    })

        if "yg" in dev_data.columns:
            yg_values = pd.to_numeric(dev_data["yg"], errors="coerce").dropna()

            if not yg_values.empty:
                total_energy = safe_float(yg_values.iloc[-1] - yg_values.iloc[0])

                timeline.append({
                    "name": "用电量",
                    "type": "energy",
                    "data": yg_values.tolist(),
                    "time_labels": [time_labels[i] for i in yg_values.index.tolist()],
                    "count": len(yg_values),
                    "max": safe_float(yg_values.max()),
                    "min": safe_float(yg_values.min()),
                    "avg": safe_float(yg_values.mean()),
                    "total": total_energy
                })

        phase_type = self._detect_phase_from_timeline(timeline)

        return {
            "dev_bh": dev_bh,
            "dev_mc": safe_str(dev_info.get("DevMC", "")),
            "part_mc": safe_str(dev_info.get("PartMC", "")),
            "has_data": True,
            "data_count": len(dev_data),
            "phase_type": phase_type,
            "timeline": timeline,
            "raw_data": dev_data.to_dict("records")[:100],
            "total_energy": total_energy
        }



    # ============================================================
    # 设备详情（用于图表展示）
    # ============================================================

    def get_device_timeline(
            self,
            device_file: str,
            data_files: List[str],
            dev_bh: str
    ) -> Dict[str, Any]:
        """获取单个设备的时序数据用于图表展示"""
        # 读取数据
        devices = self._load_device_files(device_file)
        data = self._load_data_files(data_files)

        # 转换数值列
        all_num_cols = (
                VOLTAGE_COLS +
                CURRENT_COLS +
                TEMP_COLS +
                LEAKAGE_COLS +
                ["yg"]
        )
        for col in all_num_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        # 筛选设备
        dev_data = data[data["DevBH"] == dev_bh].copy()

        if len(dev_data) == 0:
            return {
                "dev_bh": dev_bh,
                "has_data": False,
                "message": "该设备没有数据"
            }

        # 获取设备信息
        dev_info = {}
        if len(devices[devices["DevBH"] == dev_bh]) > 0:
            dev_info = devices[devices["DevBH"] == dev_bh].iloc[0]

        # 排序 - 按时间排序
        dev_data = dev_data.sort_values(by=["CreateDate"]).reset_index(drop=True)

        # 提取时间标签（用于横坐标）
        time_labels = []
        if "CreateDate" in dev_data.columns:
            time_labels = dev_data["CreateDate"].tolist()
        elif "HappenedTime" in dev_data.columns:
            time_labels = dev_data["HappenedTime"].tolist()
        elif "sendtime" in dev_data.columns:
            time_labels = dev_data["sendtime"].tolist()
        else:
            # 如果没有时间列，使用索引
            time_labels = [str(i + 1) for i in range(len(dev_data))]

        # 构建时序数据
        timeline = []
        total_energy = None

        # 温度数据
        temp_cols = [c for c in TEMP_COLS if c in dev_data.columns]
        for col in temp_cols:
            values = dev_data[col].dropna().tolist()
            if values:
                # 获取对应的时间标签
                valid_indices = dev_data[col].dropna().index.tolist()
                valid_times = [time_labels[i] for i in valid_indices if i < len(time_labels)]

                # 如果时间标签数量不匹配，使用简化的时间
                if len(valid_times) != len(values):
                    valid_times = [str(i + 1) for i in range(len(values))]

                timeline.append({
                    "name": col.upper() + " 温度",
                    "type": "temperature",
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values))
                })

        # 电流数据
        current_cols = [c for c in CURRENT_COLS if c in dev_data.columns]
        for col in current_cols:
            values = dev_data[col].dropna().tolist()
            if values:
                valid_indices = dev_data[col].dropna().index.tolist()
                valid_times = [time_labels[i] for i in valid_indices if i < len(time_labels)]

                if len(valid_times) != len(values):
                    valid_times = [str(i + 1) for i in range(len(values))]

                timeline.append({
                    "name": col.upper() + " 电流",
                    "type": "current",
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values))
                })

        # 电压数据
        voltage_cols = [c for c in VOLTAGE_COLS if c in dev_data.columns]
        for col in voltage_cols:
            values = dev_data[col].dropna().tolist()
            if values:
                valid_indices = dev_data[col].dropna().index.tolist()
                valid_times = [time_labels[i] for i in valid_indices if i < len(time_labels)]

                if len(valid_times) != len(values):
                    valid_times = [str(i + 1) for i in range(len(values))]

                timeline.append({
                    "name": col.upper() + " 电压",
                    "type": "voltage",
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values))
                })


        #剩余电流数据
        leakage_cols = [c for c in LEAKAGE_COLS if c in dev_data.columns]

        for col in leakage_cols:
            values = dev_data[col].dropna().tolist()

            if values:
                valid_indices = dev_data[col].dropna().index.tolist()
                valid_times = [time_labels[i] for i in valid_indices if i < len(time_labels)]

                if len(valid_times) != len(values):
                    valid_times = [str(i + 1) for i in range(len(values))]

                timeline.append({
                    "name": "剩余电流",
                    "type": "leakage",  # ← 就是在这里
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values))
                })


        # 用电量数据
        # yg 是用电累计
        # 图表每个点显示：当前 yg - 上一条 yg
        # 总用电量显示：当天最晚 yg - 最早 yg
        if "yg" in dev_data.columns:
            yg_values = pd.to_numeric(dev_data["yg"], errors="coerce")

            valid_indices = yg_values.dropna().index.tolist()
            valid_yg = yg_values.dropna()

            if len(valid_yg) > 0:
                total_energy = safe_float(valid_yg.iloc[-1] - valid_yg.iloc[0])

            values = valid_yg.tolist()
            valid_times = [time_labels[i] for i in valid_indices if i < len(time_labels)]

            if len(valid_times) != len(values):
                valid_times = [str(i + 1) for i in range(len(values))]

            if values:
                timeline.append({
                    "name": "用电量",
                    "type": "energy",
                    "data": values,
                    "time_labels": valid_times,
                    "count": len(values),
                    "max": safe_float(max(values)),
                    "min": safe_float(min(values)),
                    "avg": safe_float(sum(values) / len(values)),
                    "total": total_energy
                })


        # 检测相数
        phase_type = self._detect_phase_from_timeline(timeline)

        return {
            "dev_bh": dev_bh,
            "dev_mc": safe_str(dev_info.get("DevMC", "")),
            "part_mc": safe_str(dev_info.get("PartMC", "")),
            "has_data": True,
            "data_count": len(dev_data),
            "phase_type": phase_type,
            "timeline": timeline,
            "raw_data": dev_data.to_dict('records')[:100],
            "total_energy": total_energy
        }