import logging
import telebot
from telebot.types import BotCommand
from config import BOT_TOKEN
from database.db import init_db
from handlers.common import register_common_handlers
from handlers.admin import register_admin_handlers
from handlers.menu import register_menu_handlers
from handlers.scripts import register_script_handlers
from services.alert_service import start_alert_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("server-tele-bot")

def create_bot() -> telebot.TeleBot:
    """Inisialisasi bot Telegram dan seluruh handler"""
    logger.info("Menginisialisasi database dan skema RBAC...")
    # 1. Pastikan Database, RBAC, dan Server Scripts siap
    init_db()

    # 2. Inisialisasi Bot Instance
    bot = telebot.TeleBot(BOT_TOKEN)

    # 3. Daftarkan Command Dasar Global di Telegram
    bot.set_my_commands([
        BotCommand("menu", "Buka menu panel kendali interaktif"),
        BotCommand("ping", "Laporan kesehatan server Galaxy & Multiverse"),
        BotCommand("help", "Panduan dan bantuan bot")
    ])

    # 4. Daftarkan Seluruh Handler (Common & Admin didahulukan, lalu Custom Scripts)
    register_menu_handlers(bot)
    register_common_handlers(bot)
    register_admin_handlers(bot)
    register_script_handlers(bot)

    # 5. Jalankan Background Memory Alert Monitor (Ambang Batas >= 90%)
    start_alert_monitor(bot, check_interval=60)

    logger.info("Seluruh handler dan command bot berhasil didaftarkan.")
    return bot

if __name__ == "__main__":
    logger.info("Memulai Server Ngobar Bot (Modular Version)...")
    app_bot = create_bot()
    logger.info("Bot berhasil berjalan. Menunggu instruksi dari Telegram...")
    app_bot.infinity_polling(timeout=20, long_polling_timeout=20)
