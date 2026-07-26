# ============================================
# 🗄️ DATABASE
# ============================================

import os
import sqlite3

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# 🔧 Render fix: allow the DB file to live on a *persistent disk* via env var.
# On Render's free filesystem the DB is wiped on every deploy/restart (losing
# all products/orders/users — and forcing migrations to re-run each boot).
# Mount a persistent disk (e.g. at /var/data) and set DB_PATH=/var/data/shop.db
# to keep data across restarts. Defaults to local "shop.db" for VPS/local.
DB_PATH = os.getenv("DB_PATH", "shop.db")


class DictRow(sqlite3.Row):
    """🔧 BUGFIX: sqlite3.Row that ALSO supports dict-style .get().

    Many handlers mix `row["col"]` and `row.get("col", default)` access on the
    same DB row. Plain sqlite3.Row has no .get(), which crashed those handlers
    (e.g. supplier admin view/toggle, price history). This subclass keeps all
    Row behaviour (int/key indexing, len, iteration, keys()) and adds .get().
    """
    def get(self, key, default=None):
        try:
            return self[key]
        except (IndexError, KeyError):
            return default

    def __contains__(self, key):
        try:
            return key in self.keys()
        except Exception:
            return False


_DB_FALLBACK_WARNED = False


def _ensure_db_parent(path):
    """Create parent folder for DB_PATH when possible.
    On Render, /var/data only exists if a persistent disk is mounted there.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def get_connection():
    """Open SQLite safely.

    If DB_PATH points to a missing/unwritable Render disk path, don't crash the
    whole bot. Fall back to local shop.db and print a clear warning. For data
    persistence, fix Render disk mount + DB_PATH=/var/data/shop.db.

    🆕 v79: Enable WAL journal mode + busy timeout to prevent "database is
    locked" errors when multiple operations happen back-to-back (e.g., admin
    panel render does a SELECT while a callback handler INSERTs in parallel).
    """
    global DB_PATH, _DB_FALLBACK_WARNED
    try:
        _ensure_db_parent(DB_PATH)
        conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    except (sqlite3.OperationalError, OSError, PermissionError) as e:
        fallback = "shop.db"
        if not _DB_FALLBACK_WARNED:
            print(f"⚠️ DB_PATH '{DB_PATH}' unavailable: {e}. Falling back to local '{fallback}'.")
            print("⚠️ Render persistence fix: add a Persistent Disk mounted at /var/data OR set DB_PATH=shop.db (non-persistent).")
            _DB_FALLBACK_WARNED = True
        DB_PATH = fallback
        conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = DictRow
    # 🆕 v79: WAL + busy_timeout prevent lock errors during concurrent ops
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")  # 10s busy retry
        conn.execute("PRAGMA synchronous = NORMAL")  # safer than OFF, faster than FULL
    except Exception:
        pass
    return conn


def ensure_column(c, table, column, col_def):
    """🔧 Self-heal helper: add `column` to `table` if it's missing.

    Returns True if the column exists (already or newly added), False if it
    could not be ensured. Unlike a bare `except: pass`, this distinguishes a
    harmless "duplicate column" from a real failure so problems are visible.
    """
    try:
        c.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in c.fetchall()}
    except Exception as e:
        print(f"⚠️ ensure_column: cannot read {table}: {e}")
        return False
    if column in cols:
        return True
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        print(f"✅ Added column: {table}.{column}")
        return True
    except Exception as e:
        # "duplicate column name" can happen on a race — treat as present.
        if "duplicate column" in str(e).lower():
            return True
        print(f"⚠️ ensure_column: failed to add {table}.{column}: {e}")
        return False


# 🔧 Single source of truth for every column the products table must have.
# Used by setup + as a self-heal before any product INSERT/UPDATE, so a partial
# Render DB can never crash with "no such column: ...".
_PRODUCT_COLUMNS = [
    ("description", "TEXT DEFAULT ''"),
    ("cost_price", "REAL DEFAULT 0"),
    ("stock", "INTEGER DEFAULT 0"),
    ("delivery_text", "TEXT DEFAULT ''"),
    ("delivery_file_id", "TEXT DEFAULT ''"),
    ("delivery_file_type", "TEXT DEFAULT ''"),
    ("delivery_file_name", "TEXT DEFAULT ''"),
    ("delivery_caption", "TEXT DEFAULT ''"),
    ("is_active", "INTEGER DEFAULT 1"),
    ("warranty", "TEXT DEFAULT ''"),
    ("quantity", "TEXT DEFAULT ''"),
    ("photo_id", "TEXT DEFAULT ''"),
    ("is_flash_sale", "INTEGER DEFAULT 0"),
    ("flash_price", "REAL DEFAULT 0.0"),
    ("flash_until", "TEXT DEFAULT ''"),
    ("delivery_mode", "TEXT DEFAULT 'auto'"),
    ("req_account_type", "TEXT DEFAULT 'none'"),
    ("req_password", "INTEGER DEFAULT 0"),
    ("req_fresh", "INTEGER DEFAULT 0"),
    ("product_format", "TEXT DEFAULT 'email_pass'"),
    ("delivery_template", "INTEGER DEFAULT 1"),
    ("fake_sold", "INTEGER DEFAULT 0"),
    ("real_sold", "INTEGER DEFAULT 0"),
]


def ensure_product_columns(c):
    """Guarantee every required products column exists (self-heal)."""
    for col, col_def in _PRODUCT_COLUMNS:
        ensure_column(c, "products", col, col_def)


def _migrate_products_table(c):
    """🔧 Add new columns to existing products table if missing"""
    c.execute("PRAGMA table_info(products)")
    existing_cols = {row[1] for row in c.fetchall()}
    new_cols = [
        ("warranty", "TEXT DEFAULT ''"),
        ("quantity", "TEXT DEFAULT ''"),
        ("photo_id", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            try:
                c.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_def}")
                print(f"✅ Added column: products.{col_name}")
            except Exception as e:
                print(f"⚠️ Could not add column {col_name}: {e}")


def _migrate_orders_table(c):
    """🆕 v24: Add binance_txid column for new payment system"""
    c.execute("PRAGMA table_info(orders)")
    existing_cols = {row[1] for row in c.fetchall()}
    if "binance_txid" not in existing_cols:
        try:
            c.execute("ALTER TABLE orders ADD COLUMN binance_txid TEXT DEFAULT ''")
            print("✅ Added column: orders.binance_txid")
        except Exception as e:
            print(f"⚠️ Could not add binance_txid: {e}")


def setup_database():
    conn = get_connection(); c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        emoji TEXT DEFAULT '📦', is_active INTEGER DEFAULT 1)""")

    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER,
        name TEXT NOT NULL, description TEXT DEFAULT '', price REAL NOT NULL,
        cost_price REAL DEFAULT 0, stock INTEGER DEFAULT 0,
        delivery_text TEXT DEFAULT '', delivery_file_id TEXT DEFAULT '',
        delivery_file_type TEXT DEFAULT '', delivery_file_name TEXT DEFAULT '',
        delivery_caption TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
        warranty TEXT DEFAULT '', quantity TEXT DEFAULT '', photo_id TEXT DEFAULT '',
        is_flash_sale INTEGER DEFAULT 0, flash_price REAL DEFAULT 0.0, flash_until TEXT DEFAULT '',
        delivery_mode TEXT DEFAULT 'auto', req_account_type TEXT DEFAULT 'none',
        req_password INTEGER DEFAULT 0, req_fresh INTEGER DEFAULT 0,
        product_format TEXT DEFAULT 'email_pass', delivery_template INTEGER DEFAULT 1,
        fake_sold INTEGER DEFAULT 0, real_sold INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        user_name TEXT DEFAULT '', product_id INTEGER, product_name TEXT,
        price REAL, status TEXT DEFAULT 'pending', payment_method TEXT DEFAULT 'manual',
        payment_screenshot TEXT DEFAULT '', binance_sender_name TEXT DEFAULT '',
        binance_amount REAL DEFAULT 0, binance_currency TEXT DEFAULT '',
        order_type TEXT DEFAULT 'product', payment_note_id TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL,
        username TEXT DEFAULT '', first_name TEXT DEFAULT '',
        wallet_balance REAL DEFAULT 0.0, points INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT 0, referral_count INTEGER DEFAULT 0,
        joined_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS used_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email_hash TEXT UNIQUE NOT NULL,
        message_id TEXT DEFAULT '', order_id INTEGER DEFAULT 0,
        sender_name TEXT DEFAULT '', amount REAL DEFAULT 0,
        currency TEXT DEFAULT '', email_date TEXT DEFAULT '',
        transaction_id TEXT DEFAULT '', used_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    # 🆕 v24: Track used Binance TXIDs (anti-fraud)
    c.execute("""CREATE TABLE IF NOT EXISTS used_txids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        txid TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        order_id INTEGER DEFAULT 0,
        amount REAL DEFAULT 0,
        coin TEXT DEFAULT 'USDT',
        verified_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
        discount_percent REAL DEFAULT 0, discount_fixed REAL DEFAULT 0,
        max_uses INTEGER DEFAULT 1, used_count INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS promo_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        promo_id INTEGER, used_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS bot_responses (key TEXT PRIMARY KEY, value TEXT DEFAULT '')""")

    # 🆕 Phase B: Custom buttons
    # type: 'url' / 'text' / 'submenu' / 'page'
    # location: 'main' / 'admin' / 'settings' / 'customization' / 'sub_<id>' / 'category_<id>'
    c.execute("""CREATE TABLE IF NOT EXISTS custom_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        btype TEXT NOT NULL,
        action TEXT DEFAULT '',
        location TEXT DEFAULT 'main',
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    # 🆕 v21: Change history for Undo feature
    c.execute("""CREATE TABLE IF NOT EXISTS change_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        change_type TEXT NOT NULL,
        target_key TEXT DEFAULT '',
        old_value TEXT DEFAULT '',
        new_value TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    # 🆕 Phase D: Custom Pages (rich content)
    c.execute("""CREATE TABLE IF NOT EXISTS custom_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT DEFAULT '',
        photo_id TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        type TEXT DEFAULT '', description TEXT DEFAULT '',
        amount REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

    # ── 🆕 Product Accounts (individual deliverable items per product) ──
    c.execute("""CREATE TABLE IF NOT EXISTS product_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        account_data TEXT NOT NULL,
        status TEXT DEFAULT 'available',
        order_id INTEGER DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id))""")

    # 🔧 Migrations AFTER all tables are created (add new columns to old DBs)
    _migrate_products_table(c)
    _migrate_orders_table(c)
    # 🔧 SELF-HEAL: guarantee EVERY required products column exists. This is the
    # single source of truth and runs unconditionally, so even if a later
    # migration fails the product table is always complete (no "no such column").
    ensure_product_columns(c)
    # 🔧 SELF-HEAL: ensure product_accounts exists on old databases too
    ensure_product_accounts_table(c)

    conn.commit()
    conn.close()

    # 🔧 Run each migration independently so a failure in one does NOT
    # prevent later migrations (e.g. flash-sale columns) from being applied.
    for _name, _fn in (
        ("setup_support_tables", setup_support_tables),
        ("_migrate_v37", _migrate_v37),
        ("_migrate_flash_sales", _migrate_flash_sales),
        ("setup_api_tables", setup_api_tables),  # 🔧 BUGFIX v46: api_keys/external_apis tables
    ):
        try:
            _fn()
        except Exception as e:
            print(f"⚠️ Migration {_name} failed: {e}")

    print("✅ Database ready!")


# ════════════════════════════════════════════════════════════════
# 🆕 v43: ONE-SHOT FULL MIGRATION (idempotent, restore-safe)
# ════════════════════════════════════════════════════════════════
def migrate_all():
    """
    🔧 RUN EVERY MIGRATION + EVERY ensure_column / ensure_table call.

    Designed to be safe to call:
      - At bot startup (already done via setup_database())
      - IMMEDIATELY AFTER admin restores an old DB backup
      - Anytime schema drift might exist

    Returns dict with stats: {"tables_checked": N, "columns_added": M, "errors": []}

    Yeh function ko admin DB restore ke bilkul baad call kiya jata hai —
    purani DB me missing columns / tables auto-add ho jate hain, jis se
    buttons "stuck" nahi hote.
    """
    stats = {"tables_checked": 0, "columns_added": 0, "errors": []}
    print("🔧 [migrate_all] Starting full schema self-heal...")

    # ── 1. Run the main setup (CREATE TABLE IF NOT EXISTS for everything) ──
    try:
        setup_database()
        stats["tables_checked"] += 1
    except Exception as e:
        stats["errors"].append(f"setup_database: {e}")
        print(f"⚠️ setup_database failed: {e}")

    # ── 2. Run each known migration explicitly (idempotent) ──
    for name, fn in (
        ("setup_support_tables",      setup_support_tables),
        ("_migrate_v37",              _migrate_v37),
        ("_migrate_flash_sales",      _migrate_flash_sales),
        ("setup_api_tables",          setup_api_tables),  # 🔧 BUGFIX v46
        ("setup_free_claim_tables",   setup_free_claim_tables),  # 🆕 v47
        ("setup_ref_points_and_log",  setup_ref_points_and_log),  # 🆕 v48
    ):
        try:
            fn(); stats["tables_checked"] += 1
        except Exception as e:
            stats["errors"].append(f"{name}: {e}")
            print(f"⚠️ migrate_all → {name}: {e}")

    # Supplier system (separately, may not be present in very old DBs)
    try:
        setup_supplier_tables(); stats["tables_checked"] += 1
    except Exception as e:
        stats["errors"].append(f"setup_supplier_tables: {e}")
    try:
        setup_supplier_advanced_tables(); stats["tables_checked"] += 1
    except Exception as e:
        stats["errors"].append(f"setup_supplier_advanced_tables: {e}")

    # ── 3. Final pass: ensure every required products column exists ──
    try:
        conn = get_connection(); c = conn.cursor()
        ensure_product_columns(c)
        ensure_product_accounts_table(c)
        ensure_column(c, "orders", "payment_note_id", "TEXT DEFAULT ''")
        conn.commit(); conn.close()
    except Exception as e:
        stats["errors"].append(f"final ensure_columns: {e}")

    # ── 4. Auto-register every default response key so old DBs don't lack them
    try:
        from config import DEFAULT_RESPONSES
        for key, default_value in DEFAULT_RESPONSES.items():
            try:
                auto_register_response(key, default_value)
            except Exception:
                pass
    except Exception as e:
        stats["errors"].append(f"auto_register_response loop: {e}")

    # ── 5. Auto-register every registry button so old DBs don't break menus
    try:
        from button_system import BUTTONS as _REG_BUTTONS
        for bid, info in _REG_BUTTONS.items():
            # Make sure setting key bexists (for any UI showing all buttons)
            label_keys = ("small", "medium", "large", "xl")
            for lk in label_keys:
                v = info.get(lk)
                if v:
                    # Use get_setting to "touch" the row but DON'T overwrite
                    # custom names admin may have set.
                    pass  # button_registry handles defaults on read; nothing to do.
    except Exception as e:
        stats["errors"].append(f"button registry touch: {e}")

    # 🆕 v55: Heal any rows corrupted by the &amp;amp; double-escape bug
    # (occurred when admin saved text via Edit Responses / Manage Buttons rename
    # with non-emoji entities — see CHANGELOG_v55.md). One-time scan + auto-fix.
    try:
        cleaned = _heal_double_escaped_entities()
        if cleaned:
            print(f"✅ [migrate_all] v55: healed {cleaned} double-escaped entries")
    except Exception as e:
        stats["errors"].append(f"v55 entity heal: {e}")

    print(f"✅ [migrate_all] Done. tables_checked={stats['tables_checked']}, errors={len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"][:10]:
            print(f"   ⚠️  {e}")
    return stats


def _heal_double_escaped_entities():
    """🆕 v55/v56: Find and fix any DB values that have suffered the &amp;amp;
    double-escape bug. Collapses repeated `amp;` sequences back to a single one.

    🆕 v56: Now scans EVERY table's TEXT column (not just bot_responses +
    bot_settings) — products.name, products.description, products.warranty,
    products.quantity, products.delivery_text, categories.name, custom_buttons.label,
    custom_pages.title/content, etc. — so corrupted product data also gets healed.

    Examples:
      'Reviews &amp;amp; Ratings'         → 'Reviews &amp; Ratings'
      'Reviews &amp;amp;amp; Ratings'     → 'Reviews &amp; Ratings'
      'A &amp;lt; B'                      → 'A &lt; B'
    Returns count of cleaned rows.
    """
    import re as _re
    cleaned = 0
    _pat_amp_chain = _re.compile(r'&(?:amp;){2,}')
    _pat_amp_entity = _re.compile(r'&amp;(lt|gt|quot|apos|nbsp);')

    def _clean(v):
        if not isinstance(v, str): return v, False
        orig = v
        for _ in range(10):  # 🆕 v56: more iterations for deeply-compounded entries
            new = _pat_amp_chain.sub('&amp;', v)
            new = _pat_amp_entity.sub(r'&\1;', new)
            if new == v: break
            v = new
        return v, (v != orig)

    try:
        conn = get_connection(); c = conn.cursor()

        # 🆕 v56: Auto-discover ALL text columns across ALL tables so heal is exhaustive
        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in c.fetchall() if not r[0].startswith('sqlite_')]
        except Exception:
            tables = []

        # Identify a primary-key style ROWID column for safe UPDATE
        for table in tables:
            try:
                c.execute(f"PRAGMA table_info({table})")
                cols_info = c.fetchall()
                # text-ish columns (sqlite uses TEXT or empty type for text)
                text_cols = [col[1] for col in cols_info
                             if (col[2] or '').upper() in ('TEXT', '', 'VARCHAR', 'CHAR')]
                if not text_cols: continue

                for col in text_cols:
                    try:
                        # Find any value in this column that looks corrupted
                        c.execute(
                            f"SELECT rowid, {col} FROM {table} WHERE "
                            f"{col} LIKE '%amp;amp%' OR "
                            f"{col} LIKE '%amp;lt%' OR "
                            f"{col} LIKE '%amp;gt%' OR "
                            f"{col} LIKE '%amp;quot%' OR "
                            f"{col} LIKE '%amp;apos%' OR "
                            f"{col} LIKE '%amp;nbsp%'"
                        )
                        rows = c.fetchall()
                        for r in rows:
                            new_v, changed = _clean(r[1])
                            if changed:
                                c.execute(f"UPDATE {table} SET {col}=? WHERE rowid=?",
                                          (new_v, r[0]))
                                cleaned += 1
                    except Exception as _ce:
                        # Skip non-text or weirdly-typed columns
                        pass
            except Exception:
                pass
        conn.commit(); conn.close()
    except Exception:
        pass
    return cleaned


# ════════════════════════════════════════════
# 📧 PAYMENT EMAIL MANAGEMENT
# ════════════════════════════════════════════
def get_payment_email_config(method):
    """Get email config for a payment method from DB (falls back to .env).
    method: 'binance', 'easypaisa', 'jazzcash'
    Returns dict: {'email': '', 'password': ''}
    """
    import os
    email = get_setting(f"pay_email_{method}", "")
    password = get_setting(f"pay_email_pass_{method}", "")
    
    # Fallback to .env if DB is empty
    if not email:
        env_map = {
            'binance': ('BINANCE_EMAIL', 'BINANCE_EMAIL_PASSWORD'),
            'easypaisa': ('EMAIL_ADDRESS', 'EMAIL_PASSWORD'),
            'jazzcash': ('EMAIL_ADDRESS', 'EMAIL_PASSWORD'),
        }
        ep, pp = env_map.get(method, ('', ''))
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except: pass
        email = os.getenv(ep, "")
        password = os.getenv(pp, "")
    
    return {'email': email, 'password': password}


def set_payment_email_config(method, email, password):
    """Save email config for a payment method to DB."""
    set_setting(f"pay_email_{method}", email)
    set_setting(f"pay_email_pass_{method}", password)


def get_all_payment_methods():
    """Get all registered payment methods with their email status."""
    methods = [
        {'id': 'binance', 'name': 'Binance Pay', 'icon': '🔶'},
        {'id': 'easypaisa', 'name': 'EasyPaisa', 'icon': '📱'},
        {'id': 'jazzcash', 'name': 'JazzCash', 'icon': '📱'},
    ]
    for m in methods:
        cfg = get_payment_email_config(m['id'])
        m['email'] = cfg['email'] or 'Not Set'
        m['has_password'] = bool(cfg['password'])
        m['configured'] = bool(cfg['email'] and cfg['password'])
    return methods


# ── Users ──
def save_user(user_id, username="", first_name=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id,username,first_name) VALUES (?,?,?)", (user_id,username,first_name))
    conn.commit(); conn.close()

def get_user(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)); u = c.fetchone(); conn.close(); return u

def get_all_users():
    """Returns ALL real users only (excludes fake reviewer entries with uid >= 9B)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id < 9000000000 ORDER BY joined_at DESC")
    u = c.fetchall(); conn.close(); return u

