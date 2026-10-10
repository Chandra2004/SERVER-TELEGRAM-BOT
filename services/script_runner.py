import os
import platform
import subprocess
import time
from typing import Tuple, Optional, Callable
from database.user_repo import get_server_script
from services.ssh_client import run_ssh_multiverse

IS_WINDOWS = platform.system() == "Windows"

def format_script_card(title: str, target: str, status_label: str, elapsed: float, body: str) -> str:
    """Format tampilan kartu script ala terminal modern dengan proteksi panjang karakter"""
    clean_body = body.strip() if body else "Menunggu output..."
    MAX_OUTPUT_LEN = 3500
    if len(clean_body) > MAX_OUTPUT_LEN:
        clean_body = clean_body[:MAX_OUTPUT_LEN] + "\n\n... [Output dipotong karena batas Telegram]"
    clean_body = clean_body.replace("```", "'''")

    return (
        "```text\n"
        "========================================\n"
        f" SCRIPT: {title.upper()}\n"
        f" TARGET: {target.upper()} | STATUS: {status_label}\n"
        f" DURASI: {elapsed:.2f} detik\n"
        "========================================\n\n"
        f"{clean_body}\n"
        "```"
    )

def execute_server_script(
    command_name: str,
    on_progress: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """Mengeksekusi custom script bash secara real-time (Watch Mode) di Galaxy atau Multiverse"""
    script_data = get_server_script(command_name)
    if not script_data:
        return False, f"Perintah `/{command_name}` tidak terdaftar dalam konfigurasi script."

    target = script_data["target_server"]
    code = script_data["script_content"]
    title = script_data["title"]
    start_time = time.time()
    TIMEOUT_SECONDS = 180

    # 1. Eksekusi di Target Galaxy (Lokal)
    if target == "galaxy":
        if IS_WINDOWS:
            output = f"[DEV-MODE WINDOWS]\nPerintah bash disimulasikan:\n$ {code}\n\nOutput: [Simulasi Berhasil Selesai]"
            success = True
        else:
            try:
                process = subprocess.Popen(
                    ["bash", "-c", code],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                output_lines = []
                last_update = time.time()

                for line in iter(process.stdout.readline, ''):
                    output_lines.append(line)
                    now = time.time()
                    if on_progress and (now - last_update >= 1.5):
                        cur_text = "".join(output_lines)
                        preview = format_script_card(title, target, "SEDANG BERJALAN...", now - start_time, cur_text)
                        try:
                            on_progress(preview)
                        except Exception:
                            pass
                        last_update = now

                process.stdout.close()
                process.wait(timeout=TIMEOUT_SECONDS)
                success = (process.returncode == 0)
                output = "".join(output_lines) or "Perintah selesai tanpa output (Exit Code 0)."
            except subprocess.TimeoutExpired:
                process.kill()
                return False, f"Error: Eksekusi script melebihi batas waktu (Timeout {TIMEOUT_SECONDS} detik)."
            except Exception as e:
                return False, f"Error eksekusi: {str(e)}"

    # 2. Eksekusi di Target Multiverse (Remote SSH Realtime)
    elif target == "multiverse":
        if IS_WINDOWS:
            output = f"[DEV-MODE WINDOWS]\nSSH ke Multiverse disimulasikan:\n$ {code}\n\nOutput: [Simulasi Berhasil Selesai]"
            success = True
        else:
            from config import SSH_KEY_PATH, MULTIVERSE_PORT, MULTIVERSE_USER, MULTIVERSE_IP
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
                code
            ]
            try:
                process = subprocess.Popen(
                    ssh_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                output_lines = []
                last_update = time.time()

                for line in iter(process.stdout.readline, ''):
                    output_lines.append(line)
                    now = time.time()
                    if on_progress and (now - last_update >= 1.5):
                        cur_text = "".join(output_lines)
                        preview = format_script_card(title, target, "SEDANG BERJALAN...", now - start_time, cur_text)
                        try:
                            on_progress(preview)
                        except Exception:
                            pass
                        last_update = now

                process.stdout.close()
                process.wait(timeout=TIMEOUT_SECONDS)
                success = (process.returncode == 0)
                output = "".join(output_lines) or "Perintah selesai tanpa output (Exit Code 0)."
            except subprocess.TimeoutExpired:
                process.kill()
                return False, f"Error: Eksekusi SSH melebihi batas waktu (Timeout {TIMEOUT_SECONDS} detik)."
            except Exception as e:
                return False, f"Error SSH: {str(e)}"

    else:
        return False, f"Target server `{target}` tidak dikenali."

    elapsed = time.time() - start_time
    status_label = "SUKSES (Exit 0)" if success else "GAGAL / PERINGATAN"
    laporan = format_script_card(title, target, status_label, elapsed, output)
    return success, laporan
