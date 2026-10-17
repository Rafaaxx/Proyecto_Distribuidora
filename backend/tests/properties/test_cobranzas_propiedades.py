"""INV-08 e INV-13 después de cobranzas, anulaciones y saldos iniciales, contra PostgreSQL real y
con Hypothesis (change 17, tarea 16.2).

INV-08 (`docs/01` §20, COB-02): la suma de los medios de cada cobranza es igual a su importe,
también la de las aceptadas sin conexión (con un medio desactivado o sin la referencia que
exigen, que se aceptan con observación, D13) y la de las anuladas (la anulación no altera ni los
medios ni el importe). INV-13 (CC-04): el saldo de la cuenta del cliente es la suma de sus
movimientos, para secuencias arbitrarias de saldos iniciales, cobranzas y anulaciones. Ambas se
comprueban con SQL sobre la base, no con las estructuras en memoria de la prueba. Además, anular
una cobranza sin movimientos intermedios deja el saldo como estaba antes de cobrarla (CC-04).

Cada ejemplo crea su propia organización (todo se filtra por `organizacion_id`) dentro de la
transacción de `db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT` por
ejemplo porque el bus confirma la transacción del comando. Es una prueba de las invariantes, no de
concurrencia (esa confirma transacciones reales,
`tests/concurrency/test_cobranzas_concurrencia.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.cobranzas import commands as cobranzas_commands
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.sync import service as sync_service
from tests.integration.cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import crear_jornada_sql, crear_ubicacion_sql

MOMENTO = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
PERMISOS = frozenset({"REGISTRAR_COBRANZA", "ANULAR_COBRANZA"})
_MANEJADORES = {
    "COBRANZA_REGISTRAR": cobranzas_commands.manejar_cobranza_registrar,
    "COBRANZA_ANULAR": cobranzas_commands.manejar_cobranza_anular,
}

# Un medio de una cobranza: `(clase, centavos)`. Clases: 0 efectivo, 1 transferencia (exige
# referencia), 2 medio desactivado (solo sin conexión: con conexión se rechaza).
type MedioDeCobro = tuple[int, int]
type Cobro = list[MedioDeCobro]

_MEDIO = st.tuples(st.integers(min_value=0, max_value=1), st.integers(1, 300_000_000))
_MEDIO_OFFLINE = st.tuples(st.integers(min_value=0, max_value=2), st.integers(1, 300_000_000))
_COBRO = st.lists(_MEDIO, min_size=1, max_size=3)
_COBRO_OFFLINE = st.lists(_MEDIO_OFFLINE, min_size=1, max_size=3)
_SALDO_INICIAL = st.integers(min_value=1, max_value=900_000_000)
# Una operación: saldo inicial (solo entra mientras no haya otros movimientos), cobranza con
# conexión, cobranza sin conexión (con o sin la referencia que el medio exige) o anulación. El
# entero de la anulación elige entre las cobranzas vigentes (módulo).
_OPERACION = st.one_of(
    st.tuples(st.just("saldo_inicial"), _SALDO_INICIAL),
    st.tuples(st.just("cobrar"), _COBRO),
    st.tuples(st.just("cobrar_offline"), st.tuples(_COBRO_OFFLINE, st.booleans())),
    st.tuples(st.just("anular"), st.integers(min_value=0, max_value=50)),
)
_OPERACIONES = st.lists(_OPERACION, min_size=1, max_size=10)

_PROPIEDAD = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _importe(centavos: int) -> str:
    return str(Decimal(centavos).scaleb(-2))


class _Mundo:
    """Una organización con `Kiosco La Esquina`, tres medios (efectivo, transferencia con
    referencia obligatoria y uno desactivado), el motivo de anulación, un usuario con los permisos
    de cobranza y su jornada `ABIERTA`, creada dentro de la transacción del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=PERMISOS
        )
        self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
        self.efectivo_id = self._medio("Efectivo", requiere_referencia=False, activo=True)
        self.transferencia_id = self._medio("Transferencia", requiere_referencia=True, activo=True)
        self.inactivo_id = self._medio("Cheque", requiere_referencia=False, activo=False)
        self.motivo_id = self._motivo()
        self.jornada_id = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            ubicacion_id=crear_ubicacion_sql(sesion, self.org, requiere_toma=True),
        )
        self.vigentes: list[UUID] = []
        self.hay_otros_movimientos = False

    def _medio(self, nombre: str, *, requiere_referencia: bool, activo: bool) -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) VALUES (:id, :org, :nombre, :ref, :activo, "
                ":m, :m)"
            ),
            {
                "id": medio_id,
                "org": self.org,
                "nombre": nombre,
                "ref": requiere_referencia,
                "activo": activo,
                "m": MOMENTO,
            },
        )
        return medio_id

    def _motivo(self) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'ANULACION_COBRANZA', 'Error de carga', "
                "true, :m, :m)"
            ),
            {"id": motivo_id, "org": self.org, "m": MOMENTO},
        )
        return motivo_id

    def _enviar(
        self,
        tipo: str,
        contenido: dict[str, Any],
        *,
        modo: str = "ONLINE",
        jornada_id: UUID | None = None,
    ) -> Any:
        sobre = SobreComando(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,  # type: ignore[arg-type]
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=jornada_id,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)
        manejador = _MANEJADORES[tipo]

        def _ejecutar(sesion_protegida: object) -> Any:
            return manejador(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            self.sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def _medios(self, cobro: Cobro, *, con_referencia: bool = True) -> list[dict[str, Any]]:
        medios: list[dict[str, Any]] = []
        for indice, (clase, centavos) in enumerate(cobro):
            medio_id = (self.efectivo_id, self.transferencia_id, self.inactivo_id)[clase]
            referencia = f"REF-{indice}" if clase == 1 and con_referencia else None
            medios.append(
                {
                    "medio_pago_id": str(medio_id),
                    "importe": _importe(centavos),
                    "referencia": referencia,
                }
            )
        return medios

    # --- operaciones -----------------------------------------------------------------

    def saldo_inicial(self, centavos: int) -> None:
        if self.hay_otros_movimientos:
            return  # CC-08: ya no entra; se omite para que la secuencia siga siendo válida.
        cuentas_service.registrar_saldo_inicial(
            self.org,
            self.sesion,
            RELOJ,
            cuenta_tipo="CLIENTE",
            entidad_id=self.cliente_id,
            importe=_importe(centavos),
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )

    def cobrar(self, cobro: Cobro) -> UUID:
        cobranza_id = uuid4()
        self._enviar(
            "COBRANZA_REGISTRAR",
            {
                "cobranza_id": str(cobranza_id),
                "cliente_id": str(self.cliente_id),
                "importe": _importe(sum(centavos for _, centavos in cobro)),
                "medios": self._medios(cobro),
            },
        )
        self.vigentes.append(cobranza_id)
        self.hay_otros_movimientos = True
        return cobranza_id

    def cobrar_offline(self, cobro: Cobro, con_referencia: bool) -> UUID:
        cobranza_id = uuid4()
        self._enviar(
            "COBRANZA_REGISTRAR",
            {
                "cobranza_id": str(cobranza_id),
                "cliente_id": str(self.cliente_id),
                "importe": _importe(sum(centavos for _, centavos in cobro)),
                "medios": self._medios(cobro, con_referencia=con_referencia),
            },
            modo="OFFLINE",
            jornada_id=self.jornada_id,
        )
        self.vigentes.append(cobranza_id)
        self.hay_otros_movimientos = True
        return cobranza_id

    def anular(self, indice: int) -> None:
        if not self.vigentes:
            return
        self.anular_esta(self.vigentes.pop(indice % len(self.vigentes)))

    def anular_esta(self, cobranza_id: UUID) -> None:
        self._enviar(
            "COBRANZA_ANULAR",
            {"cobranza_id": str(cobranza_id), "motivo_id": str(self.motivo_id)},
        )

    # --- invariantes, comprobadas con SQL ----------------------------------------------

    def verificar_inv08(self) -> None:
        """Cada cobranza, vigente o anulada, tiene medios que suman exactamente su importe."""
        desparejas = self.sesion.execute(
            text(
                "SELECT c.id FROM cobranza c WHERE c.organizacion_id = :o AND c.importe "
                "<> (SELECT COALESCE(SUM(m.importe), 0) FROM cobranza_medio m "
                "WHERE m.organizacion_id = c.organizacion_id AND m.cobranza_id = c.id)"
            ),
            {"o": self.org},
        ).all()
        assert desparejas == []

    def verificar_libro_de_cobranzas(self) -> None:
        """Una `COBRANZA` por cada cobranza y una `ANULACION_COBRANZA` por cada anulada."""
        ((cobranzas, anuladas),) = self.sesion.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE estado = 'ANULADA') "
                "FROM cobranza WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        ((movimientos_cobranza, movimientos_anulacion),) = self.sesion.execute(
            text(
                "SELECT count(*) FILTER (WHERE tipo = 'COBRANZA'), "
                "count(*) FILTER (WHERE tipo = 'ANULACION_COBRANZA') "
                "FROM cuenta_movimiento WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        assert (movimientos_cobranza, movimientos_anulacion) == (cobranzas, anuladas)

    def verificar_inv13(self) -> None:
        ((suma,),) = self.sesion.execute(
            text(
                "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), "
                "0) FROM cuenta_movimiento WHERE organizacion_id = :o "
                "AND cuenta_tipo = 'CLIENTE' AND entidad_id = :e"
            ),
            {"o": self.org, "e": self.cliente_id},
        ).all()
        assert self.saldo() == suma
        assert cuentas_service.verificar_consistencia(self.org, self.sesion) == []

    def verificar(self) -> None:
        self.verificar_inv08()
        self.verificar_inv13()
        self.verificar_libro_de_cobranzas()

    def saldo(self) -> Decimal:
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="CLIENTE", entidad_id=self.cliente_id
        )


