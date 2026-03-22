import tempfile
import os


def test_db_has_thread_columns():
    """Verify migrate_db() adds top_comments and our_take columns."""
    from flatwhite.db import init_db, migrate_db, get_connection, DB_PATH

    # Use a temp DB so we don't touch real data
    import flatwhite.db as db_module
    orig_path = db_module.DB_PATH
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_module.DB_PATH = type(db_module.DB_PATH)(tmp.name)

    try:
        init_db()
        migrate_db()
        conn = db_module.get_connection()
        cols_raw = [row[1] for row in conn.execute("PRAGMA table_info(raw_items)").fetchall()]
        cols_cur = [row[1] for row in conn.execute("PRAGMA table_info(curated_items)").fetchall()]
        conn.close()
        assert "top_comments" in cols_raw, "top_comments missing from raw_items"
        assert "our_take" in cols_cur, "our_take missing from curated_items"
    finally:
        db_module.DB_PATH = orig_path
        os.unlink(tmp.name)
