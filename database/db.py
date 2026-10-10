import sqlite3
from contextlib import contextmanager
from config import DB_PATH, SUPERADMIN_ID

@contextmanager
def get_db_connection():
    """Context manager untuk koneksi SQLite yang thread-safe dengan WAL mode"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Inisialisasi tabel RBAC, Commands, dan Server Scripts"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Tabel Users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Tabel Roles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT
            )
        """)

        # 3. Tabel Permissions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT
            )
        """)

        # 4. Tabel Commands (Menu Autocomplete Global)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                permission_id INTEGER REFERENCES permissions(id) ON DELETE SET NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        # 5. Tabel Server Scripts (Custom Script Bash Dinamis)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_name TEXT UNIQUE NOT NULL,  -- e.g. 'cek_disk', 'cek_status'
                title TEXT NOT NULL,
                target_server TEXT NOT NULL CHECK(target_server IN ('galaxy', 'multiverse')),
                script_content TEXT NOT NULL,       -- isi bash script
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        # 6. Pivot user_roles & role_permissions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, role_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
                PRIMARY KEY (role_id, permission_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # === SEEDER DATA DEFAULT ===
        default_permissions = [
            ("server:metrics", "Melihat metrik dan kesehatan server (/ping)"),
            ("server:clean", "Mengeksekusi pembersihan sampah server (/clean)"),
            ("server:restart", "Merestart layanan server Nginx/PHP (/restart)"),
            ("server:scripts", "Membuat dan mengeksekusi custom script bash"),
            ("users:view", "Melihat daftar pengguna whitelist (/listuser)"),
            ("users:manage", "Menambah/menghapus pengguna & mengatur role (/adduser, /deluser)"),
            ("rbac:manage", "Mengelola roles, permissions, dan prompt commands")
        ]
        cursor.executemany("INSERT OR IGNORE INTO permissions (name, description) VALUES (?, ?)", default_permissions)

        default_roles = [
            ("superadmin", "Akses kontrol penuh ke seluruh sistem"),
            ("admin", "Akses monitoring dan pemeliharaan server"),
            ("viewer", "Akses baca dan monitoring kesehatan server")
        ]
        cursor.executemany("INSERT OR IGNORE INTO roles (name, description) VALUES (?, ?)", default_roles)

        # Mapping permissions ke roles
        role_permission_map = {
            "superadmin": ["server:metrics", "server:clean", "server:restart", "server:scripts", "users:view", "users:manage", "rbac:manage"],
            "admin": ["server:metrics", "server:clean", "server:restart", "users:view"],
            "viewer": ["server:metrics", "users:view"]
        }

        # Pastikan role admin tidak memiliki akses server:scripts dari seed lama
        cursor.execute("""
            DELETE FROM role_permissions 
            WHERE role_id = (SELECT id FROM roles WHERE name = 'admin')
              AND permission_id = (SELECT id FROM permissions WHERE name = 'server:scripts')
        """)

        for role_name, perm_list in role_permission_map.items():
            cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
            r_row = cursor.fetchone()
            if not r_row:
                continue
            for p_name in perm_list:
                cursor.execute("SELECT id FROM permissions WHERE name = ?", (p_name,))
                p_row = cursor.fetchone()
                if p_row:
                    cursor.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (r_row["id"], p_row["id"]))

        # Seed Script Kesehatan Server Galaxy & Multiverse
        default_scripts = [
            ("status_galaxy", "Kesehatan Server Galaxy (Web & App)", "galaxy", (
                "echo '=== [1. DISK & STORAGE] ==='\n"
                "df -h /\n\n"
                "echo '=== [2. PENGGUNAAN RAM & SWAP] ==='\n"
                "free -h\n\n"
                "echo '=== [3. CPU LOAD & UPTIME] ==='\n"
                "uptime\n\n"
                "echo '=== [4. STATUS LAYANAN UTAMA] ==='\n"
                "for svc in nginx php7.4-fpm redis-server; do echo \"$svc: $(systemctl is-active $svc 2>/dev/null || echo 'inactive')\"; done\n\n"
                "echo '=== [5. PORT LISTENING AKTIF] ==='\n"
                "ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u | paste -sd, -"
            ), SUPERADMIN_ID),
            ("status_multiverse", "Kesehatan Server Multiverse (Database)", "multiverse", (
                "echo '=== [1. DISK & STORAGE] ==='\n"
                "df -h /\n\n"
                "echo '=== [2. PENGGUNAAN RAM] ==='\n"
                "free -h\n\n"
                "echo '=== [3. CPU LOAD & UPTIME] ==='\n"
                "uptime\n\n"
                "echo '=== [4. STATUS LAYANAN MYSQL DATABASE] ==='\n"
                "echo \"mysql: $(systemctl is-active mysql 2>/dev/null || echo 'inactive')\"\n"
                "mysqladmin status 2>/dev/null || true\n\n"
                "echo '=== [5. PORT LISTENING AKTIF] ==='\n"
                "ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u | paste -sd, -"
            ), SUPERADMIN_ID)
        ]
        # Bersihkan contoh script lama
        cursor.execute("DELETE FROM server_scripts WHERE command_name IN ('cek_disk', 'cek_ram', 'cek_db_status')")
        cursor.executemany("""
            INSERT OR REPLACE INTO server_scripts (command_name, title, target_server, script_content, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, default_scripts)

        # Seed SuperAdmin
        cursor.execute("SELECT id FROM users WHERE id = ?", (SUPERADMIN_ID,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (id, username, full_name) VALUES (?, 'Owner', 'Super Admin')", (SUPERADMIN_ID,))
            cursor.execute("SELECT id FROM roles WHERE name = 'superadmin'")
            s_role = cursor.fetchone()
            if s_role:
                cursor.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)", (SUPERADMIN_ID, s_role["id"]))
