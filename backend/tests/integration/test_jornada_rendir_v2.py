"""Change 24, tarea 7.2: `JORNADA_RENDIR` v2 por el bus contra PostgreSQL real (specs
`stock/rendicion-de-jornada`, requisitos "La rendición exige la entrega y el conteo físico" y "Las
diferencias de la rendición quedan en el libro", y `stock/jornadas`; `design.md` D2, D3, D5).

Se procesa por `sync_service.procesar_comando` resolviendo el handler `(tipo, versión)` como lo
hacen el lote y la ruta. La cobertura por HTTP es de `test_jornadas_api.py`.

Reglas citadas: RUT-05, RUT-06, INV-01, INV-04, INV-05, INV-06, INV-12, INV-21, CST-12, CAT-05,
SEG-06, STK-09, SYN-02.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_jornada_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
    desactivar_producto_sql,
)

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import (
    ContenidoDeComandoInvalidoError,
    VersionDeComandoSinHandlerError,
)
from app.commands.huella import ContenidoNoSerializableError, calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.costeo.models import CostoProducto, CostoProductoMov
from app.modules.stock import (
    jornadas_commands,  # noqa: F401  (registra los handlers)
    rendicion_commands,  # noqa: F401  (registra JORNADA_RENDIR v2)
)
from app.modules.stock import repository as stock_repository
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    CantidadInvalidaError,
    ConteoIncompletoError,
    EsperadoDifiereError,
    JornadaEstadoInvalidoError,
    JornadaSinEntregaError,
    ObservacionInvalidaError,
    ProductoInactivoError,
    ProductoRepetidoError,
    RecursoNoEncontradoError,
)
from app.modules.stock.domain.movimientos import LineaDeMovimiento, LineaDeStockInicial
from app.modules.stock.models import Jornada, Rendicion, RendicionLinea, StockMovimiento
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

DIA = datetime(2026, 11, 4, tzinfo=UTC)
CARGA = DIA + timedelta(hours=7)
APERTURA = DIA + timedelta(hours=8)
VENTA = DIA + timedelta(hours=11)
ENTREGA = DIA + timedelta(hours=17)
RENDICION = DIA + timedelta(hours=18)
RENDIR = "JORNADA_RENDIR"
DIFERENCIA = "DIFERENCIA_RENDICION"

VENDEDOR = frozenset({"ABRIR_JORNADA"})
SUPERVISORA = frozenset({"RENDIR_JORNADA"})
ENCARGADA = frozenset({"LIBERAR_UBICACION"})


class Actor:
    def __init__(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        self.usuario_id = usuario_id
        self.dispositivo_id = dispositivo_id


class Entorno:
    """ "Camioneta 1" con la jornada entregada de Juan, que abrió a las 8:00; Vino A (promedio
    1050), Agua 500 y Agua 1500 (productos activos); una Supervisora con `RENDIR_JORNADA` y una
    encargada con `LIBERAR_UBICACION`."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.juan = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=VENDEDOR))
        self.supervisora = Actor(
            *crear_usuario_y_dispositivo(sesion, self.org, permisos=SUPERVISORA)
        )
        self.encargada = Actor(*crear_usuario_y_dispositivo(sesion, self.org, permisos=ENCARGADA))
        self.camioneta = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.vino = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua_500 = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.agua_1500 = crear_producto_sql(sesion, self.org, nombre="Agua 1500")
        self.jornada_id: UUID | None = None

    def cargar(self, producto_id: UUID, cantidad: int, costo: str = "1050") -> None:
        """Stock inicial en la camioneta, antes de abrir la jornada."""
        stock_service.registrar_stock_inicial(
            self.org,
            self.sesion,
            FixedClock(CARGA),
            ubicacion_id=self.camioneta,
            lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=CARGA,
        )

    def abrir(self, *, entregada: bool = True, estado: str = "ABIERTA") -> UUID:
        cambios: dict[str, Any] = {"abierta_en": APERTURA}
        if entregada:
            cambios.update(entregada_en=ENTREGA, entrega_occurred_at=ENTREGA, entrega_secuencia=9)
        self.jornada_id = crear_jornada_sql(
            self.sesion,
            self.org,
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            ubicacion_id=self.camioneta,
            estado=estado,
            **cambios,
        )
        self.sesion.commit()
        return self.jornada_id

    def vender(self, producto_id: UUID, cantidad: int) -> None:
        """Una venta de Juan con su jornada, a las 11:00."""
        stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            FixedClock(VENTA),
            lineas=[
                LineaDeMovimiento(
                    producto_id=producto_id,
                    ubicacion_id=self.camioneta,
                    cantidad_base=-cantidad,
                    tipo="VENTA",
                    costo_unitario=None,
                    origen_tipo="VENTA",
                    origen_id=uuid4(),
                    jornada_id=self.jornada_id,
                )
            ],
            usuario_id=self.juan.usuario_id,
            dispositivo_id=self.juan.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=VENTA,
        )
        self.sesion.commit()

    def sacar_por_excepcion(self, producto_id: UUID, cantidad: int) -> None:
        """Quien tiene `LIBERAR_UBICACION` saca stock del vehículo tomado."""
        stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            FixedClock(VENTA),
            lineas=[
                LineaDeMovimiento(
                    producto_id=producto_id,
                    ubicacion_id=self.camioneta,
                    cantidad_base=-cantidad,
                    tipo="AJUSTE",
                    costo_unitario=None,
                    origen_tipo="AJUSTE_STOCK",
                    origen_id=uuid4(),
                )
            ],
            usuario_id=self.encargada.usuario_id,
            dispositivo_id=self.encargada.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=VENTA,
            puede_operar_ubicacion_tomada=True,
        )
        self.sesion.commit()

    def contenido(
        self,
        lineas: list[tuple[UUID, Any, Any]],
        *,
        jornada_id: UUID | None = None,
        observacion: str | None = None,
    ) -> dict[str, Any]:
        contenido: dict[str, Any] = {
            "jornada_id": str(jornada_id or self.jornada_id),
            "lineas": [
                {
                    "producto_id": str(producto),
                    "cantidad_contada": contada,
                    "cantidad_esperada": esperada,
                }
                for producto, contada, esperada in lineas
            ],
        }
        if observacion is not None:
            contenido["observacion"] = observacion
        return contenido

    def enviar(
        self,
        contenido: dict[str, Any],
        *,
        actor: Actor | None = None,
        version: int = 2,
        operation_id: UUID | None = None,
        organizacion_id: UUID | None = None,
    ) -> Comando:
        quien = actor or self.supervisora
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=RENDIR,
            version=version,
            modo="ONLINE",
            organizacion_id=organizacion_id or self.org,
            usuario_id=quien.usuario_id,
            dispositivo_id=quien.dispositivo_id,
            occurred_at=RENDICION,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg, return-value]
                sobre, validado, sesion=sesion_protegida, reloj=FixedClock(RENDICION)
            )

        return sync_service.procesar_comando(
            self.sesion,
            FixedClock(RENDICION),
            sobre=sobre,
            huella=huella,
            ejecutar_handler=_ejecutar,
        )

    # --- lectura ---------------------------------------------------------------------------

    def jornada(self) -> Jornada:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(Jornada).where(
                Jornada.organizacion_id == self.org, Jornada.id == self.jornada_id
            )
        ).one()

    def rendiciones(self) -> list[Rendicion]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(select(Rendicion).where(Rendicion.organizacion_id == self.org))
        )

    def lineas(self) -> dict[UUID, RendicionLinea]:
        self.sesion.rollback()
        return {
            linea.producto_id: linea
            for linea in self.sesion.scalars(
                select(RendicionLinea).where(RendicionLinea.organizacion_id == self.org)
            )
        }

    def diferencias(self) -> list[StockMovimiento]:
        self.sesion.rollback()
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org, StockMovimiento.tipo == DIFERENCIA
                )
                .order_by(StockMovimiento.registered_at, StockMovimiento.id)
            )
        )

    def cantidad_de_movimientos(self) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
            )
            or 0
        )

    def saldo(self, producto_id: UUID) -> int:
        self.sesion.rollback()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=self.camioneta
        )

    def costo(self, producto_id: UUID) -> CostoProducto | None:
        self.sesion.rollback()
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org, CostoProducto.producto_id == producto_id
            )
            .execution_options(populate_existing=True)
        ).one_or_none()

    def historia_de_costo(self) -> int:
        self.sesion.rollback()
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(CostoProductoMov)
                .where(CostoProductoMov.organizacion_id == self.org)
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _sin_rendicion(entorno: Entorno, movimientos_antes: int) -> None:
    """INV-01: la rendición rechazada no deja jornada rendida, rendición, líneas ni movimientos."""
    assert entorno.jornada().estado == "ABIERTA"
    assert entorno.rendiciones() == []
    assert entorno.lineas() == {}
    assert entorno.cantidad_de_movimientos() == movimientos_antes