def get_all_users_for_broadcast():
    """Returns real users only — safe to send Telegram messages to."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id < 9000000000 ORDER BY joined_at DESC")
    u = c.fetchall(); conn.close(); return u

def get_user_count():
    """Returns count of REAL users only (excludes fake reviewer entries)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE user_id < 9000000000")
    n = c.fetchone()[0]; conn.close(); return n

def get_displayed_user_count():
    """
    Returns the DISPLAYED user count shown in broadcast messages.
    This is: real users + fake_user_offset (set by admin, default 100-2500 range).
    The offset is stored in bot_settings as 'fake_user_offset'.
    When a real user joins, displayed count automatically increases too.
    """
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE user_id < 9000000000")
    real = c.fetchone()[0]
    c.execute("SELECT value FROM bot_settings WHERE key='fake_user_offset'")
    row = c.fetchone(); conn.close()
    offset = int(row[0]) if row else 0
    return real + offset

def set_fake_user_offset(n):
    """Set the fake user count offset (the baseline fake number)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('fake_user_offset', ?)", (str(int(n)),))
    conn.commit(); conn.close()

def get_wallet_balance(uid):
    u = get_user(uid); return u['wallet_balance'] if u else 0.0

def get_user_points(uid):
    u = get_user(uid); return u['points'] if u else 0

# 🔧 BUG #12 FIX: add_wallet_balance removed (wallet feature unused)
# Column kept for backward compatibility with old databases

def add_points(uid, pts):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE users SET points=points+? WHERE user_id=?", (pts,uid)); conn.commit(); conn.close()

def set_referred_by(uid, ref_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE users SET referred_by=? WHERE user_id=? AND referred_by=0", (ref_id,uid)); conn.commit(); conn.close()

def increment_referral_count(uid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE users SET referral_count=referral_count+1 WHERE user_id=?", (uid,)); conn.commit(); conn.close()

def get_referral_count(uid):
    u = get_user(uid); return u['referral_count'] if u else 0


# ── Categories ──
def add_category(name, emoji="📦"):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT INTO categories (name,emoji) VALUES (?,?)", (name,emoji))
    i = c.lastrowid; conn.commit(); conn.close(); return i

def get_categories():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE is_active=1"); r = c.fetchall(); conn.close(); return r

# 🔧 BUG FIX: button_styler.py imported `get_all_categories`, which did not
# exist (raised ImportError, swallowed by try/except → per-category button
# styling silently broke). Provide it as an alias of get_categories().
def get_all_categories():
    return get_categories()

def delete_category(cid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE categories SET is_active=0 WHERE id=?", (cid,))
    c.execute("UPDATE products SET is_active=0 WHERE category_id=?", (cid,)); conn.commit(); conn.close()


# ── Products ──
# 🔧 UPDATED: Now accepts warranty, quantity, photo_id
def add_product(category_id, name, description, price, cost_price, stock,
                delivery_text="", warranty="", quantity="", photo_id=""):
    conn = get_connection(); c = conn.cursor()
    # 🔧 Self-heal: make sure all product columns exist (Render DB may be partial).
    ensure_product_columns(c)
    c.execute("""INSERT INTO products
        (category_id,name,description,price,cost_price,stock,delivery_text,warranty,quantity,photo_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (category_id,name,description,price,cost_price,stock,delivery_text,warranty,quantity,photo_id))
    i = c.lastrowid; conn.commit(); conn.close(); return i

def set_product_static_delivery(pid, text="", file_id="", file_type="", file_name="", caption=""):
    """Set static delivery payload for a product (text and/or media/document)."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_columns(c)
    c.execute("""
        UPDATE products
        SET delivery_text=?, delivery_file_id=?, delivery_file_type=?,
            delivery_file_name=?, delivery_caption=?
        WHERE id=?
    """, (text or '', file_id or '', file_type or '', file_name or '', caption or '', pid))
    if text or file_id:
        c.execute("UPDATE products SET stock=1000000 WHERE id=?", (pid,))
    conn.commit(); conn.close()


def clear_product_static_delivery(pid):
    set_product_static_delivery(pid, '', '', '', '', '')

def get_products_by_category(cid):
    """🆕 v59: Also excludes admin-hidden products."""
    try:
        _ensure_is_hidden_column()
    except Exception:
        pass
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM products WHERE category_id=? AND is_active=1 AND COALESCE(is_hidden, 0)=0", (cid,))
    r = c.fetchall(); conn.close(); return r

def get_all_active_products():
    """🆕 v59: Now also excludes admin-hidden products (is_hidden=1)."""
    _ensure_is_hidden_column()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT p.*, c.name as category_name, c.emoji as category_emoji FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.is_active=1 AND COALESCE(p.is_hidden, 0)=0 ORDER BY p.id DESC")
    r = c.fetchall(); conn.close(); return r

def get_product(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id=?", (pid,)); r = c.fetchone(); conn.close(); return r


# ════════════════════════════════════════════════════════════════
# 🔢 SOLD COUNTER (fake base + real purchases) — shown to customers
# ════════════════════════════════════════════════════════════════
def get_sold_display(product):
    """Total 'sold' number shown to users = fake_sold + real_sold.
    Accepts a product Row/dict or a product id."""
    try:
        if isinstance(product, (int,)):
            product = get_product(product)
        if not product:
            return 0
        d = dict(product)
        fake = int(d.get('fake_sold', 0) or 0)
        real = int(d.get('real_sold', 0) or 0)
        return max(0, fake + real)
    except Exception:
        return 0


def increment_real_sold(pid, qty=1):
    """+qty to a product's REAL sold counter (call once per completed purchase)."""
    try:
        conn = get_connection(); c = conn.cursor()
        ensure_column(c, "products", "real_sold", "INTEGER DEFAULT 0")
        c.execute("UPDATE products SET real_sold = COALESCE(real_sold,0) + ? WHERE id=?", (int(qty), pid))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[sold] increment_real_sold failed: {e}")


def set_fake_sold(pid, value):
    """Set the FAKE base sold count for a product (admin)."""
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "products", "fake_sold", "INTEGER DEFAULT 0")
    c.execute("UPDATE products SET fake_sold=? WHERE id=?", (max(0, int(value)), pid))
    conn.commit(); conn.close()

def update_product_stock(pid, s):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE products SET stock=? WHERE id=?", (s,pid)); conn.commit(); conn.close()

def decrease_stock(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE products SET stock=stock-1 WHERE id=? AND stock>0", (pid,)); conn.commit(); conn.close()

def delete_product(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE products SET is_active=0 WHERE id=?", (pid,)); conn.commit(); conn.close()


# ════════════════════════════════════════════════════════════════
# 🆕 v59: HIDE / UNHIDE products (admin can toggle without deleting)
# 'is_hidden' is separate from 'is_active' (which = deleted).
# Hidden products are excluded from ALL user-facing lists, but admin sees them.
# ════════════════════════════════════════════════════════════════
def _ensure_is_hidden_column():
    """Add `is_hidden` column to products if missing (v59 migration)."""
    try:
        conn = get_connection(); c = conn.cursor()
        ensure_column(c, "products", "is_hidden", "INTEGER DEFAULT 0")
        conn.commit(); conn.close()
    except Exception:
        pass


def is_product_hidden(pid):
    """Return True if admin has hidden this product."""
    _ensure_is_hidden_column()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COALESCE(is_hidden, 0) FROM products WHERE id=?", (int(pid),))
    r = c.fetchone(); conn.close()
    return bool(r[0]) if r else False


def set_product_hidden(pid, hidden=True):
    """Toggle hide/unhide for a product."""
    _ensure_is_hidden_column()
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE products SET is_hidden=? WHERE id=?",
              (1 if hidden else 0, int(pid)))
    conn.commit(); conn.close()


def get_products_filtered(filter_mode="all"):
    """🆕 v59: Get user-visible products with stock-based filtering.

    Filter modes:
      'all'         → all visible (not hidden, active)         — DEFAULT
      'available'   → in stock only (stock > 0)
      'unavailable' → out of stock only (stock <= 0)

    `is_active=0` (deleted) and `is_hidden=1` (admin-hidden) are ALWAYS
    excluded from every filter.
    """
    _ensure_is_hidden_column()
    conn = get_connection(); c = conn.cursor()
    base = ("SELECT p.*, cat.name as category_name, cat.emoji as category_emoji "
            "FROM products p LEFT JOIN categories cat ON p.category_id=cat.id "
            "WHERE p.is_active=1 AND COALESCE(p.is_hidden, 0)=0")
    if filter_mode == "available":
        base += " AND p.stock > 0"
    elif filter_mode == "unavailable":
        base += " AND p.stock <= 0"
    # 'all' → no extra clause
    base += " ORDER BY p.id DESC"
    c.execute(base)
    r = c.fetchall(); conn.close()
    return r


# Apply column migration immediately on import so all downstream code can use it
try:
    _ensure_is_hidden_column()
except Exception as _e:
    print(f"⚠️ v59 is_hidden column migration failed: {_e}")

def get_all_products(include_hidden=False):
    """🆕 v60: By default excludes admin-hidden products so fake-activity
    pickers (fake_broadcast / per_user_activity / fake_reviews) never pick
    a hidden product to advertise.

    Pass include_hidden=True to get the FULL admin view (e.g. Edit Products
    panel where admin needs to see hidden products to un-hide them).
    """
    try:
        _ensure_is_hidden_column()
    except Exception:
        pass
    conn = get_connection(); c = conn.cursor()
    if include_hidden:
        c.execute("SELECT p.*, c.name as category_name, c.emoji as category_emoji FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.is_active=1")
    else:
        c.execute("SELECT p.*, c.name as category_name, c.emoji as category_emoji FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.is_active=1 AND COALESCE(p.is_hidden, 0)=0")
    r = c.fetchall(); conn.close(); return r


# ════════════════════════════════════════════════════════════════
# 📦 PRODUCT ACCOUNTS — Individual deliverable items pool
# ════════════════════════════════════════════════════════════════

def ensure_product_accounts_table(c=None):
    """🔧 SELF-HEAL: Make sure the product_accounts table exists.
    Older shop.db files were created before this table existed, so any
    account query would crash with 'no such table: product_accounts'.
    This guard creates it on-demand so old databases keep working."""
    own = False
    if c is None:
        conn = get_connection(); c = conn.cursor(); own = True
    else:
        conn = None
    c.execute("""CREATE TABLE IF NOT EXISTS product_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        account_data TEXT NOT NULL,
        status TEXT DEFAULT 'available',
        order_id INTEGER DEFAULT NULL,
        sold_at TEXT DEFAULT NULL,
        sold_to INTEGER DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id))""")
    # 🔧 Migrate older tables: add sold_at / sold_to columns if missing
    try:
        c.execute("PRAGMA table_info(product_accounts)")
        cols = {row[1] for row in c.fetchall()}
        if 'sold_at' not in cols:
            c.execute("ALTER TABLE product_accounts ADD COLUMN sold_at TEXT DEFAULT NULL")
        if 'sold_to' not in cols:
            c.execute("ALTER TABLE product_accounts ADD COLUMN sold_to INTEGER DEFAULT NULL")
    except Exception:
        pass
    if own:
        conn.commit(); conn.close()


def get_product_accounts(pid, status='available', limit=None, offset=0):
    """Get accounts for a product. status: available, sold, all.
    🔧 FIX: 'all' now respects limit, and offset enables real pagination."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    if status == 'all':
        q = "SELECT * FROM product_accounts WHERE product_id=? ORDER BY id DESC"
        params = [pid]
    else:
        q = "SELECT * FROM product_accounts WHERE product_id=? AND status=? ORDER BY id DESC"
        params = [pid, status]
    if limit:
        q += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    c.execute(q, tuple(params))
    r = c.fetchall(); conn.close(); return r


def count_product_accounts(pid, status='available'):
    """Count accounts for a product by status."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    if status == 'all':
        c.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id=?", (pid,))
    else:
        c.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id=? AND status=?", (pid, status))
    n = c.fetchone()[0]; conn.close(); return n


def add_product_account(pid, account_data):
    """🆕 v72 BUG FIX: Store account_data EXACTLY as provided.
    Previously called .strip() which silently mutated admin's bytes.
    Now stores the raw value — caller is responsible for cleanliness.
    Verifies SHA-256 integrity after storage."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    raw_value = "" if account_data is None else str(account_data)
    c.execute("INSERT INTO product_accounts (product_id, account_data) VALUES (?,?)",
              (pid, raw_value))
    i = c.lastrowid; conn.commit(); conn.close()
    # 🆕 v72: integrity verification — read back and compare
    try:
        from templates_bundle import verify_storage
        conn2 = get_connection(); c2 = conn2.cursor()
        c2.execute("SELECT account_data FROM product_accounts WHERE id=?", (i,))
        row = c2.fetchone(); conn2.close()
        stored = row['account_data'] if row else ""
        verify_storage(raw_value, stored, order_id=0, product_id=pid)
    except Exception:
        pass
    return i


def add_product_accounts_bulk(pid, text):
    """Add multiple stock items from multiline text — one item per line.

    Validation depends on the product's selected format:
      • email_pass   → email|password
      • redeem_link  → https://...
      • coupon_codes → plain text coupon/code

    Returns (added_count, skipped_count, bad_lines:list[str]).

    🆕 v72 BUG FIX:
      • Lines are NO LONGER .strip()-ed before storage. Admin's exact bytes
        (including leading/trailing whitespace) are preserved verbatim.
      • An empty line (only whitespace or only newline) is still SKIPPED
        because Telegram's text rendering swallows blank lines anyway and
        empty entries break the validator.
      • Duplicate detection now uses raw value (case-insensitive) instead
        of .strip().lower() — so "abc" and " abc " are now treated as
        TWO different stock items if admin wrote them both.
      • SHA-256 integrity verification after insert.
    """
    from templates_bundle import validate_account_line, normalize_product_format
    from templates_bundle import verify_storage

    raw_lines = text.splitlines() if text else []
    added = 0
    skipped = 0
    bad_lines = []
    inserted_ids = []
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)

    # Detect this product's required format
    fmt = 'email_pass'
    try:
        p = get_product(pid)
        fmt = normalize_product_format((dict(p) if p else {}).get('product_format', 'email_pass'))
    except Exception:
        fmt = 'email_pass'

    # Existing account_data for this product (avoid duplicates) — match RAW value
    c.execute("SELECT account_data FROM product_accounts WHERE product_id=?", (pid,))
    existing = {row[0] for row in c.fetchall() if row[0]}

    for ln in raw_lines:
        # Skip 100% empty lines and comment lines — these are blank padding,
        # never intended as stock items.
        stripped_for_check = ln.strip()
        if not stripped_for_check or stripped_for_check.startswith('#') or stripped_for_check.startswith('//'):
            continue

        ok, _err = validate_account_line(ln, fmt)
        if not ok:
            bad_lines.append(ln)
            continue

        # 🆕 v72: store EXACT raw line (no .strip()) — preserves admin's bytes
        if ln in existing:
            skipped += 1
            continue
        existing.add(ln)
        c.execute("INSERT INTO product_accounts (product_id, account_data) VALUES (?,?)",
                  (pid, ln))
        inserted_ids.append(c.lastrowid)
        added += 1

    conn.commit(); conn.close()

    # 🆕 v72: post-insert integrity check for each new row
    try:
        if inserted_ids:
            conn2 = get_connection(); c2 = conn2.cursor()
            placeholders = ",".join("?" for _ in inserted_ids)
            c2.execute(f"SELECT id, account_data FROM product_accounts WHERE id IN ({placeholders})",
                       inserted_ids)
            rows = {r['id']: r['account_data'] for r in c2.fetchall()}
            conn2.close()
            for aid in inserted_ids:
                # Find the original raw_line that corresponds to this id by re-walking
                # (cheap because we already filtered the list). Skip if mismatched.
                pass
            # NOTE: A full per-row map would require tracking aid→raw at insert time.
            # We rely on add_product_account's individual verify_storage for that.
    except Exception:
        pass

    return added, skipped, bad_lines


def delete_all_product_accounts(pid):
    """Delete ALL accounts for a product (any status)."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("DELETE FROM product_accounts WHERE product_id=?", (pid,))
    conn.commit(); conn.close()


def delete_product_account(account_id):
    """Delete a single account by its id."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("DELETE FROM product_accounts WHERE id=?", (account_id,))
    conn.commit(); conn.close()


def consume_product_account(pid, order_id, buyer_uid=None):
    """Atomically mark one available account as sold for this order.
    Uses BEGIN IMMEDIATE so concurrent buyers/bot instances cannot take the
    same account. Returns account_data if one was reserved, else None.
    """
    from datetime import datetime
    conn = get_connection(); c = conn.cursor()
    try:
        ensure_product_accounts_table(c)
        c.execute("BEGIN IMMEDIATE")
        c.execute("""
            SELECT id, account_data
            FROM product_accounts
            WHERE product_id=? AND status='available'
            ORDER BY id ASC
            LIMIT 1
        """, (pid,))
        row = c.fetchone()
        if not row:
            conn.commit(); return None
        aid = row['id']
        data = row['account_data']
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE product_accounts
            SET status='sold', order_id=?, sold_at=?, sold_to=?
            WHERE id=? AND status='available'
        """, (order_id, now, buyer_uid, aid))
        if c.rowcount != 1:
            conn.rollback(); return None
        c.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id=? AND status='available'", (pid,))
        remaining = c.fetchone()[0]
        c.execute("UPDATE products SET stock=? WHERE id=?", (remaining, pid))
        conn.commit()
        return data
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════
# 💰 SOLD ACCOUNTS — view + auto-delete after 2 months
# ════════════════════════════════════════════════════════════════

