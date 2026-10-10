# Server Ngobar Telegram Bot Sentinel

Bot Telegram pengawas dan pengendali infrastruktur server portal berita **ngopibareng.id** (Server Galaxy & Server Multiverse). Dibangun dengan arsitektur **Modular Python**, **SQLite Relasional (Mode WAL)**, **Role-Based Access Control (RBAC ala Laravel/Spatie)**, dan **Custom Bash Script Engine** yang aman.

---

## Daftar Isi
1. [Arsitektur Sistem & Jaringan](#arsitektur-sistem--jaringan)
2. [Fitur Utama](#fitur-utama)
3. [Skema Database & ERD Relasional](#skema-database--erd-relasional)
4. [Matriks Otorisasi (Roles & Permissions)](#matriks-otorisasi-roles--permissions)
5. [Daftar Lengkap Perintah Bot](#daftar-lengkap-perintah-bot)
6. [Mesin Custom Script Bash](#mesin-custom-script-bash)
7. [Panel Kontrol Interaktif (/menu)](#panel-kontrol-interaktif-menu)
8. [Struktur Direktori Proyek](#struktur-direktori-proyek)
9. [Instalasi & Pengujian Lokal](#instalasi--pengujian-lokal)
10. [Konfigurasi Environment (.env)](#konfigurasi-environment-env)
11. [Panduan Deployment Produksi (Linux Systemd)](#panduan-deployment-produksi-linux-systemd)
12. [Audit Keamanan & Stabilitas Runtime](#audit-keamanan--stabilitas-runtime)

---

## Arsitektur Sistem & Jaringan

Bot berjalan sebagai background daemon di Server Galaxy dan mengontrol kedua server melalui arsitektur berikut:

```text
[HP Admin Telegram]
        │
        │ (HTTPS Outbound Long-Polling - Tanpa Buka Port Inbound)
        ▼
[Server Galaxy (server.ngopibareng.id)]  <--- Host Daemon Bot (/root/server-bot)
        │ - Menjalankan bot.py (systemd: ngobar-bot.service)
        │ - Eksekusi lokal bash/command untuk pemeliharaan Web Nginx, PHP, Redis
        │
        │ (SSH Keyless via Port 65002: /root/.ssh/id_bot_ed25519)
        ▼
[Server Multiverse (server2.ngopibareng.id)]
        │ - Dedicated Database MySQL 8.0
        │ - 1 Roundtrip SSH batch query untuk monitoring & remote script
```

---

## Fitur Utama

- **Role-Based Access Control (RBAC):** Pemisahan izin granular per pengguna (`superadmin`, `admin`, `viewer`) dengan decorator gerbang otorisasi `@can('permission:name')`.
- **Anti-Privilege Escalation:** Validasi ketat yang memblokir admin biasa mengangkat atau menghapus akun `superadmin`.
- **Menu Prompt Dinamis Telegram:** Daftar autocomplete perintah `/` di aplikasi Telegram diperbarui secara dinamis menyesuaikan izin tiap pengguna saat memanggil `/help`.
- **Custom Bash Script Engine:** SuperAdmin dapat mendaftarkan perintah baru langsung dari Telegram (contoh: `/addscript cek_storage ...`) dan menjalankannya sebagai command native `/<nama_command>` tanpa login terminal SSH.
- **Monitoring Kesehatan Dua Server (Sub-detik):** Mengumpulkan metrik Disk, RAM, CPU Load, dan Port TCP aktif kedua server dalam satu laporan ringkas. Remote query ke Multiverse dioptimasi dalam 1 batch SSH call.
- **Tahan Banting & Aman (Anti-Crash):**
  - Database SQLite dikonfigurasi dengan mode WAL (`PRAGMA journal_mode = WAL`) dan `busy_timeout = 5000` untuk mencegah *database lock* pada multi-threading.
  - Pemotongan output script otomatis pada batas aman 3500 karakter untuk mencegah batasan 4096 karakter Telegram.
  - Sanitasi karakter Markdown dan mekanisme fallback otomatis saat pengiriman pesan.
  - Audit logging menyeluruh ke database untuk setiap eksekusi perintah dan script.

---

## Skema Database & ERD Relasional

Database SQLite tersimpan di [`data/bot.db`](file:///g:/CODING/blogspot/server-tele-bot/data/bot.db) dengan relasi sebagai berikut:

```text
               ┌──────────────┐
               │    users     │
               └──────┬───────┘
                      │ 1
                      │
                      │ *
               ┌──────┴───────┐
               │  user_roles  │
               └──────┬───────┘
                      │ *
                      │
                      │ 1
               ┌──────┴───────┐             ┌───────────────┐
               │    roles     │             │ server_scripts│
               └──────┬───────┘             └───────────────┘
                      │ 1
                      │
                      │ *
               ┌──────┴───────┐
               │role_permission│
               └──────┬───────┘
                      │ *
                      │
                      │ 1
               ┌──────┴───────┐             ┌───────────────┐
               │ permissions  │ 1 ──────── *│   commands    │
               └──────────────┘             └───────────────┘
                      │
                      │ (Audit Trail)
                      ▼
               ┌──────────────┐
               │  audit_logs  │
               └──────────────┘
```

### Penjelasan Tabel:
1. **`users`**: Daftar akun Telegram yang di-whitelist (`id`, `username`, `full_name`, `is_active`, `created_at`).
2. **`roles`**: Definisi peran (`id`, `name`, `description`).
3. **`permissions`**: Izin akses atomik (`id`, `name`, `description`).
4. **`user_roles`**: Pivot tabel Many-to-Many penghubung user ke role.
5. **`role_permissions`**: Pivot tabel Many-to-Many penghubung role ke permission.
6. **`commands`**: Master prompt command Telegram bawaan bot, terhubung ke foreign key `permission_id`.
7. **`server_scripts`**: Konfigurasi custom bash script (`command_name`, `title`, `target_server`, `script_content`, `created_by`, `is_active`).
8. **`audit_logs`**: Catatan riwayat seluruh aktivitas perintah dan keamanan (`user_id`, `command_text`, `action_status`, `executed_at`).

---

## Matriks Otorisasi (Roles & Permissions)

| Permission Name | Deskripsi | SuperAdmin | Admin | Viewer |
|---|---|:---:|:---:|:---:|
| `server:metrics` | Membaca laporan kesehatan server (`/ping`, menu info) | Ya | Ya | Ya |
| `server:clean` | Menjalankan pembersihan sampah & cache Laravel (`/clean`) | Ya | Ya | - |
| `server:restart` | Merestart layanan Nginx / PHP-FPM (`/restart`) | Ya | Ya | - |
| `server:scripts` | Membuat, mengedit, dan mengeksekusi custom bash script | Ya | - | - |
| `users:view` | Melihat daftar user terdaftar (`/listuser`) | Ya | Ya | Ya |
| `users:manage` | Menambah/menghapus user dan menetapkan role (`/adduser`, `/deluser`) | Ya | - | - |
| `rbac:manage` | Mengelola role, permission, dan pivot mapping (`/role`, `/perm`, `/roleperm`) | Ya | - | - |

> [!NOTE]
> Izin `server:scripts` dikunci eksklusif untuk **SuperAdmin** demi mencegah risiko Remote Code Execution (RCE) oleh peran admin operasional biasa.

---

## Daftar Lengkap Perintah Bot

### 1. Perintah Umum & Pemantauan
- `/menu` - Membuka panel antarmuka tombol interaktif (Inline Keyboard).
- `/ping` - Mengambil laporan kesehatan realtime Galaxy & Multiverse.
- `/help` - Menampilkan panduan dan menyinkronkan daftar autocomplete Telegram sesuai role Anda.
- `/clean` - Menjalankan skrip pembersihan sampah sistem dan cache Laravel di Galaxy.
- `/restart` - Merestart service web server (`nginx` dan `php7.4-fpm`).

### 2. Manajemen Pengguna (Whitelist)
- `/listuser` - Menampilkan seluruh user terdaftar beserta role-nya.
- `/adduser <telegram_id> <role> [nama]` - Mendaftarkan user baru ke whitelist.
  - *Contoh:* `/adduser 123456789 viewer Budi_Editor`
- `/deluser <telegram_id>` - Menghapus akun dari whitelist.

### 3. Manajemen RBAC (Role, Permission & Mapping)
- `/role list` - Menampilkan daftar role yang aktif.
- `/role add <nama_role> [deskripsi]` - Membuat role baru.
- `/role del <nama_role>` - Menghapus role.
- `/perm list` - Menampilkan daftar permission yang ada.
- `/perm add <nama_perm> [deskripsi]` - Mendaftarkan permission baru.
- `/perm del <nama_perm>` - Menghapus permission.
- `/roleperm list [role]` - Melihat mapping permission per role.
- `/roleperm attach <role> <perm>` - Menambahkan permission ke suatu role.
- `/roleperm detach <role> <perm>` - Mencabut permission dari suatu role.

### 4. Manajemen Custom Script Bash
- `/listscript` - Menampilkan semua custom script yang telah terdaftar.
- `/addscript ...` - Membuat custom script bash baru (lihat format di bawah).
- `/delscript <nama_command>` - Menghapus custom script.
- `/<nama_command>` - Menjalankan script bash yang telah dibuat secara dinamis.

---

## Mesin Custom Script Bash

SuperAdmin dapat mendaftarkan bash script langsung melalui chat Telegram tanpa perlu login terminal SSH. Script dapat ditargetkan ke server **Galaxy** (lokal) atau **Multiverse** (remote SSH).

### Format 1 Baris:
```text
/addscript <nama_command> <galaxy|multiverse> <Judul Script> | <isi_bash_script>
```
*Contoh:*
```text
/addscript cek_uptime galaxy Uptime Server | uptime
/addscript cek_db multiverse Status MySQL | mysqladmin status
```

### Format Multi-Baris (Untuk Script Kompleks):
```text
/addscript <nama_command> <galaxy|multiverse> <Judul Script>
<baris perintah bash 1>
<baris perintah bash 2>
<baris perintah bash 3>
```
*Contoh:*
```text
/addscript cek_full galaxy Diagnosa Lengkap Server
df -h /
free -m
uptime
ss -tlpn
```

### Cara Eksekusi:
Setelah disimpan, perintah dapat dipanggil kapan saja dengan mengetik nama perintahnya langsung:
```text
/cek_uptime
/cek_db
/cek_full
```

---

## Panel Kontrol Interaktif (/menu)

Perintah `/menu` menyediakan Graphical User Interface (GUI) berbasis Inline Keyboard Telegram yang terorganisir ke dalam sub-menu:

```text
[ 🤖 Panel Kendali Utama Server Ngobar ]
├── 1. ⚙️ Konfigurasi & Script Server
│     ├── ▶️ /status_galaxy - Kesehatan Server Galaxy (Web & App)
│     ├── ▶️ /status_multiverse - Kesehatan Server Multiverse (Database)
│     ├── ➕ Buat Script Baru (Panduan format 1 baris & multiline)
│     └── 🗑️ Hapus Script
└── 2. 👥 Manajemen Pengguna & RBAC
      ├── 📋 Daftar User
      ├── ➕ Tambah User | 🗑️ Hapus User
      ├── 🛡️ Kelola Roles | 🔑 Permissions
      └── 🔗 Role Permissions
```

---

## Struktur Direktori Proyek

```text
server-tele-bot/
├── .env.example             # Template konfigurasi environment variable
├── .gitignore               # Konfigurasi file yang diabaikan git
├── README.md                # Dokumentasi lengkap sistem bot
├── bot.py                   # Entrypoint utama bot & konfigurasi system polling
├── config.py                # Loader konfigurasi berbasis dotenv
├── ngobar-bot.service       # Template file unit Linux systemd daemon
├── requirements.txt         # Daftar dependensi library Python
│
├── data/
│   └── bot.db               # Database SQLite lokal (WAL mode aktif)
│
├── database/
│   ├── db.py                # Inisialisasi skema tabel SQLite, WAL mode & seeding default
│   └── user_repo.py         # Repositori query: Users, Roles, Permissions, Scripts, Audit
│
├── handlers/
│   ├── admin.py             # Handler CRUD user, roles, permissions, dan roleperm
│   ├── common.py            # Handler /start, /ping, /help, /clean, /restart
│   ├── menu.py              # Handler UI panel kendali interaktif berbasis tombol inline
│   └── scripts.py           # Handler /addscript, /delscript, /listscript, & interceptor dinamis
│
├── middleware/
│   └── auth.py              # Decorator otorisasi @can, @has_role, & sanitasi input
│
└── services/
    ├── metrics.py           # Kolektor metrik sistem Galaxy & batch SSH Multiverse
    ├── script_runner.py     # Engine eksekutor bash (lokal & remote) + pemotong output
    └── ssh_client.py        # Klien SSH keyless ke Server Multiverse (BatchMode)
```

---

## Instalasi & Pengujian Lokal

Bot dilengkapi dengan **Deteksi Platform Otomatis** (`Dev Mode`). Saat dijalankan di Windows atau environment lokal tanpa SSH key Linux, bot otomatis menyimulasikan respon server tanpa melempar exception atau memicu timeout.

### 1. Clone & Masuk ke Folder:
```bash
cd server-tele-bot
```

### 2. Buat Virtual Environment (Opsional tapi Direkomendasikan):
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependensi:
```bash
pip install -r requirements.txt
```

### 4. Siapkan File `.env`:
Salin template dan sesuaikan isinya:
```bash
cp .env.example .env
```

### 5. Jalankan Bot:
```bash
python bot.py
```

---

## Konfigurasi Environment (.env)

Buat file `.env` di root folder `server-tele-bot/`:

```ini
# Telegram Bot Configuration
BOT_TOKEN=your_telegram_bot_token_here
SUPERADMIN_ID=your_telegram_user_id_here

# Server Multiverse SSH Configuration
MULTIVERSE_IP=your_multiverse_ip_here
MULTIVERSE_PORT=65002
MULTIVERSE_USER=root
SSH_KEY_PATH=/root/.ssh/id_bot_ed25519

# SQLite Database Location
DB_PATH=data/bot.db
```

---

## Panduan Deployment Produksi (Linux Systemd)

### 1. Sinkronisasi File ke Server Galaxy (Aman)
Gunakan `rsync` dengan mengecualikan file database lokal dan file `.env` produksi:
```bash
rsync -avz --exclude='data/bot.db*' --exclude='.env' --exclude='__pycache__' server-tele-bot/ root@<IP_SERVER_GALAXY>:/root/server-bot/
```

### 2. Setup di Server Galaxy:
```bash
cd /root/server-bot

# Install dependensi sistem
pip3 install -r requirements.txt

# Siapkan file .env jika belum ada
cp .env.example .env
nano .env
```

### 3. Pasang Systemd Daemon Unit:
```bash
cp /root/server-bot/ngobar-bot.service /etc/systemd/system/ngobar-bot.service
systemctl daemon-reload
systemctl enable ngobar-bot
systemctl restart ngobar-bot
systemctl status ngobar-bot --no-pager
```

### 4. Memantau Log Realtime:
```bash
journalctl -u ngobar-bot -f -n 50
```

---

## Audit Keamanan & Stabilitas Runtime

Sistem bot ini telah melewati proses audit komprehensif dengan mitigasi risiko berikut:

1. **Zero Secret Hardcoding:** Tidak ada token atau IP yang tertanam di kode sumber.
2. **Koneksi SSH Non-Interaktif:** Modul [`services/ssh_client.py`](file:///g:/CODING/blogspot/server-tele-bot/services/ssh_client.py) menggunakan opsi `-o BatchMode=yes` dan `-o ConnectTimeout=5` untuk mencegah terminal hanging saat meminta password.
3. **Pencegahan Denial of Service (DoS) Telegram API:** Output eksekusi dipotong maksimal 3500 karakter dengan label pemotongan transparan sebelum dibungkus formatting code block.
4. **Resistensi Concurrency SQLite:** Mode WAL memungkinkan proses pembacaan dan penulisan log audit berjalan simultan tanpa memicu `OperationalError: database is locked`.
5. **Pencatatan Audit Trail:** Setiap perintah yang dieksekusi atau ditolak dicatat ke tabel `audit_logs` bersama ID pengguna dan timestamp lengkap.
