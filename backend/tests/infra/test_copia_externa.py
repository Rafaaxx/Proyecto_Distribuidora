"""Copia externa cifrada (change 27b, Lote 2; D2, D4, D5, D6, D14).

Specs `sistema/respaldos` (requisitos «Copia externa de cada backup valido», «La copia externa
esta cifrada y su clave no viaja con ella», «La copia externa conserva su propia retencion y no
replica borrados», «La salud del servicio de copia refleja la ultima copia») y
`sistema/despliegue` («Aviso externo opcional»). Cita `docs/02-arquitectura.md` §16.2, §17, §18.

Corre la imagen real `infra/copia/` (rclone fijado, usuario sin privilegios) con un destino LOCAL
cifrado configurado solo por variables, y un caso contra un destino S3 de prueba (`rclone serve
s3` en otro contenedor, sin cuentas reales) para la configuracion S3 por variables.
"""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.infra.conftest import INFRA

TZ = "America/Argentina/Mendoza"
USUARIO = "999:999"
LIBROS = ("cuenta_movimiento", "stock_movimiento", "costo_producto_mov", "auditoria")
CLAVE_PLANA = "clave-de-ensayo-uno"
SAL_PLANA = "sal-de-ensayo-uno"
OTRA_CLAVE_PLANA = "clave-de-ensayo-distinta"
RUTA_LOCAL = "/destino-local/copias"
S3_ACCESO, S3_SECRETO = "ACCESOENSAYO", "SECRETOENSAYO"


def nombre(dia: date, hora: str = "030000") -> str:
    return f"distribuidora-{dia:%Y%m%d}-{hora}.dump"


def _dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def _diecinueve() -> list[str]:
    # Ejemplo de la spec: retencion despues del backup del 2026-12-31.
    diarios = [nombre(d) for d in _dias(date(2026, 12, 18), date(2026, 12, 31))]
    semanales = [
        nombre(date(2026, m, d)) for m, d in ((12, 13), (12, 6), (11, 29), (11, 22), (11, 15))
    ]
    return sorted(diarios + semanales)


# --- Arnes ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def imagen_copia(docker_cliente) -> str:
    etiqueta = "distribuidora-copia:ensayo"
    # Contexto `infra/`: la imagen incluye el retencion.sh compartido de infra/backup.
    docker_cliente.images.build(
        path=str(INFRA), dockerfile="copia/Dockerfile", tag=etiqueta, rm=True
    )
    return etiqueta


@pytest.fixture(scope="module")
def red_copia(docker_cliente) -> Iterator[str]:
    red = docker_cliente.networks.create(f"ensayo-copia-{uuid.uuid4().hex[:8]}")
    yield red.name
    red.remove()