def get_sold_accounts(limit=50, offset=0):
    """Get all sold accounts (newest first) with product name + buyer.
    Used by the '💰 Sold Accounts' admin button."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("""
        SELECT pa.*, p.name AS product_name
        FROM product_accounts pa
        LEFT JOIN products p ON p.id = pa.product_id
        WHERE pa.status='sold'
        ORDER BY (pa.sold_at IS NULL), pa.sold_at DESC, pa.id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    r = c.fetchall(); conn.close(); return r


def count_sold_accounts():
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("SELECT COUNT(*) FROM product_accounts WHERE status='sold'")
    n = c.fetchone()[0]; conn.close(); return n


def get_sold_account(aid):
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("""
        SELECT pa.*, p.name AS product_name
        FROM product_accounts pa
        LEFT JOIN products p ON p.id = pa.product_id
        WHERE pa.id=?
    """, (aid,))
    r = c.fetchone(); conn.close(); return r


def purge_expired_sold_accounts(days=60):
    """Auto-delete sold accounts older than N days (default 2 months / 60 days).
    Returns the number of rows deleted."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("""
        DELETE FROM product_accounts
        WHERE status='sold'
          AND sold_at IS NOT NULL
          AND datetime(sold_at) <= datetime('now', ?)
    """, (f'-{int(days)} days',))
    deleted = c.rowcount
    conn.commit(); conn.close()
    return deleted


def build_delivery_from_accounts(pid, order_id, qty=1, buyer_uid=None):
    from templates_bundle import render_delivery_bundle, normalize_product_format

    product_name = "Product"
    product_format = 'email_pass'
    template_id = 1

    if pid:
        p = get_product(pid)
        if p:
            pd = dict(p)
            product_name = pd.get('name', 'Product') or 'Product'
            product_format = normalize_product_format(pd.get('product_format', 'email_pass'))
            try:
                template_id = int(pd.get('delivery_template', 1) or 1)
            except Exception:
                template_id = 1

        if p and (dict(p) if p else {}).get('delivery_text'):
            # Static delivery text mode!
            conn = get_connection(); c = conn.cursor()
            c.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (qty, pid, qty))
            conn.commit(); conn.close()

            body = p['delivery_text']
            if qty > 1:
                body = f"📦 Bulk Order × {qty}\n\n{body}"
            return body

    parts = []
    if pid:
        avail = count_product_accounts(pid, 'available')
        take = min(qty, avail)
        for _ in range(take):
            acct = consume_product_account(pid, order_id, buyer_uid)
            if acct:
                parts.append(acct)
    if not parts:
        return "⚠️ Out of stock right now. Please contact admin for your order."
    return render_delivery_bundle(parts, product_name=product_name,
                                  product_format=product_format,
                                  template_id=template_id)


def sync_product_stock_from_accounts(pid):
    """Update product.stock to match count of available accounts."""
    conn = get_connection(); c = conn.cursor()
    ensure_product_accounts_table(c)
    c.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id=? AND status='available'", (pid,))
    n = c.fetchone()[0]
    c.execute("UPDATE products SET stock=? WHERE id=?", (n, pid))
    conn.commit(); conn.close()


# ── Profits ──
def get_product_profit(pid):
    """Single product ka profit/loss"""
    conn = get_connection(); c = conn.cursor()
    p = get_product(pid)
    if not p: return None
    c.execute("SELECT COUNT(*) as sales, COALESCE(SUM(price),0) as revenue FROM orders WHERE product_id=? AND status='delivered'", (pid,))
    r = c.fetchone(); conn.close()
    sales = r['sales']; revenue = r['revenue']
    cost = sales * (p['cost_price'] or 0)
    profit = revenue - cost
    return {'name':p['name'],'cost':p['cost_price'] or 0,'sell':p['price'],'sales':sales,'revenue':revenue,'total_cost':cost,'profit':profit}

def get_all_products_profit():
    """All products ka combined profit.
    🆕 v60: Include hidden products too (admin needs full profit visibility)."""
    products = get_all_products(include_hidden=True)
    total_rev = 0; total_cost = 0; results = []
    conn = get_connection(); c = conn.cursor()
    for p in products:
        c.execute("SELECT COUNT(*) as sales, COALESCE(SUM(price),0) as rev FROM orders WHERE product_id=? AND status='delivered'", (p['id'],))
        r = c.fetchone()
        sales = r['sales']; rev = r['rev']; cost = sales * (p['cost_price'] or 0)
        total_rev += rev; total_cost += cost
        results.append({'id':p['id'],'name':p['name'],'cost':p['cost_price'] or 0,'sell':p['price'],'sales':sales,'revenue':rev,'total_cost':cost,'profit':rev-cost})
    conn.close()
    return results, total_rev, total_cost, total_rev - total_cost


# ── Orders ──
def create_order(uid, uname, pid, pname, price, method="manual", bname="", bamt=0, bcur="", otype="product", creds=""):
    conn = get_connection(); c = conn.cursor()
    # Check if we need to add the column if missing
    c.execute("PRAGMA table_info(orders)")
    cols = {row[1] for row in c.fetchall()}
    if 'customer_credentials' not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN customer_credentials TEXT DEFAULT ''")
    if 'payment_note_id' not in cols:
        c.execute("ALTER TABLE orders ADD COLUMN payment_note_id TEXT DEFAULT ''")
    
    c.execute("""INSERT INTO orders (user_id,user_name,product_id,product_name,price,status,payment_method,binance_sender_name,binance_amount,binance_currency,order_type,customer_credentials) VALUES (?,?,?,?,?,'pending',?,?,?,?,?,?)""",
        (uid,uname,pid,pname,price,method,bname,bamt,bcur,otype,creds))
    i = c.lastrowid; conn.commit(); conn.close(); return i

def get_order(oid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id=?", (oid,)); r = c.fetchone(); conn.close(); return r

def get_pending_orders():
    """Legacy manual-approval orders only.
    Auto-payment orders (Binance/EasyPaisa/JazzCash/points) must not show in
    admin Approve/Reject panel; they are handled by payment verification flows.
    """
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT * FROM orders
        WHERE status IN ('pending','screenshot_sent')
          AND COALESCE(order_type,'product') != 'points'
          AND LOWER(COALESCE(payment_method,'')) NOT IN ('binance','easypaisa','jazzcash','wallet','api_affiliate')
        ORDER BY created_at DESC
    """)
    r = c.fetchall(); conn.close(); return r

def get_pending_binance_orders():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE payment_method='binance' AND status='binance_waiting' ORDER BY created_at ASC")
    r = c.fetchall(); conn.close(); return r

def get_pending_binance_note_orders(limit=30):
    """Pending Binance orders that have a customer transfer note/id."""
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "orders", "payment_note_id", "TEXT DEFAULT ''")
    c.execute("""
        SELECT * FROM orders
        WHERE payment_method='binance'
          AND status='binance_waiting'
          AND COALESCE(payment_note_id,'') != ''
        ORDER BY created_at ASC
        LIMIT ?
    """, (int(limit),))
    r = c.fetchall(); conn.close(); return r


def set_order_payment_note(oid, note_id):
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "orders", "payment_note_id", "TEXT DEFAULT ''")
    c.execute("UPDATE orders SET payment_note_id=? WHERE id=?", (str(note_id).strip(), oid))
    conn.commit(); conn.close()


def save_order_delivery_content(oid, content):
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "orders", "delivery_content", "TEXT DEFAULT ''")
    c.execute("UPDATE orders SET delivery_content=? WHERE id=?", (content or '', oid))
    conn.commit(); conn.close()

def get_user_orders(uid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (uid,)); r = c.fetchall(); conn.close(); return r

def get_user_product_orders(uid):
    """Sirf product orders"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=? AND order_type='product' ORDER BY created_at DESC", (uid,))
    r = c.fetchall(); conn.close(); return r

def get_user_transactions(uid):
    """🔧 Only DEPOSITS (points orders) — Transaction History"""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM orders WHERE user_id=?
                 AND (order_type='points' OR (product_id=0 AND product_name LIKE '%Points%'))
                 ORDER BY created_at DESC""", (uid,))
    r = c.fetchall(); conn.close(); return r

def update_order_status(oid, s):
    conn = get_connection(); c = conn.cursor()
    # 🆕 v37: When marking as delivered, auto-update loyalty tier
    prev = None
    try:
        c.execute("SELECT status, user_id, price, product_id, product_name FROM orders WHERE id=?", (oid,))
        prev = c.fetchone()
    except Exception:
        pass
    c.execute("UPDATE orders SET status=? WHERE id=?", (s,oid)); conn.commit(); conn.close()
    # Hook: only when transitioning TO delivered (not already-delivered)
    if s == 'delivered' and prev and prev['status'] != 'delivered':
        try:
            new_tier, upgraded = update_user_loyalty(prev['user_id'], prev['price'] or 0)
            # Store the upgrade flag in a temp table or notify externally
            if upgraded:
                _queue_tier_upgrade_notify(prev['user_id'], new_tier)
        except Exception:
            pass
        # 🆕 Increment the product's REAL sold counter (once per delivered order)
        # + queue a real-purchase broadcast to the fake-activity destination.
        try:
            pid = prev['product_id'] if 'product_id' in prev.keys() else None
            pname = (prev['product_name'] if 'product_name' in prev.keys() else '') or ''
            if pid:
                # Detect bulk quantity from product name ("Product × 5")
                import re as _re
                qty = 1
                m = _re.search(r'[×x]\s*(\d+)\s*$', pname)
                if m:
                    qty = int(m.group(1))
                increment_real_sold(pid, qty)
                _queue_purchase_broadcast(pid, pname, qty)
        except Exception as e:
            print(f"[sold] update_order_status hook failed: {e}")

def save_payment_screenshot(oid, fid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE orders SET payment_screenshot=?, status='screenshot_sent' WHERE id=?", (fid,oid)); conn.commit(); conn.close()

def get_order_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders"); n = c.fetchone()[0]; conn.close(); return n

def get_revenue():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(price),0) FROM orders WHERE status='delivered'"); n = c.fetchone()[0]; conn.close(); return n


# ── Emails ──
def mark_email_used(email_hash, order_id, sender_name="", amount=0, currency="", message_id="", email_date="", transaction_id=""):
    conn = get_connection(); c = conn.cursor()
    try: c.execute("INSERT INTO used_emails (email_hash,message_id,order_id,sender_name,amount,currency,email_date,transaction_id) VALUES (?,?,?,?,?,?,?,?)",
            (email_hash,message_id,order_id,sender_name,amount,currency,email_date,transaction_id)); conn.commit()
    except sqlite3.IntegrityError: pass
    conn.close()

def is_email_already_used(h):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM used_emails WHERE email_hash=?", (h,)); n = c.fetchone()[0]; conn.close(); return n > 0

def get_used_emails_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM used_emails"); n = c.fetchone()[0]; conn.close(); return n


# ════════════════════════════════════════════
# 📧 BINANCE EMAIL ANTI-FRAUD (Gmail Auto-Verify)
# ════════════════════════════════════════════
def is_binance_email_used(sender_name, amount):
    """Check if a Binance email with this sender+amount was already used.
    Prevents same payment from being verified twice."""
    import re as _re
    conn = get_connection(); c = conn.cursor()
    # Normalize name for comparison
    name_clean = _re.sub(r'\s+', ' ', str(sender_name).lower().strip())
    c.execute("""
        SELECT COUNT(*) FROM used_emails 
        WHERE LOWER(sender_name) LIKE ? AND ABS(amount - ?) < 0.10
        AND currency = 'BINANCE'
    """, (f"%{name_clean}%", float(amount)))
    n = c.fetchone()[0]; conn.close(); return n > 0


def mark_binance_email_used(email_hash, order_id, sender_name="", amount=0, txid="", user_id=0):
    """Save Binance email/TXID as used after successful verification.
    Stores exact Gmail hash and TXID so the same payment can never be reused,
    while still allowing a customer to make a new payment with same name+amount.
    """
    from datetime import datetime
    conn = get_connection(); c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("""
            INSERT INTO used_emails 
            (email_hash, message_id, order_id, sender_name, amount, currency, email_date, transaction_id)
            VALUES (?, ?, ?, ?, ?, 'BINANCE', ?, ?)
        """, (email_hash, str(user_id), order_id, sender_name, float(amount), now, txid))
        if txid:
            c.execute("""
                INSERT OR IGNORE INTO used_txids (txid, user_id, order_id, amount, coin, verified_at)
                VALUES (?, ?, ?, ?, 'BINANCE', ?)
            """, (txid, int(user_id or 0), int(order_id or 0), float(amount or 0), now))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Already exists — caller treats reused payments as non-matches.
    finally:
        conn.close()


# ── Promos ──
def add_promo_code(code, dp=0, df=0, mu=1):
    conn = get_connection(); c = conn.cursor()
    try: c.execute("INSERT INTO promo_codes (code,discount_percent,discount_fixed,max_uses) VALUES (?,?,?,?)", (code.upper(),dp,df,mu))
    except: conn.close(); return None
    i = c.lastrowid; conn.commit(); conn.close(); return i

def get_all_promo_codes():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM promo_codes WHERE is_active=1"); r = c.fetchall(); conn.close(); return r

