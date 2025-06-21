# MMBC — Multiple Marstek Battery Controller

**MMBC** is a modular, real-time controller for Marstek Venus E batteries with the goal of achieving "nul op de meter" (zero net power on the electricity meter). It reads net power from a HomeWizard P1 smart meter and controls one or more batteries over Modbus TCP. I use a waveshare rs485 to ethpoe adapter (like https://www.amazon.com.be/-/en/Waveshare-Industrial-Rail-Mount-Electrical-Isolation/dp/B0BGBQJH21/ref=sr_1_1?sr=8-1)

> ⚠️ **Early Stage**  
> This project is under active development and currently supports **only one battery**. Support for multiple batteries is planned and partially implemented. This limitation is because my second battery is still on its way.

---

## 🚀 What It Does

- Reads net power from a HomeWizard P1 smart meter
- Controls one or more Venus E batteries via RS485/Modbus TCP
- Tries to keep the grid net power as close to zero as possible

---

## ⚙️ Control Logic (Current Version)

- If the **absolute adjusted power is below 2500W**, only one battery is used:
  - It chooses the **best eligible battery** based on **State of Charge (SoC)**:
    - Lowest SoC → for charging
    - Highest SoC → for discharging
- If the **adjusted power exceeds 2500W**, the load is **split across all eligible batteries**.
- Batteries are only eligible if:
  - Charging: SoC < 100%
  - Discharging: SoC > 11%
- The controller reselects the active battery:
  - Every 5 minutes (configurable)
  - Or if the current battery becomes ineligible

---

## 🔧 Requirements

- Python 3.11+
- Marstek Venus E battery with RS485 over TCP
- P1 smart meter (e.g., HomeWizard) with API access
- Docker (optional but recommended)

---

## 📦 Quick Start (Docker)

```bash
docker build -t mmbc .
docker run --env-file .env --network host --restart unless-stopped mmbc

## 🌟 Roadmap / Wishlist

- [ ] Support for multiple Venus E batteries in live environment
- [ ] MQTT support (e.g., Home Assistant integration)
- [ ] Automatic detection of P1 meter on the local network
- [ ] Configurable control thresholds (min/max SoC, split logic)
- [ ] Live metrics export (Prometheus or web dashboard)

## 📬 Feedback & Contributions

Pull requests, issues, and feature suggestions are very welcome!

Please note:
- This is an early-stage project developed around real hardware in a personal setup.

If you're testing with your own setup, share your feedback — especially around additional meter or battery support, logging formats, or integration needs.