# --- catálogo ----------------------------------------------------------------------------


def test_el_tipo_esta_declarado_solo_online_con_handler_v2() -> None:
    declarado = catalogo_bus.tipo_declarado(RENDIR)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert declarado.permisos == ("RENDIR_JORNADA",)
    assert registro.resolver_handler(RENDIR, 2).tipo == RENDIR


@pytest.mark.parametrize("version", [1, 3])
def test_la_version_sin_conteo_ya_no_se_acepta(entorno: Entorno, version: int) -> None:
    """D2: v1 se retira. El bus resuelve el handler antes de la idempotencia (decisión del
    usuario del 2026-11-04): ni un v1 nuevo ni el reenvío de uno ya aceptado llegan al handler."""
    entorno.abrir()

    with pytest.raises(VersionDeComandoSinHandlerError) as error:
        entorno.enviar({"jornada_id": str(entorno.jornada_id)}, version=version)

    assert error.value.codigo == "VERSION_DE_COMANDO_SIN_HANDLER"
    assert entorno.jornada().estado == "ABIERTA"


# --- el camino feliz ---------------------------------------------------------------------


def test_rendicion_sin_diferencias_deja_la_jornada_en_rendicion_y_no_escribe_movimientos(
    entorno: Entorno,
) -> None:
    """RUT-06: 40 de Vino A y 12 de Agua 500 contadas; dos líneas sin diferencia."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    comando = entorno.enviar(
        entorno.contenido(
            [(entorno.vino, 40, 40), (entorno.agua_500, 12, 12)], observacion="  todo en orden "
        )
    )

    assert comando.estado == "ACEPTADO"
    jornada = entorno.jornada()
    assert jornada.estado == "EN_RENDICION"
    assert jornada.rendida_por_id == entorno.supervisora.usuario_id
    assert jornada.rendida_en == RENDICION
    (rendicion,) = entorno.rendiciones()
    assert rendicion.jornada_id == jornada.id
    assert rendicion.observacion == "todo en orden"
    assert rendicion.usuario_id == entorno.supervisora.usuario_id
    lineas = entorno.lineas()
    assert {(x.cantidad_esperada, x.cantidad_contada, x.diferencia) for x in lineas.values()} == {
        (40, 40, 0),
        (12, 12, 0),
    }
    assert all(x.costo_unitario is None for x in lineas.values())
    assert entorno.diferencias() == []
    assert entorno.cantidad_de_movimientos() == antes


def test_la_rendicion_congela_el_desglose_del_esperado(entorno: Entorno) -> None:
    """RUT-07: al abrir 10, venta de 8 y un ajuste de −2 de la encargada = esperado 0 más lo
    que se carga en la ventana. Se verifica con ventas y otros."""
    entorno.cargar(entorno.vino, 10)
    entorno.abrir()
    entorno.vender(entorno.vino, 8)
    entorno.sacar_por_excepcion(entorno.vino, 1)

    entorno.enviar(entorno.contenido([(entorno.vino, 1, 1)]))

    linea = entorno.lineas()[entorno.vino]
    assert (linea.stock_al_abrir, linea.ingresos, linea.ventas, linea.anulaciones, linea.otros) == (
        10,
        0,
        8,
        0,
        -1,
    )
    assert linea.cantidad_esperada == 10 - 8 - 1


def test_el_faltante_escribe_la_diferencia_al_promedio_con_la_jornada(entorno: Entorno) -> None:
    """RUT-06, CST-12, INV-12: 40 esperadas y 37 contadas = −3 a 1050, stock 37, promedio y
    historia de costo intactos."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    historia = entorno.historia_de_costo()

    entorno.enviar(entorno.contenido([(entorno.vino, 37, 40)]))

    (diferencia,) = entorno.diferencias()
    assert (diferencia.cantidad_base, diferencia.costo_unitario) == (-3, Decimal("1050.000000"))
    assert diferencia.origen_tipo == "RENDICION"
    assert diferencia.jornada_id == entorno.jornada_id
    (rendicion,) = entorno.rendiciones()
    assert diferencia.origen_id == rendicion.id
    linea = entorno.lineas()[entorno.vino]
    assert (linea.diferencia, linea.costo_unitario) == (-3, Decimal("1050.000000"))
    assert entorno.saldo(entorno.vino) == 37
    costo = entorno.costo(entorno.vino)
    assert costo is not None
    assert (costo.stock_total, costo.costo_promedio) == (37, Decimal("1050.000000"))
    assert entorno.historia_de_costo() == historia


