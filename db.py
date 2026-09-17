import os
import mysql.connector


class MySQLDB:
    def __init__(self):
        self.config = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", "lhy521016"),
            "database": os.getenv("MYSQL_DATABASE", "device_alarm"),
            "charset": "utf8mb4",
        }

    def get_conn(self):
        return mysql.connector.connect(**self.config)