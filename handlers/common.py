from telebot import TeleBot
from telebot.types import Message, BotCommand, BotCommandScopeChat
from middleware.auth import can
from services.metrics import get_server_health_report
from database.user_repo import get_user_allowed_commands
from handlers.menu import get_main_menu_keyboard

def sync_user_command_menu(bot: TeleBot, user_id: int):
    """Sinkronisasi menu '/' autocomplete Telegram sesuai hak akses user dari database"""
    try:
        allowed = get_user_allowed_commands(user_id)
        if allowed:
            bot_cmds = [BotCommand(c["command"], c["description"]) for c in allowed]
            bot.set_my_commands(bot_cmds, scope=BotCommandScopeChat(user_id))
    except Exception:
        pass

def register_common_handlers(bot: TeleBot):
    """Mendaftarkan handler umum: /start, /help, /menu, /ping"""

    @bot.message_handler(commands=['start', 'help', 'menu'])
    @can('server:metrics')
    def handle_menu_trigger(message: Message):
        # Sinkronkan menu '/' dinamis sesuai izin user
        sync_user_command_menu(bot, message.from_user.id)

        keyboard = get_main_menu_keyboard(message.from_user.id)
        text = (
            "🤖 *Panel Kendali Server Ngobar*\n"
            "Silakan pilih menu aksi interaktif di bawah atau ketik `/` untuk melihat daftar perintah:"
        )
        bot.reply_to(message, text, reply_markup=keyboard, parse_mode="Markdown")

    @bot.message_handler(commands=['ping'])
    @can('server:metrics')
    def handle_ping(message: Message):
        sync_user_command_menu(bot, message.from_user.id)
        laporan = get_server_health_report()
        bot.reply_to(message, laporan, parse_mode="Markdown")