def test_una_sola_diferencia_por_producto_aun_con_varios_productos(entorno: Entorno) -> None:
    """D5: faltante de uno y sobrante de otro; un movimiento por producto con diferencia."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()

    entorno.enviar(entorno.contenido([(entorno.vino, 37, 40), (entorno.agua_500, 14, 12)]))

    por_producto = {d.producto_id: d.cantidad_base for d in entorno.diferencias()}
    assert por_producto == {entorno.vino: -3, entorno.agua_500: 2}
    assert (entorno.saldo(entorno.vino), entorno.saldo(entorno.agua_500)) == (37, 14)


def test_la_rendicion_llama_una_sola_vez_a_la_puerta_con_la_jornada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3: una llamada a la puerta con `rendicion_de_jornada`."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    original = stock_service.registrar_movimientos
    llamadas: list[dict[str, Any]] = []

    def espia(*args: Any, **kwargs: Any) -> Any:
        llamadas.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(stock_service, "registrar_movimientos", espia)

    entorno.enviar(entorno.contenido([(entorno.vino, 37, 40), (entorno.agua_500, 14, 12)]))

    assert len(llamadas) == 1
    assert llamadas[0]["rendicion_de_jornada"] == entorno.jornada_id
    assert len(llamadas[0]["lineas"]) == 2


def test_sobrante_de_un_producto_no_esperado(entorno: Entorno) -> None:
    """RUT-06: Agua 1500 sin movimientos, agregada con 2 contadas y esperado 0."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()

    entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 2, 0)]))

    linea = entorno.lineas()[entorno.agua_1500]
    assert (linea.cantidad_esperada, linea.cantidad_contada, linea.diferencia) == (0, 2, 2)
    assert (linea.stock_al_abrir, linea.ingresos, linea.ventas, linea.otros) == (0, 0, 0, 0)
    assert entorno.saldo(entorno.agua_1500) == 2


