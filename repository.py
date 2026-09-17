import warnings
import pandas as pd

from .db import MySQLDB


class DataRepository:
    """Database access for the device_alarm_data table."""

    def __init__(self):
        self.db = MySQLDB()

    def _read_sql(self, sql, conn, params=None):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pandas only supports SQLAlchemy connectable.*",
                category=UserWarning,
            )
            return pd.read_sql(sql, conn, params=params)

    def load_devices(self, part_mc=None, keyword=None):
        conn = self.db.get_conn()
        sql = """
        SELECT DISTINCT
            DevBH,
            DevMC,
            TypeMC,
            DevType,
            PartMC,
            Address,
            Status
        FROM device_alarm_data
        WHERE 1=1
        """
        params = []

        if part_mc:
            sql += " AND PartMC = %s"
            params.append(part_mc)

        if keyword:
            sql += """
            AND (
                DevBH LIKE %s
                OR DevMC LIKE %s
                OR TypeMC LIKE %s
                OR DevType LIKE %s
                OR PartMC LIKE %s
                OR Address LIKE %s
            )
            """
            like = f"%{keyword}%"
            params.extend([like, like, like, like, like, like])

        df = self._read_sql(sql, conn, params=params)
        conn.close()
        return df

    def load_data(self, start_time=None, end_time=None, dev_list=None):
        conn = self.db.get_conn()
        sql = """
        SELECT
            DevBH,
            CreateDate,
            ua,
            ub,
            uc,
            ia,
            ib,
            ic,
            ta,
            tb,
            tc,
            tn,
            ld,
            yg
        FROM device_alarm_data
        WHERE 1=1
        """
        params = []

        if start_time and end_time:
            sql += " AND CreateDate BETWEEN %s AND %s"
            params.extend([start_time, end_time])

        if dev_list:
            placeholders = ",".join(["%s"] * len(dev_list))
            sql += f" AND DevBH IN ({placeholders})"
            params.extend(dev_list)

        sql += " ORDER BY DevBH, CreateDate"

        df = self._read_sql(sql, conn, params=params)
        conn.close()
        return df