class Copia:
    """Corre comandos `sh` dentro de la imagen de copia, como usuario sin privilegios."""

    def __init__(self, cliente, imagen: str, red: str) -> None:
        self.cliente, self.imagen, self.red = cliente, imagen, red
        self.obscurecidas = {
            "clave": self.obscurecer(CLAVE_PLANA),
            "sal": self.obscurecer(SAL_PLANA),
            "otra_clave": self.obscurecer(OTRA_CLAVE_PLANA),
        }

    def correr(
        self,
        script: str,
        entorno: dict[str, str] | None = None,
        volumenes: dict[str, dict[str, str]] | None = None,
        usuario: str | None = USUARIO,
        entorno_propio: bool = True,
    ) -> tuple[int, str]:
        # Los scripts de las pruebas terminan con `2>&1` donde importa el orden de los mensajes.
        c = self.cliente.containers.create(
            self.imagen,
            entrypoint=["sh", "-c", script],
            environment=self.entorno(entorno) if entorno_propio else {},
            network=self.red,
            user=usuario,
            volumes=volumenes,
        )
        try:
            c.start()
            codigo = c.wait()["StatusCode"]
            salida = c.logs(stdout=True, stderr=True).decode("utf-8", "replace")
        finally:
            c.remove(force=True)
        return codigo, salida

    def entorno(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {
            "COPIA_TIPO": "local",
            "COPIA_RUTA": RUTA_LOCAL,
            "COPIA_CLAVE_CIFRADO": self.obscurecidas["clave"],
            "COPIA_SAL_CIFRADO": self.obscurecidas["sal"],
            "BACKUP_DIARIOS": "14",
            "BACKUP_SEMANALES": "8",
            "TZ": TZ,
            **(extra or {}),
        }

    def obscurecer(self, plano: str) -> str:
        _, salida = self.correr(f"rclone obscure '{plano}'", entorno_propio=False)
        return salida.strip()

    def ahora(self, volumenes, entorno=None, extra: str = "") -> tuple[int, str]:
        return self.correr(f"{extra}sh /opt/copia/copiar.sh ahora 2>&1", entorno, volumenes)

    def destino(self, volumenes, entorno=None) -> list[str]:
        """Nombres descifrados que hay en el destino."""
        codigo, salida = self.correr(
            ". /opt/copia/lib.sh; rclone lsf cifrado: --files-only 2>/dev/null | sort",
            entorno,
            volumenes,
        )
        assert codigo == 0, salida
        return [x for x in salida.split("\n") if x.strip()]

    def sembrar_destino(self, volumenes, nombres: list[str], entorno=None) -> None:
        crear = (
            "mkdir -p /tmp/s; cd /tmp/s; for n in "
            + " ".join(nombres)
            + ('; do echo "backup de prueba $n" > "$n"; done; ')
        )
        codigo, salida = self.correr(
            crear + ". /opt/copia/lib.sh; rclone copy /tmp/s cifrado: 2>&1", entorno, volumenes
        )
        assert codigo == 0, salida


@pytest.fixture(scope="module")
def copia(docker_cliente, imagen_copia, red_copia) -> Copia:
    return Copia(docker_cliente, imagen_copia, red_copia)


@contextmanager
def volumen(cliente, imagen: str) -> Iterator[str]:
    """Volumen con nombre, de uso del usuario sin privilegios (como una carpeta montada)."""
    v = cliente.volumes.create(name=f"ensayo-copia-{uuid.uuid4().hex[:8]}")
    c = cliente.containers.create(
        imagen,
        entrypoint=["sh", "-c", "chown 999:999 /v"],
        user="0",
        volumes={v.name: {"bind": "/v", "mode": "rw"}},
    )
    try:
        c.start()
        assert c.wait()["StatusCode"] == 0
    finally:
        c.remove(force=True)
    try:
        yield v.name
    finally:
        v.remove(force=True)


@pytest.fixture
def vol_backups(docker_cliente, imagen_copia) -> Iterator[str]:
    with volumen(docker_cliente, imagen_copia) as nombre_vol:
        yield nombre_vol


@pytest.fixture
def vol_destino(docker_cliente, imagen_copia) -> Iterator[str]:
    with volumen(docker_cliente, imagen_copia) as nombre_vol:
        yield nombre_vol


@pytest.fixture
def vol_bajados(docker_cliente, imagen_copia) -> Iterator[str]:
    with volumen(docker_cliente, imagen_copia) as nombre_vol:
        yield nombre_vol


def montajes(
    backups: str | None = None,
    destino: str | None = None,
    bajados: str | None = None,
    destino_ro: bool = False,
) -> dict[str, dict[str, str]]:
    m: dict[str, dict[str, str]] = {}
    if backups:
        m[backups] = {"bind": "/backups", "mode": "ro"}  # BACKUP_DIR solo lectura (D4)
    if destino:
        m[destino] = {"bind": "/destino-local", "mode": "ro" if destino_ro else "rw"}
    if bajados:
        m[bajados] = {"bind": "/bajados", "mode": "rw"}
    return m


def sembrar_backups(copia: Copia, vol: str, nombres: list[str]) -> None:
    codigo, salida = copia.correr(
        "cd /backups; for n in "
        + " ".join(nombres)
        + '; do echo "backup de prueba $n" > "$n"; done',
        volumenes={vol: {"bind": "/backups", "mode": "rw"}},
    )
    assert codigo == 0, salida


@pytest.fixture
def backup_real(corredor, copia, vol_backups) -> tuple[str, str]:
    """Un backup real (pg_dump -Fc verificado) en el volumen de backups: (volumen, nombre)."""
    codigo, salida = corredor.correr(
        "sh /opt/backup/programar.sh ahora 2>&1",
        entorno={"BACKUP_DIR": "/backups"},
        usuario=USUARIO,
        volumenes={vol_backups: {"bind": "/backups", "mode": "rw"}},
    )
    assert codigo == 0, salida
    codigo, salida = copia.correr("ls /backups", volumenes=montajes(backups=vol_backups))
    (archivo,) = [x for x in salida.split() if x.endswith(".dump")]
    return vol_backups, archivo


# --- 2.1: copia externa cifrada ----------------------------------------------------------------


def test_un_backup_nuevo_llega_al_destino_verificado(copia, backup_real, vol_destino):
    # Escenario «Un backup nuevo llega al destino».
    vol, archivo = backup_real
    m = montajes(backups=vol, destino=vol_destino)
    codigo, salida = copia.ahora(m)
    assert codigo == 0, salida
    _, tam = copia.correr("wc -c < /backups/" + archivo, volumenes=m)
    assert f"Copia externa verificada: archivo={archivo} tamano={tam.strip()} bytes" in salida
    assert copia.destino(m) == [archivo]
    # Los registros no llevan datos del negocio.
    assert "Distribuidora de prueba" not in salida


def test_la_copia_no_repite_lo_que_ya_esta_en_el_destino(copia, vol_backups, vol_destino):
    # Triangula «Un backup nuevo llega al destino»: solo sube lo que falta.
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 30)), nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, destino=vol_destino)
    codigo, primera = copia.ahora(m)
    assert codigo == 0 and primera.count("Copia externa verificada") == 2, primera
    sembrar_backups(copia, vol_backups, [nombre(date(2027, 1, 1))])
    codigo, segunda = copia.ahora(m)
    assert codigo == 0, segunda
    assert segunda.count("Copia externa verificada") == 1
    assert nombre(date(2027, 1, 1)) in segunda and nombre(date(2026, 12, 31)) not in segunda
    assert copia.destino(m) == sorted(
        [nombre(date(2026, 12, 30)), nombre(date(2026, 12, 31)), nombre(date(2027, 1, 1))]
    )


