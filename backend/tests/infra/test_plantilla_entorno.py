"""Plantilla del archivo de entorno de producción (change 27a, Lote 2; D1, D8).

Spec `sistema/despliegue`, escenario «La plantilla no trae valores».
"""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PLANTILLA = RAIZ / "infra" / "produccion.env.example"
COMPOSE = RAIZ / "docker-compose.prod.yml"

SECRETOS = {
    "POSTGRES_PASSWORD",
    "APP_MIGRATIONS_DB_PASSWORD",
    "APP_RUNTIME_DB_PASSWORD",
    "APP_BACKUP_DB_PASSWORD",
    "APP_MANTENIMIENTO_DB_PASSWORD",
    "JWT_SECRET",
}


def _asignaciones() -> dict[str, str]:
    resultado: dict[str, str] = {}
    for linea in PLANTILLA.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", linea.strip())
        if m:
            resultado[m.group(1)] = m.group(2)
    return resultado


def test_los_secretos_aparecen_sin_valor():
    asignaciones = _asignaciones()
    for secreto in SECRETOS:
        assert secreto in asignaciones, f"falta {secreto}"
        assert asignaciones[secreto] == "", f"{secreto} no debe traer valor"


def test_lista_todas_las_variables_que_usa_el_compose():
    usadas = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", COMPOSE.read_text(encoding="utf-8")))
    faltantes = usadas - set(_asignaciones())
    assert not faltantes, f"la plantilla no lista: {sorted(faltantes)}"


def test_incluye_las_variables_de_operacion_de_la_decision_d8():
    esperadas = {
        "DOMINIO", "CADDY_TLS", "APP_VERSION", "WEB_CONCURRENCY", "LOG_LEVEL", "JWT_KID",
        "BACKUP_DIR", "BACKUP_HORA", "BACKUP_DIARIOS", "BACKUP_SEMANALES", "TZ",
    }  # fmt: skip
    assert esperadas <= set(_asignaciones())


def test_caddy_tls_reemplaza_a_acme_email_y_explica_los_dos_modos():
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "ACME_EMAIL" not in texto
    assert "internal" in texto
    assert "Let's Encrypt" in texto
    assert "localhost" in texto


def test_nada_con_aspecto_de_secreto_en_ninguna_linea():
    for linea in PLANTILLA.read_text(encoding="utf-8").splitlines():
        if linea.lstrip().startswith("#"):
            continue
        assert not re.search(r"[0-9a-f]{32,}", linea), linea


def test_gitignore_ignora_env_pero_no_la_plantilla():
    def ignorado(ruta: str) -> bool:
        r = subprocess.run(
            ["git", "check-ignore", "-q", ruta], cwd=RAIZ, capture_output=True, check=False
        )
        return r.returncode == 0

    assert ignorado("produccion.env")
    assert ignorado("infra/produccion.env")
    assert not ignorado("infra/produccion.env.example")
    assert not ignorado(".env.example")


def test_la_plantilla_documenta_la_retencion_y_el_usuario_de_los_respaldos():
    # D1 y D11: 14 + 8 por defecto; BACKUP_RETENCION ya no existe; UID/GID 999 explicados.
    asignaciones = _asignaciones()
    assert asignaciones["BACKUP_DIARIOS"] == "14"
    assert asignaciones["BACKUP_SEMANALES"] == "8"
    assert "BACKUP_RETENCION" not in asignaciones
    assert asignaciones["BACKUP_UID"] == "999"
    assert asignaciones["BACKUP_GID"] == "999"
    assert "chown" in PLANTILLA.read_text(encoding="utf-8")


def test_la_plantilla_lista_los_secretos_de_la_copia_externa_sin_valor():
    # Escenario «La plantilla no trae valores» (copia externa, D3, D5).
    asignaciones = _asignaciones()
    for secreto in (
        "COPIA_ACCESS_KEY_ID",
        "COPIA_SECRET_ACCESS_KEY",
        "COPIA_CLAVE_CIFRADO",
        "COPIA_SAL_CIFRADO",
    ):
        assert secreto in asignaciones, f"falta {secreto}"
        assert asignaciones[secreto] == "", f"{secreto} no debe traer valor"


def test_la_plantilla_documenta_el_destino_de_la_copia_y_el_ensayo_local():
    asignaciones = _asignaciones()
    assert {"COPIA_TIPO", "COPIA_RUTA", "COPIA_S3_PROVEEDOR", "COPIA_S3_ENDPOINT",
            "COPIA_S3_REGION", "AVISO_URL", "COPIA_LOCAL_DIR"} <= set(asignaciones)  # fmt: skip
    assert asignaciones["AVISO_URL"] == ""


def test_la_plantilla_documenta_el_aviso_externo_de_las_tareas():
    # ADR-073: variable propia, vacia (opcional) y explicada junto al control de healthchecks.io.
    asignaciones = _asignaciones()
    assert asignaciones["AVISO_TAREAS_URL"] == ""
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "Verificacion diaria" in texto
    assert "AVISO_URL" in texto  # se aclara que es distinta de la de la copia
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "rclone obscure" in texto
    assert "ensayo" in texto and "local" in texto
    assert "/destino-local" in texto


def test_la_plantilla_documenta_el_dia_y_la_hora_de_la_prueba_de_restauracion():
    # D10: PRUEBA_DIA y PRUEBA_HORA con sus valores por defecto, explicadas.
    asignaciones = _asignaciones()
    assert asignaciones["PRUEBA_DIA"] == "1"
    assert asignaciones["PRUEBA_HORA"] == "04:00"
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert "prueba de restauracion" in texto.lower()


def test_la_plantilla_documenta_la_contrasena_del_rol_de_mantenimiento_sin_valor():
    # Change 28, D3 (escenario «Falta la contraseña del rol de mantenimiento»).
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert _asignaciones()["APP_MANTENIMIENTO_DB_PASSWORD"] == ""
    lineas = texto[: texto.index("APP_MANTENIMIENTO_DB_PASSWORD=")].rstrip().splitlines()
    bloque = []
    for linea in reversed(lineas):
        if not linea.startswith("#"):
            break
        bloque.append(linea)
    explicacion = " ".join(bloque).lower()
    assert "tareas" in explicacion and "runbook" in explicacion


def test_la_plantilla_documenta_la_hora_de_las_tareas_periodicas():
    # Change 28, D6: TAREAS_HORA con su valor por defecto, explicada; despues del backup (03:00).
    assert _asignaciones()["TAREAS_HORA"] == "05:00"
    texto = PLANTILLA.read_text(encoding="utf-8")
    bloque = texto[: texto.index("TAREAS_HORA=")]
    explicacion = " ".join(
        linea for linea in bloque.splitlines()[-8:] if linea.startswith("#")
    ).lower()
    assert "diferencias" in explicacion and "intentos" in explicacion
