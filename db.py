import os, sqlite3
from flask import g, current_app


class DB:
    """Envoltorio mínimo para usar SQLite (local) o PostgreSQL (producción) con las mismas consultas."""
    def __init__(self, con, pg):
        self.con, self.pg = con, pg

    def execute(self, sql, args=()):
        if self.pg:
            cur = self.con.cursor()
            cur.execute(sql.replace("?", "%s"), tuple(args))
            return cur
        return self.con.execute(sql, args)

    def commit(self):
        self.con.commit()

    def close(self):
        self.con.close()


def connect(app):
    url = app.config.get("DATABASE_URL")
    if url:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return DB(psycopg2.connect(url, cursor_factory=RealDictCursor), True)
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return DB(con, False)


def now_sql():
    if current_app.config.get("DATABASE_URL"):
        return "to_char(now() at time zone 'utc','YYYY-MM-DD HH24:MI:SS')"
    return "datetime('now')"


def get_db():
    if "db" not in g:
        g.db = connect(current_app)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def add_column(db, tabla, col, tipo):
    if db.pg:
        db.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {tipo}")
    else:
        if col not in [r["name"] for r in db.execute(f"PRAGMA table_info({tabla})")]:
            db.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")


def sync_catalogos(db):
    """Deja áreas y categorías como en catalogo.py (sirve para bases nuevas y ya existentes)."""
    from catalogo import (GRUPOS, CATEGORIAS, RENOMBRAR_CATEGORIAS, RENOMBRAR_LUGARES, LUGARES_VIEJOS)
    existe = lambda t, n: db.execute(f"SELECT 1 FROM {t} WHERE nombre=?", (n,)).fetchone()
    for viejo, nuevo in RENOMBRAR_CATEGORIAS.items():
        if existe("categorias", viejo) and not existe("categorias", nuevo):
            db.execute("UPDATE categorias SET nombre=? WHERE nombre=?", (nuevo, viejo))
    for n in CATEGORIAS:
        if not existe("categorias", n):
            db.execute("INSERT INTO categorias(nombre) VALUES (?)", (n,))
    for viejo, nuevo in RENOMBRAR_LUGARES.items():
        if existe("lugares", viejo) and not existe("lugares", nuevo):
            db.execute("UPDATE lugares SET nombre=? WHERE nombre=?", (nuevo, viejo))
    for grupo, nombres in GRUPOS:
        for n in nombres:
            if existe("lugares", n):
                db.execute("UPDATE lugares SET grupo=? WHERE nombre=?", (grupo, n))
            else:
                db.execute("INSERT INTO lugares(nombre, grupo) VALUES (?,?)", (n, grupo))
    for n in LUGARES_VIEJOS:
        db.execute("DELETE FROM lugares WHERE nombre=? AND id_lugar NOT IN (SELECT id_lugar FROM reportes)", (n,))
    db.commit()


def init_db(app):
    from werkzeug.security import generate_password_hash as h
    db = connect(app)
    if db.pg:
        db.execute("SELECT pg_advisory_lock(7331)")  # evita carreras al arrancar
    schema = "schema_pg.sql" if db.pg else "schema.sql"
    with open(os.path.join(os.path.dirname(__file__), schema), encoding="utf-8") as f:
        sql = f.read()
    if db.pg:
        db.con.cursor().execute(sql)
    else:
        db.con.executescript(sql)
    add_column(db, "lugares", "grupo", "TEXT")
    add_column(db, "reportes", "curso", "TEXT")
    add_column(db, "reportes", "problema", "TEXT")
    db.commit()

    if db.execute("SELECT COUNT(*) AS n FROM estados").fetchone()["n"] == 0:
        for n in ("Pendiente", "En revisión", "Resuelto"):
            db.execute("INSERT INTO estados(nombre) VALUES (?)", (n,))
        for n, e in (("Juan Pérez", "Electricidad"), ("María Gómez", "Tecnología")):
            db.execute("INSERT INTO encargados(nombre, especialidad) VALUES (?,?)", (n, e))
        admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
        users = [("Administrador", "admin@poli.edu", admin_pw, "admin", None)]
        if os.environ.get("SEED_DEMO", "1") != "0":
            users += [("Estudiante Demo", "estudiante@poli.edu", "demo123", "estudiante", None),
                      ("Profesor Demo", "profesor@poli.edu", "demo123", "profesor", None),
                      ("Juan Pérez", "juan@poli.edu", "demo123", "mantenimiento", 1)]
        for nombre, correo, pw, rol, enc in users:
            db.execute("INSERT INTO usuarios(nombre, correo, password_hash, rol, id_encargado) VALUES (?,?,?,?,?)",
                       (nombre, correo, h(pw), rol, enc))
        db.commit()
    sync_catalogos(db)
    db.close()