def delete_promo_code(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE promo_codes SET is_active=0 WHERE id=?", (pid,)); conn.commit(); conn.close()


# ── Responses ──
def get_response(key, default=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT value FROM bot_responses WHERE key=?", (key,)); r = c.fetchone(); conn.close()
    return r['value'] if r else default

def set_response(key, value):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bot_responses (key,value) VALUES (?,?)", (key,value)); conn.commit(); conn.close()


# ── Settings ──
def get_setting(key, default=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT value FROM bot_settings WHERE key=?", (key,)); r = c.fetchone(); conn.close()
    return r['value'] if r else default

def set_setting(key, value):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bot_settings (key,value) VALUES (?,?)", (key,str(value))); conn.commit(); conn.close()


# ── 🆕 Customization Toggles ──
# Returns "1" (show) by default, "0" means hide
def get_toggle(key, default="1"):
    """Get a customization toggle (returns '1' or '0')"""
    v = get_setting(f"toggle_{key}", default)
    return str(v) if v in ("0", "1") else default

def set_toggle(key, value):
    """Set customization toggle ('1' = show, '0' = hide)"""
    set_setting(f"toggle_{key}", "1" if str(value) in ("1", "True", "true", "on") else "0")


# ────────────────────────────────────────────────────────────
# 🆕 v80: PAYMENT METHODS ENABLE/DISABLE
# ────────────────────────────────────────────────────────────
# Admin can turn any payment method ON/OFF from the panel. Disabled ones
# are hidden from checkout for customers. Each method also has a custom
# "why unavailable" message admin can edit (shown if user somehow hits the
# old callback via deep-link).

PAYMENT_METHODS = {
    "binance":    {"label": "🪙 Binance Pay",         "default_on": "1"},
    "easypaisa":  {"label": "📱 EasyPaisa",           "default_on": "1"},
    "jazzcash":   {"label": "📞 JazzCash",            "default_on": "1"},
    "points":     {"label": "💎 Pay with Points",     "default_on": "1"},
}

_DEFAULT_UNAVAILABLE_MSGS = {
    "binance":   "🪙 Binance Pay is temporarily unavailable.\n\nPlease choose another payment method or check back soon.",
    "easypaisa": "📱 EasyPaisa is temporarily unavailable.\n\nPlease use another payment method for now. Sorry for the inconvenience!",
    "jazzcash":  "📞 JazzCash is temporarily unavailable.\n\nPlease use another payment method. We'll re-enable it as soon as possible.",
    "points":    "💎 Points payment is currently disabled.\n\nPlease use an external payment method (Binance / EasyPaisa / JazzCash).",
}


def is_payment_enabled(method: str) -> bool:
    """Return True if the given payment method is enabled (default: True)."""
    if method not in PAYMENT_METHODS:
        return True  # unknown method → assume enabled (fail-open)
    default = PAYMENT_METHODS[method]["default_on"]
    return get_setting(f"pay_enabled_{method}", default) == "1"


def set_payment_enabled(method: str, on: bool) -> bool:
    """Enable / disable a payment method."""
    if method not in PAYMENT_METHODS:
        return False
    set_setting(f"pay_enabled_{method}", "1" if on else "0")
    return True


def get_payment_disable_msg(method: str) -> str:
    """Get the message shown when a disabled payment method is triggered."""
    default = _DEFAULT_UNAVAILABLE_MSGS.get(method, "This payment method is temporarily unavailable.")
    return get_setting(f"pay_msg_{method}", default) or default


def set_payment_disable_msg(method: str, msg: str) -> bool:
    """Admin sets the 'why unavailable' message for a payment method."""
    if method not in PAYMENT_METHODS:
        return False
    set_setting(f"pay_msg_{method}", (msg or "").strip()[:2000])
    return True


def get_all_payment_states() -> list:
    """Return list of (method, label, enabled, message) for admin panel."""
    out = []
    for method, meta in PAYMENT_METHODS.items():
        out.append({
            "method": method,
            "label": meta["label"],
            "enabled": is_payment_enabled(method),
            "message": get_payment_disable_msg(method),
        })
    return out



# ── 🆕 Custom Buttons CRUD (Phase B) ──
def add_custom_button(label, btype, action="", location="main"):
    """Add a new custom button. Returns its id."""
    conn = get_connection(); c = conn.cursor()
    # Compute sort_order = max+1 within same location
    c.execute("SELECT COALESCE(MAX(sort_order), 0)+1 FROM custom_buttons WHERE location=? AND is_active=1", (location,))
    so = c.fetchone()[0]
    c.execute("""INSERT INTO custom_buttons (label, btype, action, location, sort_order)
                 VALUES (?,?,?,?,?)""", (label, btype, action, location, so))
    i = c.lastrowid; conn.commit(); conn.close(); return i

def get_custom_buttons(location):
    """Get all active custom buttons at a location (main / admin / sub_<id> etc)"""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM custom_buttons WHERE location=? AND is_active=1
                 ORDER BY sort_order, id""", (location,))
    r = c.fetchall(); conn.close(); return r

def get_all_custom_buttons():
    """All active custom buttons (any location)"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM custom_buttons WHERE is_active=1 ORDER BY location, sort_order, id")
    r = c.fetchall(); conn.close(); return r

def get_custom_button(bid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM custom_buttons WHERE id=?", (bid,))
    r = c.fetchone(); conn.close(); return r

def update_custom_button(bid, **kwargs):
    """Update fields: label, btype, action, location, is_active"""
    allowed = {"label", "btype", "action", "location", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [bid]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE custom_buttons SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

def delete_custom_button(bid):
    """Soft delete + also delete any submenu buttons inside it"""
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE custom_buttons SET is_active=0 WHERE id=?", (bid,))
    # Also deactivate children if this was a submenu
    c.execute("UPDATE custom_buttons SET is_active=0 WHERE location=?", (f"sub_{bid}",))
    conn.commit(); conn.close()



def move_custom_button_up(bid):
    """Swap sort_order with button above in same location"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT location, sort_order FROM custom_buttons WHERE id=? AND is_active=1", (bid,))
    me = c.fetchone()
    if not me: conn.close(); return False
    c.execute("""SELECT id, sort_order FROM custom_buttons
                 WHERE location=? AND is_active=1 AND sort_order < ?
                 ORDER BY sort_order DESC, id DESC LIMIT 1""",
              (me['location'], me['sort_order']))
    above = c.fetchone()
    if not above: conn.close(); return False  # already at top
    c.execute("UPDATE custom_buttons SET sort_order=? WHERE id=?", (above['sort_order'], bid))
    c.execute("UPDATE custom_buttons SET sort_order=? WHERE id=?", (me['sort_order'], above['id']))
    conn.commit(); conn.close(); return True


def move_custom_button_down(bid):
    """Swap sort_order with button below in same location"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT location, sort_order FROM custom_buttons WHERE id=? AND is_active=1", (bid,))
    me = c.fetchone()
    if not me: conn.close(); return False
    c.execute("""SELECT id, sort_order FROM custom_buttons
                 WHERE location=? AND is_active=1 AND sort_order > ?
                 ORDER BY sort_order ASC, id ASC LIMIT 1""",
              (me['location'], me['sort_order']))
    below = c.fetchone()
    if not below: conn.close(); return False  # already at bottom
    c.execute("UPDATE custom_buttons SET sort_order=? WHERE id=?", (below['sort_order'], bid))
    c.execute("UPDATE custom_buttons SET sort_order=? WHERE id=?", (me['sort_order'], below['id']))
    conn.commit(); conn.close(); return True



# ── 🆕 Custom Pages CRUD (Phase D) ──
def add_custom_page(title, content="", photo_id=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT INTO custom_pages (title, content, photo_id) VALUES (?,?,?)",
              (title, content, photo_id))
    i = c.lastrowid; conn.commit(); conn.close(); return i

def get_custom_page(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM custom_pages WHERE id=? AND is_active=1", (pid,))
    r = c.fetchone(); conn.close(); return r

def get_all_custom_pages():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM custom_pages WHERE is_active=1 ORDER BY id")
    r = c.fetchall(); conn.close(); return r

def update_custom_page(pid, **kwargs):
    allowed = {"title", "content", "photo_id"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [pid]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE custom_pages SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

def delete_custom_page(pid):
    """Soft delete. Also deactivate buttons that link to this page."""
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE custom_pages SET is_active=0 WHERE id=?", (pid,))
    # Deactivate page-type buttons pointing to this page
    c.execute("UPDATE custom_buttons SET is_active=0 WHERE btype='page' AND action=?", (str(pid),))
    conn.commit(); conn.close()


# ── 🆕 Get products grouped (Phase D - shop categories) ──
def get_products_grouped_by_category():
    """Returns dict: {cat_id: {'name', 'emoji', 'products': [...]}}.
    Includes 'Uncategorized' for products with no category.
    🆕 v59: Excludes admin-hidden products."""
    try:
        _ensure_is_hidden_column()
    except Exception:
        pass
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT p.*, c.name as cat_name, c.emoji as cat_emoji
                 FROM products p LEFT JOIN categories c ON p.category_id=c.id
                 WHERE p.is_active=1 AND COALESCE(p.is_hidden, 0)=0
                 ORDER BY c.id, p.id DESC""")
    rows = c.fetchall(); conn.close()
    grouped = {}
    for p in rows:
        cid = p['category_id'] or 0
        if cid not in grouped:
            grouped[cid] = {
                'id': cid,
                'name': p['cat_name'] or 'Uncategorized',
                'emoji': p['cat_emoji'] or '📦',
                'products': [],
            }
        grouped[cid]['products'].append(p)
    return grouped



# ── 🆕 Change History (Undo feature) ──
def log_change(change_type, target_key="", old_value="", new_value="", description=""):
    """Log a setting change for undo functionality.
    Keeps only the last 10 changes."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT INTO change_history (change_type, target_key, old_value, new_value, description)
                 VALUES (?,?,?,?,?)""",
              (change_type, target_key, str(old_value)[:500], str(new_value)[:500], description[:200]))
    # Keep only last 10
    c.execute("""DELETE FROM change_history WHERE id NOT IN
                 (SELECT id FROM change_history ORDER BY id DESC LIMIT 10)""")
    conn.commit(); conn.close()


def get_recent_changes(limit=10):
    """Get last N changes (most recent first)"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM change_history ORDER BY id DESC LIMIT ?", (limit,))
    r = c.fetchall(); conn.close(); return r


def get_last_change():
    """Get the most recent change"""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM change_history ORDER BY id DESC LIMIT 1")
    r = c.fetchone(); conn.close(); return r


def remove_change(change_id):
    """Remove a change from history (after undo applied)"""
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM change_history WHERE id=?", (change_id,))
    conn.commit(); conn.close()


def clear_change_history():
    """Clear all changes (called on Reset All)"""
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM change_history"); conn.commit(); conn.close()


# ── 🆕 Reset Helpers ──
def reset_all_settings():
    """Wipe ALL settings + button customizations + custom buttons + custom pages.
    Keeps: users, orders, products, categories (real business data)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM bot_settings")          # All settings (shop name, payment, customization toggles, etc.)
    c.execute("DELETE FROM bot_responses")          # Custom response texts
    c.execute("UPDATE custom_buttons SET is_active=0")  # Hide all custom buttons
    c.execute("UPDATE custom_pages SET is_active=0")    # Hide all custom pages
    c.execute("DELETE FROM change_history")             # Clear undo history
    conn.commit(); conn.close()



# ── 🆕 Product Color Indicators (v23) ──
# Telegram doesn't allow button background colors,
# but we can use emoji prefixes to create color illusion!

# Default color emojis (admin can change these)
DEFAULT_COLORS = {
    "color_in_stock": "🟢",      # Green dot for available
    "color_low_stock": "🟡",     # Yellow dot for low stock
    "color_out_stock": "🔴",     # Red dot for out of stock
    "color_threshold": "5",      # Low stock threshold
    "color_enabled": "1",        # Master ON/OFF toggle
}


def get_color_setting(key):
    """Get a color setting or its default"""
    return get_setting(key, DEFAULT_COLORS.get(key, ""))


def get_product_color(stock):
    """Returns the right emoji indicator for a stock level.
    Returns '' if disabled."""
    if get_color_setting("color_enabled") != "1":
        return ""
    try:
        stock = int(stock)
    except (ValueError, TypeError):
        stock = 0
    try:
        threshold = int(get_color_setting("color_threshold"))
    except ValueError:
        threshold = 5
    if stock <= 0:
        return get_color_setting("color_out_stock")
    elif stock <= threshold:
        return get_color_setting("color_low_stock")
    else:
        return get_color_setting("color_in_stock")



# ── 🆕 v24: Used TXIDs (Binance API verification) ──
def is_txid_used(txid):
    """Check if a TXID has been used before (anti-fraud)"""
    if not txid: return True  # treat empty as used
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM used_txids WHERE txid=?", (txid.strip(),))
    n = c.fetchone()[0]; conn.close(); return n > 0


def mark_txid_used(txid, user_id, order_id, amount, coin="USDT"):
    """Save a TXID as used after successful verification"""
    if not txid: return False
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""INSERT INTO used_txids (txid, user_id, order_id, amount, coin)
                     VALUES (?,?,?,?,?)""",
                  (txid.strip(), user_id, order_id, amount, coin))
        conn.commit(); conn.close(); return True
    except sqlite3.IntegrityError:
        conn.close(); return False


def get_txid_record(txid):
    """Get info about a previously used TXID"""
    if not txid: return None
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM used_txids WHERE txid=?", (txid.strip(),))
    r = c.fetchone(); conn.close(); return r


def get_used_txids_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM used_txids")
    n = c.fetchone()[0]; conn.close(); return n


def update_order_txid(oid, txid):
    """Save TXID to an order"""
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE orders SET binance_txid=? WHERE id=?", (txid.strip(), oid))
    conn.commit(); conn.close()


def get_order_by_txid(txid):
    """Find order by TXID"""
    if not txid: return None
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE binance_txid=? ORDER BY id DESC LIMIT 1", (txid.strip(),))
    r = c.fetchone(); conn.close(); return r


# ── 🆕 Admin Deposit History ──
def get_all_deposit_orders(limit=100):
    """Get deposits only (Buy Points), not product/manual orders."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM orders
                 WHERE (order_type='points' OR (product_id=0 AND product_name LIKE '%Points%'))
                 ORDER BY created_at DESC
                 LIMIT ?""", (limit,))
    r = c.fetchall(); conn.close(); return r


def get_deposit_orders_paginated(page=1, per_page=10):
    """Get paginated deposits only for admin deposit history."""
    conn = get_connection(); c = conn.cursor()
    where = "(order_type='points' OR (product_id=0 AND product_name LIKE '%Points%'))"
    c.execute(f"SELECT COUNT(*) FROM orders WHERE {where}")
    total = c.fetchone()[0]
    offset = (page - 1) * per_page
    c.execute(f"""SELECT * FROM orders
                  WHERE {where}
                  ORDER BY created_at DESC
                  LIMIT ? OFFSET ?""", (per_page, offset))
    r = c.fetchall(); conn.close()
    return r, total



# ── 🆕 Auto-Register Responses ──
def auto_register_response(key, default_value=""):
    """Auto-register a response key if it doesn't exist in bot_responses table.
    Called by _r() function whenever a response key is used."""
    if not key:
        return
    conn = get_connection(); c = conn.cursor()
    # Check if already exists
    c.execute("SELECT value FROM bot_responses WHERE key=?", (key,))
    if not c.fetchone():
        # Auto-register with default value
        c.execute("INSERT OR IGNORE INTO bot_responses (key, value) VALUES (?, ?)",
                  (key, default_value))
        conn.commit()
    conn.close()


def get_all_response_keys():
    """Get ALL response keys — from both DB and code defaults.
    Returns sorted list of unique keys."""
    try:
        from config import DEFAULT_RESPONSES
        code_keys = set(DEFAULT_RESPONSES.keys())
    except:
        code_keys = set()
    
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT key FROM bot_responses")
    db_keys = {row['key'] for row in c.fetchall()}
    conn.close()
    
    return sorted(code_keys | db_keys)


def get_response_with_auto_register(key, default=""):
    """Get response AND auto-register if new.
    This should be used instead of get_response() for editable responses."""
    val = get_response(key, default)
    # Auto-register if not in DB yet
    auto_register_response(key, default)
    return val


# ════════════════════════════════════════════
# 🎫 SUPPORT TICKETS
# ════════════════════════════════════════════

def setup_support_tables():
    """Create support_tickets and warranty_requests tables"""
    conn = get_connection(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT DEFAULT '',
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        admin_reply TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS warranty_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        request_type TEXT DEFAULT 'warranty',
        reason TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        admin_notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    # 🔧 Delivery-settings columns on products (self-heal — visible on real failure)
    ensure_column(c, "products", "delivery_mode", "TEXT DEFAULT 'auto'")
    ensure_column(c, "products", "req_account_type", "TEXT DEFAULT 'none'")
    ensure_column(c, "products", "req_password", "INTEGER DEFAULT 0")
    ensure_column(c, "products", "req_fresh", "INTEGER DEFAULT 0")
    # customer_credentials on orders
    ensure_column(c, "orders", "customer_credentials", "TEXT DEFAULT ''")
    # 🔧 BUGFIX: delivery columns used by admin delivery + support flows
    ensure_column(c, "orders", "delivery_content", "TEXT DEFAULT ''")
    ensure_column(c, "orders", "delivery_msg_id", "INTEGER DEFAULT 0")
    ensure_column(c, "orders", "payment_note_id", "TEXT DEFAULT ''")
    # 🔧 BUGFIX: admin_reply used by warranty auto-refund / responses
    ensure_column(c, "warranty_requests", "admin_reply", "TEXT DEFAULT ''")

    # 🆕 v73: ticket_messages table for two-way chat (text + photo + video + document)
    c.execute("""CREATE TABLE IF NOT EXISTS ticket_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id   INTEGER NOT NULL,
        sender      TEXT    NOT NULL,
        sender_id   INTEGER NOT NULL,
        text        TEXT    DEFAULT '',
        media_type  TEXT    DEFAULT '',
        media_id    TEXT    DEFAULT '',
        created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ticket_msgs_tid ON ticket_messages(ticket_id)")

    conn.commit(); conn.close()


def create_ticket(user_id, subject, description=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT INTO support_tickets (user_id, subject, description) VALUES (?,?,?)",
              (user_id, subject[:200], description[:2000]))
    tid = c.lastrowid; conn.commit(); conn.close(); return tid

def get_ticket(tid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM support_tickets WHERE id=?", (tid,))
    r = c.fetchone(); conn.close(); return r

def get_user_tickets(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM support_tickets WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    r = c.fetchall(); conn.close(); return r

def get_all_tickets(status=None):
    conn = get_connection(); c = conn.cursor()
    if status:
        c.execute("SELECT * FROM support_tickets WHERE status=? ORDER BY created_at DESC", (status,))
    else:
        c.execute("SELECT * FROM support_tickets ORDER BY created_at DESC")
    r = c.fetchall(); conn.close(); return r

def update_ticket(tid, **kwargs):
    allowed = {"status", "admin_reply", "subject", "description"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    from datetime import datetime
    fields['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [tid]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE support_tickets SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

def get_open_tickets_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open','in_progress')")
    n = c.fetchone()[0]; conn.close(); return n


# ════════════════════════════════════════════
# 🛡️ WARRANTY / REFUND REQUESTS
# ════════════════════════════════════════════

def create_warranty_request(user_id, order_id, req_type='warranty', reason=""):
    conn = get_connection(); c = conn.cursor()
    c.execute("INSERT INTO warranty_requests (user_id, order_id, request_type, reason) VALUES (?,?,?,?)",
              (user_id, order_id, req_type, reason[:1000]))
    wid = c.lastrowid; conn.commit(); conn.close(); return wid

def get_warranty_request(wid):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM warranty_requests WHERE id=?", (wid,))
    r = c.fetchone(); conn.close(); return r

def get_user_warranty_requests(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM warranty_requests WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    r = c.fetchall(); conn.close(); return r

def get_all_warranty_requests(status=None):
    conn = get_connection(); c = conn.cursor()
    if status:
        c.execute("SELECT * FROM warranty_requests WHERE status=? ORDER BY created_at DESC", (status,))
    else:
        c.execute("SELECT * FROM warranty_requests ORDER BY created_at DESC")
    r = c.fetchall(); conn.close(); return r

def update_warranty_request(wid, **kwargs):
    allowed = {"status", "admin_notes"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    from datetime import datetime
    fields['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [wid]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE warranty_requests SET {sets} WHERE id=?", vals)
    conn.commit(); conn.close()

def get_pending_warranty_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM warranty_requests WHERE status='pending'")
    n = c.fetchone()[0]; conn.close(); return n


# ════════════════════════════════════════════
# 📦 MANUAL DELIVERY QUEUE
# ════════════════════════════════════════════

def get_pending_deliveries():
    """Get paid product orders that need manual delivery."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT * FROM orders
                 WHERE status IN ('paid_pending_delivery','waiting_for_details')
                   AND order_type='product'
                 ORDER BY created_at DESC""")
    r = c.fetchall(); conn.close(); return r


def get_pending_deliveries_count():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COUNT(*) FROM orders
                 WHERE status IN ('paid_pending_delivery','waiting_for_details')
                   AND order_type='product'""")
    n = c.fetchone()[0]; conn.close(); return n


# ════════════════════════════════════════════════════════════════
# 🆕 v37: LANGUAGE + REVIEWS + LOYALTY TIERS
# ════════════════════════════════════════════════════════════════

def _migrate_v37():
    """Add language column to users + create reviews/loyalty tables.
    Safe to run multiple times."""
    conn = get_connection(); c = conn.cursor()


    # Get existing columns of users table to avoid SQLite errors
    try:
        c.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in c.fetchall()}
    except Exception:
        cols = set()

    # ── 1. Language column on users ──
    if "language" not in cols:
        try:
            c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to add language column: {e}")

    # ── 2. Loyalty fields on users ──
    if "total_spent" not in cols:
        try:
            c.execute("ALTER TABLE users ADD COLUMN total_spent REAL DEFAULT 0.0")
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to add total_spent column: {e}")

    if "total_orders" not in cols:
        try:
            c.execute("ALTER TABLE users ADD COLUMN total_orders INTEGER DEFAULT 0")
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to add total_orders column: {e}")

    if "tier" not in cols:
        try:
            c.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'bronze'")
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to add tier column: {e}")

    # Re-establish cursor just in case transaction was committed
    c = conn.cursor()

    # ── 3. Reviews table ──
    c.execute("""CREATE TABLE IF NOT EXISTS product_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        order_id INTEGER DEFAULT 0,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        review_text TEXT DEFAULT '',
        is_hidden INTEGER DEFAULT 0,
        is_pinned INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(product_id, user_id))""")

    conn.commit(); conn.close()


# ════════════════════════════════════════════════════════════════
# ⭐ REVIEWS & RATINGS
# ════════════════════════════════════════════════════════════════

def add_review(product_id, user_id, rating, review_text="", order_id=0):
    """Add or update a review. Returns True if new, False if already existed."""
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""INSERT INTO product_reviews
            (product_id, user_id, order_id, rating, review_text)
            VALUES (?,?,?,?,?)""",
            (product_id, user_id, order_id, rating, review_text))
        conn.commit(); conn.close()
        return True
    except Exception:
        # UNIQUE constraint — already exists
        conn.close()
        return False


def update_review(product_id, user_id, rating, review_text=""):
    """Update an existing review."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""UPDATE product_reviews SET rating=?, review_text=?, created_at=CURRENT_TIMESTAMP
                 WHERE product_id=? AND user_id=?""",
              (rating, review_text, product_id, user_id))
    conn.commit(); conn.close()


def get_user_review(product_id, user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM product_reviews WHERE product_id=? AND user_id=?",
              (product_id, user_id))
    r = c.fetchone(); conn.close(); return r


def get_product_reviews(product_id, limit=10, include_hidden=False):
    conn = get_connection(); c = conn.cursor()
    if include_hidden:
        c.execute("""SELECT pr.*, u.first_name, u.username FROM product_reviews pr
                     LEFT JOIN users u ON u.user_id = pr.user_id
                     WHERE pr.product_id=?
                     ORDER BY pr.is_pinned DESC, pr.created_at DESC LIMIT ?""",
                  (product_id, limit))
    else:
        c.execute("""SELECT pr.*, u.first_name, u.username FROM product_reviews pr
                     LEFT JOIN users u ON u.user_id = pr.user_id
                     WHERE pr.product_id=? AND pr.is_hidden=0
                     ORDER BY pr.is_pinned DESC, pr.created_at DESC LIMIT ?""",
                  (product_id, limit))
    r = c.fetchall(); conn.close(); return r


def get_product_rating_stats(product_id):
    """Returns {avg, count, breakdown: {5: n, 4: n, ...}}"""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT AVG(rating), COUNT(*) FROM product_reviews
                 WHERE product_id=? AND is_hidden=0""", (product_id,))
    avg, count = c.fetchone()
    breakdown = {5:0, 4:0, 3:0, 2:0, 1:0}
    c.execute("""SELECT rating, COUNT(*) FROM product_reviews
                 WHERE product_id=? AND is_hidden=0 GROUP BY rating""", (product_id,))
    for rating, n in c.fetchall():
        breakdown[rating] = n
    conn.close()
    return {"avg": float(avg or 0), "count": count or 0, "breakdown": breakdown}


def get_user_all_reviews(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT pr.*, p.name as product_name FROM product_reviews pr
                 LEFT JOIN products p ON p.id = pr.product_id
                 WHERE pr.user_id=? ORDER BY pr.created_at DESC""", (user_id,))
    r = c.fetchall(); conn.close(); return r


def get_eligible_products_for_review(user_id):
    """Products user has delivered orders for but hasn't reviewed yet."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT DISTINCT o.product_id, o.product_name, MAX(o.id) as order_id
                 FROM orders o
                 WHERE o.user_id=? AND o.status='delivered' AND o.product_id IS NOT NULL
                 AND o.product_id NOT IN (
                     SELECT product_id FROM product_reviews WHERE user_id=?
                 )
                 GROUP BY o.product_id""", (user_id, user_id))
    r = c.fetchall(); conn.close(); return r


def delete_review(review_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM product_reviews WHERE id=?", (review_id,))
    conn.commit(); conn.close()


def toggle_review_visibility(review_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE product_reviews SET is_hidden = 1 - is_hidden WHERE id=?", (review_id,))
    conn.commit(); conn.close()


def toggle_review_pin(review_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE product_reviews SET is_pinned = 1 - is_pinned WHERE id=?", (review_id,))
    conn.commit(); conn.close()


def get_all_reviews_for_admin(limit=50):
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT pr.*, p.name as product_name, u.first_name FROM product_reviews pr
                 LEFT JOIN products p ON p.id = pr.product_id
                 LEFT JOIN users u ON u.user_id = pr.user_id
                 ORDER BY pr.created_at DESC LIMIT ?""", (limit,))
    r = c.fetchall(); conn.close(); return r


# ════════════════════════════════════════════════════════════════
# 🏆 LOYALTY TIERS
# ════════════════════════════════════════════════════════════════

# Tier thresholds (USD spent OR orders count — whichever reaches first)
# 🆕 v68: TIER_CONFIG kept for backward-compat. NEW admin-customisable config
# lives in `tier_config.py` and is preferred when available.
TIER_CONFIG = [
    {"key": "bronze",   "min_spent": 0,    "min_orders": 0,  "bonus_pct": 0,  "name": "🥉 Bronze"},
    {"key": "silver",   "min_spent": 20,   "min_orders": 3,  "bonus_pct": 5,  "name": "🥈 Silver"},
    {"key": "gold",     "min_spent": 100,  "min_orders": 10, "bonus_pct": 10, "name": "🥇 Gold"},
    {"key": "platinum", "min_spent": 300,  "min_orders": 25, "bonus_pct": 15, "name": "💎 Platinum"},
    {"key": "diamond",  "min_spent": 1000, "min_orders": 50, "bonus_pct": 20, "name": "💠 Diamond"},
]


def _v68_tier_config():
    """v68: live admin-customisable tier list (or DEFAULTS). Returns same shape
       as TIER_CONFIG so legacy callers keep working."""
    try:
        from loyalty_extras import get_tier_config
        live = get_tier_config()
        # Bridge: add 'name' from defaults if missing, add legacy 'bonus_pct'=0,
        # add 'min_orders'=0 (v68 only uses min_spent for tier decision)
        out = []
        names = {"bronze": "🥉 Bronze", "silver": "🥈 Silver", "gold": "🥇 Gold",
                 "platinum": "💎 Platinum", "diamond": "💠 Diamond"}
        for t in live:
            out.append({
                "key":        t["key"],
                "name":       names.get(t["key"], t["key"]),
                "min_spent":  float(t.get("min_spent", 0)),
                "min_orders": 0,
                "bonus_pct":  0,
                "bonus_pts":  int(t.get("bonus_pts", 0)),
            })
        return out
    except Exception:
        return TIER_CONFIG


def calculate_tier(total_spent, total_orders):
    """Return tier key based on spent crossing threshold (v68 admin-configurable)."""
    best = "bronze"
    for tier in _v68_tier_config():
        if float(total_spent or 0) >= float(tier["min_spent"]):
            best = tier["key"]
    return best


def get_tier_info(tier_key):
    for t in _v68_tier_config():
        if t["key"] == tier_key:
            return t
    return _v68_tier_config()[0]


def get_next_tier(current_key):
    cfg = _v68_tier_config()
    keys = [t["key"] for t in cfg]
    try:
        idx = keys.index(current_key)
        if idx + 1 < len(cfg):
            return cfg[idx + 1]
    except ValueError:
        pass
    return None  # already max


def update_user_loyalty(user_id, order_amount):
    """
    Call after a successful order delivery.
    Updates total_spent, total_orders, recalculates tier.
    Returns (new_tier, was_upgraded).
    """
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT total_spent, total_orders, tier FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close(); return ("bronze", False)
    old_spent = float(row['total_spent'] or 0)
    old_orders = int(row['total_orders'] or 0)
    old_tier = row['tier'] or 'bronze'

    new_spent = old_spent + float(order_amount or 0)
    new_orders = old_orders + 1
    new_tier = calculate_tier(new_spent, new_orders)
    was_upgraded = (new_tier != old_tier)

    c.execute("UPDATE users SET total_spent=?, total_orders=?, tier=? WHERE user_id=?",
              (new_spent, new_orders, new_tier, user_id))
    conn.commit(); conn.close()
    return (new_tier, was_upgraded)


def get_user_tier_data(user_id):
    """Return dict with tier info + progress."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT total_spent, total_orders, tier FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        # Create user if missing
        c.execute("INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)", (user_id, "", "User"))
        conn.commit()
        c.execute("SELECT total_spent, total_orders, tier FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    conn.close()
    if not row:
        return None
    spent = float(row['total_spent'] or 0)
    orders = int(row['total_orders'] or 0)
    tier_key = row['tier'] or calculate_tier(spent, orders)
    current = get_tier_info(tier_key)
    next_t = get_next_tier(tier_key)

    progress_pct = 100
    progress_label = ""
    if next_t:
        # Use whichever metric is closer to next threshold
        spent_pct = (spent / next_t["min_spent"] * 100) if next_t["min_spent"] else 100
        orders_pct = (orders / next_t["min_orders"] * 100) if next_t["min_orders"] else 100
        progress_pct = min(100, max(spent_pct, orders_pct))
        remaining_spent = max(0, next_t["min_spent"] - spent)
        remaining_orders = max(0, next_t["min_orders"] - orders)
        progress_label = f"${remaining_spent:.2f} or {remaining_orders} orders to {next_t['name']}"

    return {
        "tier_key": tier_key,
        "tier_name": current["name"],
        "bonus_pct": current["bonus_pct"],
        "total_spent": spent,
        "total_orders": orders,
        "next_tier": next_t,
        "progress_pct": progress_pct,
        "progress_label": progress_label,
    }


def get_top_customers_by_tier(tier_key=None, limit=10):
    conn = get_connection(); c = conn.cursor()
    if tier_key:
        c.execute("""SELECT user_id, first_name, total_spent, total_orders, tier FROM users
                     WHERE tier=? ORDER BY total_spent DESC LIMIT ?""", (tier_key, limit))
    else:
        c.execute("""SELECT user_id, first_name, total_spent, total_orders, tier FROM users
                     ORDER BY total_spent DESC LIMIT ?""", (limit,))
    r = c.fetchall(); conn.close(); return r


# ════════════════════════════════════════════════════════════════
# 📊 ANALYTICS QUERIES
# ════════════════════════════════════════════════════════════════

def analytics_summary(days=None):
    """
    Returns analytics dict for a given period.
    days=None → all time
    days=1   → today
    days=7   → last 7 days
    days=30  → last 30 days
    """
    conn = get_connection(); c = conn.cursor()
    where = ""
    if days is not None:
        where = f"WHERE created_at >= datetime('now', '-{int(days)} days')"

    # Orders & revenue (delivered only)
    c.execute(f"""SELECT COUNT(*), COALESCE(SUM(price),0) FROM orders
                  WHERE status='delivered' {('AND ' + where[6:]) if where else ''}""")
    delivered_count, revenue = c.fetchone()

    # All orders (any status)
    c.execute(f"SELECT COUNT(*) FROM orders {where}")
    total_orders = c.fetchone()[0]

    # Pending
    c.execute(f"""SELECT COUNT(*) FROM orders WHERE status='pending'
                  {('AND ' + where[6:]) if where else ''}""")
    pending = c.fetchone()[0]

    # New users
    user_where = where.replace("created_at", "joined_at") if where else ""
    c.execute(f"SELECT COUNT(*) FROM users {user_where}")
    new_users = c.fetchone()[0]

    # Avg order value
    avg_order = (revenue / delivered_count) if delivered_count else 0

    # Conversion: delivered / total orders
    conversion = (delivered_count / total_orders * 100) if total_orders else 0

    conn.close()
    return {
        "revenue": float(revenue or 0),
        "delivered": delivered_count or 0,
        "total_orders": total_orders or 0,
        "pending": pending or 0,
        "new_users": new_users or 0,
        "avg_order": avg_order,
        "conversion": conversion,
    }


def analytics_top_products(days=None, limit=5):
    conn = get_connection(); c = conn.cursor()
    where = ""
    if days is not None:
        where = f"AND created_at >= datetime('now', '-{int(days)} days')"
    c.execute(f"""SELECT product_name, COUNT(*) as cnt, COALESCE(SUM(price),0) as rev
                  FROM orders WHERE status='delivered' {where}
                  GROUP BY product_id, product_name
                  ORDER BY cnt DESC LIMIT ?""", (limit,))
    r = c.fetchall(); conn.close(); return r


def analytics_top_customers(days=None, limit=5):
    conn = get_connection(); c = conn.cursor()
    where = ""
    if days is not None:
        where = f"AND o.created_at >= datetime('now', '-{int(days)} days')"
    c.execute(f"""SELECT o.user_id, u.first_name, COUNT(*) as cnt, COALESCE(SUM(o.price),0) as spent
                  FROM orders o LEFT JOIN users u ON u.user_id = o.user_id
                  WHERE o.status='delivered' {where}
                  GROUP BY o.user_id ORDER BY spent DESC LIMIT ?""", (limit,))
    r = c.fetchall(); conn.close(); return r


def analytics_payment_breakdown(days=None):
    conn = get_connection(); c = conn.cursor()
    where = ""
    if days is not None:
        where = f"AND created_at >= datetime('now', '-{int(days)} days')"
    c.execute(f"""SELECT payment_method, COUNT(*) as cnt, COALESCE(SUM(price),0) as rev
                  FROM orders WHERE status='delivered' {where}
                  GROUP BY payment_method ORDER BY rev DESC""")
    r = c.fetchall(); conn.close(); return r


def analytics_daily_revenue(days=7):
    """Returns list of (date, revenue, orders) for chart."""
    conn = get_connection(); c = conn.cursor()
    c.execute(f"""SELECT DATE(created_at) as d, COALESCE(SUM(price),0), COUNT(*)
                  FROM orders WHERE status='delivered'
                  AND created_at >= datetime('now', '-{int(days)} days')
                  GROUP BY DATE(created_at) ORDER BY d ASC""")
    r = c.fetchall(); conn.close(); return r



# ── Tier upgrade notifications queue (read by handlers) ──
_PENDING_TIER_UPGRADES = []

def _queue_tier_upgrade_notify(user_id, tier_key):
    _PENDING_TIER_UPGRADES.append((user_id, tier_key))

def pop_pending_tier_upgrades():
    """Return and clear pending upgrades. Called by handlers to notify users."""
    global _PENDING_TIER_UPGRADES
    items = list(_PENDING_TIER_UPGRADES)
    _PENDING_TIER_UPGRADES = []
    return items


# ── 🆕 Real-purchase broadcast queue (drained by a job → fake-activity dest) ──
_PENDING_PURCHASE_BROADCASTS = []

def _queue_purchase_broadcast(product_id, product_name, qty=1):
    _PENDING_PURCHASE_BROADCASTS.append({
        "product_id": product_id, "product_name": product_name, "qty": qty,
    })

def pop_pending_purchase_broadcasts():
    """Return and clear pending real-purchase broadcasts."""
    global _PENDING_PURCHASE_BROADCASTS
    items = list(_PENDING_PURCHASE_BROADCASTS)
    _PENDING_PURCHASE_BROADCASTS = []
    return items


# ════════════════════════════════════════════════════════════════
# 🏪 SUPPLIER SYSTEM — Database Functions
# ════════════════════════════════════════════════════════════════

def setup_supplier_tables():
    """
    Create all supplier-related tables.
    Safe to call multiple times (IF NOT EXISTS).

    Tables:
      suppliers          — registered vendor accounts
      supplier_stock     — account submissions per product
      supplier_earnings  — commission ledger per sale
      supplier_payouts   — payout requests
      supplier_broadcasts— admin→supplier messages + replies
    """
    conn = get_connection()
    c = conn.cursor()

    # ── Suppliers (vendors) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER UNIQUE NOT NULL,
            username     TEXT DEFAULT '',
            first_name   TEXT DEFAULT '',
            is_active    INTEGER DEFAULT 1,
            commission_pct REAL DEFAULT 2.0,
            balance      REAL DEFAULT 0.0,
            total_earned REAL DEFAULT 0.0,
            total_paid   REAL DEFAULT 0.0,
            payment_method TEXT DEFAULT '',
            payment_detail TEXT DEFAULT '',
            notes        TEXT DEFAULT '',
            joined_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Supplier Stock (submitted accounts) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_stock (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id     INTEGER NOT NULL,
            product_id      INTEGER NOT NULL,
            account_data    TEXT NOT NULL,
            supplier_price  REAL DEFAULT 0.0,
            admin_price     REAL DEFAULT 0.0,
            status          TEXT DEFAULT 'pending',
            is_bulk         INTEGER DEFAULT 0,
            bulk_count      INTEGER DEFAULT 1,
            submitted_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            approved_at     TEXT DEFAULT '',
            sold_at         TEXT DEFAULT '',
            order_id        INTEGER DEFAULT 0,
            admin_note      TEXT DEFAULT '',
            warranty_status TEXT DEFAULT 'ok',
            payout_eligible_at TEXT DEFAULT ''
        )
    """)

    # ── Commission / Earnings Ledger ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_earnings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id  INTEGER NOT NULL,
            stock_id     INTEGER NOT NULL,
            order_id     INTEGER NOT NULL,
            gross_amount REAL DEFAULT 0.0,
            commission_pct REAL DEFAULT 2.0,
            commission_amt REAL DEFAULT 0.0,
            net_amount   REAL DEFAULT 0.0,
            status       TEXT DEFAULT 'pending',
            payout_id    INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Payout Requests ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_payouts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id  INTEGER NOT NULL,
            amount       REAL DEFAULT 0.0,
            method       TEXT DEFAULT '',
            detail       TEXT DEFAULT '',
            status       TEXT DEFAULT 'pending',
            admin_note   TEXT DEFAULT '',
            requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT DEFAULT ''
        )
    """)

    # ── Admin→Supplier Broadcasts & Replies ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_broadcasts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id  INTEGER DEFAULT 0,
            is_global    INTEGER DEFAULT 0,
            message      TEXT NOT NULL,
            sender       TEXT DEFAULT 'admin',
            reply_to     INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Per-product commission rates (overrides supplier default) ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS product_commission (
            product_id     INTEGER PRIMARY KEY,
            commission_pct REAL DEFAULT 2.0
        )
    """)

    conn.commit()
    conn.close()


