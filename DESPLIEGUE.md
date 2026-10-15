# Desplegar PoliReport

1. Sube esta carpeta a un repositorio de GitHub (el `.db` y `.venv` ya están en `.gitignore`).
2. Crea una base PostgreSQL gratuita y copia su "connection string" (`postgresql://...`).
3. En Render: New > Blueprint > elige tu repositorio (usa `render.yaml`).
4. Cuando lo pida, pega `DATABASE_URL` y elige `ADMIN_PASSWORD` (contraseña del admin).
5. Al terminar, abre la URL `https://polireport-xxxx.onrender.com`.

Notas
- `SEED_DEMO=1` crea usuarios de prueba (clave `demo123`). Ponlo en `0` para uso real.
- El plan gratuito de Render se duerme tras ~15 min sin uso (el primer acceso tarda ~1 min).
- La base PostgreSQL gratuita de Render caduca a los 30 días; para que dure, usa una externa.
- Al abrir la URL en el teléfono con HTTPS podrás instalarla en la pantalla de inicio.

# APK para Android (como una app de GitHub)
1. Despliega en Render y copia tu URL.
2. Edita `android-url.txt` en GitHub y pega esa URL (https://...).
3. En GitHub: pestaña Actions > "Build APK" > Run workflow. Al terminar, descarga `PoliReport-apk` (zip con el APK).
4. Para tener un enlace de descarga permanente: crea un Release con la etiqueta `v1.0`; el APK se adjunta solo.
5. En el celular instala el APK y permite "instalar apps desconocidas" para el navegador o gestor de archivos.
