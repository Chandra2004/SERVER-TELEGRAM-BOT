from typing import List, Dict, Any, Optional
from database.db import get_db_connection
from config import SUPERADMIN_ID

# ==========================================
# 1. OTORISASI & GATE PERMISSION
# ==========================================

def user_can(user_id: int, permission_name: str) -> bool:
    """Memeriksa apakah user memiliki permission tertentu melalui role-nya"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 
            FROM user_roles ur
            JOIN role_permissions rp ON ur.role_id = rp.role_id
            JOIN permissions p ON rp.permission_id = p.id
            WHERE ur.user_id = ? AND p.name = ?
            LIMIT 1
        """, (user_id, permission_name))
        return cursor.fetchone() is not None

def user_has_role(user_id: int, role_name: str) -> bool:
    """Memeriksa apakah user memiliki role spesifik"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
            FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = ? AND r.name = ?
            LIMIT 1
        """, (user_id, role_name.lower()))
        return cursor.fetchone() is not None

def get_user_allowed_commands(user_id: int) -> List[Dict[str, str]]:
    """Mengambil daftar prompt command yang boleh diakses user (termasuk custom script)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Commands sistem bawaan
        cursor.execute("""
            SELECT DISTINCT c.command, c.description
            FROM commands c
            LEFT JOIN permissions p ON c.permission_id = p.id
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            LEFT JOIN user_roles ur ON rp.role_id = ur.role_id AND ur.user_id = ?
            WHERE c.is_active = 1 
              AND (c.permission_id IS NULL OR ur.user_id IS NOT NULL)
            ORDER BY c.id ASC
        """, (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]

        # Tambahkan script custom jika user memiliki izin server:scripts
        if user_can(user_id, "server:scripts"):
            cursor.execute("SELECT command_name, title FROM server_scripts WHERE is_active = 1")
            for r in cursor.fetchall():
                rows.append({"command": r["command_name"], "description": f"Script: {r['title']}"})

        return rows

# ==========================================
# 2. CRUD USERS
# ==========================================

def add_user_with_role(user_id: int, role_name: str, username: Optional[str] = None, full_name: Optional[str] = None) -> bool:
    """Menambahkan user baru dan menempelkan role ke user tersebut"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        role_row = cursor.fetchone()
        if not role_row:
            return False
        role_id = role_row["id"]

        cursor.execute("""
            INSERT INTO users (id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                full_name = COALESCE(excluded.full_name, users.full_name)
        """, (user_id, username, full_name))

        cursor.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        cursor.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (user_id, role_id))
        return True

def delete_user(user_id: int) -> bool:
    """Menghapus user dari whitelist. Superadmin utama tidak dapat dihapus."""
    if user_id == SUPERADMIN_ID:
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0

def list_all_users() -> List[Dict[str, Any]]:
    """Mengambil semua user beserta role yang dimiliki"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                u.id, 
                u.username, 
                u.full_name, 
                u.created_at,
                COALESCE(GROUP_CONCAT(r.name, ', '), 'tanpa role') AS roles
            FROM users u
            LEFT JOIN user_roles ur ON u.id = ur.user_id
            LEFT JOIN roles r ON ur.role_id = r.id
            GROUP BY u.id
            ORDER BY u.created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

# ==========================================
# 3. CRUD ROLES & PERMISSIONS
# ==========================================

def create_role(name: str, description: str = "") -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO roles (name, description) VALUES (?, ?)", (name.lower(), description))
            return True
    except Exception:
        return False

def delete_role(name: str) -> bool:
    if name.lower() in ("superadmin", "viewer"):
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM roles WHERE name = ?", (name.lower(),))
        return cursor.rowcount > 0

def list_all_roles() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description FROM roles ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

def create_permission(name: str, description: str = "") -> bool:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO permissions (name, description) VALUES (?, ?)", (name, description))
            return True
    except Exception:
        return False

def delete_permission(name: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM permissions WHERE name = ?", (name,))
        return cursor.rowcount > 0

def list_all_permissions() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description FROM permissions ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

def attach_permission_to_role(role_name: str, permission_name: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name.lower(),))
        r_row = cursor.fetchone()
        cursor.execute("SELECT id FROM permissions WHERE name = ?", (permission_name,))
        p_row = cursor.fetchone()
        if not r_row or not p_row:
            return False
        cursor.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)", (r_row["id"], p_row["id"]))
        return True

def detach_permission_from_role(role_name: str, permission_name: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name.lower(),))
        r_row = cursor.fetchone()
        cursor.execute("SELECT id FROM permissions WHERE name = ?", (permission_name,))
        p_row = cursor.fetchone()
        if not r_row or not p_row:
            return False
        cursor.execute("DELETE FROM role_permissions WHERE role_id = ? AND permission_id = ? ", (r_row["id"], p_row["id"]))
        return cursor.rowcount > 0

def list_role_permissions(role_name: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT r.name as role, GROUP_CONCAT(p.name, ', ') as permissions
            FROM roles r
            LEFT JOIN role_permissions rp ON r.id = rp.role_id
            LEFT JOIN permissions p ON rp.permission_id = p.id
        """
        params = []
        if role_name:
            query += " WHERE r.name = ?"
            params.append(role_name.lower())
        query += " GROUP BY r.id ORDER BY r.id ASC"
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

# ==========================================
# 4. CRUD SERVER SCRIPTS (BASH PROMPTS)
# ==========================================

def save_server_script(command_name: str, title: str, target_server: str, script_content: str, created_by: int) -> bool:
    """Menyimpan atau memperbarui script custom bash"""
    # Bersihkan nama command (hanya huruf kecil, angka, underscore)
    clean_cmd = command_name.lower().replace("-", "_").lstrip("/")
    clean_target = target_server.lower()
    if clean_target not in ("galaxy", "multiverse"):
        clean_target = "galaxy"

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO server_scripts (command_name, title, target_server, script_content, created_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(command_name) DO UPDATE SET
                    title = excluded.title,
                    target_server = excluded.target_server,
                    script_content = excluded.script_content
            """, (clean_cmd, title, clean_target, script_content, created_by))
            return True
    except Exception:
        return False

def get_server_script(command_name: str) -> Optional[Dict[str, Any]]:
    """Mengambil data script berdasarkan nama command"""
    clean_cmd = command_name.lower().replace("-", "_").lstrip("/")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM server_scripts WHERE command_name = ? AND is_active = 1", (clean_cmd,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_server_script(command_name: str) -> bool:
    """Menghapus script custom"""
    clean_cmd = command_name.lower().replace("-", "_").lstrip("/")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM server_scripts WHERE command_name = ?", (clean_cmd,))
        return cursor.rowcount > 0

def list_server_scripts() -> List[Dict[str, Any]]:
    """Mengambil seluruh daftar script custom aktif"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, command_name, title, target_server, script_content FROM server_scripts WHERE is_active = 1 ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

# ==========================================
# 5. AUDIT LOGS
# ==========================================

def log_audit(user_id: int, action: str, status: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO audit_logs (user_id, action, status) VALUES (?, ?, ?)", (user_id, action, status))
    except Exception:
        pass