def test_el_destino_no_es_legible_sin_la_clave(copia, backup_real, vol_destino):
    # Escenario «El destino no es legible sin la clave».
    vol, archivo = backup_real
    m = montajes(backups=vol, destino=vol_destino)
    assert copia.ahora(m)[0] == 0
    codigo, crudo = copia.correr(
        "cd /destino-local && find . -type f | sed 's/^/ARCHIVO:/' && "
        "echo '--- nombres que contienen distribuidora:' && find . | grep -ci distribuidora; "
        "echo '--- archivos con PGDMP o tablas de libro:'; "
        "grep -rlE 'PGDMP|cuenta_movimiento|auditoria' . | wc -l",
        volumenes=m,
    )
    assert codigo == 0, crudo
    archivos = [x for x in crudo.split("\n") if x.startswith("ARCHIVO:")]
    assert len(archivos) == 1
    assert "distribuidora" not in archivos[0].lower() and ".dump" not in archivos[0]
    assert crudo.split("distribuidora:")[1].split("\n")[1].strip() == "0"
    assert crudo.rstrip().endswith("0")  # ningun archivo contiene el formato ni las tablas


def test_bajar_un_backup_deja_un_archivo_identico_que_pg_restore_lee(
    corredor, copia, backup_real, vol_destino, vol_bajados
):
    # Escenario «Bajar un backup de la copia externa».
    vol, archivo = backup_real
    m = montajes(backups=vol, destino=vol_destino, bajados=vol_bajados)
    assert copia.ahora(m)[0] == 0
    codigo, salida = copia.correr(f"sh /opt/copia/copiar.sh bajar {archivo} 2>&1", volumenes=m)
    assert codigo == 0, salida
    assert f"Backup bajado y descifrado: archivo={archivo}" in salida
    codigo, comparacion = copia.correr(
        f"sha256sum /backups/{archivo} /bajados/{archivo} | cut -d' ' -f1 | uniq | wc -l; "
        "ls -A /bajados",
        volumenes=m,
    )
    assert codigo == 0
    lineas = comparacion.split()
    assert lineas[0] == "1", "el archivo bajado no es identico al original"
    assert lineas[1:] == [archivo], "no debe quedar ningun temporal"
    # `pg_restore --list` (imagen de backup) lo lee con las cuatro tablas de libro.
    codigo, lista = corredor.correr(
        f"pg_restore --list /bajados/{archivo} 2>&1",
        red=False,
        usuario=USUARIO,
        volumenes={vol_bajados: {"bind": "/bajados", "mode": "ro"}},
    )
    assert codigo == 0, lista
    for libro in LIBROS:
        assert f" TABLE public {libro} " in lista


