"""Restauración de un backup y comprobación de los datos (change 27b, Lote 3; D8, D9).

Specs `sistema/respaldos`: requisitos «Restauración de un backup en una base vacía» y «La
restauración comprueba que los datos coinciden». Cita INV-05, ADR-020 y
`docs/00-vision-y-alcance.md` §9 criterio 12 (recuperar el sistema desde un backup, con los
datos iguales).

Un backup real de la base de origen migrada (conftest) se restaura en OTRO `postgres:17`
inicializado con los mismos scripts de roles que produccion, vacio, con el rol dueño del esquema
(`app_migrations`), exactamente como lo haria el servicio `restauracion` del compose.
"""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import ProgrammingError

from tests.infra.conftest import (
    BASE,
    CLAVE_BACKUP,
    CLAVE_MIGRACIONES,
    CLAVE_RUNTIME,
    CLAVE_SUPER,
    IMAGEN_POSTGRES,
    INFRA,
    SUPERUSUARIO,
    Corredor,
    Respaldo,
)

LIBROS = ("cuenta_movimiento", "stock_movimiento", "costo_producto_mov", "auditoria")
ALIAS_DESTINO = "destino"
RESTAURA = "sh /opt/backup/restaurar.sh"
COMPRUEBA = "sh /opt/backup/comprobar.sh"


# --- Arnes: un segundo servidor, vacio, con los roles de produccion -----------------------------


@dataclass
class Destino:
    contenedor: object
    red: str
    puerto: int

    def sql(self, base: str, sentencia: str) -> str:
        """Ejecuta SQL como superusuario por el socket del contenedor (sin red)."""
        codigo, salida = self.contenedor.exec_run(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                SUPERUSUARIO,
                "-d",
                base,
                "-tA",
                "-c",
                sentencia,
            ]
        )
        texto = salida.decode("utf-8", "replace")
        assert codigo == 0, texto
        return texto.strip()

    def nueva_base_vacia(self) -> str:
        """Una base recien creada, como la deja `init-app-roles.sh` (esquema de app_migrations)."""
        nombre = f"restaurada_{uuid.uuid4().hex[:8]}"
        self.sql("postgres", f"CREATE DATABASE {nombre} OWNER app_migrations")
        self.sql(nombre, "ALTER SCHEMA public OWNER TO app_migrations")
        self.sql(nombre, "GRANT USAGE ON SCHEMA public TO app_runtime")
        return nombre

    def url(self, base: str, usuario: str, clave: str) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=usuario,
            password=clave,
            host="localhost",
            port=self.puerto,
            database=base,
        )

    def motor(self, base: str, usuario: str, clave: str) -> Engine:
        return create_engine(self.url(base, usuario, clave))


@pytest.fixture(scope="module")
def destino(docker_cliente) -> Iterator[Destino]:
    red = docker_cliente.networks.create(f"ensayo-restauracion-{uuid.uuid4().hex[:8]}")
    contenedor = docker_cliente.containers.run(
        IMAGEN_POSTGRES,
        detach=True,
        environment={
            "POSTGRES_USER": SUPERUSUARIO,
            "POSTGRES_PASSWORD": CLAVE_SUPER,
            "POSTGRES_DB": BASE,
            "APP_MIGRATIONS_DB_PASSWORD": CLAVE_MIGRACIONES,
            "APP_RUNTIME_DB_PASSWORD": CLAVE_RUNTIME,
            "APP_BACKUP_DB_PASSWORD": CLAVE_BACKUP,
        },
        volumes={
            str(INFRA / "postgres" / "init-app-roles.sh"): {
                "bind": "/docker-entrypoint-initdb.d/10-init-app-roles.sh",
                "mode": "ro",
            },
            str(INFRA / "postgres" / "20-init-backup-role.sh"): {
                "bind": "/docker-entrypoint-initdb.d/20-init-backup-role.sh",
                "mode": "ro",
            },
        },
        ports={"5432/tcp": None},
        network=red.name,
        labels={"ensayo": "restauracion-27b"},
    )
    red.disconnect(contenedor)
    red.connect(contenedor, aliases=[ALIAS_DESTINO])
    try:
        puerto = _esperar(contenedor)
        yield Destino(contenedor=contenedor, red=red.name, puerto=puerto)
    finally:
        contenedor.remove(force=True, v=True)
        red.remove()