def test_sobrante_sin_promedio_se_acepta_con_costo_nulo(entorno: Entorno) -> None:
    """D5, CST-12: producto sin costo promedio."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()

    entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 2, 0)]))

    (diferencia,) = entorno.diferencias()
    assert (diferencia.producto_id, diferencia.cantidad_base) == (entorno.agua_1500, 2)
    assert diferencia.costo_unitario is None
    assert entorno.lineas()[entorno.agua_1500].costo_unitario is None


def test_conjunto_vacio_con_conteo_vacio_es_valido(entorno: Entorno) -> None:
    """D2: una jornada sin stock ni movimientos se rinde con el conteo vacío."""
    entorno.abrir()

    comando = entorno.enviar(entorno.contenido([]))

    assert comando.estado == "ACEPTADO"
    assert entorno.jornada().estado == "EN_RENDICION"
    assert entorno.lineas() == {}


# --- rechazos ----------------------------------------------------------------------------


def test_la_rendicion_exige_la_entrega(entorno: Entorno) -> None:
    entorno.cargar(entorno.vino, 40)
    entorno.abrir(entregada=False)
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(JornadaSinEntregaError):
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40)]))

    _sin_rendicion(entorno, antes)


@pytest.mark.parametrize("estado", ["EN_RENDICION", "CERRADA", "LIBERADA"])
def test_solo_se_rinde_una_jornada_abierta(entorno: Entorno, estado: str) -> None:
    entorno.abrir(estado=estado)

    with pytest.raises(JornadaEstadoInvalidoError):
        entorno.enviar(entorno.contenido([]))

    assert entorno.rendiciones() == []
    assert entorno.jornada().estado == estado


def test_falta_contar_un_producto(entorno: Entorno) -> None:
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ConteoIncompletoError) as error:
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40)]))

    assert error.value.extension == {"productos": [str(entorno.agua_500)]}
    _sin_rendicion(entorno, antes)


def test_un_producto_vendido_hasta_cero_tambien_se_cuenta(entorno: Entorno) -> None:
    """RUT-06: saldo 0 pero con movimientos en la jornada."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    entorno.vender(entorno.agua_500, 12)
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ConteoIncompletoError) as error:
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40)]))

    assert error.value.extension == {"productos": [str(entorno.agua_500)]}
    _sin_rendicion(entorno, antes)