def test_clave_equivocada_falla_y_no_deja_dump(copia, vol_backups, vol_destino, vol_bajados):
    # Escenario «Clave equivocada» (y que el nombre pedido no puede salirse de la carpeta).
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, destino=vol_destino, bajados=vol_bajados)
    assert copia.ahora(m)[0] == 0
    otra = {"COPIA_CLAVE_CIFRADO": copia.obscurecidas["otra_clave"]}
    archivo = nombre(date(2026, 12, 31))
    codigo, salida = copia.correr(
        f"sh /opt/copia/copiar.sh bajar {archivo} 2>&1; echo '--'; ls -A /bajados", otra, m
    )
    assert "clave de cifrado no abre ningun archivo del destino" in salida
    assert "ERROR" in salida
    assert ".dump" not in salida.split("--")[1]
    codigo, _ = copia.correr(f"sh /opt/copia/copiar.sh bajar {archivo} >/dev/null 2>&1", otra, m)
    assert codigo != 0
    # Triangula: con la clave buena, un archivo que no esta tambien falla y no deja nada.
    codigo, salida = copia.correr(
        f"sh /opt/copia/copiar.sh bajar {nombre(date(2020, 1, 1))} 2>&1; echo '--'; ls -A /bajados",
        volumenes=m,
    )
    assert "no esta en el destino" in salida and ".dump" not in salida.split("--")[1]
    codigo, salida = copia.correr(
        "sh /opt/copia/copiar.sh bajar ../../etc/passwd 2>&1", volumenes=m
    )
    assert codigo != 0 and "distribuidora-AAAAMMDD-HHMMSS.dump" in salida


def test_corrida_con_otra_clave_falla_en_vez_de_subir_con_la_clave_nueva(
    copia, vol_backups, vol_destino
):
    # Una clave distinta no debe mezclar archivos con dos claves en el mismo destino.
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 30))])
    m = montajes(backups=vol_backups, destino=vol_destino)
    assert copia.ahora(m)[0] == 0
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    codigo, salida = copia.ahora(m, {"COPIA_CLAVE_CIFRADO": copia.obscurecidas["otra_clave"]})
    assert codigo == 1 and "clave de cifrado" in salida
    assert copia.destino(m) == [nombre(date(2026, 12, 30))]


# --- 2.2: retencion propia del destino, sin replicar borrados ----------------------------------


def test_borrar_los_backups_locales_no_borra_nada_del_destino(copia, vol_backups, vol_destino):
    # Escenario «Se borra la carpeta de la PC».
    esperados = _diecinueve()
    m = montajes(backups=vol_backups, destino=vol_destino)
    copia.sembrar_destino(m, esperados)
    assert copia.destino(m) == esperados  # carpeta local vacia: «se borraron todos»
    codigo, salida = copia.ahora(m)
    assert codigo == 0, salida
    assert "se borro" not in salida
    assert copia.destino(m) == esperados


def test_retencion_en_el_destino_deja_los_mismos_19(copia, vol_backups, vol_destino):
    # Escenario «Retencion en el destino»: 61 dias, el ultimo recien subido.
    anteriores = [nombre(d) for d in _dias(date(2026, 11, 1), date(2026, 12, 30))]
    m = montajes(backups=vol_backups, destino=vol_destino)
    copia.sembrar_destino(m, anteriores)
    assert len(copia.destino(m)) == 60
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    codigo, salida = copia.ahora(m)
    assert codigo == 0, salida
    assert copia.destino(m) == _diecinueve()


