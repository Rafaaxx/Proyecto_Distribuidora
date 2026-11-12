"""INV-08 e INV-13 después de compras, pagos y anulaciones, contra PostgreSQL real y con
Hypothesis (change 12, tarea 11.1).

INV-08 (`docs/01` §20, PAG-01): la suma de los medios de cada pago es igual a su importe
(la anulación no altera ni los medios ni el importe). INV-13 (CC-04): el saldo de la cuenta
del proveedor es la suma de sus movimientos. Acá se prueba que `COMPRA_CONFIRMAR` (a crédito
y de contado), `COMPRA_ANULAR`, `PAGO_PROVEEDOR_REGISTRAR` y `PAGO_PROVEEDOR_ANULAR`,
ejecutados por el bus, mantienen ambas para secuencias arbitrarias, y que registrar un pago y
anularlo sin movimientos intermedios devuelve el saldo exacto. Ambas invariantes se
comprueban con SQL sobre la base, no con las estructuras en memoria de la prueba.

Cada ejemplo crea su propia organización (todo se filtra por `organizacion_id`) dentro de la
transacción de `db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT`
por ejemplo porque el bus confirma la transacción del comando. Es una prueba de las
invariantes, no de concurrencia (esa confirma transacciones reales,
`tests/concurrency/test_pagos_proveedor_concurrencia.py`).
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
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.proveedores import commands as proveedores_commands
from app.modules.sync import service as sync_service
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import (
    crear_presentacion_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

MOMENTO = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
PERMISOS = frozenset(
    {
        "REGISTRAR_COMPRA",
        "ANULAR_COMPRA",
        "PERMITIR_STOCK_NEGATIVO",
        "REGISTRAR_PAGO_PROVEEDOR",
        "ANULAR_PAGO_PROVEEDOR",
    }
)
_MANEJADORES = {
    "COMPRA_CONFIRMAR": proveedores_commands.manejar_compra_confirmar,
    "COMPRA_ANULAR": proveedores_commands.manejar_compra_anular,
    "PAGO_PROVEEDOR_REGISTRAR": proveedores_commands.manejar_pago_proveedor_registrar,
    "PAGO_PROVEEDOR_ANULAR": proveedores_commands.manejar_pago_proveedor_anular,
}

# Un pago: de 1 a 3 medios (efectivo o transferencia, con importe en centavos).
type MedioDePago = tuple[int, int]
type Pago = list[MedioDePago]

_MEDIO = st.tuples(st.integers(min_value=0, max_value=1), st.integers(1, 300_000_000))
_PAGO = st.lists(_MEDIO, min_size=1, max_size=3)
_TOTAL_DE_COMPRA = st.integers(min_value=1, max_value=900_000_000)
# Una operación: compra a crédito, compra de contado, pago, anulación de un pago o de una
# compra. El entero de las anulaciones elige entre las candidatas vigentes (módulo).
_OPERACION = st.one_of(
    st.tuples(st.just("credito"), _TOTAL_DE_COMPRA),
    st.tuples(st.just("contado"), _TOTAL_DE_COMPRA),
    st.tuples(st.just("pago"), _PAGO),
    st.tuples(st.just("anular_pago"), st.integers(min_value=0, max_value=50)),
    st.tuples(
        st.just("anular_compra"),
        st.tuples(st.integers(min_value=0, max_value=50), st.booleans()),
    ),
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
    """Una organización con un proveedor, un producto, un depósito, dos medios de pago
    (efectivo y transferencia con referencia obligatoria), los motivos de anulación y un
    usuario con permisos de compra y de pago, creada dentro de la transacción del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=PERMISOS
        )
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.producto_id = crear_producto_sql(
            sesion, self.org, nombre="Vino A", proveedor_id=self.proveedor_id
        )
        self.presentacion_id = crear_presentacion_sql(
            sesion,
            self.org,
            self.producto_id,
            nombre="Botella",
            unidades_base=1,
            es_referencia=True,
        )
        self.ubicacion_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.efectivo_id = self._medio("Efectivo", requiere_referencia=False)
        self.transferencia_id = self._medio("Transferencia", requiere_referencia=True)
        self.motivo_compra_id = self._motivo("ANULACION_COMPRA")
        self.motivo_pago_id = self._motivo("ANULACION_PAGO")
        # Compras vigentes `(id, es_de_contado)` y pagos que hoy admiten anulación.
        self.compras_vigentes: list[tuple[UUID, bool]] = []
        self.pagos_anulables: list[UUID] = []
        self.pago_de_compra: dict[UUID, UUID] = {}

    def _medio(self, nombre: str, *, requiere_referencia: bool) -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) VALUES (:id, :org, :nombre, :ref, true, "
                ":m, :m)"
            ),
            {
                "id": medio_id,
                "org": self.org,
                "nombre": nombre,
                "ref": requiere_referencia,
                "m": MOMENTO,
            },
        )
        return medio_id

    def _motivo(self, ambito: str) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, 'Error de carga', true, :m, :m)"
            ),
            {"id": motivo_id, "org": self.org, "ambito": ambito, "m": MOMENTO},
        )
        return motivo_id

    def _enviar(self, tipo: str, contenido: dict[str, Any]) -> Any:
        sobre = SobreComando(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
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

    def _medios(self, pago: Pago) -> list[dict[str, Any]]:
        return [
            {
                "medio_pago_id": str(self.transferencia_id if tipo else self.efectivo_id),
                "importe": _importe(centavos),
                "referencia": f"REF-{indice}" if tipo else None,
            }
            for indice, (tipo, centavos) in enumerate(pago)
        ]

    # --- operaciones -----------------------------------------------------------------

    def comprar(self, total_centavos: int, *, de_contado: bool) -> UUID:
        contenido: dict[str, Any] = {
            "proveedor_id": str(self.proveedor_id),
            "fecha": "2026-10-02",
            "ubicacion_id": str(self.ubicacion_id),
            "condicion": "CONTADO" if de_contado else "CREDITO",
            "total_factura": _importe(total_centavos),
            "lineas": [
                {
                    "producto_id": str(self.producto_id),
                    "presentacion_id": str(self.presentacion_id),
                    "cantidad": "3",
                    "valor": "10.00",
                    "incluye_iva": False,
                }
            ],
        }
        if de_contado:
            contenido["medios"] = self._medios([(0, total_centavos)])
        comando = self._enviar("COMPRA_CONFIRMAR", contenido)
        compra_id = UUID(str(comando.resultado["compra_id"]))
        self.compras_vigentes.append((compra_id, de_contado))
        if de_contado:
            ((pago_id,),) = self.sesion.execute(
                text("SELECT id FROM pago_proveedor WHERE organizacion_id = :o AND compra_id = :c"),
                {"o": self.org, "c": compra_id},
            ).all()
            self.pago_de_compra[compra_id] = pago_id
        return compra_id

    def pagar(self, pago: Pago) -> UUID:
        comando = self._enviar(
            "PAGO_PROVEEDOR_REGISTRAR",
            {
                "proveedor_id": str(self.proveedor_id),
                "fecha": "2026-10-02",
                "importe": _importe(sum(centavos for _, centavos in pago)),
                "medios": self._medios(pago),
            },
        )
        pago_id = UUID(str(comando.resultado["pago_id"]))
        self.pagos_anulables.append(pago_id)
        return pago_id

    def anular_pago(self, indice: int) -> None:
        if not self.pagos_anulables:
            return
        pago_id = self.pagos_anulables.pop(indice % len(self.pagos_anulables))
        self.anular_este_pago(pago_id)

    def anular_este_pago(self, pago_id: UUID) -> None:
        self._enviar(
            "PAGO_PROVEEDOR_ANULAR",
            {"pago_id": str(pago_id), "motivo_id": str(self.motivo_pago_id)},
        )

    def anular_compra(self, indice: int, devuelve_pago: bool) -> None:
        if not self.compras_vigentes:
            return
        compra_id, de_contado = self.compras_vigentes.pop(indice % len(self.compras_vigentes))
        contenido: dict[str, Any] = {
            "compra_id": str(compra_id),
            "motivo_id": str(self.motivo_compra_id),
        }
        if de_contado:
            contenido["devuelve_pago"] = devuelve_pago
        self._enviar("COMPRA_ANULAR", contenido)
        if de_contado and not devuelve_pago:
            # D2: con la compra anulada y sin devolución, su pago admite anulación aparte.
            self.pagos_anulables.append(self.pago_de_compra[compra_id])

    # --- invariantes, comprobadas con SQL ----------------------------------------------

    def verificar_inv08(self) -> None:
        """Cada pago, vigente o anulado, tiene medios que suman exactamente su importe."""
        desparejos = self.sesion.execute(
            text(
                "SELECT p.id FROM pago_proveedor p WHERE p.organizacion_id = :o AND p.importe "
                "<> (SELECT COALESCE(SUM(m.importe), 0) FROM pago_proveedor_medio m "
                "WHERE m.organizacion_id = p.organizacion_id AND m.pago_id = p.id)"
            ),
            {"o": self.org},
        ).all()
        assert desparejos == []

    def verificar_libro_de_pagos(self) -> None:
        """Un `PAGO` por cada pago y una `ANULACION_PAGO` por cada pago anulado."""
        ((pagos, anulados),) = self.sesion.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE estado = 'ANULADA') "
                "FROM pago_proveedor WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).all()
        ((movimientos_pago, movimientos_anulacion),) = self.sesion.execute(
            text(
                "SELECT count(*) FILTER (WHERE tipo = 'PAGO'), "
                "count(*) FILTER (WHERE tipo = 'ANULACION_PAGO') "
                "FROM cuenta_movimiento WHERE organizacion_id = :o AND origen_tipo IN "
                "('PAGO', 'ANULACION_PAGO')"
            ),
            {"o": self.org},
        ).all()
        assert (movimientos_pago, movimientos_anulacion) == (pagos, anulados)

    def verificar_inv13(self) -> None:
        ((suma,),) = self.sesion.execute(
            text(
                "SELECT COALESCE(SUM(CASE sentido WHEN 'AUMENTA' THEN importe ELSE -importe END), "
                "0) FROM cuenta_movimiento WHERE organizacion_id = :o "
                "AND cuenta_tipo = 'PROVEEDOR' AND entidad_id = :e"
            ),
            {"o": self.org, "e": self.proveedor_id},
        ).all()
        assert (
            cuentas_service.obtener_saldo(
                self.org, self.sesion, cuenta_tipo="PROVEEDOR", entidad_id=self.proveedor_id
            )
            == suma
        )
        assert cuentas_service.verificar_consistencia(self.org, self.sesion) == []

    def verificar(self) -> None:
        self.verificar_inv08()
        self.verificar_inv13()
        self.verificar_libro_de_pagos()

    def saldo(self) -> Decimal:
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="PROVEEDOR", entidad_id=self.proveedor_id
        )