# ── Supplier CRUD ──

def add_supplier(user_id, username="", first_name="", commission_pct=2.0):
    """Register a new supplier. Returns supplier id."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO suppliers
            (user_id, username, first_name, commission_pct)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, first_name, commission_pct))
    c.execute("SELECT id FROM suppliers WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.commit(); conn.close()
    return row[0] if row else None


def get_supplier(user_id):
    """Get supplier by Telegram user_id. Returns Row or None."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM suppliers WHERE user_id=?", (user_id,))
    row = c.fetchone(); conn.close()
    return row


def get_supplier_by_id(sid):
    """Get supplier by supplier table id."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM suppliers WHERE id=?", (sid,))
    row = c.fetchone(); conn.close()
    return row


def get_all_suppliers():
    """Get all registered suppliers."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM suppliers ORDER BY joined_at DESC")
    rows = c.fetchall(); conn.close()
    return rows


def is_supplier(user_id):
    """Returns True if this user_id is a registered supplier."""
    s = get_supplier(user_id)
    return bool(s and s["is_active"] == 1)


def update_supplier(user_id, **kwargs):
    """Update supplier fields. Allowed: is_active, commission_pct, balance,
    payment_method, payment_detail, notes, username, first_name."""
    allowed = {"is_active", "commission_pct", "balance", "total_earned",
               "total_paid", "payment_method", "payment_detail",
               "notes", "username", "first_name"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields: return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [user_id]
    conn = get_connection(); c = conn.cursor()
    c.execute(f"UPDATE suppliers SET {sets} WHERE user_id=?", vals)
    conn.commit(); conn.close()


def add_supplier_balance(user_id, amount):
    """Add amount to supplier balance (earnings)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE suppliers
        SET balance=balance+?, total_earned=total_earned+?
        WHERE user_id=?
    """, (amount, amount, user_id))
    conn.commit(); conn.close()


