import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, session, jsonify, g, send_from_directory, Response
from werkzeug.security import check_password_hash, generate_password_hash
import informes
from catalogo import PROBLEMAS
from db import get_db, close_db, init_db, now_sql

app = Flask(__name__)
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")
if app.config["DATABASE_URL"] and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Define la variable de entorno SECRET_KEY en producción")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-cambiar-en-produccion")
app.config["DATABASE"] = os.environ.get("DATABASE", os.path.join(os.path.dirname(__file__), "polireport.db"))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=90)  # la sesión dura 90 días en el teléfono
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.teardown_appcontext(close_db)

ROLES_CREAR = ("estudiante", "profesor", "admin")
PRIORIDADES = ("Alta", "Media", "Baja")
ORDEN = {"Baja": 0, "Media": 1, "Alta": 2}
APOYOS_MEDIA, APOYOS_ALTA = 3, 5   # personas que deben apoyar para subir la urgencia
FMT = "%Y-%m-%d %H:%M:%S"

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

def ahora_utc():
    return datetime.now(timezone.utc)

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
SELECT r.id_reporte, r.descripcion, r.prioridad, r.fecha, r.fecha_resuelto, r.foto, r.foto_despues,
       r.curso, r.problema, r.id_lugar, l.nombre AS lugar, l.grupo, r.id_categoria, c.nombre AS categoria,
       r.id_estado, e.nombre AS estado, r.id_usuario, u.nombre AS autor,
       r.id_encargado, en.nombre AS encargado,
       (SELECT COUNT(*) FROM apoyos a WHERE a.id_reporte=r.id_reporte) AS apoyos