def _esperar(contenedor) -> int:
    limite = time.time() + 120
    while time.time() < limite:
        contenedor.reload()
        puertos = contenedor.attrs["NetworkSettings"]["Ports"].get("5432/tcp")
        if puertos:
            puerto = int(puertos[0]["HostPort"])
            try:
                motor = create_engine(
                    URL.create(
                        "postgresql+psycopg",
                        username="app_backup",
                        password=CLAVE_BACKUP,
                        host="localhost",
                        port=puerto,
                        database=BASE,
                    )
                )
                with motor.connect() as c:
                    c.execute(text("SELECT 1"))
                motor.dispose()
                return puerto
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("PostgreSQL de destino no arranco a tiempo")


@pytest.fixture(scope="module")
def restaurador(docker_cliente, destino, imagen_backup) -> Corredor:
    return Corredor(docker_cliente, imagen_backup, destino.red)


def montaje(respaldo: Respaldo) -> dict[str, dict[str, str]]:
    return {respaldo.volumen: {"bind": "/backups", "mode": "ro"}}


def restaurar(
    restaurador: Corredor,
    respaldo: Respaldo,
    base: str,
    archivo: str | None = None,
    script: str = RESTAURA,
) -> tuple[int, str]:
    """Restaura como `app_migrations` (el rol del servicio `restauracion`)."""
    entorno = {
        "PGHOST": ALIAS_DESTINO,
        "PGUSER": "app_migrations",
        "PGPASSWORD": CLAVE_MIGRACIONES,
        "PGDATABASE": base,
        "BACKUP_DIR": "/backups",
    }
    return restaurador.correr(
        f"{script} {archivo or respaldo.nombre} 2>&1", entorno=entorno, volumenes=montaje(respaldo)
    )


def huella(motor: Engine) -> dict[str, tuple[int, str]]:
    """Conteo y suma de control (md5 del contenido ordenado) de cada tabla del esquema `public`."""
    with motor.connect() as c:
        tablas = [
            fila[0]
            for fila in c.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
            )
        ]
        resultado = {}
        for t in tablas:
            fila = c.execute(
                text(
                    f"SELECT count(*), "
                    f"md5(coalesce(string_agg(x::text, ',' ORDER BY x::text), '')) "
                    f"FROM public.{t} x"
                )
            ).one()
            resultado[t] = (fila[0], fila[1])
    return resultado


@pytest.fixture
def base_restaurada(destino, restaurador, respaldo_de_origen) -> str:
    base = destino.nueva_base_vacia()
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base)
    assert codigo == 0, salida
    return base


# --- «Restaurar en una base vacia» y «Los datos coinciden con el origen» -----------------------


def test_restaura_en_una_base_vacia_y_los_datos_coinciden_con_el_origen(
    destino, restaurador, respaldo_de_origen, base_migrada
):
    # Escenarios «Restaurar en una base vacia» y «Los datos coinciden con el origen» (00 §9
    # criterio 12): mismas tablas, mismas filas y misma suma de control que el origen.
    base = destino.nueva_base_vacia()
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base)
    assert codigo == 0, salida
    assert "Restauracion verificada" in salida
    origen = create_engine(base_migrada.url("app_migrations", CLAVE_MIGRACIONES))
    restaurada = destino.motor(base, "app_migrations", CLAVE_MIGRACIONES)
    h_origen, h_destino = huella(origen), huella(restaurada)
    assert h_destino == h_origen
    assert len(h_origen) > 20
    assert h_origen["auditoria"][0] == 3 and h_origen["organizacion"][0] == 1
    # El registro cuenta tablas y filas, pero no trae datos del negocio.
    assert "Distribuidora de prueba" not in salida and "PRUEBA-" not in salida
    origen.dispose()
    restaurada.dispose()


def test_la_restauracion_conserva_la_secuencia_y_la_version_de_migraciones(
    destino, base_restaurada, base_migrada
):
    # Los GRANT, secuencias y la version de Alembic llegan completos con el rol dueño.
    restaurada = destino.motor(base_restaurada, "app_migrations", CLAVE_MIGRACIONES)
    with restaurada.connect() as c:
        assert c.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1
        assert c.execute(text("SELECT nextval('secuencia_de_prueba')")).scalar() == 2
    restaurada.dispose()


