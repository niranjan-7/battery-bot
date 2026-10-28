# 🔋 Nothing Phone (1) Smart Battery Monitor & Auto-Charger

An autonomous battery monitoring daemon designed for **Android (Termux)** that keeps your phone battery healthy in the ideal **25% – 80%** range by automatically toggling a smart plug (e.g., Wipro Smart Extension) via **Alexa Routine Webhooks** and sending real-time alerts through **ntfy.sh**.

---

## 🚀 Features

- **Optimal Battery Health Automation**:
  - **Turn ON (< 25%)**: Automatically triggers your smart socket ON when the battery drops below 25%.
  - **Turn OFF (≥ 80%)**: Automatically turns the socket OFF when the battery reaches 80% to preserve lithium-ion battery longevity.
- **Multi-Layer Safety Protections**:
  - **Thermal Cutoff (≥ 42°C)**: Instantly cuts charging power and sends an urgent notification if the battery overheats.
  - **Max Charging Timer (60 min)**: Safety watchdog shuts off the socket if charging exceeds 60 minutes continuously, preventing overcharging if state readings stall.
  - **Emergency Low-Battery Alert (≤ 15%)**: Retries socket activation and sends a high-priority alert if the phone remains unplugged below 15%.
  - **Trigger Cooldown (5 min)**: Prevents webhook flooding while the smart socket relay toggles.
- **Zero-Friction Notifications**: Real-time push notifications delivered to phone/desktop via `ntfy.sh`.
- **Lightweight Daemon**: Designed to run 24/7 under PM2 with minimal CPU and memory footprint (< 35 MB RAM).

---

## 🛠️ Requirements

1. **Android Device**: Tested on Nothing Phone (1).
2. **Termux & Termux:API**:
   ```bash
   pkg update
   pkg install python termux-api nodejs git
   npm install -g pm2
   ```
   *(Ensure the `Termux:API` APK is also installed from F-Droid with battery permissions granted).*
3. **Smart Plug / Socket**: Any Alexa-compatible smart plug or extension.
4. **Alexa Routine Trigger**: Free webhook routine triggers from [Virtual Smart Home](https://www.virtualsmarthome.xyz/url_routine_trigger/) or similar webhook bridges.
5. **ntfy.sh Topic**: Free instant push notification channel.

---

## 📦 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/niranjan-7/battery-bot.git
   cd battery-bot
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the template and fill in your webhook URLs and notification channel:
   ```bash
   cp .env.example .env
   nano .env
   ```

---

## ⚙️ Configuration (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `NTFY_TOPIC` | *Required* | Your unique `ntfy.sh` topic channel name |
| `WEBHOOK_ON_URL` | *Required* | Alexa Routine Webhook GET URL to turn ON charger |
| `WEBHOOK_OFF_URL` | *Required* | Alexa Routine Webhook GET URL to turn OFF charger |
| `LOW_BATTERY_THRESHOLD` | `25` | Battery level (%) to turn socket ON |
| `FULL_BATTERY_THRESHOLD` | `80` | Battery level (%) to turn socket OFF |
| `CHECK_INTERVAL` | `60` | Polling loop interval in seconds |
| `ON_COOLDOWN` | `300` | Cooldown in seconds before repeating ON trigger |
| `MAX_CHARGING_DURATION`| `3600` | Maximum charging time in seconds (safety timer) |
| `THERMAL_CUTOFF_TEMP` | `42.0` | Temperature (°C) that forces immediate shutdown |
| `CRITICAL_BATTERY_THRESHOLD` | `15` | Critical alert trigger level (%) |

> ⚠️ **Security Note**: Never commit or share your `.env` file. It contains your private webhook activation tokens and `ntfy.sh` topic name.

---

## 🔄 Running as a Background Daemon (PM2)

To keep the daemon running 24/7 even after reboots:

1. **Start the process with PM2**:
   ```bash
   pm2 start battery_monitor.py --name battery-alert --interpreter python
   ```

2. **Save the PM2 process list**:
   ```bash
   pm2 save
   ```

3. **Check status and logs**:
   ```bash
   pm2 status battery-alert
   pm2 logs battery-alert --lines 50
   ```

---

## 📊 State Machine & Logic Flow

```text
[Poll Battery Every 60s]
        │
        ├── Temp ≥ 42°C? ───────────────► Trigger WEBHOOK_OFF + Urgent Ntfy (Thermal Cutoff)
        │
        ├── Charging Active?
        │       ├── Level ≥ 80%? ──────► Trigger WEBHOOK_OFF + Ntfy (Target Reached)
        │       └── Time ≥ 60m?  ──────► Trigger WEBHOOK_OFF + Ntfy (Safety Watchdog)
        │
        ├── Unplugged & Level < 25%? ──► Trigger WEBHOOK_ON + Ntfy (Cooldown: 5 min)
        │
        └── Unplugged & Level ≤ 15%? ──► Retry WEBHOOK_ON + Urgent Ntfy (Emergency Fallback)
```

---

## 📄 License

MIT License. Free to use and customize for personal home automation.
