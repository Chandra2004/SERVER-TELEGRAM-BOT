from telebot import TeleBot
from telebot.types import Message
from middleware.auth import can
from database.user_repo import (
    save_server_script, delete_server_script, list_server_scripts, get_server_script
)
from services.script_runner import execute_server_script

def register_script_handlers(bot: TeleBot):
    """Mendaftarkan handler untuk konfigurasi dan eksekusi custom script server"""

    # 1. Tambah / Simpan Script Baru
    @bot.message_handler(commands=['addscript'])
    @can('server:scripts')
    def handle_add_script(message: Message):
        """
        Format 1 baris atau multi-baris:
        /addscript <cmd> <galaxy|multiverse> <Judul>
        <isi bash script...>
        """
        lines = message.text.strip().split("\n")
        header = lines[0].split()

        if len(header) < 4 and len(lines) == 1:
            bot.reply_to(
                message,
                "Format salah.\n\n"
                "*Contoh 1 Baris:*\n"
                "`/addscript cek_uptime galaxy Cek Uptime | uptime`\n\n"
                "*Contoh Multi-Baris (Bisa multi-perintah bash):*\n"
                "`/addscript cek_status galaxy Status Web`\n"
                "df -h /\n"
                "free -m\n"
                "uptime",
                parse_mode="Markdown"
            )
            return

        cmd_name = header[1].lower().replace("-", "_").lstrip("/")
        target_server = header[2].lower()

        if target_server not in ("galaxy", "multiverse"):
            bot.reply_to(message, "Error: Target server harus `galaxy` atau `multiverse`.", parse_mode="Markdown")
            return

        if len(lines) > 1:
            title = " ".join(header[3:]) if len(header) > 3 else cmd_name
            script_body = "\n".join(lines[1:]).strip()
        else:
            # Format pemisah tanda '|'
            full_rest = " ".join(header[3:])
            if "|" in full_rest:
                title, script_body = full_rest.split("|", 1)
                title, script_body = title.strip(), script_body.strip()
            else:
                title = cmd_name
                script_body = full_rest.strip()

        if not script_body:
            bot.reply_to(message, "Error: Script bash tidak boleh kosong.")
            return

        success = save_server_script(
            command_name=cmd_name,
            title=title,
            target_server=target_server,
            script_content=script_body,
            created_by=message.from_user.id
        )

        if success:
            bot.reply_to(
                message,
                f"✅ Script `/{cmd_name}` ({title}) berhasil disimpan untuk server *{target_server.upper()}*!\n"
                f"Ketik `/{cmd_name}` kapan saja untuk menjalankannya.",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "Gagal menyimpan script ke database.")

    # 2. Hapus Script
    @bot.message_handler(commands=['delscript'])
    @can('server:scripts')
    def handle_del_script(message: Message):
        args = message.text.split()[1:]
        if not args:
            bot.reply_to(message, "Format: `/delscript <nama_command>`\nContoh: `/delscript cek_disk`", parse_mode="Markdown")
            return

        cmd_name = args[0].lower().replace("-", "_").lstrip("/")
        if delete_server_script(cmd_name):
            bot.reply_to(message, f"✅ Script `/{cmd_name}` berhasil dihapus.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"Script `/{cmd_name}` tidak ditemukan.", parse_mode="Markdown")

    # 3. Daftar Seluruh Script
    @bot.message_handler(commands=['listscript'])
    @can('server:scripts')
    def handle_list_scripts(message: Message):
        scripts = list_server_scripts()
        if not scripts:
            bot.reply_to(message, "Belum ada custom script yang terdaftar.")
            return

        lines = ["📜 *DAFTAR SCRIPT BASH TERDAFTAR*", "━━━━━━━━━━━━━━━━━━━━"]
        for s in scripts:
            lines.append(f"• `/{s['command_name']}` ({s['title']})\n  ↳ Server: *{s['target_server'].upper()}* | Script: `{s['script_content'][:40]}...`")
        lines.append("━━━━━━━━━━━━━━━━━━━━\nKetik langsung nama perintahnya (misal: `/{command_name}`) untuk eksekusi.")

        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

    # 4. Dynamic Script Interceptor (Hanya tangkap jika nama command terdaftar di tabel server_scripts)
    def is_custom_script(message: Message) -> bool:
        if not message.text or not message.text.startswith("/"):
            return False
        parts = message.text.split()
        if not parts:
            return False
        cmd_candidate = parts[0].lstrip("/").lower().replace("-", "_")
        return get_server_script(cmd_candidate) is not None

    @bot.message_handler(func=is_custom_script)
    def handle_dynamic_script_execution(message: Message):
        cmd_text = message.text.strip() if message.text else ""
        user_id = message.from_user.id
        cmd_candidate = cmd_text.split()[0].lstrip("/").lower().replace("-", "_")
        script_data = get_server_script(cmd_candidate)
        if not script_data:
            return

        from database.user_repo import user_can, log_audit
        if not user_can(user_id, "server:scripts"):
            log_audit(user_id, cmd_text, "DENIED_LACK_PERMISSION_server:scripts")
            bot.reply_to(message, "⛔ Akses Ditolak: Anda tidak memiliki izin menjalankan custom script.")
            return

        log_audit(user_id, cmd_text, f"ALLOWED_server:scripts_RUN_{cmd_candidate}")
        bot.send_chat_action(message.chat.id, "typing")
        init_card = (
            "```text\n"
            "========================================\n"
            f" SCRIPT: {cmd_candidate.upper()}\n"
            " STATUS: MEMULAI EKSEKUSI (LIVE WATCH)\n"
            "========================================\n\n"
            "Memulai proses eksekusi script...\n"
            "```"
        )
        try:
            status_msg = bot.reply_to(message, init_card, parse_mode="Markdown")
        except Exception:
            status_msg = bot.reply_to(message, init_card)

        def update_progress(preview_text: str):
            try:
                bot.edit_message_text(
                    preview_text,
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        _, laporan = execute_server_script(cmd_candidate, on_progress=update_progress)
        try:
            bot.edit_message_text(
                laporan,
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
        except Exception:
            bot.edit_message_text(
                laporan,
                chat_id=status_msg.chat.id,
                message_id=status_msg.message_id
            )
