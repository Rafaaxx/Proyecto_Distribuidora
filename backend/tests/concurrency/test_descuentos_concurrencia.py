"""Change 16, tarea 16.1: concurrencia real de `descuentos` y del tope por rol contra PostgreSQL
real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el mismo arnés que
`test_precios_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su propia
transacción (el bus lo hace en `procesar_comando`) y arranca junto a los otros en una
`threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4); los datos confirmados se
limpian al final. Una falla intermitente no se ignora.

`design.md` D15, D16: toda escritura sobre una regla toma primero el candado de su fila
(`SELECT ... FOR UPDATE`) y revalida el estado antes de escribir; el tope de un rol toma el
candado de la fila del rol (D13).

Escenarios (specs `descuentos/reglas-de-descuento` e `identidad/usuarios-y-roles`):

- dos `REGLA_DESCUENTO_PAUSAR` simultáneos con distinto `Operation-Id`: uno aceptado y otro
  `REGLA_ESTADO_INVALIDO` (`01` §18, DSC-01);
- activar y modificar el mismo borrador a la vez: o la modificación entra antes de activar, o se
  rechaza con `REGLA_NO_ES_BORRADOR`; nunca una regla activa con datos a medio cambiar (D15,
  TR-06);
- el mismo `Operation-Id` de alta en paralelo deja una sola regla (INV-06, SYN-02);
- dos `ROL_TOPE_DESCUENTO_DEFINIR` simultáneos sobre el mismo rol dejan dos filas de auditoría
  cuyo "anterior" y "nuevo" encadenan (AUD-02, D13).
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.descuentos import commands as _descuentos_commands  # noqa: F401 (registra)
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria
from tests.integration.precios_utiles import MOMENTO
from tests.integration.precios_utiles import Entorno as EntornoDePrecios

ESPERA_MAXIMA = 60
REPETICIONES = 8

CREAR = "REGLA_DESCUENTO_CREAR"
MODIFICAR = "REGLA_DESCUENTO_MODIFICAR"
ACTIVAR = "REGLA_DESCUENTO_ACTIVAR"
PAUSAR = "REGLA_DESCUENTO_PAUSAR"
DEFINIR_TOPE = "ROL_TOPE_DESCUENTO_DEFINIR"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones: simula un worker de
    FastAPI distinto (`02` §16.2)."""
    return crear_session_factory(crear_engine(database_url))()


def _regla(**cambios: Any) -> dict[str, Any]:
    """El contenido de `REGLA_DESCUENTO_CREAR` de "cajas equivalentes >= 20 -> 5 %", sobre toda
    la venta; `cambios` pisa cualquier campo."""
    contenido: dict[str, Any] = {
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": "20",
        "accion_tipo": "PORCENTAJE",
        "accion_valor": "0.050000",
        "prioridad": 1,
        "acumulable": False,
        "alcances": [],
    }
    contenido.update(cambios)
    return contenido


class _Entorno(EntornoDePrecios):
    """Una organización con un usuario que tiene `GESTIONAR_DESCUENTOS` y `ADMIN_USUARIOS`."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, permisos=frozenset({"GESTIONAR_DESCUENTOS", "ADMIN_USUARIOS"}))

    def crear_regla(self, **cambios: Any) -> UUID:
        comando = self.enviar(CREAR, _regla(**cambios))
        assert comando.resultado is not None
        return UUID(str(comando.resultado["regla_id"]))

    def activar(self, regla_id: UUID) -> Any:
        return self.enviar(ACTIVAR, {"regla_id": str(regla_id)})

    def pausar(self, regla_id: UUID) -> Any:
        return self.enviar(PAUSAR, {"regla_id": str(regla_id)})

    def modificar(self, regla_id: UUID, **campos: Any) -> Any:
        return self.enviar(MODIFICAR, {"regla_id": str(regla_id), **campos})

    def crear_rol(self, nombre: str, tope: str = "0.000000") -> UUID:
        rol = identidad_repository.crear_rol(
            self.org,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=nombre,
            tope_descuento=Decimal(tope),
            activo=True,
            momento=MOMENTO,
        )
        return rol.id

    def definir_tope(self, rol_id: UUID, tope: str) -> Any:
        return self.enviar(DEFINIR_TOPE, {"rol_id": str(rol_id), "tope_descuento": tope})


class _Escenario:
    """Una organización confirmada sobre la que cada hilo trabaja con su propia sesión."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.base = _Entorno(sesion)
            self.org = self.base.org
            self.marca_id = self.base.marca_id
            self.categoria_id = self.base.categoria_id
            sesion.commit()
        finally:
            sesion.close()
        self._contador = 0

    def nombre_nuevo(self, prefijo: str = "Regla") -> str:
        self._contador += 1
        return f"{prefijo} {self._contador}"

    def entorno(self, sesion: Session) -> _Entorno:
        """El entorno de la organización atado a la sesión de un hilo."""
        entorno = copy.copy(self.base)
        entorno.sesion = sesion
        return entorno

    def preparar(self, trabajo: Callable[[_Entorno], object]) -> object:
        """Corre `trabajo` en su propia sesión, confirmando lo que haya dejado, y devuelve su
        resultado."""
        sesion = _sesion_independiente(self.database_url)
        try:
            resultado = trabajo(self.entorno(sesion))
            sesion.commit()
            return resultado
        finally:
            sesion.close()

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def regla(self, regla_id: UUID) -> tuple[str, str, Decimal, Decimal, int]:
        """`(estado, nombre, umbral, accion_porcentaje, prioridad)` de una regla."""
        ((estado, nombre, umbral, porcentaje, prioridad),) = self.leer(
            "SELECT estado, nombre, umbral, accion_porcentaje, prioridad "
            "FROM regla_descuento WHERE organizacion_id = :o AND id = :r",
            r=regla_id,
        )
        assert isinstance(estado, str) and isinstance(nombre, str) and isinstance(prioridad, int)
        assert isinstance(umbral, Decimal) and isinstance(porcentaje, Decimal)
        return estado, nombre, umbral, porcentaje, prioridad

    def alcances(self, regla_id: UUID) -> list[tuple[str, UUID]]:
        filas = self.leer(
            "SELECT alcance_tipo, alcance_id FROM regla_descuento_alcance "
            "WHERE organizacion_id = :o AND regla_id = :r ORDER BY alcance_tipo, alcance_id",
            r=regla_id,
        )
        return [(str(tipo), UUID(str(entidad))) for tipo, entidad in filas]

    def auditorias_del_tope(self, rol_id: UUID) -> list[Auditoria]:
        sesion = _sesion_independiente(self.database_url)
        try:
            return list(
                sesion.scalars(
                    select(Auditoria).where(
                        Auditoria.organizacion_id == self.org,
                        Auditoria.accion == DEFINIR_TOPE,
                        Auditoria.entidad == "rol",
                        Auditoria.entidad_id == rol_id,
                    )
                )
            )
        finally:
            sesion.close()

    def cantidad_de_auditorias(self, accion: str) -> int:
        ((cantidad,),) = self.leer(
            "SELECT count(*) FROM auditoria WHERE organizacion_id = :o AND accion = :a", a=accion
        )
        assert isinstance(cantidad, int)
        return cantidad

    def tope_de(self, rol_id: UUID) -> Decimal:
        ((tope,),) = self.leer(
            "SELECT tope_descuento FROM rol WHERE organizacion_id = :o AND id = :r", r=rol_id
        )
        assert isinstance(tope, Decimal)
        return tope


