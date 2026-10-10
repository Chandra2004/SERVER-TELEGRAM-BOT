import platform
import subprocess
import time
from typing import Tuple
from database.user_repo import get_server_script
from services.ssh_client import run_ssh_multiverse

IS_WINDOWS = platform.system() == "Windows"

def execute_server_script(command_name: str) -> Tuple[bool, str]:
    """Mengeksekusi custom script bash di server Galaxy atau Multiverse"""
    script_data = get_server_script(command_name)
    if not script_data:
        return False, f"Perintah `/{command_name}` tidak terdaftar dalam konfigurasi script."

    target = script_data["target_server"]
    code = script_data["script_content"]
    title = script_data["title"]
    start_time = time.time()

    # 1. Eksekusi di Target Galaxy
    if target == "galaxy":
        if IS_WINDOWS:
            # Simulasi di laptop Windows
            output = f"[DEV-MODE WINDOWS]\nPerintah bash berikut berhasil disimulasikan:\n$ {code}\n\nOutput: [Simulated Success]"
            success = True
        else:
            try:
                TIMEOUT_SECONDS = 180
                res = subprocess.run(
                    ["bash", "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS
                )
                success = (res.returncode == 0)
                output = res.stdout if res.stdout else res.stderr
                if not output:
                    output = "Perintah selesai tanpa output (Exit Code 0)."
            except subprocess.TimeoutExpired:
                return False, f"Error: Eksekusi script melebihi batas waktu (Timeout {TIMEOUT_SECONDS} detik)."
            except Exception as e:
                return False, f"Error eksekusi: {str(e)}"

    # 2. Eksekusi di Target Multiverse (Remote SSH)
    elif target == "multiverse":
        if IS_WINDOWS:
            output = f"[DEV-MODE WINDOWS]\nSSH ke Multiverse disimulasikan:\n$ {code}\n\nOutput: [Simulated Success]"
            success = True
        else:
            TIMEOUT_SECONDS = 180
            success, output = run_ssh_multiverse(code, timeout=TIMEOUT_SECONDS)

    else:
        return False, f"Target server `{target}` tidak dikenali."

    elapsed = time.time() - start_time
    status_label = "SUKSES (Exit 0)" if success else "GAGAL / PERINGATAN"

    clean_output = output.strip() if output else "Perintah selesai tanpa output."
    # Batasi panjang output maksimal 3500 karakter agar muat dalam kuota 4096 karakter Telegram
    MAX_OUTPUT_LEN = 3500
    if len(clean_output) > MAX_OUTPUT_LEN:
        clean_output = clean_output[:MAX_OUTPUT_LEN] + "\n\n... [Output dipotong karena melebihi batas pesan Telegram]"

    # Ganti triple backticks di dalam output agar tidak merusak formatting code block Markdown
    clean_output = clean_output.replace("```", "'''")

    laporan = (
        "```\n"
        "========================================\n"
        f" SCRIPT: {title.upper()}\n"
        f" TARGET: {target.upper()} | STATUS: {status_label}\n"
        f" DURASI: {elapsed:.2f} detik\n"
        "========================================\n\n"
        f"{clean_output}\n"
        "```"
    )
    return success, laporan