def test_la_retencion_del_destino_ignora_lo_que_no_es_un_backup(copia, vol_backups, vol_destino):
    # Triangula la retencion: solo borra nombres con formato de backup.
    m = montajes(backups=vol_backups, destino=vol_destino)
    ajenos = ["notas.txt", "distribuidora-20261201-030000.dump.fallido"]
    copia.sembrar_destino(
        m, [nombre(d) for d in _dias(date(2026, 11, 1), date(2026, 12, 30))] + ajenos
    )
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    assert copia.ahora(m)[0] == 0
    destino = copia.destino(m)
    assert set(ajenos) <= set(destino)
    assert sorted(set(destino) - set(ajenos)) == _diecinueve()


def test_destino_inaccesible_falla_sin_borrar_y_la_siguiente_sube_lo_pendiente(
    copia, vol_backups, vol_destino
):
    # Escenario «Sin internet, la copia espera y no pierde nada» (destino sin escritura).
    anteriores = [nombre(d) for d in _dias(date(2026, 11, 1), date(2026, 12, 30))]
    sembrado = montajes(destino=vol_destino)
    copia.sembrar_destino(sembrado, anteriores)
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    codigo, salida = copia.ahora(
        montajes(backups=vol_backups, destino=vol_destino, destino_ro=True)
    )
    assert codigo == 1 and "ERROR: no se pudo copiar" in salida, salida
    assert "se borro" not in salida
    assert copia.destino(sembrado) == sorted(anteriores)  # nada borrado, nada subido
    codigo, salida = copia.ahora(montajes(backups=vol_backups, destino=vol_destino))
    assert codigo == 0, salida
    assert nombre(date(2026, 12, 31)) in copia.destino(sembrado)


# --- 2.3: salud y aviso ------------------------------------------------------------------------


def _hace(horas: float) -> str:
    momento = datetime.now(ZoneInfo(TZ)) - timedelta(hours=horas)
    return f"distribuidora-{momento:%Y%m%d-%H%M%S}.dump"


@pytest.mark.parametrize(
    ("horas", "sano"),
    [(3, True), (25, True), (27, False), (30, False)],
)
def test_salud_segun_la_antiguedad_del_ultimo_backup_en_el_destino(copia, vol_destino, horas, sano):
    # Escenarios «Copia al dia» (3 horas) y «Copia atrasada» (30 horas); 25 y 27 acotan el limite.
    m = montajes(destino=vol_destino)
    copia.sembrar_destino(m, [nombre(date(2026, 1, 1)), _hace(horas)])
    codigo, salida = copia.correr("sh /opt/copia/salud.sh 2>&1", volumenes=m)
    assert (codigo == 0) is sano, salida
    if not sano:
        assert "mas de 26 horas" in salida


def test_salud_sin_backups_en_el_destino_tolera_la_primera_hora_y_despues_falla(copia, vol_destino):
    # Triangula la salud: un destino vacio es sano solo mientras arranca el servicio.
    m = montajes(destino=vol_destino)
    codigo, salida = copia.correr(
        "mkdir -p /tmp/estado-copia; date +%s > /tmp/estado-copia/inicio; "
        "sh /opt/copia/salud.sh 2>&1",
        volumenes=m,
    )
    assert codigo == 0, salida
    codigo, salida = copia.correr(
        "mkdir -p /tmp/estado-copia; echo $(( $(date +%s) - 7200 )) > /tmp/estado-copia/inicio; "
        "sh /opt/copia/salud.sh 2>&1",
        volumenes=m,
    )
    assert codigo == 1 and "primera hora" in salida