FROM reportes r
JOIN lugares l ON l.id_lugar=r.id_lugar
JOIN categorias c ON c.id_categoria=r.id_categoria
JOIN estados e ON e.id_estado=r.id_estado
JOIN usuarios u ON u.id_usuario=r.id_usuario
LEFT JOIN encargados en ON en.id_encargado=r.id_encargado
"""
LIST_SQL = BASE_SQL.replace("r.foto, r.foto_despues,",
    "(r.foto IS NOT NULL) AS tiene_foto, (r.foto_despues IS NOT NULL) AS tiene_foto_despues,")

def puede_ver(rep):
    u = g.user
    if u["rol"] == "admin": return True
    if u["rol"] == "mantenimiento": return rep["id_encargado"] == u["id_encargado"]
    return rep["id_usuario"] == u["id_usuario"]

def foto_valida(f):
    return isinstance(f, str) and f.startswith("data:image/") and len(f) < 2_000_000

def corto(txt, n=60):
    txt = (txt or "").strip().replace("\n", " ")
    return txt if len(txt) <= n else txt[:n - 1] + "…"

def log_evento(db, rid, uid, tipo, texto):
    db.execute("INSERT INTO eventos(id_reporte,id_usuario,tipo,texto) VALUES (?,?,?,?)", (rid, uid, tipo, texto[:300]))

def avisar(db, uids, rid, texto, excepto=None):
    for uid in {u for u in uids if u and u != excepto}:
        db.execute("INSERT INTO avisos(id_usuario,id_reporte,texto) VALUES (?,?,?)", (uid, rid, texto[:200]))

def ids_admin(db):
    return [r["id_usuario"] for r in db.execute("SELECT id_usuario FROM usuarios WHERE rol='admin'")]

def ids_de_encargado(db, id_encargado):
    if not id_encargado: return []
    return [r["id_usuario"] for r in db.execute("SELECT id_usuario FROM usuarios WHERE id_encargado=?", (id_encargado,))]

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
    if foto and not foto_valida(foto):
        return err("Foto inválida o demasiado grande")
    cur = db.execute("INSERT INTO reportes(descripcion,id_lugar,id_categoria,id_usuario,prioridad,foto,curso,problema) VALUES (?,?,?,?,?,?,?,?) RETURNING id_reporte",
                     (desc, to_int(d["id_lugar"]), to_int(d["id_categoria"]), g.user["id_usuario"], prio, foto or None, curso, problema))
    rid = cur.fetchone()["id_reporte"]
    lugar = db.execute("SELECT nombre FROM lugares WHERE id_lugar=?", (to_int(d["id_lugar"]),)).fetchone()["nombre"]
    log_evento(db, rid, g.user["id_usuario"], "creado", "Reporte creado")
    avisar(db, ids_admin(db), rid, f"Nuevo reporte ({prio}) en {lugar}: {corto(problema or desc)}", excepto=g.user["id_usuario"])
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
    db = get_db()
    r = db.execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or not puede_ver(r): return err("No encontrado", 404)
    ev = db.execute("""SELECT e.tipo, e.texto, e.fecha, COALESCE(u.nombre, 'Sistema') AS autor, u.rol
                       FROM eventos e LEFT JOIN usuarios u ON u.id_usuario=e.id_usuario
                       WHERE e.id_reporte=? ORDER BY e.id_evento""", (rid,))
    return jsonify({**dict(r), "eventos": [dict(x) for x in ev]})

@app.patch("/api/reportes/<int:rid>")
@login_required("admin", "mantenimiento")
def actualizar_reporte(rid):
    db, d, u = get_db(), request.get_json(silent=True) or {}, g.user
    r = db.execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or not puede_ver(r): return err("No encontrado", 404)
    es_admin = u["rol"] == "admin"
    for k in ("id_estado", "id_encargado"):
        if d.get(k) not in (None, ""):
            d[k] = to_int(d[k])
            if d[k] is None: return err("Valor inválido")
    enc = None
    if es_admin and d.get("id_encargado"):
        enc = db.execute("SELECT * FROM encargados WHERE id_encargado=?", (d["id_encargado"],)).fetchone()
        if not enc: return err("Encargado inválido")
    estado_nuevo = d.get("id_estado") or r["id_estado"]
    if enc and estado_nuevo == 1:
        estado_nuevo = 2  # asignar encargado => En revisión
    sets, args, partes, eventos = [], [], [], []
    if estado_nuevo != r["id_estado"]:
        nombre = db.execute("SELECT nombre FROM estados WHERE id_estado=?", (estado_nuevo,)).fetchone()
        if not nombre: return err("Estado inválido")
        sets += ["id_estado=?", "fecha_resuelto=" + (now_sql() if estado_nuevo == 3 else "NULL")]; args.append(estado_nuevo)
        eventos.append(("estado", f"Estado: {r['estado']} → {nombre['nombre']}"))
        partes.append(f"pasó a {nombre['nombre']}")
    if es_admin and d.get("prioridad") and d["prioridad"] != r["prioridad"]:
        if d["prioridad"] not in PRIORIDADES: return err("Prioridad inválida")
        sets.append("prioridad=?"); args.append(d["prioridad"])
        eventos.append(("prioridad", f"Urgencia: {r['prioridad']} → {d['prioridad']}"))
    if enc and enc["id_encargado"] != r["id_encargado"]:
        sets.append("id_encargado=?"); args.append(enc["id_encargado"])
        eventos.append(("asignado", f"Asignado a {enc['nombre']}"))
        partes.append(f"fue asignado a {enc['nombre']}")
        avisar(db, ids_de_encargado(db, enc["id_encargado"]), rid,
               f"Te asignaron un reporte en {r['lugar']}: {corto(r['problema'] or r['descripcion'])}", excepto=u["id_usuario"])
    if d.get("foto_despues"):
        if not foto_valida(d["foto_despues"]): return err("Foto inválida o demasiado grande")
        sets.append("foto_despues=?"); args.append(d["foto_despues"])
        eventos.append(("foto", "Se agregó la foto del arreglo"))
        partes.append("tiene foto del arreglo")
    if not sets: return err("Nada que actualizar")
    db.execute(f"UPDATE reportes SET {', '.join(sets)} WHERE id_reporte=?", (*args, rid))
    for tipo, texto in eventos:
        log_evento(db, rid, u["id_usuario"], tipo, texto)
    if partes:
        avisar(db, [r["id_usuario"]], rid, f"Tu reporte «{corto(r['problema'] or r['descripcion'], 40)}» " + " y ".join(partes), excepto=u["id_usuario"])
    db.commit()
    return jsonify(ok=True)

@app.post("/api/reportes/<int:rid>/comentarios")
@login_required()
def comentar(rid):
    db, u = get_db(), g.user
    r = db.execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or not puede_ver(r): return err("No encontrado", 404)
    texto = ((request.get_json(silent=True) or {}).get("texto") or "").strip()
    if len(texto) < 2: return err("Escribe un comentario")
    log_evento(db, rid, u["id_usuario"], "comentario", texto[:500])
    avisar(db, [r["id_usuario"], *ids_admin(db), *ids_de_encargado(db, r["id_encargado"])], rid,
           f"{u['nombre']} comentó en «{corto(r['problema'] or r['descripcion'], 40)}»", excepto=u["id_usuario"])
    db.commit()
    return jsonify(ok=True), 201

@app.post("/api/reportes/<int:rid>/apoyo")
@login_required("estudiante", "profesor")
def apoyo(rid):
    db, u = get_db(), g.user
    r = db.execute(BASE_SQL + " WHERE r.id_reporte=?", (rid,)).fetchone()
    if not r or r["id_estado"] == 3: return err("Ese reporte ya no está abierto", 404)
    if r["id_usuario"] == u["id_usuario"]: return err("Es tu propio reporte")
    ya = db.execute("SELECT 1 FROM apoyos WHERE id_reporte=? AND id_usuario=?", (rid, u["id_usuario"])).fetchone()
    if ya:
        db.execute("DELETE FROM apoyos WHERE id_reporte=? AND id_usuario=?", (rid, u["id_usuario"]))
    else:
        db.execute("INSERT INTO apoyos(id_reporte,id_usuario) VALUES (?,?)", (rid, u["id_usuario"]))
    n = db.execute("SELECT COUNT(*) AS n FROM apoyos WHERE id_reporte=?", (rid,)).fetchone()["n"]
    prio = r["prioridad"]
    if not ya:
        objetivo = "Alta" if n >= APOYOS_ALTA else "Media" if n >= APOYOS_MEDIA else None
        if objetivo and ORDEN[objetivo] > ORDEN[prio]:
            db.execute("UPDATE reportes SET prioridad=? WHERE id_reporte=?", (objetivo, rid))
            log_evento(db, rid, None, "prioridad", f"Urgencia: {prio} → {objetivo} ({n} personas reportaron lo mismo)")
            avisar(db, [r["id_usuario"], *ids_admin(db)], rid, f"La urgencia de «{corto(r['problema'] or r['descripcion'], 40)}» subió a {objetivo}")
            prio = objetivo
        else:
            avisar(db, [r["id_usuario"]], rid, f"A otra persona también le pasa lo de «{corto(r['problema'] or r['descripcion'], 40)}»")
    db.commit()
    return jsonify(apoyos=n, yo_apoyo=not ya, prioridad=prio)

@app.get("/api/similares")
@login_required(*ROLES_CREAR)
def similares():
    lugar, cat = to_int(request.args.get("id_lugar")), to_int(request.args.get("id_categoria"))
    if lugar is None or cat is None: return jsonify([])
    desde = (ahora_utc() - timedelta(days=45)).strftime(FMT)
    uid = g.user["id_usuario"]
    rows = get_db().execute("""SELECT r.id_reporte, r.descripcion, r.problema, r.fecha, r.id_usuario,
        (SELECT COUNT(*) FROM apoyos a WHERE a.id_reporte=r.id_reporte) AS apoyos,
        (SELECT COUNT(*) FROM apoyos a WHERE a.id_reporte=r.id_reporte AND a.id_usuario=?) AS yo
        FROM reportes r WHERE r.id_lugar=? AND r.id_categoria=? AND r.id_estado<>3 AND r.fecha>=?
        ORDER BY r.fecha DESC LIMIT 5""", (uid, lugar, cat, desde))
    return jsonify([{"id_reporte": r["id_reporte"], "descripcion": corto(r["descripcion"], 120), "problema": r["problema"],
                     "fecha": r["fecha"], "apoyos": r["apoyos"], "yo_apoyo": bool(r["yo"]), "es_mio": r["id_usuario"] == uid}
                    for r in rows])

# ---------- avisos (bandeja dentro de la app) ----------
@app.get("/api/avisos")
@login_required()
def avisos():
    db, uid = get_db(), g.user["id_usuario"]
    db.execute("DELETE FROM avisos WHERE id_usuario=? AND fecha<?", (uid, (ahora_utc() - timedelta(days=60)).strftime(FMT)))
    items = [dict(r) for r in db.execute("SELECT id_aviso,id_reporte,texto,leido,fecha FROM avisos WHERE id_usuario=? ORDER BY id_aviso DESC LIMIT 40", (uid,))]
    db.commit()
    return jsonify(no_leidos=sum(1 for i in items if not i["leido"]), items=items)

@app.get("/api/avisos/conteo")
@login_required()
def avisos_conteo():
    n = get_db().execute("SELECT COUNT(*) AS n FROM avisos WHERE id_usuario=? AND leido=0", (g.user["id_usuario"],)).fetchone()["n"]
    return jsonify(no_leidos=n)

@app.post("/api/avisos/leer")
@login_required()
def avisos_leer():
    db, d = get_db(), request.get_json(silent=True) or {}
    if to_int(d.get("id")):
        db.execute("UPDATE avisos SET leido=1 WHERE id_aviso=? AND id_usuario=?", (to_int(d["id"]), g.user["id_usuario"]))
    else:
        db.execute("UPDATE avisos SET leido=1 WHERE id_usuario=?", (g.user["id_usuario"],))
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
    horas = []
    for r in db.execute("SELECT fecha, fecha_resuelto FROM reportes WHERE id_estado=3 AND fecha_resuelto IS NOT NULL"):
        horas.append((datetime.strptime(r["fecha_resuelto"], FMT) - datetime.strptime(r["fecha"], FMT)).total_seconds() / 3600)
    limite = (ahora_utc() - timedelta(days=7)).strftime(FMT)
    return jsonify(
        total=db.execute("SELECT COUNT(*) AS n FROM reportes").fetchone()["n"],
        promedio_horas=(sum(horas) / len(horas)) if horas else None,
        atrasados=db.execute("SELECT COUNT(*) AS n FROM reportes WHERE id_estado<>3 AND fecha<?", (limite,)).fetchone()["n"],
        por_estado=agg("SELECT e.nombre, COUNT(r.id_reporte) AS n FROM estados e LEFT JOIN reportes r ON r.id_estado=e.id_estado GROUP BY e.id_estado"),
        por_lugar=agg("SELECT l.nombre, COUNT(*) AS n FROM reportes r JOIN lugares l USING(id_lugar) GROUP BY l.id_lugar ORDER BY n DESC"),
        por_categoria=agg("SELECT c.nombre, COUNT(*) AS n FROM reportes r JOIN categorias c USING(id_categoria) GROUP BY c.id_categoria ORDER BY n DESC"),
        por_prioridad=agg("SELECT prioridad AS nombre, COUNT(*) AS n FROM reportes GROUP BY prioridad"))

# ---------- informes descargables ----------
def filas_informe():
    def limite(nombre, fin):
        v = request.args.get(nombre)
        try:
            dt = datetime.strptime(v, "%Y-%m-%d") + timedelta(hours=4, days=1 if fin else 0)  # hora local RD -> UTC
            return v, (dt - timedelta(seconds=1) if fin else dt).strftime(FMT)
        except (TypeError, ValueError):
            return None, None
    (desde, d_utc), (hasta, h_utc) = limite("desde", False), limite("hasta", True)
    where, args = [], []
    if d_utc: where.append("r.fecha>=?"); args.append(d_utc)
    if h_utc: where.append("r.fecha<=?"); args.append(h_utc)
    sql = LIST_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY r.fecha DESC"
    return [dict(r) for r in get_db().execute(sql, args)], desde, hasta

@app.get("/api/informe.xlsx")
@login_required("admin")
def informe_xlsx():
    rows, desde, hasta = filas_informe()
    return Response(informes.xlsx_bytes(rows, desde, hasta),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=reportes-polireport.xlsx"})

@app.get("/api/informe.pdf")
@login_required("admin")
def informe_pdf():
    rows, desde, hasta = filas_informe()
    return Response(informes.pdf_bytes(rows, desde, hasta), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=reportes-polireport.pdf"})

# ---------- administración: encargados y áreas ----------
@app.get("/api/admin/encargados")
@login_required("admin")
def adm_encargados():
    rows = get_db().execute("""SELECT en.id_encargado, en.nombre, en.especialidad, u.correo,
        (SELECT COUNT(*) FROM reportes r WHERE r.id_encargado=en.id_encargado AND r.id_estado<>3) AS abiertos
        FROM encargados en LEFT JOIN usuarios u ON u.id_encargado=en.id_encargado ORDER BY en.nombre""")
    return jsonify([dict(r) for r in rows])

@app.post("/api/admin/encargados")
@login_required("admin")
def adm_encargado_crear():
    db, d = get_db(), request.get_json(silent=True) or {}
    nombre, esp = (d.get("nombre") or "").strip(), (d.get("especialidad") or "").strip() or None
    correo, pw = (d.get("correo") or "").strip().lower(), d.get("password") or ""
    if len(nombre) < 2: return err("Escribe el nombre del encargado")
    if correo or pw:
        if "@" not in correo or len(pw) < 6: return err("Para crearle acceso: correo válido y contraseña (mín. 6)")
        if db.execute("SELECT 1 FROM usuarios WHERE correo=?", (correo,)).fetchone(): return err("Ese correo ya está registrado", 409)
    eid = db.execute("INSERT INTO encargados(nombre, especialidad) VALUES (?,?) RETURNING id_encargado", (nombre, esp)).fetchone()["id_encargado"]
    if correo:
        db.execute("INSERT INTO usuarios(nombre,correo,password_hash,rol,id_encargado) VALUES (?,?,?,?,?)",
                   (nombre, correo, generate_password_hash(pw), "mantenimiento", eid))
    db.commit()
    return jsonify(id_encargado=eid), 201

@app.patch("/api/admin/encargados/<int:eid>")
@login_required("admin")
def adm_encargado_editar(eid):
    db, d = get_db(), request.get_json(silent=True) or {}
    if not db.execute("SELECT 1 FROM encargados WHERE id_encargado=?", (eid,)).fetchone(): return err("No encontrado", 404)
    nombre, esp = (d.get("nombre") or "").strip(), (d.get("especialidad") or "").strip() or None
    if len(nombre) < 2: return err("Escribe el nombre del encargado")
    db.execute("UPDATE encargados SET nombre=?, especialidad=? WHERE id_encargado=?", (nombre, esp, eid))
    db.execute("UPDATE usuarios SET nombre=? WHERE id_encargado=?", (nombre, eid))
    if d.get("password"):
        if len(d["password"]) < 6: return err("La contraseña debe tener al menos 6 caracteres")
        db.execute("UPDATE usuarios SET password_hash=? WHERE id_encargado=?", (generate_password_hash(d["password"]), eid))
    db.commit()
    return jsonify(ok=True)

@app.delete("/api/admin/encargados/<int:eid>")
@login_required("admin")
def adm_encargado_borrar(eid):
    db = get_db()
    if db.execute("SELECT 1 FROM reportes WHERE id_encargado=?", (eid,)).fetchone():
        return err("Tiene reportes asignados. Reasígnalos primero.", 409)
    db.execute("DELETE FROM usuarios WHERE id_encargado=?", (eid,))
    db.execute("DELETE FROM encargados WHERE id_encargado=?", (eid,))
    db.commit()
    return jsonify(ok=True)

def datos_area():
    d = request.get_json(silent=True) or {}
    return (d.get("nombre") or "").strip(), (d.get("grupo") or "").strip() or None

@app.post("/api/admin/lugares")
@login_required("admin")
def adm_lugar_crear():
    db, (nombre, grupo) = get_db(), datos_area()
    if len(nombre) < 2: return err("Escribe el nombre del área")
    if db.execute("SELECT 1 FROM lugares WHERE nombre=?", (nombre,)).fetchone(): return err("Ya existe un área con ese nombre", 409)
    lid = db.execute("INSERT INTO lugares(nombre, grupo) VALUES (?,?) RETURNING id_lugar", (nombre, grupo)).fetchone()["id_lugar"]
    db.commit()
    return jsonify(id_lugar=lid), 201

@app.patch("/api/admin/lugares/<int:lid>")
@login_required("admin")
def adm_lugar_editar(lid):
    db, (nombre, grupo) = get_db(), datos_area()
    if not db.execute("SELECT 1 FROM lugares WHERE id_lugar=?", (lid,)).fetchone(): return err("No encontrado", 404)
    if len(nombre) < 2: return err("Escribe el nombre del área")
    if db.execute("SELECT 1 FROM lugares WHERE nombre=? AND id_lugar<>?", (nombre, lid)).fetchone(): return err("Ya existe un área con ese nombre", 409)
    db.execute("UPDATE lugares SET nombre=?, grupo=? WHERE id_lugar=?", (nombre, grupo, lid))
    db.commit()
    return jsonify(ok=True)

@app.delete("/api/admin/lugares/<int:lid>")
@login_required("admin")
def adm_lugar_borrar(lid):
    db = get_db()
    if db.execute("SELECT 1 FROM reportes WHERE id_lugar=?", (lid,)).fetchone():
        return err("Hay reportes en esa área; no se puede borrar (puedes renombrarla).", 409)
    db.execute("DELETE FROM lugares WHERE id_lugar=?", (lid,))
    db.commit()
    return jsonify(ok=True)

init_db(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
