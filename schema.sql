PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
  id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  correo TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN ('estudiante','profesor','admin','mantenimiento')),
  id_encargado INTEGER REFERENCES encargados(id_encargado)
);

CREATE TABLE IF NOT EXISTS lugares (
  id_lugar INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE,
  grupo TEXT
);

CREATE TABLE IF NOT EXISTS categorias (
  id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS estados (
  id_estado INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS encargados (
  id_encargado INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  especialidad TEXT
);

CREATE TABLE IF NOT EXISTS reportes (
  id_reporte INTEGER PRIMARY KEY AUTOINCREMENT,
  descripcion TEXT NOT NULL,
  id_lugar INTEGER NOT NULL REFERENCES lugares(id_lugar),
  id_categoria INTEGER NOT NULL REFERENCES categorias(id_categoria),
  id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario),
  id_encargado INTEGER REFERENCES encargados(id_encargado),
  id_estado INTEGER NOT NULL DEFAULT 1 REFERENCES estados(id_estado),
  prioridad TEXT NOT NULL DEFAULT 'Media' CHECK (prioridad IN ('Alta','Media','Baja')),
  fecha TEXT NOT NULL DEFAULT (datetime('now')),
  fecha_resuelto TEXT,
  foto TEXT,
  foto_despues TEXT,
  curso TEXT,
  problema TEXT
);

CREATE INDEX IF NOT EXISTS idx_rep_estado ON reportes(id_estado);
CREATE INDEX IF NOT EXISTS idx_rep_usuario ON reportes(id_usuario);

CREATE TABLE IF NOT EXISTS eventos (
  id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
  id_reporte INTEGER NOT NULL REFERENCES reportes(id_reporte) ON DELETE CASCADE,
  id_usuario INTEGER REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
  tipo TEXT NOT NULL,
  texto TEXT NOT NULL,
  fecha TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS avisos (
  id_aviso INTEGER PRIMARY KEY AUTOINCREMENT,
  id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
  id_reporte INTEGER REFERENCES reportes(id_reporte) ON DELETE CASCADE,
  texto TEXT NOT NULL,
  leido INTEGER NOT NULL DEFAULT 0,
  fecha TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS apoyos (
  id_reporte INTEGER NOT NULL REFERENCES reportes(id_reporte) ON DELETE CASCADE,
  id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
  PRIMARY KEY (id_reporte, id_usuario)
);
CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT);
CREATE INDEX IF NOT EXISTS idx_eventos_reporte ON eventos(id_reporte);
CREATE INDEX IF NOT EXISTS idx_avisos_usuario ON avisos(id_usuario, leido);
