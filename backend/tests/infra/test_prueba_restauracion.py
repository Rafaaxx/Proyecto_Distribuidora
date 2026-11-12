"""Prueba de restauración periódica (change 27b, Lote 3; D10, D14).

Spec `sistema/respaldos`, requisito «Prueba de restauración periódica en un entorno separado»
(escenarios «Prueba mensual buena», «Backup que no se puede restaurar» y «Prueba atrasada») y
«Aviso externo opcional». Cita `docs/02-arquitectura.md` §16.2 («al menos una vez por mes») y
`docs/00-vision-y-alcance.md` §9 criterio 12.

Corre la imagen real de `infra/backup/` SIN red (`network none`), sin credenciales de la base y
con el usuario sin privilegios del compose: la prueba levanta su propio Postgres temporal dentro
del contenedor.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.infra.conftest import Corredor

TZ = "America/Argentina/Mendoza"
USUARIO = "999:999"
PRUEBA = "sh /opt/backup/programar_prueba.sh"
SALUD = "sh /opt/backup/salud_prueba.sh"
MAS_VIEJO = "distribuidora-20260101-030000.dump"
MAS_NUEVO = "distribuidora-20260315-030000.dump"
DIA = 86400


@pytest.fixture
def estado(docker_cliente) -> Iterator[dict[str, dict[str, str]]]:
    # Volumen nuevo: hereda del directorio de la imagen el dueño 999 (como el volumen del compose).
    volumen = docker_cliente.volumes.create()
    yield {volumen.name: {"bind": "/estado-prueba", "mode": "rw"}}
    volumen.remove(force=True)


@pytest.fixture(scope="module")
def carpeta(docker_cliente, respaldo_de_origen, corredor) -> Iterator[dict[str, dict[str, str]]]:
    """Carpeta de backups con dos backups validos (el real, con dos nombres) y estorbos."""
    volumen = docker_cliente.volumes.create()
    codigo, salida = corredor.correr(
        f"cp /origen/{respaldo_de_origen.nombre} /backups/{MAS_VIEJO} "
        f"&& cp /origen/{respaldo_de_origen.nombre} /backups/{MAS_NUEVO} "
        # pg_dump deja el archivo en 0600 de root; en produccion lo escribe el usuario 999.
        "&& chown 999:999 /backups/*.dump && chmod 640 /backups/*.dump "
        # Estorbos: un fallido y un temporal mas recientes; no son backups validos.
        "&& echo basura > /backups/distribuidora-20260401-030000.dump.fallido "
        "&& echo basura > /backups/distribuidora-20260402-030000.dump.tmp",
        red=False,
        volumenes={
            respaldo_de_origen.volumen: {"bind": "/origen", "mode": "ro"},
            volumen.name: {"bind": "/backups", "mode": "rw"},
        },
    )
    assert codigo == 0, salida
    yield {volumen.name: {"bind": "/backups", "mode": "ro"}}
    volumen.remove(force=True)


def correr(
    corredor: Corredor,
    script: str,
    carpeta=None,
    estado=None,
    entorno: dict[str, str] | None = None,
    red: bool = False,
    usuario: str | None = USUARIO,
) -> tuple[int, str]:
    volumenes = {**(carpeta or {}), **(estado or {})}
    return corredor.correr(
        f"{script} 2>&1",
        entorno={"BACKUP_DIR": "/backups", "ESTADO_DIR": "/estado-prueba", **(entorno or {})},
        red=red,
        usuario=usuario,
        volumenes=volumenes or None,
    )


# --- «Prueba mensual buena» ----------------------------------------------------------------------


def test_prueba_buena_restaura_el_ultimo_backup_y_descarta_la_base_temporal(
    corredor, carpeta, estado
):
    # Escenario «Prueba mensual buena» (02 §16.2): el mas reciente por fecha del nombre, sin red y
    # sin credenciales; los .fallido y .tmp no cuentan.
    codigo, salida = correr(corredor, f"{PRUEBA} ahora", carpeta, estado)
    assert codigo == 0, salida
    assert f"Prueba de restauracion verificada: archivo={MAS_NUEVO} tablas=" in salida
    assert "filas=" in salida and "Servidor temporal descartado" in salida
    # Sin datos del negocio en el registro.
    assert "Distribuidora de prueba" not in salida
    # La salud lo ve como una prueba buena.
    codigo, salida = correr(corredor, SALUD, estado=estado)
    assert codigo == 0, salida


def test_prueba_con_un_archivo_elegido_usa_ese_y_no_el_mas_reciente(corredor, carpeta, estado):
    # Triangulacion: `ahora ARCHIVO` restaura el indicado.
    codigo, salida = correr(corredor, f"{PRUEBA} ahora {MAS_VIEJO}", carpeta, estado)
    assert codigo == 0, salida
    assert f"archivo={MAS_VIEJO}" in salida and MAS_NUEVO not in salida


def test_la_prueba_no_usa_las_credenciales_ni_la_red_del_entorno(corredor, carpeta, estado):
    # D10: aunque el entorno traiga variables de conexion de produccion (aqui las del arnes:
    # PGHOST=postgres), la prueba usa su propio servidor temporal.
    codigo, salida = correr(
        corredor,
        f"{PRUEBA} ahora",
        carpeta,
        estado,
        entorno={"PGHOST": "postgres", "PGPASSWORD": "no-debe-usarse"},
    )
    assert codigo == 0, salida


def test_sin_backups_validos_la_prueba_falla(corredor, estado, docker_cliente):
    volumen = docker_cliente.volumes.create()
    try:
        montaje = {volumen.name: {"bind": "/backups", "mode": "ro"}}
        codigo, salida = correr(corredor, f"{PRUEBA} ahora", montaje, estado)
        assert codigo != 0 and "no hay ningun backup valido" in salida
        codigo, _ = correr(corredor, SALUD, estado=estado)
        assert codigo == 1
    finally:
        volumen.remove(force=True)


def test_la_prueba_se_niega_a_correr_como_superusuario(corredor, carpeta, estado):
    # D11: el servidor temporal de Postgres no arranca como root; el mensaje lo explica.
    codigo, salida = correr(corredor, f"{PRUEBA} ahora", carpeta, estado, usuario=None)
    assert codigo != 0 and "sin privilegios" in salida


# --- «Backup que no se puede restaurar» --------------------------------------------------------


@pytest.fixture
def carpeta_danada(
    docker_cliente, respaldo_de_origen, corredor
) -> Iterator[dict[str, dict[str, str]]]:
    """El backup MAS RECIENTE esta cortado a la mitad; el anterior esta sano."""
    volumen = docker_cliente.volumes.create()
    codigo, salida = corredor.correr(
        f"cp /origen/{respaldo_de_origen.nombre} /backups/{MAS_VIEJO} "
        f"&& head -c $(( $(wc -c < /origen/{respaldo_de_origen.nombre}) / 2 )) "
        f"/origen/{respaldo_de_origen.nombre} > /backups/{MAS_NUEVO} "
        "&& chown 999:999 /backups/*.dump",
        red=False,
        volumenes={
            respaldo_de_origen.volumen: {"bind": "/origen", "mode": "ro"},
            volumen.name: {"bind": "/backups", "mode": "rw"},
        },
    )
    assert codigo == 0, salida
    yield {volumen.name: {"bind": "/backups", "mode": "ro"}}
    volumen.remove(force=True)


def test_un_backup_danado_hace_fallar_la_prueba_y_la_salud(corredor, carpeta_danada, estado):
    # Escenario «Backup que no se puede restaurar» (D10): informa error y la salud pasa a no
    # sana. No se cae al backup anterior: el mas reciente es el que importa.
    codigo, salida = correr(corredor, f"{PRUEBA} ahora", carpeta_danada, estado)
    assert codigo != 0, salida
    assert "ERROR" in salida and "Prueba de restauracion verificada" not in salida
    codigo, salida = correr(corredor, SALUD, estado=estado)
    assert codigo == 1 and "fallo" in salida


def test_una_prueba_buena_despues_de_una_fallida_vuelve_a_poner_la_salud_en_verde(
    corredor, carpeta, carpeta_danada, estado
):
    # Triangulacion: falla (backup danado) y despues sale bien (carpeta sana) en el mismo estado.
    assert correr(corredor, f"{PRUEBA} ahora", carpeta_danada, estado)[0] != 0
    assert correr(corredor, SALUD, estado=estado)[0] == 1
    assert correr(corredor, f"{PRUEBA} ahora", carpeta, estado)[0] == 0
    assert correr(corredor, SALUD, estado=estado)[0] == 0


# --- «Prueba atrasada» -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dias", "ultimo", "sano"),
    [
        (3, "ok", True),
        (34, "ok", True),  # un mes y poco: todavia dentro del margen
        (36, "ok", False),  # mas de 35 dias: atrasada
        (40, "ok", False),
        (3, "fallo", False),  # reciente pero fallida
    ],
)
def test_salud_de_la_prueba_segun_la_ultima_buena_y_la_ultima_corrida(
    corredor, estado, dias, ultimo, sano
):
    # Escenario «Prueba atrasada» (D10): no sano con la ultima buena de hace mas de 35 dias o con
    # la ultima corrida fallida.
    preparar = (
        f"echo $(( $(date +%s) - {dias} * {DIA} )) > /estado-prueba/ultima_buena && "
        f"echo {ultimo} > /estado-prueba/ultimo && "
    )
    codigo, salida = correr(corredor, f"{preparar} {SALUD}", estado=estado)
    assert (codigo == 0) == sano, salida
    if not sano:
        assert salida.strip()


@pytest.mark.parametrize(("dias_desde_inicio", "sano"), [(0, True), (20, True), (36, False)])
def test_salud_sin_ninguna_prueba_todavia_depende_de_cuando_arranco_el_servicio(
    corredor, estado, dias_desde_inicio, sano
):
    # Servicio nuevo: la primera prueba programada llega en menos de un mes; si pasan mas de 35
    # dias desde que arranco y no hubo ninguna, esta atrasada.
    preparar = f"echo $(( $(date +%s) - {dias_desde_inicio} * {DIA} )) > /estado-prueba/inicio && "
    codigo, salida = correr(corredor, f"{preparar} {SALUD}", estado=estado)
    assert (codigo == 0) == sano, salida


# --- Proxima corrida: dia PRUEBA_DIA, hora PRUEBA_HORA, en TZ ---------------------------------


def epoch(anio, mes, dia, hora=0, minuto=0) -> int:
    return int(datetime(anio, mes, dia, hora, minuto, tzinfo=ZoneInfo(TZ)).timestamp())


CASOS_PROGRAMA = [
    # (PRUEBA_DIA, PRUEBA_HORA, ahora, proxima) -- ver `programar_prueba.sh`
    (1, "04:00", epoch(2026, 11, 1, 2), epoch(2026, 11, 1, 4)),  # el mismo dia, antes de la hora
    (
        1,
        "04:00",
        epoch(2026, 11, 1, 4),
        epoch(2026, 12, 1, 4),
    ),  # justo a la hora: la del mes que viene
    (1, "04:00", epoch(2026, 11, 20, 10), epoch(2026, 12, 1, 4)),  # despues del dia
    (15, "04:00", epoch(2026, 11, 3, 10), epoch(2026, 11, 15, 4)),  # antes del dia
    (15, "23:30", epoch(2026, 11, 15, 23, 29), epoch(2026, 11, 15, 23, 30)),
    (1, "04:00", epoch(2026, 12, 20, 10), epoch(2027, 1, 1, 4)),  # diciembre: cambia de anio
    (31, "04:00", epoch(2026, 11, 10, 10), epoch(2026, 11, 30, 4)),  # noviembre no tiene 31
    (31, "04:00", epoch(2026, 11, 30, 5), epoch(2026, 12, 31, 4)),  # fin de mes ya pasado
    (31, "04:00", epoch(2027, 2, 1, 0), epoch(2027, 2, 28, 4)),  # febrero
    (30, "04:00", epoch(2028, 2, 1, 0), epoch(2028, 2, 29, 4)),  # febrero bisiesto
]


def test_la_funcion_que_calcula_la_proxima_corrida_da_lo_esperado(corredor):
    llamadas = "; ".join(
        f"echo {i} $(segundos_hasta_proxima_prueba {dia} {hora} {ahora})"
        for i, (dia, hora, ahora, _) in enumerate(CASOS_PROGRAMA)
    )
    codigo, salida = correr(
        corredor,
        f"PROGRAMAR_PRUEBA_SOLO_FUNCIONES=1 . /opt/backup/programar_prueba.sh; {llamadas}",
        entorno={"TZ": TZ},
    )
    assert codigo == 0, salida
    obtenido = {int(a): int(b) for a, b in (linea.split() for linea in salida.strip().splitlines())}
    esperado = {i: proxima - ahora for i, (_, _, ahora, proxima) in enumerate(CASOS_PROGRAMA)}
    assert obtenido == esperado


@pytest.mark.parametrize(
    ("variable", "valor"),
    [("PRUEBA_DIA", "0"), ("PRUEBA_DIA", "32"), ("PRUEBA_DIA", "uno"), ("PRUEBA_HORA", "25:00")],
)
def test_un_dia_o_una_hora_invalidos_hacen_fallar_el_arranque_nombrando_la_variable(
    corredor, estado, variable, valor
):
    codigo, salida = correr(corredor, PRUEBA, estado=estado, entorno={variable: valor})
    assert codigo == 1 and variable in salida


# --- Aviso externo opcional (D14) -----------------------------------------------------------------


@pytest.fixture
def servidor_de_aviso(docker_cliente, base_migrada) -> Iterator[object]:
    """Servidor HTTP minimo (nc de busybox): cada pedido que recibe queda en su registro."""
    c = docker_cliente.containers.run(
        "rclone/rclone:1.68.2",
        detach=True,
        entrypoint=[
            "sh",
            "-c",
            'while true; do printf "HTTP/1.1 200 OK\\r\\nContent-Length: 0\\r\\n\\r\\n" '
            "| nc -l -p 8080; echo; done",
        ],
        network=base_migrada.red,
        name=f"aviso-{uuid.uuid4().hex[:8]}",
    )
    try:
        red = docker_cliente.networks.get(base_migrada.red)
        red.disconnect(c)
        red.connect(c, aliases=["aviso"])
        time.sleep(1)
        yield c
    finally:
        c.remove(force=True)


def _pedidos(c) -> str:
    return c.logs(stdout=True, stderr=True).decode("utf-8", "replace")


def test_con_aviso_configurado_llama_al_terminar_bien_y_a_fail_al_fallar(
    corredor, carpeta, carpeta_danada, estado, servidor_de_aviso
):
    # Requisito «Aviso externo opcional» (D14), escenario «Aviso configurado», para la prueba.
    entorno = {"AVISO_URL": "http://aviso:8080/ping/PRUEBA"}
    codigo, salida = correr(corredor, f"{PRUEBA} ahora", carpeta, estado, entorno, red=True)
    assert codigo == 0, salida
    assert "GET /ping/PRUEBA HTTP" in _pedidos(servidor_de_aviso)
    codigo, salida = correr(corredor, f"{PRUEBA} ahora", carpeta_danada, estado, entorno, red=True)
    assert codigo != 0, salida
    assert "GET /ping/PRUEBA/fail HTTP" in _pedidos(servidor_de_aviso)


def test_sin_aviso_configurado_no_intenta_ninguna_llamada(
    corredor, carpeta, carpeta_danada, estado, servidor_de_aviso
):
    # Escenario «Aviso sin configurar»: ni al terminar bien ni al fallar.
    entorno = {"AVISO_URL": ""}
    assert correr(corredor, f"{PRUEBA} ahora", carpeta, estado, entorno, red=True)[0] == 0
    assert correr(corredor, f"{PRUEBA} ahora", carpeta_danada, estado, entorno, red=True)[0] != 0
    assert "GET" not in _pedidos(servidor_de_aviso)