def test_un_producto_vendido_hasta_cero_contado_en_cero_se_acepta(entorno: Entorno) -> None:
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    entorno.vender(entorno.agua_500, 12)

    entorno.enviar(entorno.contenido([(entorno.agua_500, 0, 0)]))

    linea = entorno.lineas()[entorno.agua_500]
    assert (linea.stock_al_abrir, linea.ventas, linea.cantidad_esperada) == (12, 12, 0)
    assert entorno.diferencias() == []


def test_el_esperado_cambio_mientras_se_contaba(entorno: Entorno) -> None:
    """RUT-06, STK-04: la encargada sacó 6 del vehículo; el esperado actual es 34."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    entorno.sacar_por_excepcion(entorno.vino, 6)
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(EsperadoDifiereError) as error:
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40)]))

    assert error.value.extension == {
        "distintos": [str(entorno.vino)],
        "esperados": {str(entorno.vino): 34},
    }
    _sin_rendicion(entorno, antes)


def test_con_el_esperado_actualizado_se_acepta(entorno: Entorno) -> None:
    """Triangulación del caso anterior: reenviada con 34 la rendición se registra."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    entorno.sacar_por_excepcion(entorno.vino, 6)

    entorno.enviar(entorno.contenido([(entorno.vino, 34, 34)]))

    assert entorno.jornada().estado == "EN_RENDICION"


@pytest.mark.parametrize("contada", [True, "3", None], ids=["booleano", "texto", "nulo"])
def test_una_cantidad_que_no_es_numero_es_contenido_invalido(
    entorno: Entorno, contada: Any
) -> None:
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(entorno.contenido([(entorno.vino, contada, 40)]))

    _sin_rendicion(entorno, antes)


def test_cantidad_negativa_es_cantidad_invalida(entorno: Entorno) -> None:
    """INV-04: el código es `CANTIDAD_INVALIDA` y no se escribe nada."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(CantidadInvalidaError):
        entorno.enviar(entorno.contenido([(entorno.vino, -1, 40)]))

    _sin_rendicion(entorno, antes)


def test_cantidad_con_decimales_no_entra_al_bus(entorno: Entorno) -> None:
    """INV-04: un número con decimales no es contenido válido de un comando (la huella canónica
    solo admite enteros) y la rendición no se registra."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ContenidoNoSerializableError):
        entorno.enviar(entorno.contenido([(entorno.vino, 2.5, 40)]))

    _sin_rendicion(entorno, antes)


def test_producto_repetido(entorno: Entorno) -> None:
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ProductoRepetidoError):
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.vino, 40, 40)]))

    _sin_rendicion(entorno, antes)


def test_observacion_de_mas_de_500_caracteres(entorno: Entorno) -> None:
    entorno.abrir()

    with pytest.raises(ObservacionInvalidaError):
        entorno.enviar(entorno.contenido([], observacion="a" * 501))

    assert entorno.rendiciones() == []


def test_un_producto_agregado_inexistente_es_404(entorno: Entorno) -> None:
    entorno.abrir()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(entorno.contenido([(uuid4(), 0, 0)]))

    assert entorno.rendiciones() == []


