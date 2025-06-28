from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
import random

# === CONFIGURATION ===
INFLUX_URL = "https://influxdb.olympus.mangelschots.org"
INFLUX_TOKEN = "6ZJi564_2cExFyl-mOGRFr1ucLyhhE1akVWJb1XRA1OeFSCJRj0RBg_6Ixf82yk6FAJAIey6ByiFvF3nAnvhUA=="
ORG = "15574abfe163dc19"
BUCKET = "a00aa5d41d155300"

# === SETUP CLIENT ===
client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=ORG
)

write_api = client.write_api(write_options=SYNCHRONOUS)

# === CREATE POINT ===
point = (
    Point("battery_stats")
    .tag("battery_id", "venus_A")
    .field("power_out", random.uniform(1000, 2500))
    .field("soc", random.uniform(40, 80))
    .time(datetime.utcnow())
)

# === WRITE TO INFLUX ===
write_api.write(bucket=BUCKET, org=ORG, record=point)

print("Logged data to InfluxDB.")

# === CLEANUP ===
client.close()