@pytest.mark.parametrize("libro", LIBROS)
@pytest.mark.parametrize("operacion", ["UPDATE", "DELETE"])
def test_inv05_app_runtime_sigue_sin_modificar_ni_borrar_libros_tras_restaurar(
    destino, base_restaurada, libro, operacion
):
    # INV-05, ADR-020, escenario «La aplicacion sigue sin borrar libros despues de restaurar».
    runtime = destino.motor(base_restaurada, "app_runtime", CLAVE_RUNTIME)
    sentencia = {
        "UPDATE": f"UPDATE public.{libro} SET id = id",
        "DELETE": f"DELETE FROM public.{libro}",
    }[operacion]
    with pytest.raises(ProgrammingError, match="permission denied"), runtime.begin() as c:
        c.execute(text(sentencia))
    # ...pero la aplicacion si puede leer e insertar: los permisos no se perdieron de mas.
    with runtime.connect() as c:
        assert c.execute(text(f"SELECT count(*) FROM public.{libro}")).scalar() is not None
        assert c.execute(
            text(f"SELECT has_table_privilege('app_runtime', 'public.{libro}', 'INSERT')")
        ).scalar()
    runtime.dispose()


# --- Barandas: base con datos, sistema en uso, archivo malo -----------------------------------


def test_se_niega_a_pisar_una_base_con_datos_y_no_la_modifica(
    destino, restaurador, respaldo_de_origen, base_restaurada
):
    # Escenario «Se niega a pisar una base con datos» (D8): la segunda restauracion sobre la misma
    # base termina con error y deja los datos como estaban.
    restaurada = destino.motor(base_restaurada, "app_migrations", CLAVE_MIGRACIONES)
    antes = huella(restaurada)
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo != 0
    assert "no esta vacia" in salida
    assert huella(restaurada) == antes
    restaurada.dispose()


def test_se_niega_con_una_sola_tabla_en_la_base(destino, restaurador, respaldo_de_origen):
    # Triangulacion: alcanza una tabla cualquiera para negarse; esa tabla es lo unico que queda.
    base = destino.nueva_base_vacia()
    destino.sql(base, "CREATE TABLE public.sola (id int)")
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base)
    assert codigo != 0 and "no esta vacia" in salida
    assert (
        destino.sql(
            base, "SELECT string_agg(tablename, ',') FROM pg_tables WHERE schemaname = 'public'"
        )
        == "sola"
    )


def test_se_niega_con_otra_conexion_abierta_y_pide_detener_el_backend(
    destino, restaurador, respaldo_de_origen
):
    # Escenario «Se niega con el sistema en uso» (D8).
    base = destino.nueva_base_vacia()
    en_uso = destino.motor(base, "app_runtime", CLAVE_RUNTIME)
    conexion = en_uso.connect()
    try:
        conexion.execute(text("SELECT 1"))
        codigo, salida = restaurar(restaurador, respaldo_de_origen, base)
    finally:
        conexion.close()
        en_uso.dispose()
    assert codigo != 0, salida
    assert "detenga el backend" in salida, salida
    assert destino.sql(base, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") == "0"


def test_restaura_cuando_la_otra_conexion_ya_se_cerro(destino, restaurador, respaldo_de_origen):
    # Triangulacion de la baranda: la conexion cerrada no impide restaurar.
    base = destino.nueva_base_vacia()
    motor = destino.motor(base, "app_runtime", CLAVE_RUNTIME)
    with motor.connect() as c:
        c.execute(text("SELECT 1"))
    motor.dispose()
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base)
    assert codigo == 0, salida


