# mmbc/telemetry/influx_logger.py

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone



class InfluxLogger:
    _instance = None
    @classmethod
    def create_logger(cls, url, token, org, bucket):
        """Create the singleton instance. Only call once at startup."""
        if cls._instance is not None:
            raise RuntimeError("InfluxLogger already created")
        cls._instance = cls(url, token, org, bucket)

    @classmethod
    def get_logger(cls):
        """Get the existing singleton instance."""
        if cls._instance is None:
            raise RuntimeError("InfluxLogger not yet created. Call InfluxLogger.create(...) first.")
        return cls._instance
    
    def __init__(self, url, token, org, bucket):
        if url:

            self.client = InfluxDBClient(url=url, token=token, org=org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.bucket = bucket
            self.org = org

    def log_battery_stats(self, battery_id, power_out=None, power_in=None, soc=None, extra_fields=None):
        if not self.client:
            return
        point = Point("battery_stats") \
            .tag("battery_id", battery_id) \
            .time(datetime.now(timezone.utc))

        if power_out is not None:
            point.field("power_out", power_out)
        if power_in is not None:
            point.field("power_in", power_in)
        if soc is not None:
            point.field("soc", soc)
        if extra_fields:
            for key, value in extra_fields.items():
                point.field(key, value)

        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def close(self):
        self.client.close()
