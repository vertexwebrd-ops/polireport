# Simula la base ya desplegada (esquema y datos de ejemplo anteriores) y comprueba la migración
import os, sqlite3, tempfile
from werkzeug.security import generate_password_hash as h
path = os.path.join(tempfile.mkdtemp(), "old.db")
con = sqlite3.connect(path)
con.executescript(open("schema.sql", encoding="utf-8").read()
    .replace(",\n  grupo TEXT", "").replace(",\n  curso TEXT,\n  problema TEXT", ""))  # esquema viejo
con.executemany("INSERT INTO estados(nombre) VALUES (?)", [("Pendiente",), ("En revisión",), ("Resuelto",)])
con.executemany("INSERT INTO categorias(nombre) VALUES (?)", [("Electricidad",), ("Tecnología",), ("Mobiliario",), ("Baños",), ("Otros",)])
con.executemany("INSERT INTO lugares(nombre) VALUES (?)", [("Aula 4to Informática",), ("Aula 2do Comercio",), ("Laboratorio",), ("Pasillo",), ("Baños",), ("Dirección",), ("Patio",)])
con.execute("INSERT INTO usuarios(nombre,correo,password_hash,rol) VALUES ('A','a@x.com',?, 'admin')", (h("x"),))
con.execute("INSERT INTO reportes(descripcion,id_lugar,id_categoria,id_usuario) VALUES ('viejo 1',1,4,1)")   # Aula 4to Informática + Baños
con.execute("INSERT INTO reportes(descripcion,id_lugar,id_categoria,id_usuario) VALUES ('viejo 2',2,1,1)")   # Aula 2do Comercio (en uso)
con.commit(); con.close()

os.environ["DATABASE"] = path
from app import app
db = sqlite3.connect(path); db.row_factory = sqlite3.Row
nombres = [r["nombre"] for r in db.execute("SELECT nombre FROM lugares")]
assert "4.º de Informática" in nombres and "Aula 4to Informática" not in nombres      # renombrada
assert "Aula 2do Comercio" in nombres                                                   # en uso: se conserva
assert "Pasillo" not in nombres and "Patio" not in nombres                              # sin uso: se retira
assert "5.º de Enfermería" in nombres and len(nombres) == len(set(nombres))
assert db.execute("SELECT nombre FROM categorias WHERE id_categoria=4").fetchone()[0] == "Agua y plomería"
assert db.execute("SELECT COUNT(*) FROM reportes").fetchone()[0] == 2                  # reportes intactos
r = db.execute("SELECT l.nombre FROM reportes r JOIN lugares l USING(id_lugar) WHERE r.id_reporte=1").fetchone()[0]
assert r == "4.º de Informática"
import importlib, db as dbmod
dbmod.init_db(app)  # segunda ejecución: idempotente
assert db.execute("SELECT COUNT(*) FROM lugares WHERE nombre='Cocina'").fetchone()[0] == 1
print("MIGRACION OK")