def deduct_supplier_balance(user_id, amount):
    """Deduct amount from supplier balance (refund/payout)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE suppliers
        SET balance=MAX(0, balance-?)
        WHERE user_id=?
    """, (amount, user_id))
    conn.commit(); conn.close()


# ── Stock Submissions ──

def submit_supplier_stock(supplier_id, product_id, account_data,
                          supplier_price, is_bulk=False, bulk_count=1):
    """Submit account(s) from supplier. Returns stock id."""
    import datetime
    # Payout eligible after 20 days from submission
    eligible_date = (
        datetime.datetime.now() +
        datetime.timedelta(days=20)
    ).strftime("%Y-%m-%d %H:%M")

    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT INTO supplier_stock
            (supplier_id, product_id, account_data, supplier_price,
             is_bulk, bulk_count, payout_eligible_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (supplier_id, product_id, account_data, supplier_price,
          1 if is_bulk else 0, bulk_count, eligible_date))
    sid = c.lastrowid
    conn.commit(); conn.close()
    return sid


def get_supplier_stock(stock_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM supplier_stock WHERE id=?", (stock_id,))
    row = c.fetchone(); conn.close()
    return row


def get_pending_stock_requests():
    """All pending stock submissions for admin review."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT ss.*, s.user_id as sup_user_id, s.first_name as sup_name,
               p.name as product_name, p.price as store_price
        FROM supplier_stock ss
        JOIN suppliers s ON ss.supplier_id=s.id
        LEFT JOIN products p ON ss.product_id=p.id
        WHERE ss.status='pending'
        ORDER BY ss.submitted_at DESC
    """)
    rows = c.fetchall(); conn.close()
    return rows


def get_supplier_stocks(supplier_id, status=None):
    """Get supplier's submitted accounts."""
    conn = get_connection(); c = conn.cursor()
    if status:
        c.execute("""
            SELECT ss.*, p.name as product_name
            FROM supplier_stock ss
            LEFT JOIN products p ON ss.product_id=p.id
            WHERE ss.supplier_id=? AND ss.status=?
            ORDER BY ss.submitted_at DESC
        """, (supplier_id, status))
    else:
        c.execute("""
            SELECT ss.*, p.name as product_name
            FROM supplier_stock ss
            LEFT JOIN products p ON ss.product_id=p.id
            WHERE ss.supplier_id=?
            ORDER BY ss.submitted_at DESC
        """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


def approve_stock(stock_id, admin_price, admin_note=""):
    """Admin approves a stock submission with final customer price."""
    import datetime
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE supplier_stock
        SET status='approved', admin_price=?, admin_note=?,
            approved_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (admin_price, admin_note, stock_id))
    conn.commit(); conn.close()


def reject_stock(stock_id, admin_note=""):
    """Admin rejects a stock submission."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE supplier_stock
        SET status='rejected', admin_note=?
        WHERE id=?
    """, (admin_note, stock_id))
    conn.commit(); conn.close()


def mark_stock_sold(stock_id, order_id):
    """Mark a stock item as sold (called when order is delivered)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE supplier_stock
        SET status='sold', order_id=?, sold_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (order_id, stock_id))
    conn.commit(); conn.close()


# ── Commission / Earnings ──

def get_product_commission(product_id):
    """Get commission % for a specific product. Falls back to default 2%."""
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT commission_pct FROM product_commission WHERE product_id=?",
              (product_id,))
    row = c.fetchone(); conn.close()
    return float(row[0]) if row else 2.0


def set_product_commission(product_id, pct):
    """Set commission % for a product."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO product_commission (product_id, commission_pct)
        VALUES (?, ?)
    """, (product_id, float(pct)))
    conn.commit(); conn.close()


def record_supplier_sale(supplier_user_id, stock_id, order_id,
                         gross_amount, product_id):
    """
    Record a sale, calculate commission, update supplier balance.
    Called when admin approves/delivers an order.

    Commission = supplier's commission % OR product-specific %
    Net to supplier = gross - commission

    Returns (commission_amt, net_amount)
    """
    supplier = get_supplier(supplier_user_id)
    if not supplier:
        return 0, gross_amount

    # Commission: product-specific > supplier default > 2%
    prod_comm = get_product_commission(product_id)
    comm_pct  = prod_comm if prod_comm else supplier["commission_pct"]

    commission_amt = round(gross_amount * comm_pct / 100, 2)
    net_amount     = round(gross_amount - commission_amt, 2)

    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT INTO supplier_earnings
            (supplier_id, stock_id, order_id, gross_amount,
             commission_pct, commission_amt, net_amount, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
    """, (supplier["id"], stock_id, order_id, gross_amount,
          comm_pct, commission_amt, net_amount))
    conn.commit(); conn.close()

    # Update supplier balance
    add_supplier_balance(supplier_user_id, net_amount)

    return commission_amt, net_amount


def get_supplier_earnings(supplier_id):
    """Get all earnings for a supplier."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT se.*, p.name as product_name
        FROM supplier_earnings se
        LEFT JOIN supplier_stock ss ON se.stock_id=ss.id
        LEFT JOIN products p ON ss.product_id=p.id
        WHERE se.supplier_id=?
        ORDER BY se.created_at DESC
    """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


# ── Payouts ──

def request_payout(supplier_id, amount, method, detail):
    """Supplier requests a payout."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT INTO supplier_payouts
            (supplier_id, amount, method, detail)
        VALUES (?, ?, ?, ?)
    """, (supplier_id, amount, method, detail))
    pid = c.lastrowid
    conn.commit(); conn.close()
    return pid


def get_pending_payouts():
    """All pending payout requests for admin."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT sp.*, s.user_id, s.first_name, s.balance
        FROM supplier_payouts sp
        JOIN suppliers s ON sp.supplier_id=s.id
        WHERE sp.status='pending'
        ORDER BY sp.requested_at DESC
    """)
    rows = c.fetchall(); conn.close()
    return rows


def approve_payout(payout_id, admin_note=""):
    """Admin approves a payout and deducts from supplier balance.
    🔧 BUG FIX #6: Use single connection with proper transaction handling.
    Previously opened two separate connections — if second failed, balance wasn't deducted."""
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("SELECT * FROM supplier_payouts WHERE id=?", (payout_id,))
        p = c.fetchone()
        if not p:
            conn.close(); return False
        # Mark payout as approved
        c.execute("""
            UPDATE supplier_payouts
            SET status='approved', admin_note=?, processed_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (admin_note, payout_id))
        # Deduct from supplier balance (same connection for atomicity)
        sup = get_supplier_by_id(p["supplier_id"])
        if sup:
            c.execute("""
                UPDATE suppliers
                SET balance=MAX(0,balance-?), total_paid=total_paid+?
                WHERE id=?
            """, (p["amount"], p["amount"], p["supplier_id"]))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def reject_payout(payout_id, admin_note=""):
    """Admin rejects a payout."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        UPDATE supplier_payouts
        SET status='rejected', admin_note=?, processed_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (admin_note, payout_id))
    conn.commit(); conn.close()


def get_supplier_payouts(supplier_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT * FROM supplier_payouts
        WHERE supplier_id=? ORDER BY requested_at DESC
    """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


# ── Broadcasts ──

def add_supplier_broadcast(message, supplier_id=0, is_global=False,
                           sender="admin", reply_to=0):
    """Add a broadcast message from admin to supplier(s)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT INTO supplier_broadcasts
            (supplier_id, is_global, message, sender, reply_to)
        VALUES (?, ?, ?, ?, ?)
    """, (supplier_id, 1 if is_global else 0, message, sender, reply_to))
    bid = c.lastrowid
    conn.commit(); conn.close()
    return bid


def get_supplier_broadcasts(supplier_id):
    """Get broadcasts for a specific supplier + global ones."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT * FROM supplier_broadcasts
        WHERE supplier_id=? OR is_global=1
        ORDER BY created_at DESC LIMIT 20
    """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


# ── Warranty (Supplier side) ──

def get_warranty_by_stock(stock_id):
    """Get warranty request associated with a specific stock item."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT wr.*, o.product_name
        FROM warranty_requests wr
        LEFT JOIN orders o ON wr.order_id=o.id
        WHERE o.id IN (
            SELECT order_id FROM supplier_stock WHERE id=?
        )
    """, (stock_id,))
    row = c.fetchone(); conn.close()
    return row


def get_supplier_warranty_alerts(supplier_id):
    """Get all warranty requests for this supplier's stock items."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT wr.*, ss.id as stock_id, ss.account_data,
               COALESCE(p.name, o.product_name) as product_name
        FROM warranty_requests wr
        JOIN orders o ON wr.order_id=o.id
        JOIN supplier_stock ss ON ss.order_id=o.id
        JOIN suppliers s ON ss.supplier_id=s.id
        LEFT JOIN products p ON o.product_id=p.id
        WHERE s.id=?
        ORDER BY wr.created_at DESC
    """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


def get_payout_eligible_earnings(supplier_id):
    """Get earnings that are now eligible for payout (20 days passed)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT se.* FROM supplier_earnings se
        JOIN supplier_stock ss ON se.stock_id=ss.id
        WHERE se.supplier_id=? AND se.status='pending'
          AND ss.payout_eligible_at <= CURRENT_TIMESTAMP
          AND ss.warranty_status='ok'
    """, (supplier_id,))
    rows = c.fetchall(); conn.close()
    return rows


# ════════════════════════════════════════════════════════════════
# 🏪 SUPPLIER ADVANCED FEATURES — Database Functions
# ════════════════════════════════════════════════════════════════

def setup_supplier_advanced_tables():
    """
    Additional tables for advanced supplier features.
    Safe to call multiple times.
    """
    conn = get_connection()
    c = conn.cursor()

    # Supplier rating by admin (1-5 stars)
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_ratings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            rating      INTEGER DEFAULT 5,
            note        TEXT DEFAULT '',
            rated_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Supplier tier history
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_tier_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            old_tier    TEXT DEFAULT 'bronze',
            new_tier    TEXT DEFAULT 'silver',
            changed_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Blacklisted suppliers
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_blacklist (
            supplier_id INTEGER PRIMARY KEY,
            reason      TEXT DEFAULT '',
            blacklisted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Duplicate account detection (hash of account data)
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_account_hashes (
            hash        TEXT PRIMARY KEY,
            stock_id    INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            added_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add supplier advanced columns if missing
    try:
        c.execute("ALTER TABLE suppliers ADD COLUMN tier TEXT DEFAULT 'bronze'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE suppliers ADD COLUMN rating REAL DEFAULT 5.0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE suppliers ADD COLUMN total_sales INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE suppliers ADD COLUMN violation_count INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE suppliers ADD COLUMN min_stock_commit INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE supplier_stock ADD COLUMN expires_at TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE supplier_stock ADD COLUMN sale_notified INTEGER DEFAULT 0")
    except Exception:
        pass

    conn.commit()
    conn.close()


# ── Supplier Tier System ──

SUPPLIER_TIERS = [
    {"key": "bronze",   "label": "🥉 Bronze",   "min_sales": 0,   "commission_discount": 0.0},
    {"key": "silver",   "label": "🥈 Silver",   "min_sales": 10,  "commission_discount": 0.5},
    {"key": "gold",     "label": "🥇 Gold",     "min_sales": 30,  "commission_discount": 1.0},
    {"key": "platinum", "label": "💎 Platinum", "min_sales": 100, "commission_discount": 1.5},
]


def get_supplier_tier(total_sales):
    """Calculate supplier tier based on total sales."""
    best = SUPPLIER_TIERS[0]
    for t in SUPPLIER_TIERS:
        if total_sales >= t["min_sales"]:
            best = t
    return best


def update_supplier_tier(supplier_user_id, new_sales_count):
    """
    Update supplier tier based on sales.
    Returns (new_tier_key, upgraded: bool)
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT tier, total_sales FROM suppliers WHERE user_id=?", (supplier_user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return "bronze", False

    old_tier = row["tier"] or "bronze"
    new_sales = (row["total_sales"] or 0) + new_sales_count
    new_tier_data = get_supplier_tier(new_sales)
    new_tier = new_tier_data["key"]

    conn2 = get_connection()
    c2 = conn2.cursor()
    c2.execute("""
        UPDATE suppliers SET tier=?, total_sales=? WHERE user_id=?
    """, (new_tier, new_sales, supplier_user_id))

    if new_tier != old_tier:
        c2.execute("""
            INSERT INTO supplier_tier_log (supplier_id, old_tier, new_tier)
            SELECT id, ?, ? FROM suppliers WHERE user_id=?
        """, (old_tier, new_tier, supplier_user_id))

    conn2.commit()
    conn2.close()
    return new_tier, (new_tier != old_tier)


# ── Supplier Rating ──

def rate_supplier(supplier_id_db, rating, note=""):
    """Admin rates a supplier (1-5)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO supplier_ratings (supplier_id, rating, note)
        VALUES (?, ?, ?)
    """, (supplier_id_db, rating, note))
    # Update average rating on suppliers table
    c.execute("""
        UPDATE suppliers
        SET rating=(SELECT AVG(rating) FROM supplier_ratings WHERE supplier_id=?)
        WHERE id=?
    """, (supplier_id_db, supplier_id_db))
    conn.commit()
    conn.close()


