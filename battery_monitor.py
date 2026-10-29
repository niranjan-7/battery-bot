import json
import os
import subprocess
import time
import requests


def load_env(env_path=None):
    """
    Loads key-value pairs from .env into os.environ without overriding
    existing environment variables. Works without third-party dependencies.
    """
    search_paths = []
    if env_path:
        search_paths.append(env_path)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_paths.append(os.path.join(script_dir, ".env"))
        search_paths.append(os.path.join(os.getcwd(), ".env"))

    for path in search_paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if key not in os.environ:
                                os.environ[key] = val
                break
            except Exception as e:
                print(f"Warning: Failed to read .env file at {path}: {e}")


# Initialize environment variables
load_env()

# Webhook & Notification Configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
WEBHOOK_ON_URL = os.getenv("WEBHOOK_ON_URL", "")
WEBHOOK_OFF_URL = os.getenv("WEBHOOK_OFF_URL", "")

# Automation Thresholds & Timing Parameters
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
LOW_BATTERY_THRESHOLD = int(os.getenv("LOW_BATTERY_THRESHOLD", "25"))
FULL_BATTERY_THRESHOLD = int(os.getenv("FULL_BATTERY_THRESHOLD", "80"))
CRITICAL_BATTERY_THRESHOLD = int(os.getenv("CRITICAL_BATTERY_THRESHOLD", "15"))
THERMAL_CUTOFF_TEMP = float(os.getenv("THERMAL_CUTOFF_TEMP", "42.0"))
ON_COOLDOWN = int(os.getenv("ON_COOLDOWN", "300"))
MAX_CHARGING_DURATION = int(os.getenv("MAX_CHARGING_DURATION", "3600"))
CRITICAL_ALERT_INTERVAL = int(os.getenv("CRITICAL_ALERT_INTERVAL", "900"))

# State Tracking
charging_started_at = None
last_on_webhook_time = None
last_critical_alert_time = None


