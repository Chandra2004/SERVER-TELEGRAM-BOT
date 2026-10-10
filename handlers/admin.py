from telebot import TeleBot
from telebot.types import Message
from middleware.auth import can
from database.user_repo import (
    add_user_with_role, delete_user, list_all_users, user_has_role,
    create_role, delete_role, list_all_roles,
    create_permission, delete_permission, list_all_permissions,
    attach_permission_to_role, detach_permission_from_role, list_role_permissions
)
from config import SUPERADMIN_ID

def escape_md(text: str) -> str:
    """Escape karakter reserved Telegram Markdown V1 agar tidak merusak entitas pesan"""
    if not text:
        return ""
    for ch in ['_', '*', '`', '[']:
        text = text.replace(ch, f"\\{ch}")
    return text

def register_admin_handlers(bot: TeleBot):
    """Mendaftarkan seluruh handler CRUD untuk Users, Roles, Permissions, dan Role_Permissions"""

    # ==========================================
    # 1. CRUD USERS
    # ==========================================

    @bot.message_handler(commands=['adduser'])
    @can('users:manage')
    def handle_add_user(message: Message):
        args = message.text.split()[1:]
        if len(args) < 2:
            bot.reply_to(
                message,
                "Format: `/adduser <telegram_id> <role> [nama]`\nContoh: `/adduser 123456789 viewer Budi_Editor`",
                parse_mode="Markdown"
            )
            return

        target_id_str, role = args[0], args[1].lower()
        full_name = " ".join(args[2:]) if len(args) > 2 else "Tanpa Nama"

        if not target_id_str.isdigit():
            bot.reply_to(message, "Error: Telegram ID harus angka.")
            return

        # Cegah eskalasi hak akses: Hanya superadmin yang boleh menetapkan role superadmin
        caller_id = message.from_user.id
        if role == "superadmin" and caller_id != SUPERADMIN_ID and not user_has_role(caller_id, "superadmin"):
            bot.reply_to(message, "⛔ Akses Ditolak: Hanya SuperAdmin yang berhak menetapkan role superadmin.")
            return

        success = add_user_with_role(user_id=int(target_id_str), role_name=role, full_name=full_name)
        if success:
            bot.reply_to(message, f"✅ User `{target_id_str}` ({escape_md(full_name)}) diset ke role *{role}*.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"Gagal: Role `{role}` belum terdaftar di tabel roles.", parse_mode="Markdown")

    @bot.message_handler(commands=['deluser'])
    @can('users:manage')
    def handle_del_user(message: Message):
        args = message.text.split()[1:]
        if not args or not args[0].isdigit():
            bot.reply_to(message, "Format: `/deluser <telegram_id>`", parse_mode="Markdown")
            return

        target_id = int(args[0])
        caller_id = message.from_user.id
        if target_id == SUPERADMIN_ID:
            bot.reply_to(message, "Error: SuperAdmin utama tidak dapat dihapus.")
            return

        # Cegah admin biasa menghapus akun superadmin
        if user_has_role(target_id, "superadmin") and caller_id != SUPERADMIN_ID and not user_has_role(caller_id, "superadmin"):
            bot.reply_to(message, "⛔ Akses Ditolak: Anda tidak memiliki wewenang untuk menghapus akun SuperAdmin.")
            return

        if delete_user(target_id):
            bot.reply_to(message, f"✅ User `{target_id}` berhasil dihapus.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "User tidak ditemukan.", parse_mode="Markdown")

    @bot.message_handler(commands=['listuser'])
    @can('users:view')
    def handle_list_user(message: Message):
        users = list_all_users()
        lines = ["📋 *DAFTAR PENGGUNA TERDAFTAR*", "━━━━━━━━━━━━━━━━━━━━"]
        for u in users:
            nama = escape_md(u.get('full_name') or '-')
            lines.append(f"• `{u['id']}` | *{u['roles']}* | {nama}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

    # ==========================================
    # 2. CRUD ROLES (/role)
    # ==========================================

    @bot.message_handler(commands=['role'])
    @can('rbac:manage')
    def handle_roles_crud(message: Message):
        args = message.text.split()[1:]
        sub = args[0].lower() if args else "list"

        if sub == "list":
            roles = list_all_roles()
            lines = ["🛡️ *DAFTAR ROLES*", "━━━━━━━━━━━━━━━━━━━━"]
            for r in roles:
                desc = f" - _{r['description']}_" if r['description'] else ""
                lines.append(f"• *{r['name']}*{desc}")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nGunakan `/role add <nama> [desc]` atau `/role del <nama>`")
            bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

        elif sub == "add" and len(args) >= 2:
            role_name = args[1].lower()
            desc = " ".join(args[2:]) if len(args) > 2 else ""
            if create_role(role_name, desc):
                bot.reply_to(message, f"✅ Role *{role_name}* berhasil dibuat.", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"Gagal: Role *{role_name}* sudah ada.", parse_mode="Markdown")

        elif sub == "del" and len(args) >= 2:
            role_name = args[1].lower()
            if delete_role(role_name):
                bot.reply_to(message, f"✅ Role *{role_name}* berhasil dihapus.", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"Gagal menghapus role *{role_name}* (Protected/Tidak ditemukan).", parse_mode="Markdown")
        else:
            bot.reply_to(message, "Format salah.\n• `/role list`\n• `/role add <name> [desc]`\n• `/role del <name>`", parse_mode="Markdown")

    # ==========================================
    # 3. CRUD PERMISSIONS (/perm)
    # ==========================================

    @bot.message_handler(commands=['perm'])
    @can('rbac:manage')
    def handle_permissions_crud(message: Message):
        args = message.text.split()[1:]
        sub = args[0].lower() if args else "list"

        if sub == "list":
            perms = list_all_permissions()
            lines = ["🔑 *DAFTAR PERMISSIONS*", "━━━━━━━━━━━━━━━━━━━━"]
            for p in perms:
                desc = f" - _{p['description']}_" if p['description'] else ""
                lines.append(f"• `{p['name']}`{desc}")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nGunakan `/perm add <name> [desc]` atau `/perm del <name>`")
            bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

        elif sub == "add" and len(args) >= 2:
            perm_name = args[1]
            desc = " ".join(args[2:]) if len(args) > 2 else ""
            if create_permission(perm_name, desc):
                bot.reply_to(message, f"✅ Permission `{perm_name}` berhasil dibuat.", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"Gagal: Permission `{perm_name}` sudah ada.", parse_mode="Markdown")

        elif sub == "del" and len(args) >= 2:
            perm_name = args[1]
            if delete_permission(perm_name):
                bot.reply_to(message, f"✅ Permission `{perm_name}` dihapus.", parse_mode="Markdown")
            else:
                bot.reply_to(message, "Gagal menghapus permission.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "Format salah.\n• `/perm list`\n• `/perm add <name> [desc]`\n• `/perm del <name>`", parse_mode="Markdown")

    # ==========================================
    # 4. CRUD ROLE_PERMISSIONS (/roleperm)
    # ==========================================

    @bot.message_handler(commands=['roleperm'])
    @can('rbac:manage')
    def handle_role_permissions_crud(message: Message):
        args = message.text.split()[1:]
        sub = args[0].lower() if args else "list"

        if sub == "list":
            target_role = args[1].lower() if len(args) > 1 else None
            mappings = list_role_permissions(target_role)
            lines = ["🔗 *MAPPING ROLE PERMISSIONS*", "━━━━━━━━━━━━━━━━━━━━"]
            for m in mappings:
                perms = m.get('permissions') or 'tidak ada izin'
                lines.append(f"• *{m['role']}*:\n  ↳ `{perms}`")
            lines.append("━━━━━━━━━━━━━━━━━━━━\nGunakan:\n• `/roleperm attach <role> <perm>`\n• `/roleperm detach <role> <perm>`")
            bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

        elif sub == "attach" and len(args) >= 3:
            role_name, perm_name = args[1].lower(), args[2]
            if attach_permission_to_role(role_name, perm_name):
                bot.reply_to(message, f"✅ Permission `{perm_name}` berhasil dipasang ke role *{role_name}*.", parse_mode="Markdown")
            else:
                bot.reply_to(message, "Gagal: Role atau Permission tidak ditemukan.", parse_mode="Markdown")

        elif sub == "detach" and len(args) >= 3:
            role_name, perm_name = args[1].lower(), args[2]
            if detach_permission_from_role(role_name, perm_name):
                bot.reply_to(message, f"✅ Permission `{perm_name}` dicabut dari role *{role_name}*.", parse_mode="Markdown")
            else:
                bot.reply_to(message, "Gagal mencabut permission.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "Format salah.\n• `/roleperm list [role]`\n• `/roleperm attach <role> <perm>`\n• `/roleperm detach <role> <perm>`", parse_mode="Markdown")