def test_salud_no_sana_si_la_ultima_corrida_fallo_por_la_clave(copia, vol_backups, vol_destino):
    # Requisito «La salud del servicio de copia…»: falla por credenciales o por la clave, aun con
    # un backup reciente en el destino.
    m = montajes(backups=vol_backups, destino=vol_destino)
    copia.sembrar_destino(m, [_hace(3)])
    otra = {"COPIA_CLAVE_CIFRADO": copia.obscurecidas["otra_clave"]}
    codigo, salida = copia.correr("sh /opt/copia/salud.sh 2>&1", volumenes=m)
    assert codigo == 0, salida  # con la clave buena, sano
    codigo, salida = copia.correr(
        "sh /opt/copia/copiar.sh ahora >/dev/null 2>&1; sh /opt/copia/salud.sh 2>&1", otra, m
    )
    assert codigo == 1 and "clave de cifrado" in salida


def test_un_fallo_de_red_no_vuelve_no_sano_a_un_servicio_con_copia_reciente(
    copia, vol_backups, vol_destino
):
    # Triangula: el destino sin escritura (transitorio) no es credenciales ni clave.
    sembrado = montajes(destino=vol_destino)
    copia.sembrar_destino(sembrado, [_hace(3)])
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, destino=vol_destino, destino_ro=True)
    codigo, salida = copia.correr(
        "sh /opt/copia/copiar.sh ahora >/dev/null 2>&1; echo CORRIDA=$?; "
        "sh /opt/copia/salud.sh 2>&1",
        volumenes=m,
    )
    assert "CORRIDA=1" in salida
    assert codigo == 0, salida


@contextmanager
def servidor_de_aviso(cliente, imagen: str, red: str) -> Iterator[object]:
    """Servidor HTTP minimo (nc de busybox): imprime en su registro cada pedido que recibe."""
    c = cliente.containers.run(
        imagen,
        detach=True,
        entrypoint=[
            "sh",
            "-c",
            'while true; do printf "HTTP/1.1 200 OK\\r\\nContent-Length: 0\\r\\n\\r\\n" '
            "| nc -l -p 8080; echo; done",
        ],
        network=red,
        user=USUARIO,
    )
    try:
        cliente.networks.get(red).disconnect(c)
        cliente.networks.get(red).connect(c, aliases=["aviso"])
        time.sleep(1)
        yield c
    finally:
        c.remove(force=True)


def _pedidos(c) -> str:
    return c.logs(stdout=True, stderr=True).decode("utf-8", "replace")


def test_con_aviso_configurado_llama_al_terminar_bien_y_a_fail_al_fallar(
    docker_cliente, imagen_copia, red_copia, copia, vol_backups, vol_destino
):
    # Requisito «Aviso externo opcional», escenario «Aviso configurado».
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, destino=vol_destino)
    aviso = {"AVISO_URL": "http://aviso:8080/ping/ABC"}
    with servidor_de_aviso(docker_cliente, imagen_copia, red_copia) as servidor:
        codigo, salida = copia.ahora(m, aviso)
        assert codigo == 0, salida
        pedidos = _pedidos(servidor)
        assert "GET /ping/ABC HTTP" in pedidos and "/fail" not in pedidos
        # Con la clave equivocada la corrida falla y llama a la variante de falla.
        otra = {**aviso, "COPIA_CLAVE_CIFRADO": copia.obscurecidas["otra_clave"]}
        codigo, salida = copia.ahora(m, otra)
        assert codigo == 1, salida
        assert "GET /ping/ABC/fail HTTP" in _pedidos(servidor)


def test_sin_aviso_configurado_no_intenta_ninguna_llamada(
    docker_cliente, imagen_copia, red_copia, copia, vol_backups, vol_destino
):
    # Escenario «Aviso sin configurar»: ni al terminar bien ni al fallar.
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, destino=vol_destino)
    with servidor_de_aviso(docker_cliente, imagen_copia, red_copia) as servidor:
        assert copia.ahora(m, {"AVISO_URL": ""})[0] == 0
        otra = {"AVISO_URL": "", "COPIA_CLAVE_CIFRADO": copia.obscurecidas["otra_clave"]}
        assert copia.ahora(m, otra)[0] == 1
        assert "GET" not in _pedidos(servidor)


# --- 2.3: destino S3 de prueba (configuracion S3 solo por variables) ---------------------------