def get_battery_status():
    """Queries Termux battery status API."""
    try:
        result = subprocess.run(
            ["termux-battery-status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error reading battery status: {e}")
        return None


def call_webhook(url, label):
    """Sends HTTP GET request to webhook URL with 1 retry on failure."""
    if not url:
        print(f"[{label}] Webhook skipped: URL not configured.")
        return False

    for attempt in range(1, 3):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                print(f"[{label}] Webhook triggered successfully (HTTP 200)")
                return True
            print(f"[{label}] Webhook attempt {attempt} returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"[{label}] Webhook attempt {attempt} exception: {e}")
        if attempt < 2:
            time.sleep(2)
    return False


def send_ntfy(message, title="Nothing Phone (1) Battery", priority="default", tags=None):
    """Sends notification to ntfy.sh topic."""
    if not NTFY_TOPIC:
        print("Ntfy skipped: NTFY_TOPIC not configured.")
        return

    headers = {
        "Title": title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = tags
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        print(f"Ntfy notification sent [{priority}]: {message}")
    except Exception as e:
        print(f"Error sending ntfy notification: {e}")


def acquire_wake_lock():
    """Acquires Termux CPU wake-lock so the daemon runs continuously when the screen is off."""
    try:
        subprocess.run(["termux-wake-lock"], check=False, timeout=5)
        print("Acquired Termux CPU wake-lock (prevents Android sleep).")
    except Exception as e:
        print(f"Warning: Could not acquire Termux wake-lock: {e}")


def main():
    global charging_started_at, last_on_webhook_time, last_critical_alert_time

    acquire_wake_lock()

    print("Nothing Phone (1) Battery Monitor & Auto-Charging Daemon started.")
    print(f"Polling every {CHECK_INTERVAL}s | ON threshold < {LOW_BATTERY_THRESHOLD}% | OFF threshold >= {FULL_BATTERY_THRESHOLD}%")

    if not NTFY_TOPIC:
        print("Warning: NTFY_TOPIC is not set. Push notifications will be disabled.")
    if not WEBHOOK_ON_URL or not WEBHOOK_OFF_URL:
        print("Warning: Alexa webhook URLs not fully configured.")

    while True:
        status = get_battery_status()

        if status:
            percentage = status.get("percentage", 100)
            plugged = status.get("plugged", "UNPLUGGED")
            temperature = float(status.get("temperature", 0.0))
            is_charging = (plugged != "UNPLUGGED")
            now = time.time()

            timer_display = f"Active ({int((now - charging_started_at)/60)}m)" if charging_started_at else "None"
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Battery: {percentage}% | Status: {plugged} | Temp: {temperature:.1f}°C | "
                f"ChargingTimer: {timer_display}"
            )

            # 1. Thermal Safety Cutoff (>= 42°C)
            if temperature >= THERMAL_CUTOFF_TEMP:
                if is_charging or charging_started_at is not None:
                    print(f"CRITICAL: Temperature {temperature:.1f}°C exceeds {THERMAL_CUTOFF_TEMP}°C! Cutting off power.")
                    call_webhook(WEBHOOK_OFF_URL, "Thermal Cutoff")
                    charging_started_at = None
                    send_ntfy(
                        f"🔥 Thermal Cutoff: Battery temperature reached {temperature:.1f}°C while charging! Switched OFF Wipro charger.",
                        title="High Battery Temperature",
                        priority="urgent",
                        tags="warning,fire",
                    )
                time.sleep(CHECK_INTERVAL)
                continue

            # 2. Sync External Charging State
            if is_charging and charging_started_at is None:
                charging_started_at = now
                print(f"Charger is plugged ({plugged}). Initialized charging_started_at.")

            # 3. Turn OFF Condition (>= 80% OR 60-Minute Timer)
            if is_charging or charging_started_at is not None:
                charge_duration = (now - charging_started_at) if charging_started_at else 0
                hit_full = percentage >= FULL_BATTERY_THRESHOLD
                hit_timer = charge_duration >= MAX_CHARGING_DURATION

                if hit_full or hit_timer:
                    reason = (
                        f"reaching {FULL_BATTERY_THRESHOLD}%"
                        if hit_full
                        else f"hitting 60-minute timer ({int(charge_duration / 60)}m elapsed)"
                    )
                    print(f"Turn OFF condition met: {reason}. Triggering OFF webhook.")
                    call_webhook(WEBHOOK_OFF_URL, "Turn OFF")
                    charging_started_at = None
                    send_ntfy(
                        f"🔋 Battery at {percentage}% ({temperature:.1f}°C). Switched OFF Wipro charger due to {reason}.",
                        title="Charging Complete / Stopped",
                        priority="default",
                        tags="battery,heavy_check_mark",
                    )

            # 4. Turn ON Condition (< 25% and UNPLUGGED)
            if percentage < LOW_BATTERY_THRESHOLD and not is_charging:
                can_trigger_on = (last_on_webhook_time is None) or ((now - last_on_webhook_time) >= ON_COOLDOWN)
                if can_trigger_on:
                    print(f"Battery below {LOW_BATTERY_THRESHOLD}% ({percentage}%). Triggering ON webhook.")
                    if call_webhook(WEBHOOK_ON_URL, "Turn ON"):
                        charging_started_at = now
                        last_on_webhook_time = now
                        send_ntfy(
                            f"⚡ Battery at {percentage}% ({temperature:.1f}°C). Switched ON Wipro charger.",
                            title="Charger Activated",
                            priority="default",
                            tags="zap,battery",
                        )

            # 5. Emergency Fallback Alert (<= 15% and UNPLUGGED)
            if percentage <= CRITICAL_BATTERY_THRESHOLD and not is_charging:
                can_trigger_critical = (
                    last_critical_alert_time is None or (now - last_critical_alert_time) >= CRITICAL_ALERT_INTERVAL
                )
                if can_trigger_critical:
                    print(f"EMERGENCY: Battery at {percentage}% and still UNPLUGGED! Retrying ON webhook.")
                    call_webhook(WEBHOOK_ON_URL, "Emergency Turn ON")
                    last_on_webhook_time = now
                    if charging_started_at is None:
                        charging_started_at = now
                    send_ntfy(
                        f"🚨 CRITICAL: Battery dropped to {percentage}%! Wipro charger failed to turn ON!",
                        title="CRITICAL: Low Battery",
                        priority="urgent",
                        tags="rotating_light,warning",
                    )
                    last_critical_alert_time = now

            # 6. Reset State When Unplugged Normally (>= 25% and UNPLUGGED after ON cooldown)
            if (
                not is_charging
                and percentage >= LOW_BATTERY_THRESHOLD
                and charging_started_at is not None
                and (now - (last_on_webhook_time or 0)) >= ON_COOLDOWN
            ):
                print(f"Phone is unplugged at {percentage}%. Resetting charging_started_at timer.")
                charging_started_at = None

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
