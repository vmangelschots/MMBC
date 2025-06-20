from core.controller import Controller
from batteries.fake_battery import FakeBattery
from batteries.venus_battery import VenusBattery
from meters.homewizard_p1_meter import HomeWizardP1Meter

if __name__ == "__main__":
    # Create one fake meter and two fake batteries
    meter = HomeWizardP1Meter()

    batteries = [
        VenusBattery(name="Marstek", ip='172.21.0.101')
    ]

    # Create and start the controller
    controller = Controller(meter=meter, batteries=batteries, interval_seconds=4)
    controller.run_forever()