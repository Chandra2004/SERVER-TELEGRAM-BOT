import os
import subprocess
from typing import Tuple
from config import MULTIVERSE_IP, MULTIVERSE_PORT, MULTIVERSE_USER, SSH_KEY_PATH

def run_ssh_multiverse(command: str, timeout: int = 5) -> Tuple[bool, str]:
    """Menjalankan perintah SSH ke Server Multiverse secara aman"""
    # Jika berjalan di laptop (key Linux tidak ditemukan), lewati agar tidak meminta password
    if not os.path.exists(SSH_KEY_PATH):
        return False, "SSH Key tidak ditemukan (Mode Pengujian Lokal)"

    ssh_args = [
        "ssh",
        "-i", SSH_KEY_PATH,
        "-p", str(MULTIVERSE_PORT),
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{MULTIVERSE_USER}@{MULTIVERSE_IP}",
        command
    ]
    try:
        res = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if res.returncode == 0:
            return True, res.stdout.strip()
        return False, res.stderr.strip() or "SSH execution failed"
    except subprocess.TimeoutExpired:
        return False, "SSH connection timeout"
    except Exception as e:
        return False, str(e)
