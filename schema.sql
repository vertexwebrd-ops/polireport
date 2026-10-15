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
  nombre TEXT NOT NULL UNIQUE
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
  foto TEXT
);

CREATE INDEX IF NOT EXISTS idx_rep_estado ON reportes(id_estado);
CREATE INDEX IF NOT EXISTS idx_rep_usuario ON reportes(id_usuario);
