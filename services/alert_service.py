import time
import logging
import threading
import subprocess
from typing import Dict, Any, List
import telebot
from config import SUPERADMIN_ID
from database.user_repo import get_alert_recipients
from services.ssh_client import run_ssh_multiverse
from services.metrics import IS_WINDOWS

logger = logging.getLogger("server-tele-bot.alert")

# Ambang batas metrik
ALERT_THRESHOLD = 90.0      # Kirim peringatan jika penggunaan >= 90%
RECOVERY_THRESHOLD = 85.0   # Kirim notifikasi pulih jika turun < 85%
ALERT_COOLDOWN = 1800       # Cooldown 30 menit per metrik jika kondisi masih >= 90%

# State tracker untuk mencegah spam/alert flood
_alert_state: Dict[str, Dict[str, Any]] = {
    "galaxy_ram": {"alerted": False, "last_alert_time": 0.0, "val": 0.0},
    "galaxy_disk": {"alerted": False, "last_alert_time": 0.0, "val": 0.0},
    "multiverse_ram": {"alerted": False, "last_alert_time": 0.0, "val": 0.0},
    "multiverse_disk": {"alerted": False, "last_alert_time": 0.0, "val": 0.0},
}


def check_galaxy_usage() -> Dict[str, Any]:
    """Mengambil metrik RAM dan Disk Galaxy secara presisi dalam persentase numerik"""
    if IS_WINDOWS:
        return {
            "ram_pct": 38.0,
            "ram_str": "1.5G / 3.9G (38%)",
            "disk_pct": 32.0,
            "disk_str": "31G / 97G (32%)",
            "online": True
        }
    try:
        # Disk (%)
        disk_raw = subprocess.check_output(
            "df -P / | awk 'NR==2 {gsub(/%/, \"\", $5); print $5}'",
            shell=True, text=True, timeout=4
        ).strip()
        disk_pct = float(disk_raw) if disk_raw else 0.0

        disk_str = subprocess.check_output(
            "df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'",
            shell=True, text=True, timeout=4
        ).strip()

        # RAM (%)
        ram_raw = subprocess.check_output(
            "free -m | awk 'NR==2 {printf \"%.1f\", ($3/$2)*100}'",
            shell=True, text=True, timeout=4
        ).strip()
        ram_pct = float(ram_raw) if ram_raw else 0.0

        ram_str = subprocess.check_output(
            "free -m | awk 'NR==2 {printf \"%.1fG / %.1fG (%.0f%%)\", $3/1024, $2/1024, ($3/$2)*100}'",
            shell=True, text=True, timeout=4
        ).strip()

        return {
            "ram_pct": ram_pct,
            "ram_str": ram_str,
            "disk_pct": disk_pct,
            "disk_str": disk_str,
            "online": True
        }
    except Exception as e:
        logger.error(f"Gagal mengambil metrik Galaxy: {e}")
        return {"ram_pct": 0.0, "ram_str": "Error", "disk_pct": 0.0, "disk_str": "Error", "online": False}


def check_multiverse_usage() -> Dict[str, Any]:
    """Mengambil metrik RAM dan Disk Multiverse via 1 roundtrip SSH"""
    if IS_WINDOWS:
        return {
            "ram_pct": 27.0,
            "ram_str": "2.1G / 7.8G (27%)",
            "disk_pct": 37.0,
            "disk_str": "18G / 49G (37%)",
            "online": True
        }

    batch_cmd = (
        "df -P / | awk 'NR==2 {gsub(/%/, \"\", $5); print $5}'; "
        "echo '___DELIM___'; "
        "df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'; "
        "echo '___DELIM___'; "
        "free -m | awk 'NR==2 {printf \"%.1f\", ($3/$2)*100}'; "
        "echo '___DELIM___'; "
        "free -m | awk 'NR==2 {printf \"%.1fG / %.1fG (%.0f%%)\", $3/1024, $2/1024, ($3/$2)*100}'"
    )
    success, raw = run_ssh_multiverse(batch_cmd, timeout=8)
    if not success or not raw:
        return {"ram_pct": 0.0, "ram_str": "Error", "disk_pct": 0.0, "disk_str": "Error", "online": False}

    try:
        parts = [p.strip() for p in raw.split("___DELIM___")]
        disk_pct = float(parts[0]) if len(parts) > 0 and parts[0] else 0.0
        disk_str = parts[1] if len(parts) > 1 and parts[1] else "Error"
        ram_pct = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
        ram_str = parts[3] if len(parts) > 3 and parts[3] else "Error"
        return {
            "ram_pct": ram_pct,
            "ram_str": ram_str,
            "disk_pct": disk_pct,
            "disk_str": disk_str,
            "online": True
        }
    except Exception as e:
        logger.error(f"Gagal mem-parsing metrik Multiverse: {e}")
        return {"ram_pct": 0.0, "ram_str": "Error", "disk_pct": 0.0, "disk_str": "Error", "online": False}


def _send_alert_to_all(bot: telebot.TeleBot, text: str):
    """Mengirim pesan alert darurat ke seluruh SuperAdmin dan Admin aktif"""
    recipients = get_alert_recipients()
    for uid in recipients:
        try:
            bot.send_message(uid, text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Gagal mengirim notifikasi alert ke user {uid}: {e}")


def _evaluate_metric(
    bot: telebot.TeleBot,
    state_key: str,
    server_title: str,
    server_host: str,
    metric_label: str,
    val_pct: float,
    detail_str: str,
    action_hint: str
):
    """Mengevaluasi batas ambang, cooldown, dan transisi pemulihan"""
    now = time.time()
    state = _alert_state[state_key]

    # Kondisi Kritis (>= 90%)
    if val_pct >= ALERT_THRESHOLD:
        should_alert = False
        if not state["alerted"]:
            should_alert = True
        elif (now - state["last_alert_time"]) >= ALERT_COOLDOWN:
            should_alert = True

        if should_alert:
            state["alerted"] = True
            state["last_alert_time"] = now
            state["val"] = val_pct
            waktu = time.strftime("%Y-%m-%d %H:%M:%S WIB")

            pesan = (
                "🚨 *[PERINGATAN KRITIS] MEMORI SERVER >= 90%*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🕒 *Waktu:* `{waktu}`\n"
                f"🖥️ *Server:* `{server_title}` (`{server_host}`)\n"
                f"📊 *{metric_label}:* `{val_pct:.1f}%` ({detail_str})\n"
                "⚠️ *Status:* Ambang batas 90% terlampaui!\n\n"
                f"💡 *Rekomendasi Tindakan:*\n{action_hint}\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            logger.warning(f"ALERT TRIGGERED: {server_title} {metric_label} at {val_pct:.1f}%")
            _send_alert_to_all(bot, pesan)

    # Kondisi Pemulihan (< 85% setelah sebelumnya ter-alert)
    elif state["alerted"] and val_pct < RECOVERY_THRESHOLD:
        state["alerted"] = False
        state["val"] = val_pct
        waktu = time.strftime("%Y-%m-%d %H:%M:%S WIB")

        pesan = (
            "✅ *[PEMULIHAN] MEMORI KEMBALI NORMAL (< 90%)*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 *Waktu:* `{waktu}`\n"
            f"🖥️ *Server:* `{server_title}` (`{server_host}`)\n"
            f"📊 *{metric_label}:* `{val_pct:.1f}%` ({detail_str})\n"
            "🟢 *Status:* Beban sistem telah kembali stabil.\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        logger.info(f"RECOVERY TRIGGERED: {server_title} {metric_label} dropped to {val_pct:.1f}%")
        _send_alert_to_all(bot, pesan)


def check_and_notify(bot: telebot.TeleBot):
    """Pemeriksaan satu putaran untuk Galaxy dan Multiverse"""
    # 1. Cek Galaxy
    gal = check_galaxy_usage()
    if gal.get("online"):
        _evaluate_metric(
            bot=bot,
            state_key="galaxy_ram",
            server_title="Galaxy (Web & App)",
            server_host="server.ngopibareng.id",
            metric_label="Penggunaan RAM",
            val_pct=gal["ram_pct"],
            detail_str=gal["ram_str"],
            action_hint="• Jalankan `/hapus_sampah_galaxy` untuk flush RAM & cache.\n• Cek kondisi via `/ping`."
        )
        _evaluate_metric(
            bot=bot,
            state_key="galaxy_disk",
            server_title="Galaxy (Web & App)",
            server_host="server.ngopibareng.id",
            metric_label="Penyimpanan Disk (/)",
            val_pct=gal["disk_pct"],
            detail_str=gal["disk_str"],
            action_hint="• Jalankan `/hapus_sampah_galaxy` untuk memangkas log & cache.\n• Periksa kapasitas direktori storage."
        )

    # 2. Cek Multiverse
    mul = check_multiverse_usage()
    if mul.get("online"):
        _evaluate_metric(
            bot=bot,
            state_key="multiverse_ram",
            server_title="Multiverse (Database)",
            server_host="server2.ngopibareng.id",
            metric_label="Penggunaan RAM",
            val_pct=mul["ram_pct"],
            detail_str=mul["ram_str"],
            action_hint="• Periksa proses dan koneksi MySQL yang menggantung.\n• Cek kesehatan via `/ping`."
        )
        _evaluate_metric(
            bot=bot,
            state_key="multiverse_disk",
            server_title="Multiverse (Database)",
            server_host="server2.ngopibareng.id",
            metric_label="Penyimpanan Disk (/)",
            val_pct=mul["disk_pct"],
            detail_str=mul["disk_str"],
            action_hint="• Purge binary logs MySQL atau hapus rotasi log lawas.\n• Cek status disk via `/ping`."
        )


def start_alert_monitor(bot: telebot.TeleBot, check_interval: int = 60):
    """Menjalankan background daemon thread untuk memantau memori secara otomatis"""
    def _worker():
        logger.info(f"Memory Alert Monitor Daemon aktif (Interval: {check_interval}s, Ambang: {ALERT_THRESHOLD}%).")
        # Jeda 10 detik saat boot awal agar startup bot stabil
        time.sleep(10)
        while True:
            try:
                check_and_notify(bot)
            except Exception as e:
                logger.error(f"Error pada loop Memory Alert Daemon: {e}")
            time.sleep(check_interval)

    t = threading.Thread(target=_worker, daemon=True, name="MemoryAlertDaemon")
    t.start()
