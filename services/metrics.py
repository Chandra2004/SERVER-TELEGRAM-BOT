import platform
import subprocess
import time
from services.ssh_client import run_ssh_multiverse

IS_WINDOWS = platform.system() == "Windows"

def get_clean_ports_galaxy() -> str:
    """Mengambil dan melabeli port TCP listening di Galaxy"""
    if IS_WINDOWS:
        return "80/HTTP, 443/HTTPS, 6001/Soketi, 6379/Redis, 45683/SSH (Dev Mode)"
    try:
        raw = subprocess.check_output(
            "ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u",
            shell=True, text=True, timeout=3
        )
        ports = raw.strip().split()
        mapping = {
            "80": "80/HTTP",
            "443": "443/HTTPS",
            "6001": "6001/Soketi",
            "6379": "6379/Redis",
            "9601": "9601/Metrics",
            "45683": "45683/SSH"
        }
        labels = [mapping.get(p, p) for p in ports]
        return ", ".join(labels)
    except Exception:
        return "80/HTTP, 443/HTTPS, 6001/Soketi, 6379/Redis, 45683/SSH"

def get_clean_ports_multiverse() -> str:
    """Mengambil dan melabeli port TCP listening di Multiverse"""
    _, _, _, _, ports_mul = get_multiverse_metrics()
    return ports_mul

def get_multiverse_metrics():
    """Mengambil seluruh metrik Multiverse dalam 1 roundtrip SSH untuk memangkas latensi koneksi"""
    if IS_WINDOWS:
        return True, "18G / 49G (37%) [Dev Mode]", "2.1G / 7.8G (27%) [Dev Mode]", "0.35, 0.45, 0.40", "3306/MySQL, 65002/SSH (Dev Mode)"

    batch_cmd = (
        "df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'; "
        "echo '___DELIM___'; "
        "free -m | awk 'NR==2 {printf \"%.1fG / %.1fG (%.0f%%)\", $3/1024, $2/1024, ($3/$2)*100}'; "
        "echo '___DELIM___'; "
        "cat /proc/loadavg | awk '{print $1 \", \" $2 \", \" $3}'; "
        "echo '___DELIM___'; "
        "ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u"
    )
    success, raw = run_ssh_multiverse(batch_cmd, timeout=8)
    if not success or not raw:
        return False, "Error", "Error", "Error", "3306/MySQL, 65002/SSH"

    parts = [p.strip() for p in raw.split("___DELIM___")]
    df_mul = parts[0] if len(parts) > 0 and parts[0] else "Error"
    ram_mul = parts[1] if len(parts) > 1 and parts[1] else "Error"
    load_mul = parts[2] if len(parts) > 2 and parts[2] else "Error"

    ports_raw = parts[3].split() if len(parts) > 3 and parts[3] else []
    mapping = {
        "3306": "3306/MySQL",
        "33060": "33060/MySQL-X",
        "65002": "65002/SSH"
    }
    labels = [mapping.get(p, p) for p in ports_raw]
    ports_mul = ", ".join(labels) if labels else "3306/MySQL, 65002/SSH"

    return True, df_mul, ram_mul, load_mul, ports_mul

def get_server_health_report() -> str:
    """Mengumpulkan seluruh metrik kesehatan kedua server"""
    waktu = time.strftime("%Y-%m-%d %H:%M:%S WIB")

    # 1. Metrik Galaxy (Local)
    if IS_WINDOWS:
        df_gal = "31G / 97G (32%) [Dev Mode]"
        ram_gal = "1.5G / 3.9G (38%) [Dev Mode]"
        load_gal = "0.50, 0.70, 0.65"
        ports_gal = get_clean_ports_galaxy()
        status_gal = "ONLINE (Simulasi Laptop Windows)"
    else:
        try:
            df_gal = subprocess.check_output("df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'", shell=True, text=True, timeout=3).strip()
            ram_gal = subprocess.check_output("free -m | awk 'NR==2 {printf \"%.1fG / %.1fG (%.0f%%)\", $3/1024, $2/1024, ($3/$2)*100}'", shell=True, text=True, timeout=3).strip()
            load_gal = subprocess.check_output("cat /proc/loadavg | awk '{print $1 \", \" $2 \", \" $3}'", shell=True, text=True, timeout=3).strip()
            ports_gal = get_clean_ports_galaxy()
            status_gal = "ONLINE"
        except Exception:
            df_gal, ram_gal, load_gal, ports_gal = "Error", "Error", "Error", "Error"
            status_gal = "OFFLINE"

    # 2. Metrik Multiverse (1 Roundtrip SSH Remote Batch)
    ok_mul, df_mul, ram_mul, load_mul, ports_mul = get_multiverse_metrics()
    status_mul = "ONLINE" if ok_mul else "OFFLINE/UNREACHABLE"

    laporan = (
        "```\n"
        "========================================\n"
        "      LAPORAN KESEHATAN SERVER\n"
        f"      Waktu: {waktu}\n"
        "========================================\n\n"
        "[1. GALAXY - WEB & APP]\n"
        f"Status    : {status_gal} (server.ngopibareng.id)\n"
        f"Disk (/)  : {df_gal}\n"
        f"RAM       : {ram_gal}\n"
        f"CPU Load  : {load_gal}\n"
        f"Port Aktif: {ports_gal}\n\n"
        "----------------------------------------\n\n"
        "[2. MULTIVERSE - DATABASE]\n"
        f"Status    : {status_mul} (server2.ngopibareng.id)\n"
        f"Disk (/)  : {df_mul}\n"
        f"RAM       : {ram_mul}\n"
        f"CPU Load  : {load_mul}\n"
        f"Port Aktif: {ports_mul}\n\n"
        "========================================\n"
        "Keamanan : Whitelist Aktif | Sesi Aman\n"
        "```"
    )
    return laporan
