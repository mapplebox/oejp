# Octopus Energy Japan – Home Assistant Integration (OEJP)

An **unofficial Home Assistant custom integration** for **Octopus Energy Japan**, built on top of the official OEJP GraphQL API.

This integration focuses on **electricity consumption, power estimation, and cost tracking**, designed specifically for Japanese accounts and time zones.

---

## Overview

The OEJP integration retrieves half-hourly electricity usage from Octopus Energy Japan and exposes it as Home Assistant sensors.

It is designed to:
- Work reliably with Home Assistant’s async architecture
- Minimize API calls
- Provide clean energy and cost data for dashboards and automations
- Integrate seamlessly with the Home Assistant Energy Dashboard

---

## Features

- 🔐 Authentication via official OEJP GraphQL API
- ⚡ Half-hourly electricity consumption (kWh)
- 🔌 Estimated power usage (W) derived from 30-minute intervals
- 📊 Daily, monthly, and previous month consumption
- 💴 Cost calculation in Japanese Yen (user-defined ¥/kWh)
- 📈 Total-increasing energy sensor for Energy Dashboard & Utility Meter
- ♻️ Automatic token refresh and recovery
- 🇯🇵 Correct handling of Japan Standard Time (Asia/Tokyo)

---

## Available Sensors

### Energy & Power

| Sensor | Description |
|------|------------|
| OEJP Power | Estimated current power usage (W) |
| OEJP Last half hour | Energy used in the last 30-minute interval (kWh) |
| OEJP Today | Energy usage today (kWh) |
| OEJP Yesterday | Energy usage yesterday (kWh) |
| OEJP Month to date | Energy usage for the current month (kWh) |
| OEJP Last month | Energy usage for the previous month (kWh) |

### Cost Sensors

| Sensor | Description |
|------|------------|
| OEJP Cost today | Electricity cost today (¥) |
| OEJP Cost month to date | Electricity cost for the current month (¥) |

### Energy Dashboard

| Sensor | Description |
|------|------------|
| OEJP Energy total | Cumulative energy consumption (kWh, total_increasing) |

This sensor is intended to be used as an **Energy Source** in the Home Assistant Energy Dashboard.

---

## Power Calculation

Power is derived from half-hourly energy readings using:

