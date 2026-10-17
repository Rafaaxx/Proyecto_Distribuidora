"""Change 17b, tarea 12.1: concurrencia real de los medios de pago administrables y de la
protección del último administrador, contra PostgreSQL real (Testcontainers, `READ COMMITTED`,
`docs/02-arquitectura.md` §7.1). Mismo arnés que `test_condicion_iva_concurrencia.py`: cada
hilo tiene su propia conexión/sesión, confirma su propia transacción por el bus
(`sync_service.procesar_comando`) y arranca junto a los otros en una `threading.Barrier`. Nunca
hay rollback externo (`CLAUDE.md` §4).

Escenarios (`design.md` D4, D8, ADR-053):

- dos bajas simultáneas de los dos últimos medios activos: una sola se acepta y queda uno
  activo (`ULTIMO_MEDIO_ACTIVO`, INV-01);
- dos `ROL_PERMISOS_CAMBIAR` simultáneos que quitan `ADMIN_USUARIOS` a los dos únicos roles que
  lo tienen: uno solo se acepta (`IDENTIDAD_SIN_ADMINISTRADOR`, INV-01);
- el mismo cambio de permisos sobre UN solo rol, hecho por dos peticiones a la vez, no deja a la
  organización sin administrador aunque cada una haya leído los permisos actuales antes del
  bloqueo (la lectura vieja nunca hace que se salte la validación ni que se quite de más);
- dos altas simultáneas de "Mercado Pago": una `NOMBRE_DUPLICADO` (INV-02);
- doble envío simultáneo del mismo comando con el mismo `operation_id`: una sola fila (INV-06).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.core.errors import DomainError
from app.core.ids import nuevo_id
from app.modules.configuracion import commands as _configuracion_commands  # noqa: F401
from app.modules.identidad import commands as _identidad_commands  # noqa: F401
from app.modules.identidad import repository as identidad_repository
from app.modules.sync import service as sync_service
from tests.concurrency.test_compras_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _sesion_independiente,
)
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)

ADMIN_USUARIOS = "ADMIN_USUARIOS"
RONDAS = 3


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Escenario:
    """Una organización confirmada con un administrador de medios (`ADMIN_CONFIGURACION`) y
    un administrador de usuarios (`ADMIN_USUARIOS`)."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.admin_id, self.admin_dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"ADMIN_CONFIGURACION", ADMIN_USUARIOS})
            )
            sesion.commit()
        finally:
            sesion.close()

    # --- armado de datos (cada pieza confirma) ----------------------------------------

    def crear_medio(self, nombre: str, *, activo: bool = True) -> UUID:
        medio_id = uuid4()
        sesion = _sesion_independiente(self.database_url)
        try:
            sesion.execute(
                text(
                    "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                    "activo, creado_en, actualizado_en) "
                    "VALUES (:id, :o, :n, false, :a, :m, :m)"
                ),
                {"id": medio_id, "o": self.org, "n": nombre, "a": activo, "m": MOMENTO},
            )
            sesion.commit()
        finally:
            sesion.close()
        return medio_id

    def crear_rol_con_usuario(self, nombre: str, permisos: frozenset[str]) -> UUID:
        """Un rol activo con los permisos dados y un usuario activo. Devuelve el id del rol."""
        sesion = _sesion_independiente(self.database_url)
        try:
            rol = identidad_repository.crear_rol(
                self.org,
                sesion,
                rol_id=nuevo_id(),
                nombre=nombre,
                tope_descuento=Decimal("0"),
                activo=True,
                momento=MOMENTO,
            )
            for codigo in sorted(permisos):
                identidad_repository.asignar_permiso_a_rol(
                    self.org, sesion, rol_id=rol.id, permiso_codigo=codigo
                )
            identidad_repository.crear_usuario(
                self.org,
                sesion,
                usuario_id=nuevo_id(),
                usuario=f"u-{uuid4().hex[:8]}",
                nombre="Persona de prueba",
                email=None,
                password_hash="hash",
                rol_id=rol.id,
                estado="ACTIVO",
                momento=MOMENTO,
            )
            sesion.commit()
            return rol.id
        finally:
            sesion.close()

    # --- comandos por el bus ----------------------------------------------------------

    def enviar(
        self,
        sesion: Session,
        tipo: str,
        contenido: dict[str, Any],
        operation_id: UUID | None = None,
    ) -> Any:
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(
                sobre,
                validado,
                sesion=sesion_protegida,  # type: ignore[arg-type]
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def baja_de_medio(self, sesion: Session, medio_id: UUID, nombre: str) -> Any:
        return self.enviar(
            sesion,
            "MEDIO_PAGO_MODIFICAR",
            {
                "medio_pago_id": str(medio_id),
                "nombre": nombre,
                "requiere_referencia": False,
                "activo": False,
            },
        )

    def alta_de_medio(self, sesion: Session, nombre: str, operation_id: UUID | None = None) -> Any:
        return self.enviar(
            sesion,
            "MEDIO_PAGO_CREAR",
            {"nombre": nombre, "requiere_referencia": True},
            operation_id,
        )

    def cambiar_permisos(self, sesion: Session, rol_id: UUID, permisos: list[str]) -> Any:
        return self.enviar(
            sesion, "ROL_PERMISOS_CAMBIAR", {"rol_id": str(rol_id), "permisos": permisos}
        )

    # --- lecturas confirmadas ---------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def medios_activos(self) -> int:
        ((cantidad,),) = self.leer(
            "SELECT count(*) FROM medio_pago WHERE organizacion_id = :o AND activo"
        )
        assert isinstance(cantidad, int)
        return cantidad

    def medios_con_nombre(self, nombre: str) -> int:
        ((cantidad,),) = self.leer(
            "SELECT count(*) FROM medio_pago WHERE organizacion_id = :o "
            "AND lower(nombre) = lower(:n)",
            n=nombre,
        )
        assert isinstance(cantidad, int)
        return cantidad

    def roles_con_permiso(self, codigo: str) -> int:
        ((cantidad,),) = self.leer(
            "SELECT count(*) FROM rol_permiso WHERE organizacion_id = :o AND permiso_codigo = :c",
            c=codigo,
        )
        assert isinstance(cantidad, int)
        return cantidad

    def auditorias(self, accion: str, entidad: str) -> int:
        ((cantidad,),) = self.leer(
            "SELECT count(*) FROM auditoria WHERE organizacion_id = :o "
            "AND accion = :a AND entidad = :e",
            a=accion,
            e=entidad,
        )
        assert isinstance(cantidad, int)
        return cantidad


def _codigos(errores: dict[int, BaseException]) -> list[str]:
    assert all(isinstance(error, DomainError) for error in errores.values()), errores
    return sorted(error.codigo for error in errores.values() if isinstance(error, DomainError))


class TestDosBajasDeLosDosUltimosMediosActivos:
    """INV-01, ADR-053, D4: `MEDIO_PAGO_MODIFICAR` bloquea los medios de la organización
    (`FOR UPDATE`) antes de contar los activos: dos bajas simultáneas no dejan cero."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_una_sola_se_acepta_y_queda_un_medio_activo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        efectivo = escenario.crear_medio("Efectivo")
        billetera = escenario.crear_medio("Billetera")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_medio(sesion, efectivo, "Efectivo"),
            lambda sesion: escenario.baja_de_medio(sesion, billetera, "Billetera"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert next(iter(resultados.values())).estado == "ACEPTADO"
        assert _codigos(errores) == ["ULTIMO_MEDIO_ACTIVO"]
        assert escenario.medios_activos() == 1
        assert escenario.auditorias("MEDIO_PAGO_MODIFICAR", "medio_pago") == 1

    def test_con_tres_activos_las_dos_bajas_se_aceptan(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el bloqueo no rechaza de más cuando sobran medios."""
        escenario = _Escenario(database_url)
        efectivo = escenario.crear_medio("Efectivo")
        billetera = escenario.crear_medio("Billetera")
        escenario.crear_medio("Cheque")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_medio(sesion, efectivo, "Efectivo"),
            lambda sesion: escenario.baja_de_medio(sesion, billetera, "Billetera"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2
        assert escenario.medios_activos() == 1


class TestDosCambiosQueQuitanAdminUsuariosASusUnicosRoles:
    """INV-01, ADR-053, D8: `ROL_PERMISOS_CAMBIAR` bloquea la configuración de la organización
    antes de contar los administradores: dos cambios simultáneos sobre roles distintos se
    serializan y el segundo ve el rol del primero ya sin el permiso."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_uno_solo_se_acepta_y_queda_un_rol_administrador(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        # El administrador de la organización (`ADMIN_USUARIOS`) ya es un tercer rol: se lo
        # quita de partida para que los dos roles de la prueba sean los únicos.
        sesion = _sesion_independiente(database_url)
        try:
            sesion.execute(
                text("DELETE FROM rol_permiso WHERE organizacion_id = :o AND permiso_codigo = :c"),
                {"o": escenario.org, "c": ADMIN_USUARIOS},
            )
            sesion.commit()
        finally:
            sesion.close()
        rol_a = escenario.crear_rol_con_usuario("Rol A", frozenset({ADMIN_USUARIOS}))
        rol_b = escenario.crear_rol_con_usuario("Rol B", frozenset({ADMIN_USUARIOS}))
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.cambiar_permisos(sesion, rol_a, []),
            lambda sesion: escenario.cambiar_permisos(sesion, rol_b, []),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert next(iter(resultados.values())).estado == "ACEPTADO"
        assert _codigos(errores) == ["IDENTIDAD_SIN_ADMINISTRADOR"]
        assert escenario.roles_con_permiso(ADMIN_USUARIOS) == 1

    def test_con_un_tercer_rol_administrador_los_dos_cambios_se_aceptan(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el administrador de la organización conserva el permiso, así que el
        bloqueo no rechaza de más."""
        escenario = _Escenario(database_url)
        rol_a = escenario.crear_rol_con_usuario("Rol A", frozenset({ADMIN_USUARIOS}))
        rol_b = escenario.crear_rol_con_usuario("Rol B", frozenset({ADMIN_USUARIOS}))
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.cambiar_permisos(sesion, rol_a, []),
            lambda sesion: escenario.cambiar_permisos(sesion, rol_b, []),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2
        assert escenario.roles_con_permiso(ADMIN_USUARIOS) == 1


class TestDosCambiosSimultaneosSobreElMismoRol:
    """`permisos_actuales` del rol editado se lee ANTES del bloqueo de la configuración. Cuando
    otra petición lo cambia en el medio, la lectura vieja nunca deja a la organización sin
    administrador: solo se quita lo que la lectura vieja decía que había, y el permiso
    `ADMIN_USUARIOS` se valida siempre que la lectura vieja lo incluía."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_dos_cambios_que_lo_quitan_del_unico_rol_aceptan_uno_solo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            sesion.execute(
                text("DELETE FROM rol_permiso WHERE organizacion_id = :o AND permiso_codigo = :c"),
                {"o": escenario.org, "c": ADMIN_USUARIOS},
            )
            sesion.commit()
        finally:
            sesion.close()
        rol = escenario.crear_rol_con_usuario("Único", frozenset({ADMIN_USUARIOS, "VER_REPORTES"}))
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.cambiar_permisos(sesion, rol, ["VER_REPORTES"]),
            lambda sesion: escenario.cambiar_permisos(sesion, rol, []),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        # El primero en tomar el bloqueo quita el permiso al único rol: se rechaza. El segundo,
        # que leyó el permiso antes, tampoco puede quitarlo. Ninguno lo logra.
        assert not resultados, f"{resultados}, errores={errores}"
        assert _codigos(errores) == ["IDENTIDAD_SIN_ADMINISTRADOR", "IDENTIDAD_SIN_ADMINISTRADOR"]
        assert escenario.roles_con_permiso(ADMIN_USUARIOS) == 1

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_un_cambio_que_lo_conserva_y_otro_que_lo_quita_no_dejan_la_organizacion_sin_admin(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            sesion.execute(
                text("DELETE FROM rol_permiso WHERE organizacion_id = :o AND permiso_codigo = :c"),
                {"o": escenario.org, "c": ADMIN_USUARIOS},
            )
            sesion.commit()
        finally:
            sesion.close()
        rol = escenario.crear_rol_con_usuario("Único", frozenset({ADMIN_USUARIOS}))
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.cambiar_permisos(
                sesion, rol, [ADMIN_USUARIOS, "VER_REPORTES"]
            ),
            lambda sesion: escenario.cambiar_permisos(sesion, rol, []),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert _codigos(errores) == ["IDENTIDAD_SIN_ADMINISTRADOR"]
        assert len(resultados) == 1
        assert escenario.roles_con_permiso(ADMIN_USUARIOS) == 1


class TestDosAltasSimultaneasDelMismoNombre:
    """INV-02, D3: el índice único `(organizacion_id, lower(nombre))` decide; el perdedor
    espera al ganador y responde `NOMBRE_DUPLICADO`."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_una_se_acepta_y_la_otra_es_duplicada(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_medio(sesion, "Mercado Pago"),
            lambda sesion: escenario.alta_de_medio(sesion, "mercado pago"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _codigos(errores) == ["NOMBRE_DUPLICADO"]
        assert escenario.medios_con_nombre("Mercado Pago") == 1
        assert escenario.auditorias("MEDIO_PAGO_CREAR", "medio_pago") == 1

    def test_nombres_distintos_se_aceptan_los_dos(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el índice no rechaza nombres distintos."""
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_medio(sesion, "Mercado Pago"),
            lambda sesion: escenario.alta_de_medio(sesion, "Cuenta DNI"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2


class TestDobleEnvioSimultaneoDelMismoComando:
    """INV-06: dos envíos del mismo `operation_id` a la vez producen un solo efecto."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_el_alta_queda_una_sola_vez(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_medio(sesion, "Mercado Pago", operation_id),
            lambda sesion: escenario.alta_de_medio(sesion, "Mercado Pago", operation_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert {c.estado for c in resultados.values()} == {"ACEPTADO"}
        assert escenario.medios_con_nombre("Mercado Pago") == 1
        assert escenario.auditorias("MEDIO_PAGO_CREAR", "medio_pago") == 1
