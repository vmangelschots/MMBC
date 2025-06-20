from core.controller import Controller
from meters.homewizard_p1_meter import HomeWizardP1Meter
from batteries.venus_battery import VenusBattery

if __name__ == "__main__":
    # Real HomeWizard P1 meter
    meter = HomeWizardP1Meter()  # replace with your actual IP

    # One real Venus battery
    batteries = [
        VenusBattery(ip="172.21.0.101", unit_id=1, name="VenusBattery1")  # replace with your battery's IP
    ]

    controller = Controller(meter=meter, batteries=batteries, interval_seconds=3)
    controller.run_forever()