# Escenario: "INV-08 — propiedad sobre cobranzas aceptadas"
# Escenario: "INV-13 — saldo igual a la suma del libro"
@_PROPIEDAD
@given(_OPERACIONES)
def test_inv08_inv13_tras_cobranzas_anulaciones_y_saldos_iniciales_aleatorios(
    db_session: Session, operaciones: list[tuple[str, Any]]
) -> None:
    mundo = _Mundo(db_session)

    for tipo, dato in operaciones:
        if tipo == "saldo_inicial":
            mundo.saldo_inicial(dato)
        elif tipo == "cobrar":
            mundo.cobrar(dato)
        elif tipo == "cobrar_offline":
            mundo.cobrar_offline(*dato)
        else:
            mundo.anular(dato)

    mundo.verificar()


@_PROPIEDAD
@given(_SALDO_INICIAL, _COBRO)
def test_anular_una_cobranza_sin_movimientos_intermedios_devuelve_el_saldo_exacto(
    db_session: Session, deuda_centavos: int, cobro: Cobro
) -> None:
    mundo = _Mundo(db_session)
    mundo.saldo_inicial(deuda_centavos)
    antes = mundo.saldo()

    cobranza_id = mundo.cobrar(cobro)
    assert mundo.saldo() == antes - Decimal(sum(centavos for _, centavos in cobro)).scaleb(-2)
    mundo.anular_esta(cobranza_id)

    assert mundo.saldo() == antes
    mundo.verificar()


