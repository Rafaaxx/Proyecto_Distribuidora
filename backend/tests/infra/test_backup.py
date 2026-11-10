"""Servicio de backups (change 27a, Lote 3; D10, D12, D13, D14).

Spec `sistema/respaldos`. Cita `docs/02-arquitectura.md` §16.2 y §17, y `docs/00` §9 criterio 12.
Corre los scripts reales de `infra/backup/` dentro de la imagen real (postgres:17) contra una
base migrada y con datos (fixtures de `conftest.py`). Los archivos de backup viven dentro del
contenedor de cada prueba (sin montajes del equipo), para que no dependan del sistema de
archivos de quien corre la prueba.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

RAIZ = Path(__file__).resolve().parents[3]
BACKUP = RAIZ / "infra" / "backup"
LIBROS = ("cuenta_movimiento", "stock_movimiento", "costo_producto_mov", "auditoria")
NOMBRE_VALIDO = re.compile(r"^distribuidora-\d{8}-\d{6}\.dump$")
PG_DUMP_REAL = "/usr/lib/postgresql/17/bin/pg_dump"

# pg_dump que escribe un archivo y despues lo trunca: simula disco lleno / corte a mitad.
STUB_TRUNCADO = f"""
mkdir -p /stub
cat > /stub/pg_dump <<'EOF'
#!/bin/sh
for a in "$@"; do case "$a" in --file=*) f="${{a#--file=}}";; esac; done
{PG_DUMP_REAL} "$@" || exit $?
truncate -s 300 "$f"
EOF
chmod +x /stub/pg_dump
export PATH=/stub:$PATH
"""

# pg_dump que escribe algo y muere a mitad con error.
STUB_INTERRUMPIDO = """
mkdir -p /stub
cat > /stub/pg_dump <<'EOF'
#!/bin/sh
for a in "$@"; do case "$a" in --file=*) f="${a#--file=}";; esac; done
echo parcial > "$f"
echo "pg_dump: error: el servidor cerro la conexion" >&2
exit 1
EOF
chmod +x /stub/pg_dump
export PATH=/stub:$PATH
"""


def _resultado(salida: str) -> tuple[int, str, list[str]]:
    """Separa la salida de `_con_listado`: codigo de salida, registro y archivos."""
    antes, _, despues = salida.partition("---RC=")
    codigo, _, listado = despues.partition("\n")
    return int(codigo), antes, [x for x in listado.split("\n") if x.strip()]


def _con_listado(comando: str, carpeta: str = "/tmp/respaldos") -> str:
    return f'{comando}; rc=$?; echo "---RC=$rc"; ls -1A {carpeta}; exit 0'


# --- Archivos del servicio ---------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["Dockerfile", "respaldar.sh", "salud.sh", "programar.sh"])
def test_archivos_del_servicio_existen(nombre):
    assert (BACKUP / nombre).is_file()


def test_los_scripts_del_repositorio_usan_saltos_de_linea_unix():
    # Un .sh con CRLF no corre en Linux («/bin/sh^M: bad interpreter»). Aplica a lo que se copia
    # a una imagen o se monta en un contenedor.
    con_crlf = [
        str(p.relative_to(RAIZ))
        for p in [*(RAIZ / "infra").rglob("*.sh")]
        if b"\r\n" in p.read_bytes()
    ]
    assert not con_crlf, f"Scripts con CRLF: {con_crlf}"


def test_gitattributes_fuerza_lf_en_los_scripts():
    texto = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.sh\s+text\s+eol=lf\s*$", texto, re.MULTILINE)


def test_dockerfile_parte_de_postgres_17_y_normaliza_saltos_de_linea():
    texto = (BACKUP / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM postgres:17(\s|$)", texto, re.MULTILINE)
    assert "\\r" in texto  # sed que quita CR, por si el contexto vino de Windows con CRLF


# --- Backup a pedido y verificacion ------------------------------------------------------


def test_backup_a_pedido_crea_archivo_verificado_con_permisos_600(corredor):
    codigo, salida = corredor.correr(
        "sh /opt/backup/programar.sh ahora; rc=$?; echo ---RC=$rc; "
        "stat -c '%a %n' /tmp/respaldos/*; stat -c '%a' /tmp/respaldos; "
        "for f in /tmp/respaldos/*.dump; do pg_restore --list $f; done; exit 0"
    )
    assert codigo == 0
    rc, _, _ = _resultado(salida)
    assert rc == 0
    registro = salida.partition("---RC=")[0]
    assert "Backup verificado" in registro
    assert re.search(r"archivo=distribuidora-\d{8}-\d{6}\.dump", registro)
    assert re.search(r"tamano=\d+ bytes", registro)
    despues = salida.partition("---RC=")[2]
    assert re.search(r"^600 /tmp/respaldos/distribuidora-\d{8}-\d{6}\.dump$", despues, re.M)
    assert re.search(r"^700$", despues, re.M)
    for libro in LIBROS:
        assert re.search(rf"TABLE public {libro} ", despues), libro
    assert "organizacion" in despues


def test_el_backup_lleva_las_secuencias_con_solo_lectura(corredor):
    # Prueba de D11: pg_read_all_data alcanza para un pg_dump completo, secuencias incluidas.
    _, salida = corredor.correr(
        "sh /opt/backup/respaldar.sh >/dev/null 2>&1; "
        "pg_restore --list /tmp/respaldos/*.dump | grep -i 'secuencia_de_prueba'"
    )
    assert "SEQUENCE public secuencia_de_prueba" in salida
    assert "SEQUENCE SET public secuencia_de_prueba" in salida


def test_backup_que_se_interrumpe_no_deja_archivo_final_ni_temporal(corredor):
    codigo, salida = corredor.correr(
        _con_listado(STUB_INTERRUMPIDO + "sh /opt/backup/respaldar.sh")
    )
    rc, registro, archivos = _resultado(salida)
    assert rc != 0
    assert archivos == []
    assert "ERROR" in registro


def test_con_la_base_inalcanzable_falla_sin_dejar_archivos(corredor):
    codigo, salida = corredor.correr(
        _con_listado("sh /opt/backup/respaldar.sh"), entorno={"PGHOST": "no-existe"}
    )
    rc, registro, archivos = _resultado(salida)
    assert rc != 0
    assert archivos == []
    assert "ERROR" in registro


def test_archivo_truncado_pasa_a_fallido_y_no_cuenta(corredor):
    _, salida = corredor.correr(_con_listado(STUB_TRUNCADO + "sh /opt/backup/respaldar.sh"))
    rc, registro, archivos = _resultado(salida)
    assert rc != 0
    assert len(archivos) == 1
    assert re.fullmatch(r"distribuidora-\d{8}-\d{6}\.dump\.fallido", archivos[0])
    assert not any(a.endswith(".dump") or a.endswith(".tmp") for a in archivos)
    assert "ERROR" in registro and "Backup verificado" not in registro


# --- Usuario sin privilegios (27b, D11) -----------------------------------------------------


@pytest.fixture
def carpeta_de_999(docker_cliente, imagen_backup):
    """Volumen de Docker cuya raiz pertenece a 999:999, como el `chown 999:999` del runbook."""
    volumen = docker_cliente.volumes.create()
    preparacion = docker_cliente.containers.run(
        imagen_backup,
        entrypoint=["sh", "-c", "chown 999:999 /datos && chmod 700 /datos"],
        user="0:0",
        volumes={volumen.name: {"bind": "/datos", "mode": "rw"}},
        remove=True,
    )
    del preparacion
    yield {volumen.name: {"bind": "/tmp/respaldos", "mode": "rw"}}
    volumen.remove(force=True)


def test_backup_con_usuario_sin_privilegios_escribe_en_la_carpeta(corredor, carpeta_de_999):
    # Escenario «Backup con usuario sin privilegios» (D11): el proceso no es root y el archivo
    # queda en el directorio de backups.
    _, salida = corredor.correr(
        "id -u; id -g; sh /opt/backup/programar.sh ahora; rc=$?; echo ---RC=$rc; "
        "ls -ln /tmp/respaldos; exit 0",
        usuario="999:999",
        volumenes=carpeta_de_999,
    )
    assert salida.startswith("999\n999\n")
    rc, _, _ = _resultado(salida)
    assert rc == 0
    assert re.search(r"^-rw------- 1 999 999 \d+ .* distribuidora-\d{8}-\d{6}\.dump$", salida, re.M)


def test_con_usuario_sin_privilegios_el_servicio_programa_y_la_salud_funciona(
    corredor, carpeta_de_999
):
    # El directorio de estado (ESTADO_DIR) debe ser escribible sin root y la salud debe leerlo.
    _, salida = corredor.correr(
        "timeout 3 sh /opt/backup/programar.sh >/dev/null 2>&1; "
        "echo PRIMERA=$(test -s /tmp/estado-backup/primera && echo si || echo no); "
        "sh /opt/backup/salud.sh; echo SALUD=$?; exit 0",
        entorno={"BACKUP_DIR": "/tmp/respaldos"},
        usuario="999:999",
        volumenes=carpeta_de_999,
        red=False,
    )
    assert "PRIMERA=si" in salida
    assert "SALUD=0" in salida


def test_los_scripts_son_legibles_y_no_escribibles_por_el_usuario_sin_privilegios(corredor):
    _, salida = corredor.correr(
        "for f in /opt/backup/*.sh; do test -r $f || echo ILEGIBLE:$f; "
        "test -w $f && echo ESCRIBIBLE:$f; done; echo FIN; exit 0",
        usuario="999:999",
        red=False,
    )
    assert "FIN" in salida
    assert "ILEGIBLE" not in salida
    assert "ESCRIBIBLE" not in salida


# --- Retencion ---------------------------------------------------------------------------


def _crear_antiguos(cantidad: int, extra: str = "") -> str:
    # Falsos backups «de hace N dias» (el contenido no importa: la retencion va por nombre).
    lineas = ["mkdir -p /tmp/respaldos"]
    for dias in range(cantidad, 0, -1):
        fecha = (datetime(2026, 1, 31) - timedelta(days=dias)).strftime("%Y%m%d")
        lineas.append(f"echo x > /tmp/respaldos/distribuidora-{fecha}-030000.dump")
    return "; ".join(lineas) + "; " + extra


def test_retencion_por_defecto_conserva_14_diarios_y_8_semanales(corredor):
    # Requisito «Retencion de 14 backups diarios y 8 semanales» (D1): 25 backups viejos
    # (2026-01-06 al 2026-01-30) mas el nuevo. Quedan los 13 diarios mas recientes viejos
    # (01-18 al 01-30), el nuevo, y el semanal de la semana 01-05..01-11 (el del 01-11).
    _, salida = corredor.correr(_con_listado(_crear_antiguos(25) + "sh /opt/backup/respaldar.sh"))
    rc, _, archivos = _resultado(salida)
    assert rc == 0
    assert all(NOMBRE_VALIDO.match(a) for a in archivos)
    assert archivos == sorted(archivos)
    assert len(archivos) == 15
    assert archivos[0] == "distribuidora-20260111-030000.dump"
    assert archivos[1] == "distribuidora-20260118-030000.dump"
    assert "distribuidora-20260110-030000.dump" not in archivos


def test_retencion_respeta_backup_diarios_y_backup_semanales(corredor):
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(5) + "sh /opt/backup/respaldar.sh"),
        entorno={"BACKUP_DIARIOS": "2", "BACKUP_SEMANALES": "1"},
    )
    _, _, archivos = _resultado(salida)
    assert len(archivos) == 2  # el nuevo y el 01-30; el semanal es el nuevo
    assert archivos[0] == "distribuidora-20260130-030000.dump"


def test_backup_retencion_ya_no_se_lee(corredor):
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(5) + "sh /opt/backup/respaldar.sh"),
        entorno={"BACKUP_RETENCION": "1"},
    )
    rc, _, archivos = _resultado(salida)
    assert rc == 0
    assert len(archivos) == 6


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("BACKUP_DIARIOS", "abc"),
        ("BACKUP_DIARIOS", "0"),
        ("BACKUP_SEMANALES", "0"),
        ("BACKUP_SEMANALES", "-3"),
    ],
)
def test_cantidades_invalidas_fallan_nombrando_la_variable(corredor, variable, valor):
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(3) + "sh /opt/backup/respaldar.sh 2>&1"),
        entorno={variable: valor},
    )
    rc, _, archivos = _resultado(salida)
    assert rc != 0
    # stderr se unio a stdout en la orden: el contenedor puede entregar ambos en otro orden.
    assert variable in salida
    assert len(archivos) == 3  # no hizo backup ni borro nada


def test_backup_fallido_no_borra_nada(corredor):
    # Escenario «Un backup fallido no dispara la limpieza».
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(25) + "sh /opt/backup/respaldar.sh"),
        entorno={"PGHOST": "no-existe"},
    )
    rc, _, archivos = _resultado(salida)
    assert rc != 0
    assert len(archivos) == 25


def test_verificacion_fallida_no_dispara_la_limpieza(corredor):
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(25) + STUB_TRUNCADO + "sh /opt/backup/respaldar.sh")
    )
    _, _, archivos = _resultado(salida)
    validos = [a for a in archivos if NOMBRE_VALIDO.match(a)]
    assert len(validos) == 25
    assert any(a.endswith(".fallido") for a in archivos)


def test_retencion_no_toca_archivos_ajenos_ni_fallidos(corredor):
    # Escenario «Archivos ajenos no se tocan», con una subcarpeta incluida.
    previos = (
        "echo x > /tmp/respaldos/restauracion-de-prueba.sql; "
        "echo x > /tmp/respaldos/distribuidora-20250101-030000.dump.fallido; "
        "echo x > /tmp/respaldos/distribuidora-20250101-030000.dump.tmp; "
        "echo x > /tmp/respaldos/notas.txt; "
        "mkdir -p /tmp/respaldos/bajados; "
        "echo x > /tmp/respaldos/bajados/distribuidora-20200101-030000.dump; "
    )
    _, salida = corredor.correr(
        _con_listado(_crear_antiguos(9, previos) + "sh /opt/backup/respaldar.sh"),
        entorno={"BACKUP_DIARIOS": "3", "BACKUP_SEMANALES": "1"},
    )
    _, _, archivos = _resultado(salida)
    assert "restauracion-de-prueba.sql" in archivos
    assert "notas.txt" in archivos
    assert "bajados" in archivos
    assert "distribuidora-20250101-030000.dump.fallido" in archivos
    assert "distribuidora-20250101-030000.dump.tmp" in archivos
    assert len([a for a in archivos if NOMBRE_VALIDO.match(a)]) == 3


# --- Salud -------------------------------------------------------------------------------


def _salud(corredor, preparacion: str) -> int:
    _, salida = corredor.correr(
        f"mkdir -p /tmp/respaldos /tmp/estado; {preparacion}; "
        "ESTADO_DIR=/tmp/estado sh /opt/backup/salud.sh >/dev/null 2>&1; echo RC=$?; exit 0",
        red=False,
    )
    return int(re.search(r"RC=(\d+)", salida).group(1))


def _dump(horas: float, nombre: str = "distribuidora-20260101-030000.dump") -> str:
    ruta = f"/tmp/respaldos/{nombre}"
    return f"echo x > {ruta}; touch -d '{int(horas * 60)} minutes ago' {ruta}"


def test_salud_con_backup_de_hace_3_horas_esta_sano(corredor):
    assert _salud(corredor, _dump(3)) == 0


def test_salud_con_backup_de_hace_30_horas_no_esta_sano(corredor):
    assert _salud(corredor, _dump(30)) != 0


def test_salud_cuenta_el_mas_reciente_aunque_haya_viejos(corredor):
    viejo = _dump(100, "distribuidora-20250101-030000.dump")
    nuevo = _dump(2, "distribuidora-20260102-030000.dump")
    assert _salud(corredor, f"{viejo}; {nuevo}") == 0


def test_salud_ignora_fallidos_y_temporales(corredor):
    prep = (
        "echo x > /tmp/respaldos/distribuidora-20260101-030000.dump.fallido; "
        "echo x > /tmp/respaldos/distribuidora-20260101-030000.dump.tmp; " + _dump(40)
    )
    assert _salud(corredor, prep) != 0
    solo_fallido = "echo x > /tmp/respaldos/distribuidora-20260101-030000.dump.fallido"
    assert (
        _salud(corredor, solo_fallido + "; echo $(( $(date +%s) - 7200 )) > /tmp/estado/primera")
        != 0
    )


def test_salud_sin_backups_es_sana_antes_de_la_primera_hora_programada(corredor):
    assert _salud(corredor, "echo $(( $(date +%s) + 3600 )) > /tmp/estado/primera") == 0
    # Dentro de la hora de gracia posterior a la hora programada.
    assert _salud(corredor, "echo $(( $(date +%s) - 1200 )) > /tmp/estado/primera") == 0


def test_salud_sin_backups_pasada_la_primera_hora_programada_no_esta_sana(corredor):
    assert _salud(corredor, "echo $(( $(date +%s) - 7200 )) > /tmp/estado/primera") != 0


# --- Hora programada ---------------------------------------------------------------------


def _segundos_hasta(corredor, tz: str, hora: str, ahora: datetime) -> int:
    _, salida = corredor.correr(
        "PROGRAMAR_SOLO_FUNCIONES=1 . /opt/backup/programar.sh; "
        f"echo SEG=$(segundos_hasta_proxima {hora} {int(ahora.timestamp())}); exit 0",
        entorno={"TZ": tz},
        red=False,
    )
    return int(re.search(r"SEG=(\d+)", salida).group(1))


MENDOZA = ZoneInfo("America/Argentina/Mendoza")


def test_proxima_corrida_antes_de_la_hora_es_hoy(corredor):
    ahora = datetime(2026, 11, 7, 1, 0, 0, tzinfo=MENDOZA)
    assert _segundos_hasta(corredor, "America/Argentina/Mendoza", "03:00", ahora) == 7200


def test_proxima_corrida_despues_de_la_hora_es_manana(corredor):
    ahora = datetime(2026, 11, 7, 3, 0, 1, tzinfo=MENDOZA)
    assert _segundos_hasta(corredor, "America/Argentina/Mendoza", "03:00", ahora) == 86399


def test_proxima_corrida_justo_a_la_hora_es_manana(corredor):
    ahora = datetime(2026, 11, 7, 3, 0, 0, tzinfo=MENDOZA)
    assert _segundos_hasta(corredor, "America/Argentina/Mendoza", "03:00", ahora) == 86400


def test_proxima_corrida_cerca_de_la_medianoche(corredor):
    ahora = datetime(2026, 11, 7, 23, 59, 30, tzinfo=MENDOZA)
    assert _segundos_hasta(corredor, "America/Argentina/Mendoza", "03:00", ahora) == 3 * 3600 + 30
    ahora2 = datetime(2026, 11, 7, 0, 0, 30, tzinfo=MENDOZA)
    assert _segundos_hasta(corredor, "America/Argentina/Mendoza", "00:15", ahora2) == 15 * 60 - 30


def test_proxima_corrida_respeta_el_cambio_de_hora_de_la_zona(corredor):
    ny = ZoneInfo("America/New_York")
    ahora = datetime(2026, 3, 7, 3, 0, 1, tzinfo=ny)  # un dia antes de pasar al horario de verano
    assert _segundos_hasta(corredor, "America/New_York", "03:00", ahora) == 23 * 3600 - 1


def test_hora_invalida_hace_fallar_al_servicio(corredor):
    codigo, salida = corredor.correr(
        "sh /opt/backup/programar.sh; echo RC=$?; exit 0",
        entorno={"BACKUP_HORA": "25:99"},
        red=False,
    )
    assert "RC=0" not in salida
    assert "BACKUP_HORA" in salida
