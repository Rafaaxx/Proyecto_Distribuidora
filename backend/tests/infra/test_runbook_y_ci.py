"""Runbook, CI y reglas de saltos de linea (change 27a, Lote 4; D1, D16, D17).

Spec `sistema/despliegue`, «Primera puesta en marcha documentada» y «Actualizacion a una version
nueva». Son pruebas de lectura de archivos: no requieren Docker.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
RUNBOOK = RAIZ / "docs" / "runbook" / "puesta-en-marcha.md"
CI = RAIZ / ".github" / "workflows" / "ci.yml"
README = RAIZ / "README.md"


def test_gitattributes_fuerza_lf_en_los_caddyfile():
    texto = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^Caddyfile\*\s+text\s+eol=lf\s*$", texto, re.MULTILINE)


def test_ci_corre_las_pruebas_de_infra_en_el_trabajo_de_integracion():
    texto = CI.read_text(encoding="utf-8")
    bloque = texto.split("integracion-testcontainers:")[1].split("build-frontend:")[0]
    assert re.search(r"pytest\s+tests/integration\s+tests/infra", bloque)


def test_ci_corre_las_pruebas_de_concurrencia_en_un_paso_propio():
    """Change 28, tarea 5.3 (D12; spec `sistema/integracion-continua`, escenario «Las pruebas de
    concurrencia corren en cada push»): `pytest tests/concurrency` en su propio paso del trabajo
    de integracion (sus `conftest` chocan con los de integracion si se juntan en un comando)."""
    texto = CI.read_text(encoding="utf-8")
    bloque = texto.split("integracion-testcontainers:")[1].split("build-frontend:")[0]
    pasos = re.findall(r"^\s+run:\s*(python -m pytest .+)$", bloque, re.MULTILINE)
    assert "python -m pytest tests/concurrency" in pasos
    for comando in pasos:
        if "tests/concurrency" in comando:
            assert "tests/integration" not in comando and "tests/infra" not in comando


def test_ci_no_deja_la_concurrencia_como_pendiente_en_el_readme_de_workflows():
    texto = (RAIZ / ".github" / "workflows" / "README.md").read_text(encoding="utf-8")
    assert "no se agrega un job de CI para un directorio vacío" not in texto
    assert "tests/concurrency" in texto


def test_readme_enlaza_al_runbook():
    assert "docs/runbook/puesta-en-marcha.md" in README.read_text(encoding="utf-8")


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "fragmento",
    [
        "CADDY_TLS=internal",  # escenario 1
        "icacls",  # archivo de entorno protegido en Windows
        "pki/authorities/local/root.crt",  # certificado raiz de Caddy
        "Ajustes de confianza de certificados",  # iPhone
        "openssl rand -hex 32",  # secretos
        "Read-Host -AsSecureString",  # siembra en PowerShell
        "read -s",  # siembra en Git Bash / Linux
        "python -m app.seed",
        "run --rm backup ahora",  # backup a pedido
        "api/v1/version",  # verificar la actualizacion
        "CREATE ROLE app_backup",  # SQL sobre un volumen existente
        "pg_read_all_data",
        "/etc/distribuidora/produccion.env",  # escenario 2
        "chmod 600",
        "Let's Encrypt",
        "port forwarding",  # limitacion de la oficina
        "reserva DHCP",
        "New-NetFirewallRule",
        "git checkout",  # actualizacion
    ],
)
def test_runbook_cubre_lo_que_pide_la_tarea(fragmento):
    assert fragmento in _runbook()


def test_runbook_presenta_primero_la_pc_de_la_oficina():
    texto = _runbook()
    esc1 = texto.index("## Escenario 1:")
    esc2 = texto.index("## Escenario 2:")
    comun = texto.index("## Pasos comunes")
    assert esc1 < esc2 < comun


def test_runbook_no_trae_secretos_con_valor():
    texto = _runbook()
    # Ninguna asignacion de secreto con un valor hexadecimal largo pegado.
    assert not re.search(r"(PASSWORD|JWT_SECRET)=[0-9a-f]{32,}", texto)


def test_enlaces_relativos_del_runbook_existen():
    for destino in re.findall(r"\]\((?!https?:|#)([^)#]+)", _runbook()):
        assert (RUNBOOK.parent / destino).resolve().exists(), destino


def _seccion_actualizar() -> str:
    texto = _runbook()
    inicio = texto.index("### C9 Actualizar")
    return texto[inicio : texto.index("### C10", inicio)]


def test_actualizar_migra_con_run_antes_de_reemplazar_con_up():
    # Observado en el ensayo (D15, paso 18): `up -d` con migraciones fallidas deja el sistema caido.
    seccion = _seccion_actualizar()
    run = seccion.index("run --rm migraciones")
    up = seccion.index("dc up -d")
    assert run < up


def test_actualizar_explica_que_hacer_si_las_migraciones_fallan_y_si_quedo_caido():
    seccion = _seccion_actualizar()
    assert "Si las migraciones fallan" in seccion
    assert "Si el sistema quedó caído" in seccion
    assert "sigue funcionando" in seccion


def test_runbook_no_afirma_que_up_protege_al_backend_viejo():
    assert "no reemplaza el backend" not in _runbook()


# --- Runbook de restauracion (change 27b, Lote 4; D7, D12, D14, D15) -------------------------

RESTAURACION = RAIZ / "docs" / "runbook" / "restauracion.md"


def _restauracion() -> str:
    return RESTAURACION.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "fragmento",
    [
        "hoja de recuperación",  # escenario «Restaurar con solo la hoja de recuperación»
        "COPIA_CLAVE_CIFRADO",
        "COPIA_SAL_CIFRADO",
        "copia-externa bajar",  # bajar un archivo de la copia externa
        "--profile restauracion run --rm restauracion",  # la orden de restaurar
        "stop backend",  # backend detenido antes de restaurar
        "no esta vacia",  # mensaje de la negativa
        "detenga el backend",
        "no es un backup valido",
        "run --rm migraciones",
        "up -d",
        "Restauracion verificada",
        "prueba-restauracion ahora",  # prueba mensual a pedido
        "Prueba de restauracion verificada",
        "dc ps",  # revision semanal: unica senal de la prueba mensual
        "chown 999:999",  # Linux
        "COPIA_TIPO=local",  # ensayo
        "no-aplica",
        "Mudanza",  # escenario «Mudanza de los datos a otro equipo»
        "cola",
        "30 días",  # el equipo viejo se conserva
        "Si algo no funciona",
    ],
)
def test_runbook_de_restauracion_nombra_lo_clave(fragmento):
    assert fragmento in _restauracion()


def test_runbook_de_restauracion_frena_la_mudanza_hasta_vaciar_la_cola():
    texto = _restauracion()
    mudanza = texto[texto.index("## Mudanza") :]
    assert "cola" in mudanza and "vacía" in mudanza
    # La cola se revisa antes de detener el equipo viejo y de hacer el backup.
    assert mudanza.index("vacía") < mudanza.index("run --rm backup ahora")


def test_runbook_de_restauracion_restaura_antes_de_migrar_y_levantar():
    texto = _restauracion()
    restaurar = texto.index("--profile restauracion run --rm restauracion")
    migrar = texto.index("run --rm migraciones", restaurar)
    levantar = texto.index("up -d", migrar)
    assert restaurar < migrar < levantar


def test_runbook_de_restauracion_no_trae_secretos_con_valor():
    assert not re.search(
        r"(PASSWORD|JWT_SECRET|CLAVE_CIFRADO|SAL_CIFRADO)=[0-9A-Za-z]{20,}", _restauracion()
    )


def test_enlaces_relativos_del_runbook_de_restauracion_existen():
    for destino in re.findall(r"\]\((?!https?:|#)([^)#]+)", _restauracion()):
        assert (RESTAURACION.parent / destino).resolve().exists(), destino


def test_readme_enlaza_al_runbook_de_restauracion():
    assert "docs/runbook/restauracion.md" in README.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "fragmento",
    [
        "BACKUP_DIARIOS",
        "BACKUP_SEMANALES",
        "chown 999:999",
        "rclone obscure",
        "copia-externa",
        "prueba-restauracion",
        "COPIA_TIPO=local",
        "AVISO_URL",
        "restauracion.md",
    ],
)
def test_puesta_en_marcha_cubre_la_copia_externa_y_la_retencion(fragmento):
    assert fragmento in _runbook()


def test_puesta_en_marcha_ya_no_nombra_la_retencion_vieja():
    # Solo se nombra para avisar que ya no existe (quien actualiza la reconoce en su archivo).
    assert _runbook().count("BACKUP_RETENCION") == 2  # C7 y la lista de actualizacion desde el 27a
    assert "`BACKUP_RETENCION`, que ya no existe" in _runbook()
    assert "los últimos 7" not in _runbook()


# --- Ajustes de la prueba manual (change 27b, 5.1) --------------------------------------------

CHOWN_WINDOWS = 'docker run --rm -v "C:/distribuidora/backups:/b" alpine chown -R 999:999 /b'


def test_puesta_en_marcha_explica_el_chown_de_windows_para_carpetas_del_27a():
    texto = _runbook()
    assert CHOWN_WINDOWS in texto
    assert "Permission denied" in texto
    assert "no hace falta hacer nada" not in texto  # ya no es cierto para una carpeta existente


def test_puesta_en_marcha_trae_la_lista_para_actualizar_desde_el_27a():
    texto = _runbook()
    sec = texto[texto.index("Actualizar desde 0.27") :]
    for f in (
        "chown -R 999:999",
        "BACKUP_DIARIOS",
        "BACKUP_SEMANALES",
        "COPIA_",
        "PRUEBA_",
        "bajados",
        "up -d --build",
    ):
        assert f in sec, f


def test_restauracion_explica_el_chown_de_windows_y_la_fila_de_permission_denied():
    texto = _restauracion()
    assert CHOWN_WINDOWS in texto
    tabla = texto[texto.index("## Si algo no funciona") :]
    assert "Permission denied" in tabla and "/backups" in tabla


def test_ensayo_baja_la_oficina_sin_v_antes_de_levantar_caddy_del_entorno_separado():
    texto = _restauracion()
    ens = texto[texto.index("## Ensayar sin tocar") : texto.index("## Mudanza")]
    assert "bajados" in ens and "dc2" in ens
    assert "rclone lsf cifrado:" in ens
    assert "dc2 up -d postgres" in ens and "dc2 run --rm migraciones" in ens
    baja = ens.index("dc down\n")  # sin -v, solo la linea
    assert baja < ens.index("dc2 up -d caddy") < ens.index("dc2 down -v") < ens.index("dc up -d\n")
    assert "172.30.10.0/24" in ens
    assert "uno por línea" in ens


def _bloque_de_aceptacion() -> str:
    texto = CI.read_text(encoding="utf-8")
    assert "\n  aceptacion-playwright:" in texto, "falta el trabajo de aceptación de Playwright"
    return texto.split("\n  aceptacion-playwright:")[1].split("\n  build-frontend:")[0]


def test_ci_corre_playwright_solo_en_push_a_main():
    """Change 28, tarea 7.4 (D16; spec `sistema/integracion-continua`, «La suite de aceptación corre
    en la rama principal»): el trabajo de Playwright se ejecuta solo en push a `main`; los demás
    trabajos siguen corriendo en cada push y pull request."""
    bloque = _bloque_de_aceptacion()
    assert re.search(
        r"^\s+if:\s*github\.event_name == 'push' && github\.ref == 'refs/heads/main'\s*$",
        bloque,
        re.MULTILINE,
    )
    assert re.search(r"^\s+push:\s*$", CI.read_text(encoding="utf-8"), re.MULTILINE)


def test_ci_levanta_el_entorno_y_corre_la_suite_con_el_script_de_aceptacion():
    bloque = _bloque_de_aceptacion()
    assert re.search(r"^\s+run:\s*npm run test:e2e\s*$", bloque, re.MULTILINE)
    assert "npx playwright install" in bloque and "chromium" in bloque


def test_ci_sube_las_trazas_de_las_pruebas_fallidas():
    bloque = _bloque_de_aceptacion()
    paso = bloque.split("upload-artifact")[1]
    assert re.search(r"^\s+if:\s*failure\(\)\s*$", bloque, re.MULTILINE)
    assert "frontend/test-results" in paso
    assert "frontend/playwright-report" in paso


# --- Runbook del change 28 (tarea 8.1; D2, D3, D5, D6, D14) ---------------------------------


@pytest.mark.parametrize(
    "fragmento",
    [
        "CREATE ROLE app_mantenimiento",  # entorno existente: crear el rol ANTES de migrar
        "APP_MANTENIMIENTO_DB_PASSWORD",
        "-v clave=",  # contraseña como variable de psql, sin pegarla en el SQL
        "run --rm tareas ahora",  # verificación a pedido
        "Verificación de consistencia: sin diferencias",
        "no corregir a mano",
        "TAREAS_HORA",
        "AVISO_TAREAS_URL",
        "healthchecks.io",
        "Verificación diaria",
        "run --rm tareas ahora",
        "npm run test:e2e",  # suite de aceptación
        "distribuidora-aceptacion",
    ],
)
def test_runbook_cubre_las_tareas_periodicas_y_la_aceptacion(fragmento):
    assert fragmento in _runbook()


def test_runbook_ya_no_dice_que_tareas_no_puede_avisar_por_internet():
    # ADR-073: `tareas` tambien esta en la red `salida` y avisa por su propia variable.
    texto = _runbook()
    assert "Limitación del aviso externo" not in texto
    assert "no puede llamar a `AVISO_URL`" not in texto


def test_runbook_crea_el_rol_de_mantenimiento_antes_de_migrar():
    texto = _runbook()
    seccion = texto[texto.index("### C12") : texto.index("## Si algo no funciona")]
    assert seccion.index("CREATE ROLE app_mantenimiento") < seccion.index("run --rm migraciones")


def test_runbook_explica_la_salud_de_tareas_y_por_que_puede_avisar_por_internet():
    texto = _runbook()
    assert "`tareas` pasa a «unhealthy»" in texto
    # ADR-073: `datos` no sale a internet; `tareas` sale solo por `salida`.
    assert "`datos` (la de la base, que **no** tiene salida a internet)" in texto
    assert "la red `salida`" in texto


def test_actualizar_menciona_el_rol_de_mantenimiento_antes_de_migrar():
    seccion = _seccion_actualizar()
    assert "C12" in seccion
