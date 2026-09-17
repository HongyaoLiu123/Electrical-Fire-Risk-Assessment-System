import pandas as pd
import mysql.connector


DEVICE_FILE = r"D:\实习文件\C3设备0615.csv"
DATA_FILE = r"D:\实习文件\MDJ-C3设备数据-20241025.csv"
DATA_FILE  = r"D:\实习文件\7月12-14设备数据表.csv"

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "lhy521016",
    "database": "device_alarm",
    "charset": "utf8mb4",
}


def read_csv_file(path):
    for encoding in ["utf-8-sig", "utf-8", "gbk"]:
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue

    raise ValueError(f"无法读取文件编码: {path}")


def clean_value(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    if isinstance(value, str):
        value = value.strip()

        if value == "" or value.upper() == "NULL":
            return None

    return value


def get_first(row, names, default=None):
    for name in names:
        if name in row.index:
            value = clean_value(row.get(name))

            if value is not None:
                return value

    return default


def to_float(value):
    value = clean_value(value)

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_time(value):
    value = clean_value(value)

    if value is None:
        return None

    dt = pd.to_datetime(value, errors="coerce")

    if pd.isna(dt):
        return None

    return dt.to_pydatetime()


def build_device_map(device_df):
    device_map = {}

    for _, row in device_df.iterrows():
        dev_bh = clean_value(row.get("DevBH"))

        if dev_bh is None:
            continue

        dev_bh = str(dev_bh)

        if dev_bh not in device_map:
            device_map[dev_bh] = row

    return device_map


def import_to_device_alarm_data(device_df, data_df):
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()

    device_map = build_device_map(device_df)

    sql = """
    INSERT INTO device_alarm_data
    (
        DevBH,
        DevMC,
        TypeMC,
        DevType,
        PartMC,
        Address,
        Status,
        CreateDate,
        ua, ub, uc,
        ia, ib, ic,
        ta, tb, tc, tn,
        ld,
        yg
    )
    VALUES
    (
        %s, %s, %s, %s, %s, %s, %s,
        %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s,
        %s
    )
    """

    rows = []

    for _, data_row in data_df.iterrows():
        dev_bh = clean_value(data_row.get("DevBH"))

        if dev_bh is None:
            continue

        dev_bh = str(dev_bh)
        device_row = device_map.get(dev_bh)

        if device_row is not None:
            dev_mc = get_first(device_row, ["DevMC", "DeviceName", "ComName"], dev_bh)
            type_mc = get_first(device_row, ["TypeMC", "DWETypeMC", "DevType"], "")
            dev_type = get_first(device_row, ["DevType", "DWEType"], "")
            part_mc = get_first(device_row, ["PartMC", "AreaMC"], "")
            address = get_first(device_row, ["Address", "OtherAreaMC"], "")
            status = get_first(device_row, ["Status", "state"], "")
        else:
            dev_mc = dev_bh
            type_mc = get_first(data_row, ["DevType"], "")
            dev_type = get_first(data_row, ["DevType"], "")
            part_mc = ""
            address = ""
            status = get_first(data_row, ["state"], "")

        create_date = parse_time(get_first(data_row, [
            "CreateDate",
            "HappenedTime",
            "sendtime",
            "collect_time",
            "采集时间",
            "时间",
        ]))

        rows.append((
            dev_bh,
            dev_mc,
            type_mc,
            dev_type,
            part_mc,
            address,
            status,
            create_date,

            to_float(data_row.get("ua")),
            to_float(data_row.get("ub")),
            to_float(data_row.get("uc")),

            to_float(data_row.get("ia")),
            to_float(data_row.get("ib")),
            to_float(data_row.get("ic")),

            to_float(data_row.get("ta")),
            to_float(data_row.get("tb")),
            to_float(data_row.get("tc")),
            to_float(data_row.get("tn")),

            to_float(data_row.get("ld")),
            to_float(data_row.get("yg")),
        ))

    if not rows:
        print("没有可导入的数据，请检查点数据文件是否包含 DevBH")
        cursor.close()
        conn.close()
        return

    cursor.executemany(sql, rows)
    conn.commit()

    cursor.close()
    conn.close()

    print(f"导入完成，共导入 {len(rows)} 条点数据到 device_alarm_data")


if __name__ == "__main__":
    device_df = read_csv_file(DEVICE_FILE)
    data_df = read_csv_file(DATA_FILE)

    print("设备文件列名:")
    print(device_df.columns.tolist())

    print("点数据文件列名:")
    print(data_df.columns.tolist())

    import_to_device_alarm_data(device_df, data_df)