def test_faltante_de_un_producto_inactivo_se_acepta(entorno: Entorno) -> None:
    """CAT-05, ADR-068 punto 6 (decisión 2026-11-05): un inactivo con 5 esperadas y 3 contadas
    registra la diferencia -2 y el saldo queda en lo contado."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_1500, 5)
    entorno.abrir()
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.agua_1500)
    entorno.sesion.commit()

    entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 3, 5)]))

    linea = entorno.lineas()[entorno.agua_1500]
    assert (linea.cantidad_esperada, linea.cantidad_contada, linea.diferencia) == (5, 3, -2)
    (diferencia,) = entorno.diferencias()
    assert (diferencia.producto_id, diferencia.cantidad_base) == (entorno.agua_1500, -2)
    assert entorno.saldo(entorno.agua_1500) == 3
    assert entorno.jornada().estado == "EN_RENDICION"


def test_sobrante_de_un_producto_inactivo_exige_reactivar(entorno: Entorno) -> None:
    """CAT-05: un inactivo con 5 esperadas y 7 contadas se rechaza y no escribe nada."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_1500, 5)
    entorno.abrir()
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.agua_1500)
    entorno.sesion.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ProductoInactivoError):
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 7, 5)]))

    _sin_rendicion(entorno, antes)


def test_inactivo_sin_diferencia_se_acepta_sin_movimiento(entorno: Entorno) -> None:
    """Diferencia cero: no hay línea en el libro, así que la actividad no se exige."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_1500, 5)
    entorno.abrir()
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.agua_1500)
    entorno.sesion.commit()

    entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 5, 5)]))

    assert entorno.diferencias() == []
    assert entorno.lineas()[entorno.agua_1500].diferencia == 0


def test_diferencia_de_un_producto_inactivo(entorno: Entorno) -> None:
    """CAT-05, INV-01: un inactivo agregado con 3 contadas (sobrante) se rechaza y no escribe
    nada."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.agua_1500)
    entorno.sesion.commit()
    antes = entorno.cantidad_de_movimientos()

    with pytest.raises(ProductoInactivoError):
        entorno.enviar(entorno.contenido([(entorno.vino, 40, 40), (entorno.agua_1500, 3, 0)]))

    _sin_rendicion(entorno, antes)


def test_el_vendedor_no_rinde(entorno: Entorno) -> None:
    """SEG-06: Juan no tiene `RENDIR_JORNADA`."""
    entorno.abrir()

    with pytest.raises(PermisoRequeridoError):
        entorno.enviar(entorno.contenido([]), actor=entorno.juan)

    assert entorno.rendiciones() == []
    assert entorno.jornada().estado == "ABIERTA"


def test_rendir_la_jornada_de_otra_organizacion_es_404(
    entorno: Entorno, db_session: Session
) -> None:
    """INV-21: la jornada existe pero en otra organización."""
    entorno.abrir()
    ajena = Entorno(db_session)
    ajena.sesion.commit()

    with pytest.raises(RecursoNoEncontradoError):
        entorno.enviar(
            entorno.contenido([]),
            actor=ajena.supervisora,
            organizacion_id=ajena.org,
        )

    assert entorno.jornada().estado == "ABIERTA"


def test_el_doble_envio_devuelve_el_resultado_original(entorno: Entorno) -> None:
    """INV-06, SYN-02: el mismo `operation_id` no rinde dos veces ni escribe otra diferencia."""
    entorno.cargar(entorno.vino, 40)
    entorno.abrir()
    operation_id = uuid4()
    contenido = entorno.contenido([(entorno.vino, 37, 40)])

    primero = entorno.enviar(contenido, operation_id=operation_id)
    segundo = entorno.enviar(contenido, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.rendiciones()) == 1
    assert len(entorno.diferencias()) == 1
    assert entorno.saldo(entorno.vino) == 37


def test_una_falla_a_mitad_de_la_rendicion_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: si la escritura de la segunda diferencia falla, no queda rendición, líneas ni
    movimientos y la jornada sigue `ABIERTA`."""
    entorno.cargar(entorno.vino, 40)
    entorno.cargar(entorno.agua_500, 12, "300")
    entorno.abrir()
    antes = entorno.cantidad_de_movimientos()
    original = stock_repository.insertar_movimiento
    escritas: list[int] = []

    def falla_la_segunda(*args: Any, **kwargs: Any) -> Any:
        escritas.append(1)
        if len(escritas) == 2:
            raise RuntimeError("falla inyectada")
        return original(*args, **kwargs)

    monkeypatch.setattr(stock_repository, "insertar_movimiento", falla_la_segunda)

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(entorno.contenido([(entorno.vino, 37, 40), (entorno.agua_500, 14, 12)]))

    assert len(escritas) == 2
    _sin_rendicion(entorno, antes)