def _en_paralelo(
    escenario: _Escenario, trabajos: list[Callable[[_Entorno], object]]
) -> tuple[list[str], list[object]]:
    """Corre cada trabajo en su hilo y su sesión, todos arrancando juntos. Devuelve, por trabajo,
    `"OK"` o el código del error de dominio (o el nombre de la excepción), y su resultado."""
    barrera = threading.Barrier(len(trabajos))
    veredictos: list[str] = ["NO_CORRIO"] * len(trabajos)
    resultados: list[object] = [None] * len(trabajos)

    def _hilo(indice: int) -> None:
        sesion = _sesion_independiente(escenario.database_url)
        try:
            entorno = escenario.entorno(sesion)
            barrera.wait(timeout=10)
            resultados[indice] = trabajos[indice](entorno)
            veredictos[indice] = "OK"
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            veredictos[indice] = str(getattr(error, "codigo", type(error).__name__))
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_hilo, args=(i,)) for i in range(len(trabajos))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA)
    assert not any(hilo.is_alive() for hilo in hilos), (
        "Un hilo quedó colgado (posible interbloqueo)."
    )
    return veredictos, resultados


class TestDosPausasSimultaneas:
    """`01` §18, DSC-01, `design.md` D15: dos `REGLA_DESCUENTO_PAUSAR` simultáneos de una regla
    activa, con distinto `Operation-Id`, se serializan con el candado de la regla: uno la pausa y
    el otro la encuentra ya pausada."""

    def test_uno_aceptado_y_otro_con_regla_estado_invalido(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        for _ in range(REPETICIONES):
            regla_id = escenario.preparar(
                lambda entorno: _activa(entorno, escenario.nombre_nuevo())
            )
            assert isinstance(regla_id, UUID)
            pausas_antes = escenario.cantidad_de_auditorias(PAUSAR)

            veredictos, _ = _en_paralelo(
                escenario,
                [lambda entorno, regla_id=regla_id: entorno.pausar(regla_id) for _ in range(2)],
            )

            assert sorted(veredictos) == ["OK", "REGLA_ESTADO_INVALIDO"], veredictos
            assert escenario.regla(regla_id)[0] == "PAUSADA"
            # El aceptado deja su auditoría; el rechazado, ninguna (AUD-02).
            assert escenario.cantidad_de_auditorias(PAUSAR) - pausas_antes == 1


def _activa(entorno: _Entorno, nombre: str) -> UUID:
    regla_id = entorno.crear_regla(nombre=nombre)
    entorno.activar(regla_id)
    return regla_id


class TestActivarContraModificar:
    """D15, TR-06: activar y modificar el mismo borrador a la vez. Hay dos órdenes y los dos son
    correctos: la modificación entra antes y la regla se activa con TODOS los datos nuevos, o
    llega después y se rechaza con `REGLA_NO_ES_BORRADOR` (la regla queda activa con TODOS los
    datos viejos). Lo que no puede pasar es una regla activa con datos a medio cambiar."""

    def test_nunca_una_regla_activa_con_datos_a_medio_cambiar(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        viejos = ("Vieja", Decimal("20.0000"), Decimal("0.050000"), 1)
        nuevos = ("Nueva", Decimal("40.0000"), Decimal("0.100000"), 7)
        modificaciones_aceptadas = 0

        for _ in range(REPETICIONES):
            regla_id = escenario.preparar(
                lambda entorno: entorno.crear_regla(
                    nombre="Vieja",
                    tipo="VOLUMEN_ALCANCE",
                    alcances=[{"tipo": "MARCA", "entidad_id": str(escenario.marca_id)}],
                )
            )
            assert isinstance(regla_id, UUID)

            veredictos, _ = _en_paralelo(
                escenario,
                [
                    lambda entorno, regla_id=regla_id: entorno.activar(regla_id),
                    lambda entorno, regla_id=regla_id: entorno.modificar(
                        regla_id,
                        nombre="Nueva",
                        tipo="VOLUMEN_ALCANCE",
                        medida="CAJAS_EQUIVALENTES",
                        operador="GTE",
                        umbral="40",
                        accion_tipo="PORCENTAJE",
                        accion_valor="0.100000",
                        prioridad=7,
                        acumulable=False,
                        alcances=[{"tipo": "CATEGORIA", "entidad_id": str(escenario.categoria_id)}],
                    ),
                ],
            )

            estado, nombre, umbral, porcentaje, prioridad = escenario.regla(regla_id)
            assert veredictos[0] == "OK", veredictos
            assert estado == "ACTIVA"
            datos = (nombre, umbral, porcentaje, prioridad)
            alcances = escenario.alcances(regla_id)
            if veredictos[1] == "OK":
                modificaciones_aceptadas += 1
                assert datos == nuevos, f"Datos a medio cambiar: {datos}"
                assert alcances == [("CATEGORIA", escenario.categoria_id)]
            else:
                assert veredictos[1] == "REGLA_NO_ES_BORRADOR", veredictos
                assert datos == viejos, f"Datos a medio cambiar: {datos}"
                assert alcances == [("MARCA", escenario.marca_id)]
        # Las dos entradas de la carrera son válidas; esto solo deja constancia de cuál ocurrió.
        assert 0 <= modificaciones_aceptadas <= REPETICIONES


class TestMismoOperationIdEnParalelo:
    """INV-06, SYN-02: envíos simultáneos del MISMO alta con el mismo `Operation-Id` tienen un
    solo efecto; todos informan la misma regla."""

    def test_una_sola_regla(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)

        for _ in range(REPETICIONES):
            operation_id = uuid4()
            nombre = escenario.nombre_nuevo("Alta")
            altas_antes = escenario.cantidad_de_auditorias(CREAR)

            veredictos, resultados = _en_paralelo(
                escenario,
                [
                    lambda entorno, nombre=nombre, operation_id=operation_id: entorno.enviar(
                        CREAR, _regla(nombre=nombre), operation_id=operation_id
                    )
                    for _ in range(3)
                ],
            )

            assert veredictos == ["OK", "OK", "OK"], veredictos
            informadas = {str(comando.resultado["regla_id"]) for comando in resultados}  # type: ignore[attr-defined,union-attr]
            assert len(informadas) == 1
            ((reglas,),) = escenario.leer(
                "SELECT count(*) FROM regla_descuento WHERE organizacion_id = :o AND nombre = :n",
                n=nombre,
            )
            assert reglas == 1
            ((comandos,),) = escenario.leer(
                "SELECT count(*) FROM comando WHERE organizacion_id = :o AND operation_id = :op",
                op=operation_id,
            )
            assert comandos == 1
            assert escenario.cantidad_de_auditorias(CREAR) - altas_antes == 1


class TestDosTopesSimultaneosSobreElMismoRol:
    """AUD-02, `design.md` D13: dos `ROL_TOPE_DESCUENTO_DEFINIR` simultáneos sobre el mismo rol se
    serializan con el candado del rol. Quedan dos filas de auditoría cuyo "anterior" y "nuevo"
    encadenan (el nuevo de la primera es el anterior de la segunda) y el rol queda con el último."""

    def test_el_anterior_y_el_nuevo_encadenan(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)

        for _ in range(REPETICIONES):
            rol_id = escenario.preparar(
                lambda entorno: entorno.crear_rol(escenario.nombre_nuevo("Rol"), "0.000000")
            )
            assert isinstance(rol_id, UUID)

            veredictos, _ = _en_paralelo(
                escenario,
                [
                    lambda entorno, rol_id=rol_id: entorno.definir_tope(rol_id, "0.050000"),
                    lambda entorno, rol_id=rol_id: entorno.definir_tope(rol_id, "0.100000"),
                ],
            )

            assert veredictos == ["OK", "OK"], veredictos
            auditorias = escenario.auditorias_del_tope(rol_id)
            assert len(auditorias) == 2
            por_anterior = {a.antes["tope_descuento"]: a for a in auditorias if a.antes}
            assert len(por_anterior) == 2, "Dos auditorías con el mismo valor anterior"
            primera = por_anterior["0.000000"]
            segunda = por_anterior[primera.despues["tope_descuento"]]  # type: ignore[index]
            assert segunda is not primera
            assert {primera.despues["tope_descuento"], segunda.despues["tope_descuento"]} == {  # type: ignore[index]
                "0.050000",
                "0.100000",
            }
            assert escenario.tope_de(rol_id) == Decimal(segunda.despues["tope_descuento"])  # type: ignore[index]
