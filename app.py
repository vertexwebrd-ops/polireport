import os
from datetime import timedelta
from functools import wraps
from flask import Flask, request, session, jsonify, g, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from catalogo import PROBLEMAS
from db import get_db, close_db, init_db, now_sql

app = Flask(__name__)
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")
if app.config["DATABASE_URL"] and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Define la variable de entorno SECRET_KEY en producción")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-cambiar-en-produccion")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=90)  # la sesión dura 90 días en el teléfono
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.config["DATABASE"] = os.environ.get("DATABASE", os.path.join(os.path.dirname(__file__), "polireport.db"))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.teardown_appcontext(close_db)

ROLES_CREAR = ("estudiante", "profesor", "admin")
PRIORIDADES = ("Alta", "Media", "Baja")

# ---------- frontend (PWA) ----------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/sw.js")
def service_worker():
    r = send_from_directory(app.static_folder, "sw.js")
    r.headers["Cache-Control"] = "no-cache"
    return r

# ---------- helpers ----------
def to_int(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def err(msg, code=400):
    return jsonify(error=msg), code

def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            uid = session.get("uid")
            if not uid:
                return err("No autenticado", 401)
            u = get_db().execute("SELECT * FROM usuarios WHERE id_usuario=?", (uid,)).fetchone()
            if not u:
                session.clear()
                return err("No autenticado", 401)
            if roles and u["rol"] not in roles:
                return err("Sin permiso", 403)
            g.user = u
            return fn(*a, **kw)
        return wrapper
    return deco

BASE_SQL = """
SELECT r.id_reporte, r.descripcion, r.prioridad, r.fecha, r.fecha_resuelto, r.foto,
       r.id_lugar, l.nombre AS lugar, l.grupo, r.curso, r.problema, r.id_categoria, c.nombre AS categoria,
       r.id_estado, e.nombre AS estado, r.id_usuario, u.nombre AS autor,
       r.id_encargado, en.nombre AS encargado
FROM reportes r
JOIN lugares l ON l.id_lugar=r.id_lugar
JOIN categorias c ON c.id_categoria=r.id_categoria
JOIN estados e ON e.id_estado=r.id_estado
JOIN usuarios u ON u.id_usuario=r.id_usuario
LEFT JOIN encargados en ON en.id_encargado=r.id_encargado
"""

LIST_SQL = BASE_SQL.replace("r.foto,", "(r.foto IS NOT NULL) AS tiene_foto,")

def puede_ver(rep):
    u = g.user
    if u["rol"] == "admin": return True
    if u["rol"] == "mantenimiento": return rep["id_encargado"] == u["id_encargado"]
    return rep["id_usuario"] == u["id_usuario"]

# ---------- auth ----------
@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = get_db().execute("SELECT * FROM usuarios WHERE correo=?", ((d.get("correo") or "").strip().lower(),)).fetchone()
    if not u or not check_password_hash(u["password_hash"], d.get("password") or ""):
        return err("Correo o contraseña incorrectos", 401)
    session.permanent = True
    session["uid"] = u["id_usuario"]
    return jsonify(id=u["id_usuario"], nombre=u["nombre"], rol=u["rol"])

@app.post("/api/registro")
def registro():
    d = request.get_json(silent=True) or {}
    nombre, correo, pw = (d.get("nombre") or "").strip(), (d.get("correo") or "").strip().lower(), d.get("password") or ""
    rol = d.get("rol", "estudiante")
    if not nombre or "@" not in correo or len(pw) < 6:
        return err("Nombre, correo válido y contraseña (mín. 6) son obligatorios")
    if rol not in ("estudiante", "profesor"):
        return err("Rol no permitido")
    db = get_db()
    if db.execute("SELECT 1 FROM usuarios WHERE correo=?", (correo,)).fetchone():
        return err("Ese correo ya está registrado", 409)
    cur = db.execute("INSERT INTO usuarios(nombre,correo,password_hash,rol) VALUES (?,?,?,?) RETURNING id_usuario",
                     (nombre, correo, generate_password_hash(pw), rol))
    uid = cur.fetchone()["id_usuario"]
    db.commit()
    session.permanent = True
    session["uid"] = uid
    return jsonify(id=uid, nombre=nombre, rol=rol), 201

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/yo")
@login_required()
def yo():
    u = g.user
    return jsonify(id=u["id_usuario"], nombre=u["nombre"], rol=u["rol"])

# ---------- catálogos ----------
@app.get("/api/catalogos")
@login_required()
def catalogos():
    db = get_db()
    q = lambda t, o: [dict(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY {o}")]
    return jsonify(lugares=q("lugares", "id_lugar"), categorias=q("categorias", "id_categoria"), estados=q("estados", "id_estado"),
                   encargados=q("encargados", "id_encargado"), prioridades=list(PRIORIDADES), problemas=PROBLEMAS)

# ---------- reportes ----------
@app.post("/api/reportes")
@login_required(*ROLES_CREAR)
def crear_reporte():
    d = request.get_json(silent=True) or {}
    desc = (d.get("descripcion") or "").strip()
    prio = d.get("prioridad", "Media")
    if len(desc) < 5: return err("Describe el problema (mín. 5 caracteres)")
    if prio not in PRIORIDADES: return err("Prioridad inválida")
    db = get_db()
    for tabla, campo in (("lugares", "id_lugar"), ("categorias", "id_categoria")):
        if to_int(d.get(campo)) is None or not db.execute(f"SELECT 1 FROM {tabla} WHERE {campo}=?", (to_int(d.get(campo)),)).fetchone():
            return err(f"{campo} inválido")
    curso = (d.get("curso") or "").strip()[:60] or None
    problema = (d.get("problema") or "").strip() or None
    if problema:
        cat = db.execute("SELECT nombre FROM categorias WHERE id_categoria=?", (to_int(d["id_categoria"]),)).fetchone()
        if problema not in PROBLEMAS.get(cat["nombre"], []):
            return err("Problemática inválida para ese tipo de problema")
    foto = d.get("foto")
    if foto and not (isinstance(foto, str) and foto.startswith("data:image/") and len(foto) < 2_000_000):
        return err("Foto inválida o demasiado grande")
    cur = db.execute("INSERT INTO reportes(descripcion,id_lugar,id_categoria,id_usuario,prioridad,foto,curso,problema) VALUES (?,?,?,?,?,?,?,?) RETURNING id_reporte",
                     (desc, to_int(d["id_lugar"]), to_int(d["id_categoria"]), g.user["id_usuario"], prio, foto or None, curso, problema))
    rid = cur.fetchone()["id_reporte"]
    db.commit()
    return jsonify(id_reporte=rid), 201

@app.get("/api/reportes")
@login_required()
def listar_reportes():
    u, where, args = g.user, [], []
    if u["rol"] in ("estudiante", "profesor"):
        where.append("r.id_usuario=?"); args.append(u["id_usuario"])
    elif u["rol"] == "mantenimiento":
        where.append("r.id_encargado=?"); args.append(u["id_encargado"])
    for param, col in (("estado", "r.id_estado"), ("prioridad", "r.prioridad"),
                       ("categoria", "r.id_categoria"), ("lugar", "r.id_lugar")):
        v = request.args.get(param)
        if v:
            if param != "prioridad":
                v = to_int(v)
                if v is None: continue
            where.append(f"{col}=?"); args.append(v)
    q = request.args.get("q")
    if q: where.append("LOWER(r.descripcion) LIKE ?"); args.append(f"%{q.lower()}%")
    sql = LIST_SQL + (" WHERE " + " AND ".join(where) if where else "") + \
          " ORDER BY CASE r.prioridad WHEN 'Alta' THEN 0 WHEN 'Media' THEN 1 ELSE 2 END, r.fecha DESC"
    return jsonify([dict(r) for r in get_db().execute(sql, args)])

@app.get("/api/reportes/<int:rid>")
@login_required()
def ver_reporte(rid):
    r = get_db().execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or not puede_ver(r): return err("No encontrado", 404)
    return jsonify(dict(r))

@app.patch("/api/reportes/<int:rid>")
@login_required("admin", "mantenimiento")
def actualizar_reporte(rid):
    db, d = get_db(), request.get_json(silent=True) or {}
    r = db.execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or not puede_ver(r): return err("No encontrado", 404)
    sets, args = [], []
    es_admin = g.user["rol"] == "admin"
    if es_admin and d.get("id_encargado") and d.get("id_estado", r["id_estado"]) == 1:
        d["id_estado"] = 2  # asignar encargado => En revisión
    for k in ("id_estado", "id_encargado"):
        if k in d and d[k] not in (None, ""):
            d[k] = to_int(d[k])
            if d[k] is None: return err("Valor inválido")
    if "id_estado" in d:
        if not db.execute("SELECT 1 FROM estados WHERE id_estado=?", (d["id_estado"],)).fetchone():
            return err("Estado inválido")
        sets.append("id_estado=?"); args.append(d["id_estado"])
        sets.append("fecha_resuelto=" + (now_sql() if d["id_estado"] == 3 else "NULL"))
    if es_admin and "prioridad" in d:
        if d["prioridad"] not in PRIORIDADES: return err("Prioridad inválida")
        sets.append("prioridad=?"); args.append(d["prioridad"])
    if es_admin and d.get("id_encargado"):
        if not db.execute("SELECT 1 FROM encargados WHERE id_encargado=?", (d["id_encargado"],)).fetchone():
            return err("Encargado inválido")
        sets.append("id_encargado=?"); args.append(d["id_encargado"])
    if not sets: return err("Nada que actualizar")
    db.execute(f"UPDATE reportes SET {', '.join(sets)} WHERE id_reporte=?", (*args, rid))
    db.commit()
    return jsonify(ok=True)

@app.get("/api/historial")
@login_required("admin")
def historial():
    rows = get_db().execute(LIST_SQL + " WHERE r.id_estado=3 ORDER BY r.fecha_resuelto DESC")
    return jsonify([dict(r) for r in rows])

# ---------- estadísticas ----------
@app.get("/api/estadisticas")
@login_required("admin")
def estadisticas():
    db = get_db()
    def agg(sql): return [dict(r) for r in db.execute(sql)]
    return jsonify(
        total=db.execute("SELECT COUNT(*) AS n FROM reportes").fetchone()["n"],
        por_estado=agg("SELECT e.nombre, COUNT(r.id_reporte) AS n FROM estados e LEFT JOIN reportes r ON r.id_estado=e.id_estado GROUP BY e.id_estado"),
        por_lugar=agg("SELECT l.nombre, COUNT(*) AS n FROM reportes r JOIN lugares l USING(id_lugar) GROUP BY l.id_lugar ORDER BY n DESC"),
        por_categoria=agg("SELECT c.nombre, COUNT(*) AS n FROM reportes r JOIN categorias c USING(id_categoria) GROUP BY c.id_categoria ORDER BY n DESC"),
        por_prioridad=agg("SELECT prioridad AS nombre, COUNT(*) AS n FROM reportes GROUP BY prioridad"))

init_db(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
