"""INV-12 e INV-13 después de compras y anulaciones, contra PostgreSQL real y con Hypothesis
(change 11, tarea 14.1).

INV-12 (`docs/01` §20, STK-04): el stock de cada producto y ubicación es igual a la suma de
sus movimientos y `stock_total` es la suma de sus saldos. INV-13 (CC-04): el saldo de la
cuenta del proveedor es la suma de sus movimientos. Acá se prueba que `COMPRA_CONFIRMAR` y
`COMPRA_ANULAR`, ejecutadas por el bus, las mantienen para secuencias arbitrarias de compras
a crédito y anulaciones (la anulación puede dejar stock negativo: el usuario tiene
`PERMITIR_STOCK_NEGATIVO`, CMP-07), y que confirmar y anular una compra sin movimientos
intermedios devuelve el stock y el saldo exactos.

Cada ejemplo crea su propia organización (todo se filtra por `organizacion_id`) dentro de
la transacción de `db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT`
por ejemplo porque el bus confirma la transacción del comando. Es una prueba de la
invariante, no de concurrencia (esa confirma transacciones reales,
`tests/concurrency/test_compras_concurrencia.py`).
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
from app.modules.stock import service as stock_service
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
PERMISOS = frozenset({"REGISTRAR_COMPRA", "ANULAR_COMPRA", "PERMITIR_STOCK_NEGATIVO"})

# Una compra: líneas (producto 0-1, cajas o botellas 1-30, valor en centavos) sin repetir
# producto, un total de factura en centavos y una ubicación 0-1.
type LineaDeCompra = tuple[int, int, int]
type Compra = tuple[list[LineaDeCompra], int, int]

_LINEAS = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=1),
        st.integers(min_value=1, max_value=30),
        st.integers(min_value=1, max_value=5_000_000),
    ),
    min_size=1,
    max_size=2,
    unique_by=lambda linea: linea[0],
)
_COMPRA = st.tuples(
    _LINEAS,
    st.integers(min_value=1, max_value=900_000_000),
    st.integers(min_value=0, max_value=1),
)
# Una operación: ("compra", ...) o ("anular", índice entre las compras todavía vigentes).
_OPERACION = st.one_of(
    st.tuples(st.just("compra"), _COMPRA),
    st.tuples(st.just("anular"), st.integers(min_value=0, max_value=50)),
)
_OPERACIONES = st.lists(_OPERACION, min_size=1, max_size=8)

_PROPIEDAD = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _importe(centavos: int) -> str:
    return str(Decimal(centavos).scaleb(-2))


class _Mundo:
    """Una organización con un proveedor, dos productos (el primero con Caja x6 de
    referencia, el segundo con Botella), dos ubicaciones y un usuario con permisos de
    compra, creada dentro del `SAVEPOINT` del ejemplo."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=PERMISOS
        )
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.productos: list[UUID] = []
        self.presentaciones: list[UUID] = []
        for indice, (nombre, unidades) in enumerate((("Vino A", 6), ("Cerveza B", 1))):
            producto_id = crear_producto_sql(
                sesion, self.org, nombre=nombre, proveedor_id=self.proveedor_id
            )
            self.productos.append(producto_id)
            self.presentaciones.append(
                crear_presentacion_sql(
                    sesion,
                    self.org,
                    producto_id,
                    nombre="Caja x6" if indice == 0 else "Botella",
                    unidades_base=unidades,
                    es_referencia=True,
                )
            )
        self.ubicaciones = [
            crear_ubicacion_sql(sesion, self.org, nombre=f"Depósito {i}") for i in range(2)
        ]
        self.motivo_id = uuid4()
        sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, 'ANULACION_COMPRA', 'Error de carga', "
                "true, :m, :m)"
            ),
            {"id": self.motivo_id, "org": self.org, "m": MOMENTO},
        )
        self.vigentes: list[UUID] = []

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
        manejador = (
            proveedores_commands.manejar_compra_confirmar
            if tipo == "COMPRA_CONFIRMAR"
            else proveedores_commands.manejar_compra_anular
        )

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

    def comprar(self, compra: Compra) -> UUID:
        lineas, total_centavos, ubicacion = compra
        comando = self._enviar(
            "COMPRA_CONFIRMAR",
            {
                "proveedor_id": str(self.proveedor_id),
                "fecha": "2026-10-02",
                "ubicacion_id": str(self.ubicaciones[ubicacion]),
                "condicion": "CREDITO",
                "total_factura": _importe(total_centavos),
                "lineas": [
                    {
                        "producto_id": str(self.productos[producto]),
                        "presentacion_id": str(self.presentaciones[producto]),
                        "cantidad": str(cantidad),
                        "valor": _importe(centavos),
                        "incluye_iva": False,
                    }
                    for producto, cantidad, centavos in lineas
                ],
            },
        )
        compra_id = UUID(str(comando.resultado["compra_id"]))
        self.vigentes.append(compra_id)
        return compra_id

    def anular(self, indice: int) -> None:
        if not self.vigentes:
            return
        compra_id = self.vigentes.pop(indice % len(self.vigentes))
        self._enviar(
            "COMPRA_ANULAR",
            {"compra_id": str(compra_id), "motivo_id": str(self.motivo_id)},
        )

    def verificar_inv12(self) -> None:
        libro = {
            (fila[0], fila[1]): int(fila[2])
            for fila in self.sesion.execute(
                text(
                    "SELECT producto_id, ubicacion_id, SUM(cantidad_base) FROM stock_movimiento "
                    "WHERE organizacion_id = :o GROUP BY producto_id, ubicacion_id"
                ),
                {"o": self.org},
            ).all()
        }
        for (producto_id, ubicacion_id), suma in libro.items():
            assert (
                stock_service.obtener_saldo(
                    self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
                )
                == suma
            )
        # `verificar_consistencia` compara cada saldo con su libro y cada `stock_total` con
        # la suma de los saldos del producto.
        assert stock_service.verificar_consistencia(self.org, self.sesion) == []

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

    def estado(self) -> tuple[list[int], Decimal]:
        """Stock por producto y ubicación (en el orden fijo) y saldo de la cuenta."""
        stock = [
            stock_service.obtener_saldo(
                self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
            )
            for producto_id in self.productos
            for ubicacion_id in self.ubicaciones
        ]
        saldo = cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="PROVEEDOR", entidad_id=self.proveedor_id
        )
        return stock, saldo