@contextmanager
def servidor_s3(cliente, imagen: str, red: str) -> Iterator[object]:
    """Destino compatible con S3 de prueba: `rclone serve s3` con el cubo `cubo` y credenciales."""
    c = cliente.containers.run(
        imagen,
        detach=True,
        entrypoint=[
            "sh",
            "-c",
            "mkdir -p /tmp/s3/cubo && exec rclone serve s3 /tmp/s3 --addr :9000 "
            f"--auth-key {S3_ACCESO},{S3_SECRETO}",
        ],
        network=red,
        user=USUARIO,
    )
    try:
        cliente.networks.get(red).disconnect(c)
        cliente.networks.get(red).connect(c, aliases=["s3"])
        limite = time.time() + 30
        while time.time() < limite:
            codigo, _ = c.exec_run(["sh", "-c", "nc -z localhost 9000"])
            if codigo == 0:
                break
            time.sleep(0.5)
        yield c
    finally:
        c.remove(force=True)


def _s3(**cambios: str) -> dict[str, str]:
    return {
        "COPIA_TIPO": "s3",
        "COPIA_RUTA": "cubo/copias",
        "COPIA_S3_ENDPOINT": "http://s3:9000",
        "COPIA_S3_PROVEEDOR": "Other",
        "COPIA_ACCESS_KEY_ID": S3_ACCESO,
        "COPIA_SECRET_ACCESS_KEY": S3_SECRETO,
        **cambios,
    }


def test_destino_s3_sube_cifrado_baja_y_se_recupera_de_un_corte(
    docker_cliente, imagen_copia, red_copia, copia, vol_backups, vol_bajados
):
    # Configuracion S3 solo por variables; «Sin internet, la copia espera y no pierde nada».
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 30)), nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups, bajados=vol_bajados)
    with servidor_s3(docker_cliente, imagen_copia, red_copia):
        # Endpoint inalcanzable (corte): falla, no sube nada.
        codigo, salida = copia.ahora(m, _s3(COPIA_S3_ENDPOINT="http://sin-internet:9000"))
        assert codigo == 1 and "ERROR" in salida, salida
        # Vuelve el servicio: la corrida siguiente sube todo lo pendiente.
        codigo, salida = copia.ahora(m, _s3())
        assert codigo == 0, salida
        assert salida.count("Copia externa verificada") == 2
        assert copia.destino(m, _s3()) == [nombre(date(2026, 12, 30)), nombre(date(2026, 12, 31))]
        # El proveedor solo ve nombres y contenido cifrados.
        codigo, crudo = copia.correr(
            ". /opt/copia/lib.sh; rclone lsf bruto:cubo/copias 2>&1", _s3(), m
        )
        assert codigo == 0 and crudo.strip() and "distribuidora" not in crudo.lower()
        # Bajar desde S3 deja el archivo identico.
        archivo = nombre(date(2026, 12, 31))
        codigo, salida = copia.correr(
            f"sh /opt/copia/copiar.sh bajar {archivo} 2>&1 "
            f"&& cmp /backups/{archivo} /bajados/{archivo}"
            " && echo IGUAL",
            _s3(),
            m,
        )
        assert codigo == 0 and "IGUAL" in salida, salida


def test_destino_s3_con_credenciales_malas_falla_y_la_salud_lo_dice(
    docker_cliente, imagen_copia, red_copia, copia, vol_backups
):
    # Salud: la ultima corrida fallo por credenciales.
    sembrar_backups(copia, vol_backups, [nombre(date(2026, 12, 31))])
    m = montajes(backups=vol_backups)
    with servidor_s3(docker_cliente, imagen_copia, red_copia):
        malas = _s3(COPIA_SECRET_ACCESS_KEY="otro-secreto")
        codigo, salida = copia.correr(
            "sh /opt/copia/copiar.sh ahora 2>&1; echo CORRIDA=$?; sh /opt/copia/salud.sh 2>&1",
            malas,
            m,
        )
        assert "CORRIDA=1" in salida and "ERROR" in salida, salida
        assert codigo == 1 and "credenciales" in salida
