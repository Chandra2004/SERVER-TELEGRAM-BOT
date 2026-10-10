import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bot.db"

# Muat variabel dari .env
load_dotenv(BASE_DIR / ".env")

# Telegram Credentials (Wajib ada di .env)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("FATAL: BOT_TOKEN tidak ditemukan di environment atau file .env")

superadmin_raw = os.getenv("SUPERADMIN_ID")
if not superadmin_raw:
    raise ValueError("FATAL: SUPERADMIN_ID tidak ditemukan di environment atau file .env")
SUPERADMIN_ID = int(superadmin_raw)

# SSH Server Multiverse (Remote DB)
MULTIVERSE_IP = os.getenv("MULTIVERSE_IP", "127.0.0.1")
MULTIVERSE_PORT = int(os.getenv("MULTIVERSE_PORT", "22"))
MULTIVERSE_USER = os.getenv("MULTIVERSE_USER", "root")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/root/.ssh/id_bot_ed25519")