@_PROPIEDAD
@given(_OPERACIONES)
def test_inv12_inv13_tras_compras_y_anulaciones_aleatorias(
    db_session: Session, operaciones: list[tuple[str, Any]]
) -> None:
    mundo = _Mundo(db_session)

    for tipo, dato in operaciones:
        if tipo == "compra":
            mundo.comprar(dato)
        else:
            mundo.anular(dato)

    mundo.verificar_inv12()
    mundo.verificar_inv13()


@_PROPIEDAD
@given(_COMPRA, _COMPRA)
def test_confirmar_y_anular_sin_movimientos_intermedios_devuelve_stock_y_saldo_exactos(
    db_session: Session, previa: Compra, compra: Compra
) -> None:
    mundo = _Mundo(db_session)
    mundo.comprar(previa)
    antes = mundo.estado()

    mundo.comprar(compra)
    mundo.anular(len(mundo.vigentes) - 1)

    assert mundo.estado() == antes
    mundo.verificar_inv12()
    mundo.verificar_inv13()


def test_el_mundo_de_la_propiedad_compra_y_anula_de_verdad_y_no_vacuamente(
    db_session: Session,
) -> None:
    """Guarda contra una propiedad vacua: las compras dejan stock y deuda reales y la
    anulación los revierte parcialmente, y las invariantes se verifican sobre eso."""
    mundo = _Mundo(db_session)

    mundo.comprar(([(0, 10, 600_000), (1, 5, 110_000)], 15_000_000, 0))
    primera = mundo.comprar(([(1, 7, 120_000)], 1_000_000, 1))

    assert mundo.estado() == ([60, 0, 5, 7], Decimal("160000.00"))
    mundo.anular(mundo.vigentes.index(primera))
    assert mundo.estado() == ([60, 0, 5, 0], Decimal("150000.00"))
    mundo.verificar_inv12()
    mundo.verificar_inv13()
