from telebot import TeleBot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.user_repo import (
    user_can, list_all_users, list_all_roles, list_all_permissions, list_role_permissions, list_server_scripts
)
from services.metrics import get_server_health_report
from services.script_runner import execute_server_script

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Membuat keyboard menu utama sesuai hak akses user"""
    markup = InlineKeyboardMarkup(row_width=1)
    
    # 1. Konfigurasi & Custom Script Bash
    if user_can(user_id, "server:scripts"):
        markup.add(InlineKeyboardButton("⚙️ Konfigurasi & Script Server", callback_data="menu:scripts"))

    # 2. Manajemen Pengguna & RBAC
    if user_can(user_id, "users:view") or user_can(user_id, "users:manage") or user_can(user_id, "rbac:manage"):
        markup.add(InlineKeyboardButton("👥 Manajemen Pengguna & RBAC", callback_data="menu:mgmt"))

    return markup

def get_scripts_keyboard() -> InlineKeyboardMarkup:
    """Keyboard submenu konfigurasi dan script server"""
    markup = InlineKeyboardMarkup(row_width=1)
    scripts = list_server_scripts()
    
    # Buat tombol klik-eksekusi untuk setiap script yang aktif
    for s in scripts:
        btn_text = f"▶️ /{s['command_name']} - {s['title']} ({s['target_server'][:3].upper()})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"exec_script:{s['command_name']}"))

    markup.row(
        InlineKeyboardButton("➕ Buat Script Baru", callback_data="script_help:add"),
        InlineKeyboardButton("🗑️ Hapus Script", callback_data="script_help:del")
    )
    markup.add(InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:main"))
    return markup

def get_mgmt_keyboard() -> InlineKeyboardMarkup:
    """Membuat keyboard submenu manajemen pengguna dan RBAC"""
    markup = InlineKeyboardMarkup(row_width=2)
    btn_list_user = InlineKeyboardButton("📋 Daftar User", callback_data="mgmt:listuser")
    btn_add_user = InlineKeyboardButton("➕ Tambah User", callback_data="mgmt:adduser")
    btn_del_user = InlineKeyboardButton("🗑️ Hapus User", callback_data="mgmt:deluser")
    btn_roles = InlineKeyboardButton("🛡️ Kelola Roles", callback_data="mgmt:roles")
    btn_perms = InlineKeyboardButton("🔑 Permissions", callback_data="mgmt:perms")
    btn_roleperm = InlineKeyboardButton("🔗 Role Permissions", callback_data="mgmt:roleperm")
    btn_back = InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:main")

    markup.add(btn_list_user)
    markup.add(btn_add_user, btn_del_user)
    markup.add(btn_roles, btn_perms)
    markup.add(btn_roleperm)
    markup.add(btn_back)
    return markup

def register_menu_handlers(bot: TeleBot):
    """Mendaftarkan handler interaktif menu berjenjang"""

    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu:") or call.data.startswith("mgmt:") or call.data.startswith("script_help:") or call.data.startswith("exec_script:"))
    def handle_menu_callbacks(call: CallbackQuery):
        user_id = call.from_user.id
        action = call.data

        # 1. Kembali ke Menu Utama
        if action == "menu:main":
            bot.edit_message_text(
                "🤖 *Panel Kendali Utama Server Ngobar*\nSilakan pilih menu di bawah:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard(user_id)
            )
            bot.answer_callback_query(call.id)

        # 2. Eksekusi Ping
        elif action == "menu:ping":
            if not user_can(user_id, "server:metrics"):
                bot.answer_callback_query(call.id, "Akses ditolak!", show_alert=True)
                return
            bot.answer_callback_query(call.id, "Mengambil metrik server...")
            laporan = get_server_health_report()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="menu:ping"))
            markup.add(InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:main"))
            bot.edit_message_text(
                laporan,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )

        # 3. Submenu Konfigurasi & Script Server
        elif action == "menu:scripts":
            if not user_can(user_id, "server:scripts"):
                bot.answer_callback_query(call.id, "Akses ditolak!", show_alert=True)
                return
            bot.edit_message_text(
                "⚙️ *Konfigurasi & Custom Script Server*\nKlik tombol script di bawah untuk langsung mengeksekusi:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_scripts_keyboard()
            )
            bot.answer_callback_query(call.id)

        # 4. Eksekusi Script via Klik Tombol
        elif action.startswith("exec_script:"):
            if not user_can(user_id, "server:scripts"):
                bot.answer_callback_query(call.id, "Akses ditolak!", show_alert=True)
                return
            cmd_name = action.split(":")[1]
            bot.answer_callback_query(call.id, f"Mengeksekusi /{cmd_name}...")
            _, laporan = execute_server_script(cmd_name)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Daftar Script", callback_data="menu:scripts"))
            try:
                bot.edit_message_text(
                    laporan,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                bot.edit_message_text(
                    laporan,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )

        # 5. Panduan Buat Script Baru
        elif action == "script_help:add":
            text = (
                "➕ *Panduan Membuat Custom Bash Script*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Ketik pesan di chat dengan salah satu format berikut:\n\n"
                "*1. Format 1 Baris:*\n"
                "`/addscript <cmd> <galaxy|multiverse> <Judul> | <script>`\n"
                "Contoh: `/addscript cek_uptime galaxy Uptime Server | uptime`\n\n"
                "*2. Format Multi-Baris (Untuk Script Panjang):*\n"
                "`/addscript cek_storage galaxy Cek Partisi`\n"
                "df -h /\n"
                "du -sh /var/log\n\n"
                "Setelah dibuat, perintah otomatis bisa dipanggil dengan `/<cmd>`."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Script", callback_data="menu:scripts"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 6. Panduan Hapus Script
        elif action == "script_help:del":
            text = (
                "🗑️ *Hapus Custom Script*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Ketik: `/delscript <nama_command>`\n"
                "Contoh: `/delscript cek_disk`"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Script", callback_data="menu:scripts"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 7. Submenu Manajemen Pengguna
        elif action == "menu:mgmt":
            if not (user_can(user_id, "users:view") or user_can(user_id, "users:manage") or user_can(user_id, "rbac:manage")):
                bot.answer_callback_query(call.id, "Akses ditolak!", show_alert=True)
                return
            bot.edit_message_text(
                "👥 *Menu Manajemen Pengguna & RBAC*\nPilih fitur yang ingin Anda kelola:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_mgmt_keyboard()
            )
            bot.answer_callback_query(call.id)

        # 8. Manajemen User: List
        elif action == "mgmt:listuser":
            if not user_can(user_id, "users:view"):
                bot.answer_callback_query(call.id, "Akses ditolak!", show_alert=True)
                return
            users = list_all_users()
            lines = ["📋 *DAFTAR PENGGUNA TERDAFTAR*", "━━━━━━━━━━━━━━━━━━━━"]
            for u in users:
                nama = u.get('full_name') or '-'
                lines.append(f"• `{u['id']}` | *{u['roles']}* | {nama}")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text("\n".join(lines), chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 9. Manajemen User: Add
        elif action == "mgmt:adduser":
            text = "➕ *Tambah Pengguna Baru*\n\nFormat: `/adduser <telegram_id> <role> [nama]`\nContoh: `/adduser 123456789 viewer Budi_Editor`"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 10. Manajemen User: Del
        elif action == "mgmt:deluser":
            text = "🗑️ *Hapus Pengguna*\n\nFormat: `/deluser <telegram_id>`\nContoh: `/deluser 123456789`"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 11. Manajemen Roles
        elif action == "mgmt:roles":
            roles = list_all_roles()
            lines = ["🛡️ *DAFTAR ROLES*", "━━━━━━━━━━━━━━━━━━━━"]
            for r in roles:
                desc = f" - _{r['description']}_" if r['description'] else ""
                lines.append(f"• *{r['name']}*{desc}")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nPerintah:\n• `/role add <nama> [desc]`\n• `/role del <nama>`")
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text("\n".join(lines), chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 12. Manajemen Permissions
        elif action == "mgmt:perms":
            perms = list_all_permissions()
            lines = ["🔑 *DAFTAR PERMISSIONS*", "━━━━━━━━━━━━━━━━━━━━"]
            for p in perms:
                desc = f" - _{p['description']}_" if p['description'] else ""
                lines.append(f"• `{p['name']}`{desc}")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nPerintah:\n• `/perm add <nama> [desc]`\n• `/perm del <nama>`")
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text("\n".join(lines), chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)

        # 13. Role Permissions Mapping
        elif action == "mgmt:roleperm":
            mappings = list_role_permissions()
            lines = ["🔗 *MAPPING ROLE PERMISSIONS*", "━━━━━━━━━━━━━━━━━━━━"]
            for m in mappings:
                perms = m.get('permissions') or 'tidak ada izin'
                lines.append(f"• *{m['role']}*:\n  ↳ `{perms}`")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nPerintah:\n• `/roleperm attach <role> <perm>`\n• `/roleperm detach <role> <perm>`")
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔙 Kembali ke Manajemen", callback_data="menu:mgmt"))
            bot.edit_message_text("\n".join(lines), chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id)
