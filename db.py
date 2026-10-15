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
    db.commit()

    if db.execute("SELECT COUNT(*) AS n FROM estados").fetchone()["n"] == 0:
        for n in ("Pendiente", "En revisión", "Resuelto"):
            db.execute("INSERT INTO estados(nombre) VALUES (?)", (n,))
        for n in ("Electricidad", "Tecnología", "Mobiliario", "Baños", "Otros"):
            db.execute("INSERT INTO categorias(nombre) VALUES (?)", (n,))
        for n in ("Aula 4to Informática", "Aula 2do Comercio", "Laboratorio", "Pasillo", "Baños", "Dirección", "Patio"):
            db.execute("INSERT INTO lugares(nombre) VALUES (?)", (n,))
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
    db.close()
