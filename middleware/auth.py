import re
from functools import wraps
from database.user_repo import user_can, user_has_role, log_audit

def sanitize_input(text: str) -> bool:
    """Memeriksa teks perintah Telegram dari karakter berbahaya atau overflow"""
    if not text:
        return True
    # Perintah /addscript memerlukan payload script bash yang bisa memuat variabel ($), pipe (|), semicolon (;), dan multiline
    if text.startswith("/addscript"):
        return len(text) <= 4000
    if len(text) > 300:
        return False
    # Untuk perintah umum bot, cegah injeksi tag/karakter kontrol berbahaya
    if bool(re.search(r"[<>{}`$\\]", text)):
        return False
    return True

def can(permission_name: str):
    """
    Decorator otorisasi berbasis Permission ala Laravel (@can).
    Contoh penggunaan: @can('server:metrics')
    """
    def decorator(handler_func):
        @wraps(handler_func)
        def wrapper(message, *args, **kwargs):
            user_id = message.from_user.id
            cmd_text = message.text.strip() if message.text else ""

            # 1. Sanitasi input
            if not sanitize_input(cmd_text):
                log_audit(user_id, cmd_text, "BLOCKED_MALICIOUS_INPUT")
                return

            # 2. Cek apakah user memiliki permission yang dibutuhkan
            if not user_can(user_id, permission_name):
                log_audit(user_id, cmd_text, f"DENIED_LACK_PERMISSION_{permission_name}")
                bot = kwargs.get('bot')
                # Jika ingin silent drop atau kirim pesan penolakan
                return

            log_audit(user_id, cmd_text, f"ALLOWED_{permission_name}")
            return handler_func(message, *args, **kwargs)
        return wrapper
    return decorator

def has_role(role_name: str):
    """
    Decorator otorisasi berbasis Role.
    Contoh penggunaan: @has_role('superadmin')
    """
    def decorator(handler_func):
        @wraps(handler_func)
        def wrapper(message, *args, **kwargs):
            user_id = message.from_user.id
            cmd_text = message.text.strip() if message.text else ""

            if not sanitize_input(cmd_text):
                log_audit(user_id, cmd_text, "BLOCKED_MALICIOUS_INPUT")
                return

            if not user_has_role(user_id, role_name):
                log_audit(user_id, cmd_text, f"DENIED_LACK_ROLE_{role_name}")
                return

            log_audit(user_id, cmd_text, f"ALLOWED_ROLE_{role_name}")
            return handler_func(message, *args, **kwargs)
        return wrapper
    return decorator