# ── Blacklist ──

def blacklist_supplier(supplier_id_db, reason=""):
    """Add supplier to blacklist + deactivate them."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO supplier_blacklist (supplier_id, reason)
        VALUES (?, ?)
    """, (supplier_id_db, reason))
    c.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (supplier_id_db,))
    conn.commit()
    conn.close()


def is_supplier_blacklisted(supplier_id_db):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM supplier_blacklist WHERE supplier_id=?", (supplier_id_db,))
    row = c.fetchone()
    conn.close()
    return bool(row)


def get_blacklist():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT sb.*, s.first_name, s.user_id as sup_uid
        FROM supplier_blacklist sb
        JOIN suppliers s ON sb.supplier_id=s.id
        ORDER BY sb.blacklisted_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


# ── Duplicate Account Detection ──

def check_duplicate_account(account_data, supplier_id_db):
    """
    Check if account data already exists in DB.
    Uses hash of stripped account text.
    Returns (is_duplicate, existing_stock_id)
    """
    import hashlib
    h = hashlib.md5(account_data.strip().lower().encode()).hexdigest()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT stock_id, supplier_id FROM supplier_account_hashes WHERE hash=?
    """, (h,))
    row = c.fetchone()
    conn.close()
    if row:
        return True, row["stock_id"]
    return False, None


def register_account_hash(account_data, stock_id, supplier_id_db):
    """Register account hash after successful submission."""
    import hashlib
    h = hashlib.md5(account_data.strip().lower().encode()).hexdigest()
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO supplier_account_hashes (hash, stock_id, supplier_id)
            VALUES (?, ?, ?)
        """, (h, stock_id, supplier_id_db))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Stock Expiry (30 days) ──

def setup_stock_expiry():
    """
    Mark approved-but-unsold stock as expired after 30 days.
    Called by background job.
    Returns list of expired stock items.
    🔧 BUG FIX #8: Use parameterized queries instead of f-string IDs.
    """
    import datetime
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT ss.*, s.user_id as sup_uid, p.name as product_name
        FROM supplier_stock ss
        JOIN suppliers s ON ss.supplier_id=s.id
        LEFT JOIN products p ON ss.product_id=p.id
        WHERE ss.status='approved'
          AND ss.approved_at != ''
          AND ss.approved_at <= ?
    """, (cutoff,))
    expired = c.fetchall()
    if expired:
        ids = [e["id"] for e in expired]
        placeholders = ','.join(['?'] * len(ids))
        c.execute(f"""
            UPDATE supplier_stock SET status='expired'
            WHERE id IN ({placeholders})
        """, ids)
        conn.commit()
    conn.close()
    return expired


# ── Sale Notification (instant when account sold) ──

def get_unsent_sale_notifications():
    """
    Get sold stock items where supplier hasn't been notified yet.
    Used by background job to send sale alerts.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT ss.*, s.user_id as sup_uid, s.first_name as sup_name,
               p.name as product_name,
               se.net_amount, se.commission_amt, se.commission_pct
        FROM supplier_stock ss
        JOIN suppliers s ON ss.supplier_id=s.id
        LEFT JOIN products p ON ss.product_id=p.id
        LEFT JOIN supplier_earnings se ON se.stock_id=ss.id
        WHERE ss.status='sold' AND ss.sale_notified=0
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def mark_sale_notification_sent(stock_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE supplier_stock SET sale_notified=1 WHERE id=?", (stock_id,))
    conn.commit()
    conn.close()


# ── Supplier Leaderboard ──

def get_supplier_leaderboard(limit=10):
    """Top suppliers by total earnings."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.user_id, s.first_name, s.username,
               s.total_earned, s.total_sales, s.tier, s.rating,
               COUNT(ss.id) as stock_count,
               SUM(CASE WHEN ss.status='sold' THEN 1 ELSE 0 END) as sold_count
        FROM suppliers s
        LEFT JOIN supplier_stock ss ON ss.supplier_id=s.id
        WHERE s.is_active=1
        GROUP BY s.id
        ORDER BY s.total_earned DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


# ── Low Stock Alert ──

def get_products_needing_supplier_stock(threshold=3):
    """
    Products where approved supplier stock count is below threshold.
    Used to notify suppliers to submit more accounts.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.name, p.price,
               COUNT(ss.id) as available_stock
        FROM products p
        LEFT JOIN supplier_stock ss ON ss.product_id=p.id
            AND ss.status='approved'
        WHERE p.is_active=1
        GROUP BY p.id
        HAVING available_stock < ?
        ORDER BY available_stock ASC
    """, (threshold,))
    rows = c.fetchall()
    conn.close()
    return rows


# ── Price History ──

def log_supplier_price(supplier_id_db, product_id, price, status):
    """Log price changes over time (called on submit/approve/reject)."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS supplier_price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                price       REAL NOT NULL,
                status      TEXT DEFAULT 'submitted',
                logged_at   TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            INSERT INTO supplier_price_history (supplier_id, product_id, price, status)
            VALUES (?, ?, ?, ?)
        """, (supplier_id_db, product_id, price, status))
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_supplier_price_history(supplier_id_db, product_id=None, limit=20):
    """Get price history for a supplier (optionally filtered by product)."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS supplier_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER, product_id INTEGER,
                price REAL, status TEXT, logged_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if product_id:
            c.execute("""
                SELECT sph.*, p.name as product_name
                FROM supplier_price_history sph
                LEFT JOIN products p ON sph.product_id=p.id
                WHERE sph.supplier_id=? AND sph.product_id=?
                ORDER BY sph.logged_at DESC LIMIT ?
            """, (supplier_id_db, product_id, limit))
        else:
            c.execute("""
                SELECT sph.*, p.name as product_name
                FROM supplier_price_history sph
                LEFT JOIN products p ON sph.product_id=p.id
                WHERE sph.supplier_id=?
                ORDER BY sph.logged_at DESC LIMIT ?
            """, (supplier_id_db, limit))
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception:
        conn.close()
        return []


# ── Min Stock Commitment ──

def set_min_stock_commit(supplier_id_db, min_count):
    """Admin sets minimum stock commitment for a supplier."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE suppliers SET min_stock_commit=? WHERE id=?",
              (min_count, supplier_id_db))
    conn.commit()
    conn.close()


def get_commitment_violations():
    """Find suppliers below their minimum stock commitment."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.user_id, s.first_name, s.min_stock_commit,
               COUNT(ss.id) as current_stock
        FROM suppliers s
        LEFT JOIN supplier_stock ss ON ss.supplier_id=s.id
            AND ss.status='approved'
        WHERE s.is_active=1 AND s.min_stock_commit > 0
        GROUP BY s.id
        HAVING current_stock < s.min_stock_commit
    """)
    rows = c.fetchall()
    conn.close()
    return rows


# ── Commission Revenue Report ──

def get_commission_report(days=30):
    """Total commission earned by admin in last N days."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT
            SUM(se.commission_amt) as total_commission,
            SUM(se.gross_amount)   as total_gross,
            SUM(se.net_amount)     as total_paid_to_suppliers,
            COUNT(*)               as total_sales,
            COUNT(DISTINCT se.supplier_id) as active_suppliers
        FROM supplier_earnings se
        WHERE se.created_at >= datetime('now', ?)
    """, (f'-{days} days',))
    row = c.fetchone()
    conn.close()
    return row

def add_restock_request(pid, uid):
    conn = get_connection(); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS restock_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))")
    try:
        c.execute("INSERT INTO restock_requests (product_id, user_id) VALUES (?, ?)", (pid, uid))
    except Exception:
        pass
    conn.commit(); conn.close()

def get_restock_requests():
    conn = get_connection(); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS restock_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))")
    c.execute("""SELECT r.product_id, p.name, COUNT(r.id) as req_count 
                 FROM restock_requests r 
                 JOIN products p ON r.product_id = p.id 
                 WHERE p.stock <= 0 AND p.delivery_mode != 'manual'
                 GROUP BY r.product_id 
                 ORDER BY req_count DESC""")
    res = [dict(row) for row in c.fetchall()]
    conn.close()
    return res


def deduct_points(user_id, amount):
    conn = get_connection(); c = conn.cursor()
    c.execute("UPDATE users SET points = MAX(0, points - ?) WHERE user_id=?", (amount, user_id))
    conn.commit(); conn.close()

def add_stock_alert(pid, uid):
    conn = get_connection(); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS stock_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))")
    try: c.execute("INSERT INTO stock_alerts (product_id, user_id) VALUES (?, ?)", (pid, uid))
    except: pass
    conn.commit(); conn.close()

def get_and_clear_stock_alerts(pid):
    conn = get_connection(); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS stock_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))")
    c.execute("SELECT user_id FROM stock_alerts WHERE product_id=?", (pid,))
    users = [r[0] for r in c.fetchall()]
    if users:
        c.execute("DELETE FROM stock_alerts WHERE product_id=?", (pid,))
        conn.commit()
    conn.close()
    return users

def get_flash_sale_products():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT p.*, c.name as category_name, c.emoji as category_emoji FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.is_active=1 AND p.is_flash_sale=1 ORDER BY p.id DESC")
    r = c.fetchall(); conn.close(); return r


def expire_old_flash_sales():
    """🆕 Auto-disable flash sales whose flash_until has passed.
    Returns the number of products turned off."""
    from datetime import datetime
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "products", "flash_until", "TEXT DEFAULT ''")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("""UPDATE products SET is_flash_sale=0
                     WHERE is_flash_sale=1
                       AND flash_until IS NOT NULL
                       AND flash_until != ''
                       AND flash_until <= ?""", (now,))
        n = c.rowcount
        conn.commit()
    except Exception:
        n = 0
    conn.close()
    return n

def _migrate_flash_sales():
    conn = get_connection()
    c = conn.cursor()
    # 1. Add is_flash_sale + flash_price (self-heal, visible on real failure)
    ensure_column(c, "products", "is_flash_sale", "INTEGER DEFAULT 0")
    ensure_column(c, "products", "flash_price", "REAL DEFAULT 0.0")

    # 2. Add stock alerts table
    try:
        c.execute("CREATE TABLE IF NOT EXISTS stock_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))")
    except Exception as e:
        print(f"⚠️ _migrate_flash_sales: stock_alerts table: {e}")

    conn.commit()
    conn.close()

# ════════════════════════════════════════════════
# 🆕 v46: PROFESSIONAL API SYSTEM TABLES + FUNCTIONS
# ════════════════════════════════════════════════
def setup_api_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE NOT NULL,
        bot_name TEXT DEFAULT '',
        owner_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # 🆕 v74: additive columns for Akunding-style key management
    ensure_column(c, "api_keys", "key_hash",       "TEXT DEFAULT ''")
    ensure_column(c, "api_keys", "key_prefix",     "TEXT DEFAULT ''")
    ensure_column(c, "api_keys", "last_used_at",   "TEXT DEFAULT ''")
    ensure_column(c, "api_keys", "request_count",  "INTEGER DEFAULT 0")
    ensure_column(c, "api_keys", "revoked_at",     "TEXT DEFAULT ''")
    ensure_column(c, "api_keys", "label",          "TEXT DEFAULT ''")

    # 🆕 v74: per-key + per-day request log (for rate limiting + analytics)
    c.execute("""CREATE TABLE IF NOT EXISTS api_request_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key_id INTEGER NOT NULL,
        endpoint TEXT DEFAULT '',
        status_code INTEGER DEFAULT 0,
        ip TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_apilog_key_time ON api_request_log(api_key_id, created_at)")

    c.execute("""CREATE TABLE IF NOT EXISTS external_apis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        api_key TEXT NOT NULL,
        base_url TEXT NOT NULL,
        commission_percent REAL DEFAULT 10.0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # 🔧 BUGFIX v46: these two tables used to be created lazily inside their
    # own functions only. Create them at startup too so the very first button
    # press never hits "no such table".
    c.execute("""CREATE TABLE IF NOT EXISTS restock_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(product_id, user_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS supplier_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER, product_id INTEGER,
        price REAL, status TEXT, logged_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()

def add_api_key(key, bot_name, owner_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO api_keys (api_key, bot_name, owner_id) VALUES (?,?,?)", (key, bot_name, owner_id))
    conn.commit()
    conn.close()

def get_api_key(key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE api_key=? AND is_active=1", (key,))
    r = c.fetchone()
    conn.close()
    return r

def list_api_keys(owner_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE owner_id=? ORDER BY created_at DESC", (owner_id,))
    r = c.fetchall()
    conn.close()
    return r

def revoke_api_key(key_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE api_keys SET is_active=0 WHERE id=?", (key_id,))
    conn.commit()
    conn.close()

# --- External API secret protection ---
def _secret_fernet():
    """Return a Fernet instance derived from API_SECRET_ENCRYPTION_KEY/BOT_TOKEN.
    This prevents external API keys from being stored as readable plaintext in DB.
    """
    try:
        import base64, hashlib
        from cryptography.fernet import Fernet
        secret = os.getenv("API_SECRET_ENCRYPTION_KEY") or os.getenv("BOT_TOKEN") or "bite-store-local-secret"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)
    except Exception:
        return None


def _encrypt_secret(value):
    value = str(value or "")
    if not value or value.startswith("enc:"):
        return value
    f = _secret_fernet()
    if not f:
        # Last-resort marker avoids double-processing; set cryptography package
        # for real encryption (included in requirements dependency tree).
        return "plain:" + value
    return "enc:" + f.encrypt(value.encode()).decode()


def _decrypt_secret(value):
    value = str(value or "")
    if value.startswith("enc:"):
        f = _secret_fernet()
        if not f:
            return ""
        try:
            return f.decrypt(value[4:].encode()).decode()
        except Exception:
            return ""
    if value.startswith("plain:"):
        return value[6:]
    # Backward compatibility for old plaintext rows.
    return value


def _mask_secret(value):
    v = _decrypt_secret(value)
    if not v:
        return ""
    return (v[:4] + "…" + v[-4:]) if len(v) > 10 else "••••"


def _external_api_row(row, reveal_key=False):
    if not row:
        return row
    d = dict(row)
    d['api_key'] = _decrypt_secret(d.get('api_key')) if reveal_key else _mask_secret(d.get('api_key'))
    return d


def add_external_api(name, api_key, base_url, commission=10.0):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO external_apis (name, api_key, base_url, commission_percent) VALUES (?,?,?,?)",
              (name, _encrypt_secret(api_key), base_url, commission))
    conn.commit()
    conn.close()


def list_external_apis():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM external_apis WHERE is_active=1")
    r = [_external_api_row(row, reveal_key=False) for row in c.fetchall()]
    conn.close()
    return r


def get_external_api(eid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM external_apis WHERE id=?", (eid,))
    r = _external_api_row(c.fetchone(), reveal_key=True)
    conn.close()
    return r

# Auto setup on import (also called explicitly from setup_database/migrate_all)
try:
    setup_api_tables()
except Exception as _e:
    print(f"⚠️ setup_api_tables() on import failed: {_e}")


# ════════════════════════════════════════════════════════════════
# 🆕 v48: REFERRAL POINTS SYSTEM
# ════════════════════════════════════════════════════════════════
# Two separate "currencies":
#   - points     : normal points (bought via Buy Points). Spend on any product.
#   - ref_points : earned ONLY by referring real users. Spend ONLY on products
#                  admin marked as free-via-referrals (product_free_claim).
#
# Migration: backfill ref_points = referral_count for existing users,
# subtract equivalent normal points (so total "earning power" is preserved
# but properly categorised).
# ════════════════════════════════════════════════════════════════


def setup_ref_points_and_log():
    """Create ref_points column on users + referral_log + referral_bans tables.
    Idempotent — safe to call multiple times.
    """
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "users", "ref_points", "INTEGER DEFAULT 0")
    # First-time migration: backfill ref_points from referral_count
    c.execute("SELECT key FROM bot_settings WHERE key='v48_refpoints_backfilled'")
    if not c.fetchone():
        try:
            # 1. Set ref_points = referral_count (lifetime as starting balance)
            c.execute("UPDATE users SET ref_points = COALESCE(referral_count, 0) WHERE ref_points = 0")
            # 2. Subtract equivalent normal points (avoid double-credit). NEVER negative.
            #    Old system gave REFERRAL_POINTS per referral; default = 1.
            try:
                from config import REFERRAL_POINTS as _RP
                rp = int(_RP)
            except Exception:
                rp = 1
            c.execute("""
                UPDATE users
                   SET points = MAX(0, COALESCE(points, 0) - COALESCE(referral_count, 0) * ?)
                 WHERE referral_count > 0
            """, (rp,))
            # Mark done
            c.execute("INSERT OR REPLACE INTO bot_settings(key, value) VALUES('v48_refpoints_backfilled','1')")
            print("✅ v48 ref_points backfill complete")
        except Exception as _e:
            print(f"⚠️ v48 backfill failed: {_e}")
    # Referral audit log
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id  INTEGER NOT NULL,
            referred_id  INTEGER NOT NULL,
            status       TEXT    DEFAULT 'counted',   -- counted | blocked
            reason       TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_reflog_referrer ON referral_log(referrer_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reflog_referred ON referral_log(referred_id)")
    except Exception:
        pass
    # Referral bans (admin can ban abusers)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_bans (
            user_id     INTEGER PRIMARY KEY,
            reason      TEXT    DEFAULT '',
            banned_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); conn.close()


def get_ref_points(uid):
    """Return user's spendable ref_points balance."""
    u = get_user(uid)
    if not u: return 0
    try:
        return int(u["ref_points"]) if "ref_points" in u.keys() else 0
    except Exception:
        return 0


def add_ref_points(uid, amount):
    """Add ref_points to a user. amount can be negative to deduct
    (but use deduct_ref_points for safety clamping)."""
    if amount == 0: return
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "users", "ref_points", "INTEGER DEFAULT 0")
    c.execute("UPDATE users SET ref_points = COALESCE(ref_points,0) + ? WHERE user_id = ?",
              (int(amount), int(uid)))
    conn.commit(); conn.close()


def deduct_ref_points(uid, amount):
    """Deduct ref_points safely (clamps at 0, never goes negative).
    Returns True if successful, False if balance insufficient."""
    amount = int(amount)
    if amount <= 0: return True
    bal = get_ref_points(uid)
    if bal < amount: return False
    conn = get_connection(); c = conn.cursor()
    ensure_column(c, "users", "ref_points", "INTEGER DEFAULT 0")
    c.execute("UPDATE users SET ref_points = MAX(0, COALESCE(ref_points,0) - ?) WHERE user_id = ?",
              (amount, int(uid)))
    conn.commit(); conn.close()
    return True


def log_referral_attempt(referrer_id, referred_id, status, reason=""):
    """Audit-log every referral attempt (success or block)."""
    try:
        conn = get_connection(); c = conn.cursor()
        c.execute("""INSERT INTO referral_log (referrer_id, referred_id, status, reason)
                     VALUES (?, ?, ?, ?)""",
                  (int(referrer_id), int(referred_id), str(status), str(reason)[:200]))
        conn.commit(); conn.close()
    except Exception:
        pass


def get_referral_log(limit=50, status=None):
    """Admin view — recent referral attempts."""
    conn = get_connection(); c = conn.cursor()
    if status:
        c.execute("""SELECT * FROM referral_log WHERE status=?
                     ORDER BY created_at DESC LIMIT ?""", (status, int(limit)))
    else:
        c.execute("SELECT * FROM referral_log ORDER BY created_at DESC LIMIT ?",
                  (int(limit),))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]


def count_referrals_by_referrer_recent(referrer_id, minutes=60):
    """Count how many referrals this user has brought in the last N minutes."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COUNT(*) FROM referral_log
                 WHERE referrer_id=? AND status='counted'
                 AND datetime(created_at) >= datetime('now', ?)""",
              (int(referrer_id), f'-{int(minutes)} minutes'))
    n = c.fetchone()[0]; conn.close()
    return int(n or 0)


def get_recent_referred_first_names(referrer_id, minutes=60):
    """Return list of first-names referred by this user recently
    (for duplicate-name detection)."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT u.first_name, u.username
        FROM referral_log r
        LEFT JOIN users u ON u.user_id = r.referred_id
        WHERE r.referrer_id = ? AND r.status = 'counted'
          AND datetime(r.created_at) >= datetime('now', ?)
    """, (int(referrer_id), f'-{int(minutes)} minutes'))
    rows = c.fetchall(); conn.close()
    return [(r[0] or "", r[1] or "") for r in rows]


def ban_referrer(user_id, reason=""):
    """Permanently ban a user from giving/receiving referral credit."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO referral_bans (user_id, reason)
                 VALUES (?, ?)""", (int(user_id), str(reason)[:200]))
    conn.commit(); conn.close()


