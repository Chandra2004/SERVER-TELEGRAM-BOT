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

        # Seed Script Kesehatan Server Galaxy & Multiverse (Format Rapi & Mobile-Friendly)
        galaxy_script = (
            "echo '[1. PENYIMPANAN DISK]'\n"
            "df -h / | awk 'NR==2 {printf \"  Partisi / : %s / %s (%s terpakai)\\n  Tersedia  : %s\\n\", $3, $2, $5, $4}'\n"
            "echo ''\n"
            "echo '[2. PENGGUNAAN MEMORI]'\n"
            "free -m | awk 'NR==2 {printf \"  RAM       : %.1fG / %.1fG (%.0f%%)\\n  Sisa RAM  : %.1fG\\n\", $3/1024, $2/1024, ($3/$2)*100, $7/1024}'\n"
            "free -m | awk 'NR==3 {if ($2 > 0) printf \"  Swap      : %.0fM / %.0fM (%.0f%%)\\n\", $3, $2, ($3/$2)*100; else print \"  Swap      : Nonaktif\"}'\n"
            "echo ''\n"
            "echo '[3. PROSESOR & UPTIME]'\n"
            "awk '{printf \"  CPU Load  : %s, %s, %s\\n\", $1, $2, $3}' /proc/loadavg\n"
            "uptime -p 2>/dev/null | sed 's/up /  Uptime    : /' || uptime | awk '{print \"  Uptime    : \" $3, $4}'\n"
            "echo ''\n"
            "echo '[4. STATUS LAYANAN]'\n"
            "for svc in nginx php7.4-fpm redis-server; do\n"
            "  st=$(systemctl is-active $svc 2>/dev/null || echo 'inactive')\n"
            "  printf \"  %-12s: [%s]\\n\" \"$svc\" \"$(echo $st | tr 'a-z' 'A-Z')\"\n"
            "done\n"
            "echo ''\n"
            "echo '[5. PORT LISTENING]'\n"
            "ports=$(ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u)\n"
            "out_ports=''\n"
            "for p in $ports; do\n"
            "  case $p in\n"
            "    80) desc='80/HTTP' ;;\n"
            "    443) desc='443/HTTPS' ;;\n"
            "    6001) desc='6001/Soketi' ;;\n"
            "    6379) desc='6379/Redis' ;;\n"
            "    9100) desc='9100/NodeExp' ;;\n"
            "    9121) desc='9121/RedisExp' ;;\n"
            "    9601) desc='9601/Metrics' ;;\n"
            "    45683) desc='45683/SSH' ;;\n"
            "    53) desc='53/DNS' ;;\n"
            "    *) desc=\"$p\" ;;\n"
            "  esac\n"
            "  out_ports=\"${out_ports:+$out_ports, }$desc\"\n"
            "done\n"
            "echo \"  $out_ports\""
        )

        multiverse_script = (
            "echo '[1. PENYIMPANAN DISK]'\n"
            "df -h / | awk 'NR==2 {printf \"  Partisi / : %s / %s (%s terpakai)\\n  Tersedia  : %s\\n\", $3, $2, $5, $4}'\n"
            "echo ''\n"
            "echo '[2. PENGGUNAAN MEMORI]'\n"
            "free -m | awk 'NR==2 {printf \"  RAM       : %.1fG / %.1fG (%.0f%%)\\n  Sisa RAM  : %.1fG\\n\", $3/1024, $2/1024, ($3/$2)*100, $7/1024}'\n"
            "free -m | awk 'NR==3 {if ($2 > 0) printf \"  Swap      : %.0fM / %.0fM (%.0f%%)\\n\", $3, $2, ($3/$2)*100; else print \"  Swap      : Nonaktif\"}'\n"
            "echo ''\n"
            "echo '[3. PROSESOR & UPTIME]'\n"
            "awk '{printf \"  CPU Load  : %s, %s, %s\\n\", $1, $2, $3}' /proc/loadavg\n"
            "uptime -p 2>/dev/null | sed 's/up /  Uptime    : /' || uptime | awk '{print \"  Uptime    : \" $3, $4}'\n"
            "echo ''\n"
            "echo '[4. STATUS LAYANAN MYSQL DATABASE]'\n"
            "st=$(systemctl is-active mysql 2>/dev/null || echo 'inactive')\n"
            "printf \"  MySQL Daemon  : [%s]\\n\" \"$(echo $st | tr 'a-z' 'A-Z')\"\n"
            "if command -v mysqladmin >/dev/null 2>&1; then\n"
            "  ms=$(mysqladmin status 2>/dev/null)\n"
            "  if [ -n \"$ms\" ]; then\n"
            "    th=$(echo \"$ms\" | grep -o 'Threads: [0-9]*' | awk '{print $NF}')\n"
            "    qps=$(echo \"$ms\" | grep -o 'Queries per second avg: [0-9.]*' | awk '{print $NF}')\n"
            "    slow=$(echo \"$ms\" | grep -o 'Slow queries: [0-9]*' | awk '{print $NF}')\n"
            "    echo \"  Threads Aktif : $th\"\n"
            "    echo \"  Rata-rata QPS : $qps\"\n"
            "    echo \"  Slow Queries  : $slow\"\n"
            "  fi\n"
            "fi\n"
            "echo ''\n"
            "echo '[5. PORT LISTENING]'\n"
            "ports=$(ss -tlpn | awk 'NR>1 {split($4, a, \":\"); print a[length(a)]}' | sort -n -u)\n"
            "out_ports=''\n"
            "for p in $ports; do\n"
            "  case $p in\n"
            "    3306) desc='3306/MySQL' ;;\n"
            "    33060) desc='33060/MySQL-X' ;;\n"
            "    65002) desc='65002/SSH' ;;\n"
            "    53) desc='53/DNS' ;;\n"
            "    443) desc='443' ;;\n"
            "    *) desc=\"$p\" ;;\n"
            "  esac\n"
            "  out_ports=\"${out_ports:+$out_ports, }$desc\"\n"
            "done\n"
            "echo \"  $out_ports\""
        )

        default_scripts = [
            ("status_galaxy", "Kesehatan Server Galaxy (Web & App)", "galaxy", galaxy_script, SUPERADMIN_ID),
            ("status_multiverse", "Kesehatan Server Multiverse (Database)", "multiverse", multiverse_script, SUPERADMIN_ID)
        ]
        # Bersihkan contoh script lama
        cursor.execute("DELETE FROM server_scripts WHERE command_name IN ('cek_disk', 'cek_ram', 'cek_db_status')")
        for cmd_name, title, target, content, creator in default_scripts:
            cursor.execute("""
                INSERT INTO server_scripts (command_name, title, target_server, script_content, created_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(command_name) DO UPDATE SET
                    title = excluded.title,
                    target_server = excluded.target_server,
                    script_content = excluded.script_content
            """, (cmd_name, title, target, content, creator))

        # Seed SuperAdmin
        cursor.execute("SELECT id FROM users WHERE id = ?", (SUPERADMIN_ID,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (id, username, full_name) VALUES (?, 'Owner', 'Super Admin')", (SUPERADMIN_ID,))
            cursor.execute("SELECT id FROM roles WHERE name = 'superadmin'")
            s_role = cursor.fetchone()
            if s_role:
                cursor.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)", (SUPERADMIN_ID, s_role["id"]))
