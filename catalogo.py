"""Datos propios del centro: áreas (agrupadas), tipos de problema y problemáticas."""

GRUPOS = [
    ("Áreas generales", ["Cocina", "Salón de maestros", "Comedor", "Cafetería", "Papelería",
                         "Laboratorio", "Baños", "Segundo dibujo", "Otra área"]),
    ("Informática", ["4.º de Informática", "5.º de Informática", "6.º de Informática",
                     "Laboratorio antiguo de Informática"]),
    ("Contabilidad", ["4.º de Contabilidad", "5.º de Contabilidad", "6.º de Contabilidad"]),
    ("Gastronomía", ["4.º Gastronomía", "5.º Gastronomía", "6.º Gastronomía",
                     "Taller de Gastronomía", "Almacén"]),
    ("Refrigeración y Electricidad", ["Taller de Refrigeración", "4.º Refrigeración", "5.º Electricidad"]),
    ("Alojamiento", ["Servicios de Alojamiento", "Taller de Servicios de Alojamiento",
                     "Taller de lavandería (Alojamiento)", "4.º de Alojamiento", "6.º de Alojamiento"]),
    ("Enfermería", ["Laboratorio y taller de Enfermería", "5.º de Enfermería", "6.º de Enfermería"]),
    ("Administración", ["Administración", "Psicología", "Coordinación de Orientación Psicológica",
                        "Coordinación Curricular"]),
]

CATEGORIAS = ["Electricidad", "Agua y plomería", "Mobiliario", "Infraestructura",
              "Limpieza", "Tecnología", "Climatización", "Otros"]

PROBLEMAS = {
    "Electricidad": ["Bombillos dañados", "Tomacorrientes que no funcionan", "Interruptores dañados",
                     "Problemas con la energía eléctrica"],
    "Agua y plomería": ["Llaves o grifos dañados", "Fugas de agua", "Inodoros o lavamanos dañados", "Falta de agua"],
    "Mobiliario": ["Sillas rotas", "Mesas dañadas", "Escritorios deteriorados", "Armarios o estantes dañados"],
    "Infraestructura": ["Puertas o ventanas dañadas", "Paredes deterioradas", "Pisos dañados",
                        "Techos con filtraciones", "Problemas con cerraduras"],
    "Limpieza": ["Acumulación de basura", "Área sucia", "Falta de zafacones", "Mal estado de baños"],
    "Tecnología": ["Computadoras que no funcionan", "Proyectores dañados", "Problemas con internet",
                   "Equipos tecnológicos con fallas"],
    "Climatización": ["Aires acondicionados que no funcionan"],
    "Otros": [],
}

# Migración de bases ya creadas con los datos de ejemplo anteriores
RENOMBRAR_CATEGORIAS = {"Baños": "Agua y plomería"}
RENOMBRAR_LUGARES = {"Aula 4to Informática": "4.º de Informática"}
LUGARES_VIEJOS = ["Aula 2do Comercio", "Pasillo", "Dirección", "Patio"]  # se borran si nadie los usa