@_PROPIEDAD
@given(_OPERACIONES)
def test_inv08_inv13_tras_compras_pagos_y_anulaciones_aleatorios(
    db_session: Session, operaciones: list[tuple[str, Any]]
) -> None:
    mundo = _Mundo(db_session)

    for tipo, dato in operaciones:
        if tipo == "credito":
            mundo.comprar(dato, de_contado=False)
        elif tipo == "contado":
            mundo.comprar(dato, de_contado=True)
        elif tipo == "pago":
            mundo.pagar(dato)
        elif tipo == "anular_pago":
            mundo.anular_pago(dato)
        else:
            mundo.anular_compra(*dato)

    mundo.verificar()


@_PROPIEDAD
@given(_TOTAL_DE_COMPRA, _PAGO)
def test_registrar_y_anular_un_pago_sin_movimientos_intermedios_devuelve_el_saldo_exacto(
    db_session: Session, deuda_centavos: int, pago: Pago
) -> None:
    mundo = _Mundo(db_session)
    mundo.comprar(deuda_centavos, de_contado=False)
    antes = mundo.saldo()

    pago_id = mundo.pagar(pago)
    assert mundo.saldo() == antes - Decimal(sum(centavos for _, centavos in pago)).scaleb(-2)
    mundo.anular_este_pago(pago_id)

    assert mundo.saldo() == antes
    mundo.verificar()


def test_el_mundo_de_la_propiedad_paga_y_anula_de_verdad_y_no_vacuamente(
    db_session: Session,
) -> None:
    """Guarda contra una propiedad vacua: la compra a crédito deja deuda real, el pago con
    dos medios la reduce, la anulación la restituye y las invariantes se verifican sobre
    filas que existen en la base (pagos, medios y movimientos)."""
    mundo = _Mundo(db_session)

    mundo.comprar(15_000_000, de_contado=False)
    pago_id = mundo.pagar([(0, 6_000_000), (1, 2_500_000)])

    assert mundo.saldo() == Decimal("65000.00")
    ((pagos, medios),) = db_session.execute(
        text(
            "SELECT (SELECT count(*) FROM pago_proveedor WHERE organizacion_id = :o), "
            "(SELECT count(*) FROM pago_proveedor_medio WHERE organizacion_id = :o)"
        ),
        {"o": mundo.org},
    ).all()
    assert (pagos, medios) == (1, 2)
    mundo.anular_este_pago(pago_id)
    assert mundo.saldo() == Decimal("150000.00")
    mundo.verificar()