@_PROPIEDAD
@given(_SALDO_INICIAL, _COBRO_OFFLINE, st.booleans())
def test_inv08_una_cobranza_sin_conexion_con_observaciones_conserva_la_suma_de_sus_medios(
    db_session: Session, deuda_centavos: int, cobro: Cobro, con_referencia: bool
) -> None:
    mundo = _Mundo(db_session)
    mundo.saldo_inicial(deuda_centavos)
    antes = mundo.saldo()

    cobranza_id = mundo.cobrar_offline(cobro, con_referencia)

    assert mundo.saldo() == antes - Decimal(sum(centavos for _, centavos in cobro)).scaleb(-2)
    mundo.verificar_inv08()
    mundo.anular_esta(cobranza_id)
    assert mundo.saldo() == antes
    mundo.verificar()


def test_el_mundo_de_la_propiedad_cobra_y_anula_de_verdad_y_no_vacuamente(
    db_session: Session,
) -> None:
    """Guarda contra una propiedad vacua: el saldo inicial deja deuda real, la cobranza con dos
    medios la reduce, la sin conexión con un medio desactivado también, la anulación restituye y
    las invariantes se verifican sobre filas que existen en la base."""
    mundo = _Mundo(db_session)
    mundo.saldo_inicial(15_000_000)
    cobranza_id = mundo.cobrar([(0, 6_000_000), (1, 2_500_000)])
    mundo.cobrar_offline([(2, 1_000_000)], con_referencia=False)

    assert mundo.saldo() == Decimal("65000.00") - Decimal("10000.00")
    ((cobranzas, medios, observaciones),) = db_session.execute(
        text(
            "SELECT (SELECT count(*) FROM cobranza WHERE organizacion_id = :o), "
            "(SELECT count(*) FROM cobranza_medio WHERE organizacion_id = :o), "
            "(SELECT count(*) FROM observacion WHERE organizacion_id = :o "
            "AND codigo = 'MEDIO_INACTIVO')"
        ),
        {"o": mundo.org},
    ).all()
    assert (cobranzas, medios, observaciones) == (2, 3, 1)
    mundo.anular_esta(cobranza_id)
    assert mundo.saldo() == Decimal("150000.00") - Decimal("10000.00")
    mundo.verificar()