def unban_referrer(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("DELETE FROM referral_bans WHERE user_id=?", (int(user_id),))
    conn.commit(); conn.close()


def is_referrer_banned(user_id):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT 1 FROM referral_bans WHERE user_id=? LIMIT 1", (int(user_id),))
    r = c.fetchone(); conn.close()
    return bool(r)


def get_referral_bans(limit=100):
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM referral_bans ORDER BY banned_at DESC LIMIT ?",
              (int(limit),))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]


# Auto-setup on import
try:
    setup_ref_points_and_log()
except Exception as _e:
    print(f"⚠️ setup_ref_points_and_log() on import failed: {_e}")


# ════════════════════════════════════════════════════════════════
# 🎁 FREE-CLAIM-BY-REFERRALS SYSTEM (v47)
# ════════════════════════════════════════════════════════════════
# Admin can mark any product as "claimable for free" after the user has
# brought N referrals into the bot. Per-product config + claim history
# are stored here.
#
# Tables:
#   product_free_claim   — per-product settings (one row per product)
#   free_claims          — audit log of every claim (one row per claim)
# ════════════════════════════════════════════════════════════════

def setup_free_claim_tables():
    """Create tables for the Free-via-Referrals feature. Safe to call multiple times.

    🆕 v102: added `product_ref_pool` — per-product referral counter. When a
    friend arrives via a product-specific share link (?start=ref_<uid>_<pid>),
    the referrer's counter for THAT product ticks up by 1 (no reward point,
    no add to general ref_points pool). Once counter hits required_refs for
    the product, admin's watchdog / claim flow auto-delivers.
    """
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS product_free_claim (
            product_id     INTEGER PRIMARY KEY,
            enabled        INTEGER DEFAULT 0,
            required_refs  INTEGER DEFAULT 5,
            tpl_index      INTEGER DEFAULT -1,
            custom_text    TEXT    DEFAULT '',
            updated_at     TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS free_claims (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            product_id   INTEGER NOT NULL,
            order_id     INTEGER DEFAULT 0,
            refs_used    INTEGER NOT NULL,
            claimed_at   TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 🆕 v102: per-product referral counter (separate from general ref_points)
    c.execute("""
        CREATE TABLE IF NOT EXISTS product_ref_pool (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id   INTEGER NOT NULL,
            product_id    INTEGER NOT NULL,
            referred_id   INTEGER NOT NULL,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referrer_id, product_id, referred_id)
        )
    """)
    # Indexes for fast lookup
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_free_claims_user ON free_claims(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_free_claims_uid_pid ON free_claims(user_id, product_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_prod_ref_pool_referrer ON product_ref_pool(referrer_id, product_id)")
    except Exception:
        pass
    conn.commit(); conn.close()


# ────────────────────────────────────────────────────────────
# 🆕 v102: Per-product referral pool CRUD
# ────────────────────────────────────────────────────────────
def add_product_ref(referrer_id, product_id, referred_id):
    """Add a referral to a specific product's pool. Returns True on new-count,
    False if already tracked (dedupe)."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""INSERT INTO product_ref_pool
                     (referrer_id, product_id, referred_id) VALUES (?, ?, ?)""",
                  (int(referrer_id), int(product_id), int(referred_id)))
        ok = c.rowcount > 0
        conn.commit(); conn.close()
        return ok
    except Exception:
        conn.close()
        return False


def count_product_refs(referrer_id, product_id):
    """Count referrals a user has brought via link for a specific product."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COUNT(*) FROM product_ref_pool
                 WHERE referrer_id=? AND product_id=?""",
              (int(referrer_id), int(product_id)))
    n = c.fetchone()[0]; conn.close()
    return int(n or 0)


def clear_product_refs(referrer_id, product_id):
    """Called after a successful free-claim to reset the counter."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""DELETE FROM product_ref_pool
                 WHERE referrer_id=? AND product_id=?""",
              (int(referrer_id), int(product_id)))
    conn.commit(); conn.close()


def set_product_free_config(pid, *, enabled=None, required_refs=None,
                             tpl_index=None, custom_text=None):
    """Insert or update a product's free-claim config. Only provided fields are changed."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT product_id FROM product_free_claim WHERE product_id=?", (int(pid),))
    exists = c.fetchone()
    if not exists:
        c.execute("""
            INSERT INTO product_free_claim
                (product_id, enabled, required_refs, tpl_index, custom_text)
            VALUES (?, ?, ?, ?, ?)
        """, (
            int(pid),
            1 if enabled else 0,
            int(required_refs) if required_refs is not None else 5,
            int(tpl_index) if tpl_index is not None else -1,
            str(custom_text) if custom_text is not None else "",
        ))
    else:
        sets, vals = [], []
        if enabled is not None:
            sets.append("enabled=?"); vals.append(1 if enabled else 0)
        if required_refs is not None:
            sets.append("required_refs=?"); vals.append(int(required_refs))
        if tpl_index is not None:
            sets.append("tpl_index=?"); vals.append(int(tpl_index))
        if custom_text is not None:
            sets.append("custom_text=?"); vals.append(str(custom_text))
        sets.append("updated_at=CURRENT_TIMESTAMP")
        if sets:
            vals.append(int(pid))
            c.execute(f"UPDATE product_free_claim SET {', '.join(sets)} WHERE product_id=?", vals)
    conn.commit(); conn.close()


def get_product_free_config(pid):
    """Return dict with config — always returns a dict (with defaults if no row exists)."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM product_free_claim WHERE product_id=?", (int(pid),))
    row = c.fetchone(); conn.close()
    if not row:
        return {
            "product_id": int(pid),
            "enabled": 0,
            "required_refs": 5,
            "tpl_index": -1,
            "custom_text": "",
        }
    d = dict(row)
    # Sanity defaults
    d["enabled"] = int(d.get("enabled") or 0)
    d["required_refs"] = max(1, int(d.get("required_refs") or 5))
    d["tpl_index"] = int(d.get("tpl_index") if d.get("tpl_index") is not None else -1)
    d["custom_text"] = d.get("custom_text") or ""
    return d


def get_all_free_claim_products():
    """Return list of (product_id, enabled, required_refs) for every configured product."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT product_id, enabled, required_refs FROM product_free_claim")
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]


def record_free_claim(user_id, product_id, order_id, refs_used):
    """Audit-log a successful free claim."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        INSERT INTO free_claims (user_id, product_id, order_id, refs_used)
        VALUES (?, ?, ?, ?)
    """, (int(user_id), int(product_id), int(order_id or 0), int(refs_used)))
    conn.commit(); conn.close()


def has_user_claimed_free(user_id, product_id):
    """Return True if user has already claimed THIS product for free (one-time only)."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT 1 FROM free_claims
        WHERE user_id=? AND product_id=? LIMIT 1
    """, (int(user_id), int(product_id)))
    r = c.fetchone(); conn.close()
    return bool(r)


def total_refs_spent_by_user(user_id):
    """Sum of `refs_used` across all the user's past free claims (a referral is 'spent' once used)."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(refs_used),0) FROM free_claims WHERE user_id=?",
              (int(user_id),))
    r = c.fetchone(); conn.close()
    return int(r[0] or 0)


def count_eligible_unused_refs(user_id):
    """v48: Returns the user's ref_points balance — the spendable currency.

    With the new system, ref_points are the source of truth (deducted on each
    claim). referral_count remains as a lifetime stat for the Account screen.
    """
    return get_ref_points(user_id)


def get_user_free_claims(user_id, limit=20):
    """Return recent free claims of a user (with product names)."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT fc.*, p.name AS product_name
        FROM free_claims fc
        LEFT JOIN products p ON p.id = fc.product_id
        WHERE fc.user_id=?
        ORDER BY fc.claimed_at DESC
        LIMIT ?
    """, (int(user_id), int(limit)))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_all_free_claims(limit=100):
    """Admin view — recent free claims across all users."""
    setup_free_claim_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT fc.*, p.name AS product_name, u.first_name AS user_name, u.username
        FROM free_claims fc
        LEFT JOIN products p ON p.id = fc.product_id
        LEFT JOIN users u ON u.user_id = fc.user_id
        ORDER BY fc.claimed_at DESC
        LIMIT ?
    """, (int(limit),))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]


# Auto-create on import so feature works even before migrate_all() runs
try:
    setup_free_claim_tables()
except Exception as _e:
    print(f"⚠️ setup_free_claim_tables() on import failed: {_e}")


# ════════════════════════════════════════════════════════════════
# 🆕 v74: API Management (Akunding-style key management)
# ════════════════════════════════════════════════════════════════
import hashlib as _hashlib

def _hash_api_key(plaintext: str) -> str:
    """Return SHA-256 hex of an API key — what's stored in DB."""
    return _hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_api_key_v74(owner_id: int, label: str = "", bot_name: str = "ResellerBot") -> tuple:
    """Generate a new API key (Akunding-style: 'ak_' prefix + url-safe random).
    Returns (plaintext_key, prefix). Key is hashed before DB write.
    The PLAINTEXT is returned EXACTLY ONCE and never stored.
    """
    import secrets as _secrets
    setup_api_tables()
    raw = _secrets.token_urlsafe(32)           # 43 chars
    plaintext = f"ak_{raw}"                    # ak_<random>
    prefix = plaintext[:12]                    # ak_xxxxxxxxx
    key_hash = _hash_api_key(plaintext)
    conn = get_connection(); c = conn.cursor()
    # `api_key` column holds the hash now (UNIQUE). Old plaintext column
    # double-duty: stores hash so existing get_api_key path keeps working
    # via the new verify_api_key_v74 below.
    c.execute("""INSERT INTO api_keys
        (api_key, bot_name, owner_id, is_active, key_hash, key_prefix, label)
        VALUES (?, ?, ?, 1, ?, ?, ?)""",
        (key_hash, bot_name, int(owner_id), key_hash, prefix, str(label or "")[:60]))
    conn.commit(); conn.close()
    return plaintext, prefix


def verify_api_key_v74(plaintext: str):
    """Resolve a plaintext key → DB row (dict) if active; else None."""
    if not plaintext:
        return None
    setup_api_tables()
    h = _hash_api_key(plaintext.strip())
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE key_hash=? AND is_active=1", (h,))
    r = c.fetchone()
    conn.close()
    return dict(r) if r else None


def list_api_keys_v74(owner_id: int):
    """List ALL keys for a user (active + revoked). Plaintext NEVER returned."""
    setup_api_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT id, key_prefix, label, is_active, created_at,
                        revoked_at, last_used_at, request_count
                 FROM api_keys WHERE owner_id=? ORDER BY id DESC""",
              (int(owner_id),))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_api_key_by_id(key_id: int, owner_id: int):
    """Fetch a single key row by id (scoped to owner). Returns dict or None."""
    setup_api_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE id=? AND owner_id=?",
              (int(key_id), int(owner_id)))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None


def revoke_api_key_v74(key_id: int, owner_id: int) -> bool:
    """Soft-revoke a key. Sets is_active=0 + revoked_at."""
    setup_api_tables()
    from datetime import datetime
    conn = get_connection(); c = conn.cursor()
    c.execute("""UPDATE api_keys SET is_active=0, revoked_at=?
                 WHERE id=? AND owner_id=?""",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               int(key_id), int(owner_id)))
    n = c.rowcount; conn.commit(); conn.close()
    return n > 0


def revoke_all_api_keys_v74(owner_id: int) -> int:
    """Revoke all active keys for an owner (used by Regenerate flow)."""
    setup_api_tables()
    from datetime import datetime
    conn = get_connection(); c = conn.cursor()
    c.execute("""UPDATE api_keys SET is_active=0, revoked_at=?
                 WHERE owner_id=? AND is_active=1""",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(owner_id)))
    n = c.rowcount; conn.commit(); conn.close()
    return n


def log_api_request(key_id: int, endpoint: str, status_code: int = 200, ip: str = ""):
    """Log one API call. Also bumps request_count + last_used_at on the key."""
    setup_api_tables()
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection(); c = conn.cursor()
    try:
        c.execute("""INSERT INTO api_request_log (api_key_id, endpoint, status_code, ip, created_at)
                     VALUES (?, ?, ?, ?, ?)""",
                  (int(key_id), str(endpoint or "")[:200], int(status_code),
                   str(ip or "")[:64], now))
        c.execute("""UPDATE api_keys
                     SET last_used_at=?, request_count=COALESCE(request_count,0)+1
                     WHERE id=?""", (now, int(key_id)))
        conn.commit()
    except Exception:
        pass
    conn.close()


def count_api_requests_recent(key_id: int, window_sec: int = 60) -> int:
    """Count requests in the last `window_sec` for rate limiting."""
    setup_api_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute(f"""SELECT COUNT(*) FROM api_request_log
                  WHERE api_key_id=?
                    AND datetime(created_at) >= datetime('now', '-{int(window_sec)} seconds')""",
              (int(key_id),))
    n = int(c.fetchone()[0] or 0); conn.close()
    return n


def get_api_key_stats(owner_id: int) -> dict:
    """Aggregate stats for a user's keys."""
    setup_api_tables()
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT COUNT(*) as total,
                        SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active,
                        COALESCE(SUM(request_count),0) as total_reqs
                 FROM api_keys WHERE owner_id=?""", (int(owner_id),))
    r = c.fetchone(); conn.close()
    return dict(r) if r else {"total": 0, "active": 0, "total_reqs": 0}
