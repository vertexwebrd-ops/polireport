import os, tempfile
os.environ["DATABASE"] = os.path.join(tempfile.mkdtemp(), "t.db")
from app import app
c = app.test_client()
def login(u, p): return c.post("/api/login", json={"correo": u, "password": p})

assert login("estudiante@poli.edu", "mal").status_code == 401
assert login("estudiante@poli.edu", "demo123").status_code == 200
r = c.post("/api/reportes", json={"descripcion": "Abanico dañado", "id_lugar": 1, "id_categoria": 1, "prioridad": "Media"})
assert r.status_code == 201, r.json
rid = r.json["id_reporte"]
assert c.patch(f"/api/reportes/{rid}", json={"id_estado": 3}).status_code == 403   # estudiante no edita
assert c.get("/api/estadisticas").status_code == 403
assert len(c.get("/api/reportes").json) == 1
c.post("/api/logout")

login("admin@poli.edu", "admin123")
assert c.patch(f"/api/reportes/{rid}", json={"id_encargado": 1, "prioridad": "Alta"}).status_code == 200
rep = c.get(f"/api/reportes/{rid}").json
assert rep["estado"] == "En revisión" and rep["prioridad"] == "Alta" and rep["encargado"] == "Juan Pérez"
assert c.get("/api/estadisticas").json["total"] == 1
c.post("/api/logout")

login("juan@poli.edu", "demo123")
assert len(c.get("/api/reportes").json) == 1
assert c.patch(f"/api/reportes/{rid}", json={"id_estado": 3}).status_code == 200
c.post("/api/logout")

login("admin@poli.edu", "admin123")
h = c.get("/api/historial").json
assert len(h) == 1 and h[0]["fecha_resuelto"]
print("TODO OK")
assert c.get("/").status_code == 200 and b"PoliReport" in c.get("/").data
assert c.get("/sw.js").status_code == 200
assert c.get("/static/manifest.webmanifest").status_code == 200
print("FRONT OK")
# asignar con id_estado=1 explícito (como lo envía la app) => En revisión
c.post("/api/logout"); login("estudiante@poli.edu", "demo123")
r2 = c.post("/api/reportes", json={"descripcion": "Proyector intermitente", "id_lugar": 3, "id_categoria": 2}).json["id_reporte"]
c.post("/api/logout"); login("admin@poli.edu", "admin123")
c.patch(f"/api/reportes/{r2}", json={"id_estado": 1, "id_encargado": 2, "prioridad": "Media"})
assert c.get(f"/api/reportes/{r2}").json["estado"] == "En revisión"
print("ASIGNAR OK")
# filtros, búsqueda sin distinguir mayúsculas, entradas inválidas
assert len(c.get("/api/reportes?q=PROYECTOR").json) == 1
assert len(c.get("/api/reportes?estado=abc").json) == 2
assert c.get("/api/reportes?prioridad=Alta").status_code == 200
c.post("/api/logout"); login("estudiante@poli.edu", "demo123")
assert c.post("/api/reportes", json={"descripcion": "algo roto", "id_lugar": "x", "id_categoria": 1}).status_code == 400
assert c.post("/api/reportes", json={"descripcion": "algo roto", "id_lugar": 1, "id_categoria": 1, "foto": "javascript:alert(1)"}).status_code == 400
assert c.post("/api/reportes", json={"descripcion": "con foto", "id_lugar": 1, "id_categoria": 1, "foto": "data:image/jpeg;base64,AAAA"}).status_code == 201
print("VALIDACIONES OK")
# la lista no manda la foto; el detalle sí
c.post("/api/logout"); login("estudiante@poli.edu", "demo123")
lst = c.get("/api/reportes").json
con_foto = [r for r in lst if r.get("tiene_foto")]
assert con_foto and "foto" not in lst[0]
assert c.get(f"/api/reportes/{con_foto[0]['id_reporte']}").json["foto"].startswith("data:image/")
print("LISTA LIGERA OK")
# la sesión persiste (cookie con fecha de expiración)
c.post("/api/logout")
r = login("admin@poli.edu", "admin123")
assert "expires=" in r.headers.get("Set-Cookie", "").lower(), r.headers.get("Set-Cookie")
print("SESION PERSISTENTE OK")
# catálogo del centro
cat = c.get("/api/catalogos").json
assert any(l["nombre"] == "5.º de Enfermería" and l["grupo"] == "Enfermería" for l in cat["lugares"])
assert [k["nombre"] for k in cat["categorias"]][:3] == ["Electricidad", "Agua y plomería", "Mobiliario"]
assert "Fugas de agua" in cat["problemas"]["Agua y plomería"]
c.post("/api/logout"); login("estudiante@poli.edu", "demo123")
ok = c.post("/api/reportes", json={"descripcion": "No enciende", "id_lugar": 8, "id_categoria": 6,
            "problema": "Computadoras que no funcionan", "curso": "5to Informática A", "prioridad": "Alta"})
assert ok.status_code == 201, ok.json
det = c.get(f"/api/reportes/{ok.json['id_reporte']}").json
assert det["problema"] == "Computadoras que no funcionan" and det["curso"] == "5to Informática A" and det["grupo"]
bad = c.post("/api/reportes", json={"descripcion": "No enciende", "id_lugar": 8, "id_categoria": 1, "problema": "Fugas de agua"})
assert bad.status_code == 400
print("CATALOGO OK")