def vacias(destino: Destino, base: str) -> bool:
    return destino.sql(base, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") == "0"


@contextmanager
def dump_de_otra_base(
    destino: Destino, restaurador: Corredor, sentencias: list[str], despues: list[str] = ()
) -> Iterator[dict[str, dict[str, str]]]:
    """Arma una base aparte con `sentencias` (tablas del rol app_migrations), la vuelca a un
    volumen como `distribuidora-20260101-030000.dump` y la borra (corriendo `despues`)."""
    origen = f"otra_{uuid.uuid4().hex[:8]}"
    destino.sql("postgres", f"CREATE DATABASE {origen} OWNER app_migrations")
    destino.sql(origen, "ALTER SCHEMA public OWNER TO app_migrations")
    for s in sentencias:
        # Las tablas son del rol dueño del esquema; las que empiezan con «!» van como superusuario.
        destino.sql(origen, s[1:] if s.startswith("!") else f"SET ROLE app_migrations; {s}")
    volumen = restaurador.cliente.volumes.create()
    try:
        codigo, salida = restaurador.correr(
            "pg_dump -Fc -f /tmp/otros/distribuidora-20260101-030000.dump",
            entorno={
                "PGHOST": ALIAS_DESTINO,
                "PGUSER": SUPERUSUARIO,
                "PGPASSWORD": CLAVE_SUPER,
                "PGDATABASE": origen,
            },
            volumenes={volumen.name: {"bind": "/tmp/otros", "mode": "rw"}},
        )
        assert codigo == 0, salida
        destino.sql("postgres", f"DROP DATABASE {origen}")
        for s in despues:
            destino.sql("postgres", s)
        yield {volumen.name: {"bind": "/backups", "mode": "ro"}}
    finally:
        volumen.remove(force=True)


def restaurar_de(restaurador: Corredor, volumenes, base: str) -> tuple[int, str]:
    return restaurador.correr(
        f"{RESTAURA} distribuidora-20260101-030000.dump 2>&1",
        entorno={
            "PGHOST": ALIAS_DESTINO,
            "PGUSER": "app_migrations",
            "PGPASSWORD": CLAVE_MIGRACIONES,
            "PGDATABASE": base,
            "BACKUP_DIR": "/backups",
        },
        volumenes=volumenes,
    )


def test_un_archivo_que_no_existe_se_rechaza_sin_tocar_la_base(
    destino, restaurador, respaldo_de_origen
):
    # D8: el archivo se verifica ANTES de tocar nada.
    base = destino.nueva_base_vacia()
    codigo, salida = restaurar(restaurador, respaldo_de_origen, base, archivo="no-existe.dump")
    assert codigo != 0 and "no existe" in salida
    assert vacias(destino, base)


def test_un_archivo_ilegible_se_rechaza_sin_tocar_la_base(destino, restaurador):
    base = destino.nueva_base_vacia()
    volumen = restaurador.cliente.volumes.create()
    try:
        montaje_rw = {volumen.name: {"bind": "/backups", "mode": "rw"}}
        codigo, salida = restaurador.correr(
            "echo basura > /backups/distribuidora-20260101-030000.dump",
            volumenes=montaje_rw,
        )
        assert codigo == 0, salida
        codigo, salida = restaurar_de(
            restaurador, {volumen.name: {"bind": "/backups", "mode": "ro"}}, base
        )
        assert codigo != 0 and "no es un backup valido" in salida
        assert vacias(destino, base)
    finally:
        volumen.remove(force=True)


def test_un_archivo_sin_las_tablas_de_libro_se_rechaza_sin_tocar_la_base(destino, restaurador):
    # D8: el archivo debe traer las cuatro tablas de libro; un backup de otra base no se restaura.
    with dump_de_otra_base(destino, restaurador, ["CREATE TABLE public.otra (id int)"]) as v:
        base = destino.nueva_base_vacia()
        codigo, salida = restaurar_de(restaurador, v, base)
        assert codigo != 0 and "cuenta_movimiento" in salida
        assert vacias(destino, base)


def test_un_archivo_que_falla_a_mitad_deja_la_base_sin_tablas(destino, restaurador):
    # Escenario «Un error a mitad deja la base vacia» (D8): una sola transaccion. El archivo trae
    # las cuatro tablas de libro y una tabla cuyo dueño no existe en el destino: las primeras
    # tablas se crean y el error llega despues, a mitad de la restauracion.
    destino.sql("postgres", "CREATE ROLE rol_fantasma")
    sentencias = [f"CREATE TABLE public.{t} (id int)" for t in LIBROS]
    sentencias += [
        "CREATE TABLE public.zeta_ajena (id int)",
        "INSERT INTO public.zeta_ajena VALUES (1)",
        "!ALTER TABLE public.zeta_ajena OWNER TO rol_fantasma",
    ]
    with dump_de_otra_base(
        destino, restaurador, sentencias, despues=["DROP ROLE rol_fantasma"]
    ) as v:
        base = destino.nueva_base_vacia()
        codigo, salida = restaurar_de(restaurador, v, base)
        assert codigo != 0, salida
        assert "rol_fantasma" in salida, salida
        assert vacias(destino, base)


def test_un_archivo_sin_version_de_migraciones_restaura_pero_falla_la_comprobacion(
    destino, restaurador
):
    # Triangulacion: un archivo valido (cuatro libros, sin dueño ajeno) se restaura, y la
    # comprobacion final exige la version de migraciones que este archivo de juguete no trae.
    sentencias = [f"CREATE TABLE public.{t} (id int)" for t in LIBROS]
    with dump_de_otra_base(destino, restaurador, sentencias) as v:
        base = destino.nueva_base_vacia()
        codigo, salida = restaurar_de(restaurador, v, base)
        assert codigo != 0 and "alembic_version" in salida, salida
        assert "Restaurando" in salida and "pg_restore: error" not in salida


# --- «La restauracion comprueba que los datos coinciden» ---------------------------------------


def comprobar(restaurador, respaldo, base, entorno_extra=None):
    entorno = {
        "PGHOST": ALIAS_DESTINO,
        "PGUSER": "app_migrations",
        "PGPASSWORD": CLAVE_MIGRACIONES,
        "PGDATABASE": base,
        "BACKUP_DIR": "/backups",
        **(entorno_extra or {}),
    }
    return restaurador.correr(
        f"{COMPRUEBA} {respaldo.nombre} 2>&1", entorno=entorno, volumenes=montaje(respaldo)
    )


def test_la_comprobacion_pasa_con_la_base_restaurada(
    restaurador, respaldo_de_origen, base_restaurada
):
    codigo, salida = comprobar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo == 0, salida
    assert "tablas" in salida and "filas" in salida


def test_una_tabla_con_menos_filas_hace_fallar_la_comprobacion_y_la_nombra(
    destino, restaurador, respaldo_de_origen, base_restaurada
):
    # Escenario «Una tabla no coincide» (D9): la tabla se nombra y no se muestran datos.
    destino.sql(base_restaurada, "DELETE FROM public.auditoria WHERE accion = 'PRUEBA-1'")
    codigo, salida = comprobar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo != 0
    assert "auditoria" in salida
    assert "PRUEBA-" not in salida and "Distribuidora de prueba" not in salida


def test_una_tabla_con_filas_de_mas_tambien_falla(
    destino, restaurador, respaldo_de_origen, base_restaurada
):
    # Triangulacion: la comparacion es de igualdad, no solo de faltantes.
    destino.sql(
        base_restaurada,
        "INSERT INTO public.auditoria (id, organizacion_id, accion, entidad, occurred_at, "
        "registered_at) SELECT gen_random_uuid(), id, 'EXTRA', 'cosa', now(), now() "
        "FROM public.organizacion",
    )
    codigo, salida = comprobar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo != 0 and "auditoria" in salida


def test_la_comprobacion_falla_si_app_runtime_puede_borrar_un_libro(
    destino, restaurador, respaldo_de_origen, base_restaurada
):
    # INV-05: la comprobacion mira los permisos, no solo las filas.
    destino.sql(base_restaurada, "GRANT DELETE ON public.cuenta_movimiento TO app_runtime")
    codigo, salida = comprobar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo != 0
    assert "cuenta_movimiento" in salida and "app_runtime" in salida


def test_la_comprobacion_falla_si_falta_la_version_de_migraciones(
    destino, restaurador, respaldo_de_origen, base_restaurada
):
    destino.sql(base_restaurada, "DELETE FROM public.alembic_version")
    codigo, salida = comprobar(restaurador, respaldo_de_origen, base_restaurada)
    assert codigo != 0 and "alembic_version" in salida, salida
