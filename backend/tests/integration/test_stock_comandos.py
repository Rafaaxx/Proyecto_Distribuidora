"""Tarea 6.1: `UBICACION_CREAR`, `UBICACION_MODIFICAR` y `STOCK_INICIAL_REGISTRAR`
v1 por el bus, contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `test_cuentas_corrientes_comandos.py`). La cobertura por escenario
de la spec vía HTTP es del grupo 9; acá se prueba el comando: catálogo, esquema
estricto, permiso, escritura, auditoría única del bus e idempotencia.

Reglas citadas: STK-02, STK-03, STK-05, INV-01, INV-04, INV-06, SYN-02, SYN-06,
CST-11, `01` §21, ADR-022 y `design.md` D1, D2, D4, D5, D6, D7, D8.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql, desactivar_producto_sql

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.costeo import service as costeo_service
from app.modules.costeo.domain.errores import CostoInvalidoError
from app.modules.identidad.models import Auditoria
from app.modules.stock import commands as stock_commands
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import (
    NombreDuplicadoError,
    ProductoConOperacionesError,
    ProductoInactivoError,
    ProductoRepetidoError,
    RecursoNoEncontradoError,
    StockInsuficienteError,
    UbicacionConStockError,
    UbicacionInactivaError,
    VehiculoRequiereTomaError,
)
from app.modules.stock.models import StockMovimiento, Ubicacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

CREAR = "UBICACION_CREAR"
MODIFICAR = "UBICACION_MODIFICAR"
INICIAL = "STOCK_INICIAL_REGISTRAR"

PERMISOS_COMPLETOS = frozenset({"ADMIN_CONFIGURACION", "IMPORTAR_DATOS"})

_MANEJADORES = {
    CREAR: stock_commands.manejar_ubicacion_crear,
    MODIFICAR: stock_commands.manejar_ubicacion_modificar,
    INICIAL: stock_commands.manejar_stock_inicial_registrar,
}


class Entorno:
    def __init__(self, sesion: Session, *, permisos: frozenset[str] = PERMISOS_COMPLETOS) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.producto_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.otro_producto_id = crear_producto_sql(sesion, self.org, nombre="Vino B")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        sesion.commit()

    def contenido_inicial(self, **cambios: object) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "ubicacion_id": str(self.deposito_id),
            "lineas": [
                {
                    "producto_id": str(self.producto_id),
                    "cantidad_base": 60,
                    "costo_unitario": "1000.00",
                }
            ],
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(
        self, tipo: str, contenido: dict[str, Any], *, operation_id: UUID | None = None
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
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

    def enviar(
        self, tipo: str, contenido: dict[str, Any], *, operation_id: UUID | None = None
    ) -> Comando:
        sobre = self.sobre(tipo, contenido, operation_id=operation_id)
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return _MANEJADORES[tipo](  # type: ignore[operator]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def ubicaciones(self) -> list[Ubicacion]:
        return list(
            self.sesion.scalars(
                select(Ubicacion).where(Ubicacion.organizacion_id == self.org)
            ).all()
        )

    def movimientos(self, producto_id: UUID | None = None) -> list[StockMovimiento]:
        consulta = select(StockMovimiento).where(StockMovimiento.organizacion_id == self.org)
        if producto_id is not None:
            consulta = consulta.where(StockMovimiento.producto_id == producto_id)
        return list(self.sesion.scalars(consulta.order_by(StockMovimiento.registered_at)).all())

    def saldo(self, producto_id: UUID, ubicacion_id: UUID | None = None) -> int:
        return stock_service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=producto_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
        )

    def promedio(self, producto_id: UUID) -> Decimal | None:
        return costeo_service.obtener_promedio(self.org, self.sesion, producto_id)

    def auditorias(self, operation_id: UUID) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            )
            or 0
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- catálogo y esquema ------------------------------------------------------


@pytest.mark.parametrize("tipo", [CREAR, MODIFICAR, INICIAL])
def test_los_tipos_estan_declarados_online_y_sin_offline_con_handler_v1(tipo: str) -> None:
    """`02` §6.5: solo online (D1, D2)."""
    declarado = catalogo_bus.tipo_declarado(tipo)

    assert declarado is not None
    assert declarado.admite_online is True
    assert declarado.admite_offline is False
    handler = registro.resolver_handler(tipo, 1)
    assert (handler.tipo, handler.version) == (tipo, 1)


def test_el_esquema_de_stock_inicial_acepta_lineas_con_cantidad_entera_y_costo_string() -> None:
    contenido = stock_commands.StockInicialRegistrarContenidoV1.model_validate(
        {
            "ubicacion_id": str(uuid4()),
            "lineas": [
                {"producto_id": str(uuid4()), "cantidad_base": 60, "costo_unitario": "1000.50"},
                {"producto_id": str(uuid4()), "cantidad_base": -12},
            ],
        }
    )

    assert contenido.lineas[0].costo_unitario == "1000.50"
    assert contenido.lineas[1].cantidad_base == -12
    assert contenido.lineas[1].costo_unitario is None


@pytest.mark.parametrize("cantidad", ["12", True, None], ids=["texto", "booleano", "nulo"])
def test_una_cantidad_que_no_es_un_entero_se_rechaza_en_el_esquema(
    entorno: Entorno, cantidad: object
) -> None:
    """INV-04: cantidades enteras, sin conversión silenciosa."""
    linea = {"producto_id": str(entorno.producto_id), "cantidad_base": cantidad}
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=[linea]))

    assert entorno.movimientos() == []


def test_el_esquema_rechaza_una_cantidad_con_decimales() -> None:
    """INV-04: un número con decimales no se convierte en silencio (la huella del
    bus tampoco lo admite, así que este caso solo llega hasta el esquema)."""
    with pytest.raises(ValueError):
        stock_commands.LineaStockInicialContenidoV1.model_validate(
            {"producto_id": str(uuid4()), "cantidad_base": 1.5, "costo_unitario": "5"}
        )
    linea = stock_commands.LineaStockInicialContenidoV1.model_validate(
        {"producto_id": str(uuid4()), "cantidad_base": 2, "costo_unitario": "5"}
    )
    assert linea.cantidad_base == 2


@pytest.mark.parametrize(
    ("tipo", "cambios"),
    [
        (CREAR, {"organizacion_id": str(uuid4())}),
        (CREAR, {"activo": False}),
        (CREAR, {"tipo": "CAMION"}),
        (CREAR, {"requiere_toma": "si"}),
        (INICIAL, {"organizacion_id": str(uuid4())}),
        (INICIAL, {"ubicacion_id": "no-es-un-uuid"}),
        (INICIAL, {"lineas": "no-es-una-lista"}),
    ],
)
def test_un_contenido_malformado_se_rechaza_sin_efectos(
    entorno: Entorno, tipo: str, cambios: dict[str, object]
) -> None:
    """SYN-06: catálogos cerrados y `extra="forbid"`: la organización sale del
    token."""
    if tipo == CREAR:
        contenido: dict[str, Any] = {
            "nombre": "Camión 1",
            "tipo": "DEPOSITO",
            "requiere_toma": False,
        }
        contenido.update(cambios)
    else:
        contenido = entorno.contenido_inicial(**cambios)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(tipo, contenido)

    assert len(entorno.ubicaciones()) == 1  # solo el depósito del entorno
    assert entorno.movimientos() == []


@pytest.mark.parametrize("faltante", ["ubicacion_id", "lineas"])
def test_un_campo_obligatorio_faltante_de_stock_inicial_se_rechaza(
    entorno: Entorno, faltante: str
) -> None:
    contenido = entorno.contenido_inicial()
    del contenido[faltante]

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(INICIAL, contenido)


# --- ubicaciones (STK-02, D2, D7, D8) -----------------------------------------


def test_alta_de_un_deposito_audita_una_sola_vez_y_devuelve_el_id(entorno: Entorno) -> None:
    operation_id = uuid4()

    comando = entorno.enviar(
        CREAR,
        {"nombre": "Depósito central", "tipo": "DEPOSITO", "requiere_toma": False},
        operation_id=operation_id,
    )

    assert comando.estado == "ACEPTADO"
    creada = next(u for u in entorno.ubicaciones() if u.nombre == "Depósito central")
    assert creada.activo is True
    assert creada.tipo == "DEPOSITO"
    assert creada.requiere_toma is False
    assert creada.actualizado_por_id == entorno.usuario_id
    assert comando.resultado == {"ubicacion_id": str(creada.id)}
    assert entorno.auditorias(operation_id) == 1  # ADR-022: la única es la del bus


def test_el_alta_de_un_vehiculo_con_toma_se_acepta_y_sin_toma_se_rechaza(
    entorno: Entorno,
) -> None:
    """STK-02, D7: un vehículo siempre requiere toma."""
    entorno.enviar(CREAR, {"nombre": "Camión 1", "tipo": "VEHICULO", "requiere_toma": True})

    with pytest.raises(VehiculoRequiereTomaError):
        entorno.enviar(CREAR, {"nombre": "Camión 2", "tipo": "VEHICULO", "requiere_toma": False})

    assert sorted(u.nombre for u in entorno.ubicaciones()) == ["Camión 1", "Depósito"]


def test_un_nombre_repetido_sin_distinguir_mayusculas_es_duplicado(entorno: Entorno) -> None:
    with pytest.raises(NombreDuplicadoError):
        entorno.enviar(CREAR, {"nombre": " depósito ", "tipo": "OTRO", "requiere_toma": False})

    assert len(entorno.ubicaciones()) == 1


def test_modificar_cambia_los_datos_y_reactiva(entorno: Entorno) -> None:
    contenido = {
        "ubicacion_id": str(entorno.deposito_id),
        "nombre": "Depósito norte",
        "tipo": "OTRO",
        "requiere_toma": True,
        "activo": False,
    }
    entorno.enviar(MODIFICAR, contenido)
    (ubicacion,) = entorno.ubicaciones()
    assert (ubicacion.nombre, ubicacion.tipo, ubicacion.requiere_toma, ubicacion.activo) == (
        "Depósito norte",
        "OTRO",
        True,
        False,
    )

    entorno.enviar(MODIFICAR, {**contenido, "activo": True})

    (ubicacion,) = entorno.ubicaciones()
    assert ubicacion.activo is True


def test_no_se_desactiva_una_ubicacion_con_stock(entorno: Entorno) -> None:
    """D8: `UBICACION_CON_STOCK`, y la ubicación sigue activa."""
    entorno.enviar(INICIAL, entorno.contenido_inicial())

    with pytest.raises(UbicacionConStockError):
        entorno.enviar(
            MODIFICAR,
            {
                "ubicacion_id": str(entorno.deposito_id),
                "nombre": "Depósito",
                "tipo": "DEPOSITO",
                "requiere_toma": False,
                "activo": False,
            },
        )

    (ubicacion,) = entorno.ubicaciones()
    assert ubicacion.activo is True


def test_modificar_una_ubicacion_ajena_o_inexistente_es_404(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion)
    ajena = crear_ubicacion_sql(entorno.sesion, otra.id, nombre="Ajena")
    entorno.sesion.commit()

    for ubicacion_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.enviar(
                MODIFICAR,
                {
                    "ubicacion_id": str(ubicacion_id),
                    "nombre": "Nuevo",
                    "tipo": "DEPOSITO",
                    "requiere_toma": False,
                    "activo": True,
                },
            )

    (ubicacion,) = entorno.ubicaciones()
    assert ubicacion.nombre == "Depósito"


# --- stock inicial (D4, D5, D6) ---------------------------------------------------


def test_stock_inicial_registra_movimiento_saldo_promedio_y_audita_una_vez(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()

    comando = entorno.enviar(INICIAL, entorno.contenido_inicial(), operation_id=operation_id)

    assert comando.estado == "ACEPTADO"
    (movimiento,) = entorno.movimientos()
    assert movimiento.tipo == "STOCK_INICIAL"
    assert movimiento.cantidad_base == 60
    assert movimiento.costo_unitario == Decimal("1000.000000")
    assert movimiento.origen_tipo == "STOCK_INICIAL"
    assert movimiento.origen_id == operation_id  # D5
    assert movimiento.operation_id == operation_id
    assert movimiento.occurred_at == MOMENTO
    assert movimiento.usuario_id == entorno.usuario_id
    assert movimiento.dispositivo_id == entorno.dispositivo_id  # del sobre
    assert entorno.saldo(entorno.producto_id) == 60
    assert entorno.promedio(entorno.producto_id) == Decimal("1000.000000")
    assert entorno.auditorias(operation_id) == 1


def test_el_resultado_no_expone_costos_y_lista_las_lineas(entorno: Entorno) -> None:
    comando = entorno.enviar(INICIAL, entorno.contenido_inicial())

    (movimiento,) = entorno.movimientos()
    assert comando.resultado == {
        "ubicacion_id": str(entorno.deposito_id),
        "lineas": [
            {
                "producto_id": str(entorno.producto_id),
                "movimiento_id": str(movimiento.id),
                "cantidad_base": 60,
                "saldo": 60,
            }
        ],
    }


def test_dos_ingresos_recalculan_el_promedio_y_una_correccion_negativa_no_lo_toca(
    entorno: Entorno,
) -> None:
    """CST-11 (ejemplo de `01` §6.2) y D4: el negativo egresa al promedio vigente."""
    entorno.enviar(INICIAL, entorno.contenido_inicial())
    entorno.enviar(
        INICIAL,
        entorno.contenido_inicial(
            lineas=[
                {
                    "producto_id": str(entorno.producto_id),
                    "cantidad_base": 60,
                    "costo_unitario": "1100",
                }
            ]
        ),
    )
    assert entorno.promedio(entorno.producto_id) == Decimal("1050.000000")

    entorno.enviar(
        INICIAL,
        entorno.contenido_inicial(
            lineas=[{"producto_id": str(entorno.producto_id), "cantidad_base": -12}]
        ),
    )

    assert entorno.saldo(entorno.producto_id) == 108
    assert entorno.promedio(entorno.producto_id) == Decimal("1050.000000")
    (correccion,) = [m for m in entorno.movimientos() if m.cantidad_base < 0]
    assert correccion.cantidad_base == -12
    assert correccion.costo_unitario == Decimal("1050.000000")


def test_varias_lineas_se_registran_de_forma_atomica(entorno: Entorno) -> None:
    """INV-01: una línea inválida no deja ni la primera."""
    lineas = [
        {"producto_id": str(entorno.producto_id), "cantidad_base": 10, "costo_unitario": "5"},
        {"producto_id": str(entorno.otro_producto_id), "cantidad_base": -1},
    ]

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=lineas))

    assert entorno.movimientos() == []
    assert entorno.saldo(entorno.producto_id) == 0
    assert entorno.promedio(entorno.producto_id) is None


def test_dos_lineas_validas_registran_dos_movimientos(entorno: Entorno) -> None:
    lineas = [
        {"producto_id": str(entorno.producto_id), "cantidad_base": 10, "costo_unitario": "5"},
        {"producto_id": str(entorno.otro_producto_id), "cantidad_base": 20, "costo_unitario": "7"},
    ]

    entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=lineas))

    assert entorno.saldo(entorno.producto_id) == 10
    assert entorno.saldo(entorno.otro_producto_id) == 20
    assert len(entorno.movimientos()) == 2


def test_un_producto_repetido_en_el_comando_se_rechaza(entorno: Entorno) -> None:
    linea = {"producto_id": str(entorno.producto_id), "cantidad_base": 5, "costo_unitario": "5"}

    with pytest.raises(ProductoRepetidoError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=[linea, linea]))

    assert entorno.movimientos() == []


@pytest.mark.parametrize("costo", ["0", "-5", "1.1234567", "abc", 1000])
def test_un_costo_invalido_se_rechaza_como_error_de_dominio(
    entorno: Entorno, costo: object
) -> None:
    """D6: string decimal positivo con hasta 6 decimales; un número JSON no."""
    linea = {"producto_id": str(entorno.producto_id), "cantidad_base": 5, "costo_unitario": costo}

    with pytest.raises(CostoInvalidoError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=[linea]))

    assert entorno.movimientos() == []


def test_una_correccion_que_deja_negativo_el_saldo_se_rechaza(entorno: Entorno) -> None:
    entorno.enviar(INICIAL, entorno.contenido_inicial())

    with pytest.raises(StockInsuficienteError):
        entorno.enviar(
            INICIAL,
            entorno.contenido_inicial(
                lineas=[{"producto_id": str(entorno.producto_id), "cantidad_base": -61}]
            ),
        )

    assert entorno.saldo(entorno.producto_id) == 60


def test_una_ubicacion_inactiva_ajena_o_inexistente_no_recibe_stock(entorno: Entorno) -> None:
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Inactiva", activo=False)
    otra = crear_organizacion(entorno.sesion)
    ajena = crear_ubicacion_sql(entorno.sesion, otra.id, nombre="Ajena")
    entorno.sesion.commit()

    with pytest.raises(UbicacionInactivaError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(ubicacion_id=str(inactiva)))
    for ubicacion_id in (ajena, uuid4()):
        with pytest.raises(RecursoNoEncontradoError):
            entorno.enviar(INICIAL, entorno.contenido_inicial(ubicacion_id=str(ubicacion_id)))

    assert entorno.movimientos() == []


def test_un_producto_ajeno_o_inexistente_es_404(entorno: Entorno) -> None:
    otra = crear_organizacion(entorno.sesion)
    ajeno = crear_producto_sql(entorno.sesion, otra.id)
    entorno.sesion.commit()

    for producto_id in (ajeno, uuid4()):
        linea = {"producto_id": str(producto_id), "cantidad_base": 5, "costo_unitario": "5"}
        with pytest.raises(RecursoNoEncontradoError):
            entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=[linea]))

    assert entorno.movimientos() == []


def test_un_producto_con_movimientos_de_otro_tipo_no_admite_stock_inicial(
    entorno: Entorno,
) -> None:
    """D4: `PRODUCTO_CON_OPERACIONES` (el otro tipo entra por el servicio)."""
    entorno.enviar(INICIAL, entorno.contenido_inicial())
    stock_service.registrar_movimientos(
        entorno.org,
        entorno.sesion,
        RELOJ,
        lineas=[
            stock_service.LineaDeMovimiento(
                producto_id=entorno.producto_id,
                ubicacion_id=entorno.deposito_id,
                cantidad_base=6,
                tipo="COMPRA",
                costo_unitario="1200",
                origen_tipo="COMPRA",
                origen_id=uuid4(),
            )
        ],
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        operation_id=uuid4(),
        occurred_at=MOMENTO,
    )
    entorno.sesion.commit()

    with pytest.raises(ProductoConOperacionesError):
        entorno.enviar(INICIAL, entorno.contenido_inicial())

    assert entorno.saldo(entorno.producto_id) == 66


# --- cobertura por escenario de `stock-inicial` (tarea 9.1) --------------------


def test_un_ingreso_en_otra_ubicacion_recalcula_el_promedio_de_la_organizacion(
    entorno: Entorno,
) -> None:
    """Escenario "Stock inicial en otra ubicación recalcula el promedio" (CST-10,
    CST-11): el promedio es por producto y organización, no por ubicación."""
    vehiculo_id = crear_ubicacion_sql(
        entorno.sesion, entorno.org, nombre="Camioneta", tipo="VEHICULO", requiere_toma=True
    )
    entorno.sesion.commit()
    entorno.enviar(INICIAL, entorno.contenido_inicial())

    entorno.enviar(
        INICIAL,
        entorno.contenido_inicial(
            ubicacion_id=str(vehiculo_id),
            lineas=[
                {
                    "producto_id": str(entorno.producto_id),
                    "cantidad_base": 60,
                    "costo_unitario": "1100.000000",
                }
            ],
        ),
    )

    assert entorno.promedio(entorno.producto_id) == Decimal("1050.000000")
    assert entorno.saldo(entorno.producto_id) == 60
    assert entorno.saldo(entorno.producto_id, vehiculo_id) == 60


def test_un_costo_mal_cargado_se_corrige_llevando_el_stock_a_cero_y_recargando(
    entorno: Entorno,
) -> None:
    """Escenario "Corregir un costo mal cargado" (CST-11, D4): con stock previo
    cero el promedio pasa a ser el costo del nuevo ingreso."""
    producto = str(entorno.producto_id)
    entorno.enviar(
        INICIAL,
        entorno.contenido_inicial(
            lineas=[{"producto_id": producto, "cantidad_base": 60, "costo_unitario": "10000"}]
        ),
    )
    assert entorno.promedio(entorno.producto_id) == Decimal("10000.000000")

    entorno.enviar(
        INICIAL, entorno.contenido_inicial(lineas=[{"producto_id": producto, "cantidad_base": -60}])
    )
    entorno.enviar(
        INICIAL,
        entorno.contenido_inicial(
            lineas=[{"producto_id": producto, "cantidad_base": 60, "costo_unitario": "1000"}]
        ),
    )

    assert entorno.saldo(entorno.producto_id) == 60
    assert entorno.promedio(entorno.producto_id) == Decimal("1000.000000")


def test_un_comando_con_ubicacion_o_producto_inactivos_se_rechaza_sin_efectos(
    entorno: Entorno,
) -> None:
    """Escenario "Ubicación o producto inactivos" (CAT-05, D8) por el bus."""
    inactiva = crear_ubicacion_sql(entorno.sesion, entorno.org, nombre="Cerrada", activo=False)
    entorno.sesion.commit()
    with pytest.raises(UbicacionInactivaError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(ubicacion_id=str(inactiva)))

    desactivar_producto_sql(entorno.sesion, entorno.org, entorno.producto_id)
    entorno.sesion.commit()
    with pytest.raises(ProductoInactivoError):
        entorno.enviar(INICIAL, entorno.contenido_inicial())

    assert entorno.movimientos() == []
    assert entorno.promedio(entorno.producto_id) is None


# --- idempotencia (INV-06, SYN-02) ----------------------------------------------


def test_el_reenvio_devuelve_el_resultado_original_sin_duplicar(entorno: Entorno) -> None:
    operation_id = uuid4()

    primero = entorno.enviar(INICIAL, entorno.contenido_inicial(), operation_id=operation_id)
    segundo = entorno.enviar(INICIAL, entorno.contenido_inicial(), operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.movimientos()) == 1
    assert entorno.saldo(entorno.producto_id) == 60
    assert entorno.auditorias(operation_id) == 1


def test_el_mismo_operation_id_con_otro_contenido_es_inconsistente(entorno: Entorno) -> None:
    operation_id = uuid4()
    entorno.enviar(INICIAL, entorno.contenido_inicial(), operation_id=operation_id)
    otro = [{"producto_id": str(entorno.producto_id), "cantidad_base": 5, "costo_unitario": "9"}]

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(INICIAL, entorno.contenido_inicial(lineas=otro), operation_id=operation_id)

    assert entorno.saldo(entorno.producto_id) == 60


def test_el_alta_repetida_con_el_mismo_operation_id_crea_una_sola_ubicacion(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    contenido = {"nombre": "Camión 1", "tipo": "VEHICULO", "requiere_toma": True}

    primero = entorno.enviar(CREAR, contenido, operation_id=operation_id)
    segundo = entorno.enviar(CREAR, contenido, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.ubicaciones()) == 2
    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(CREAR, {**contenido, "nombre": "Camión 2"}, operation_id=operation_id)


# --- permiso (D1, D2, SEG-06) -----------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "permisos"),
    [
        (CREAR, frozenset({"IMPORTAR_DATOS"})),
        (MODIFICAR, frozenset({"IMPORTAR_DATOS"})),
        (INICIAL, frozenset({"ADMIN_CONFIGURACION"})),
    ],
)
def test_sin_el_permiso_de_cada_comando_se_rechaza_sin_efectos_ni_reserva(
    db_session: Session, tipo: str, permisos: frozenset[str]
) -> None:
    entorno = Entorno(db_session, permisos=permisos)
    operation_id = uuid4()
    contenido = {
        CREAR: {"nombre": "Nueva", "tipo": "OTRO", "requiere_toma": False},
        MODIFICAR: {
            "ubicacion_id": str(entorno.deposito_id),
            "nombre": "Cambiada",
            "tipo": "OTRO",
            "requiere_toma": False,
            "activo": True,
        },
        INICIAL: entorno.contenido_inicial(),
    }[tipo]

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(tipo, contenido, operation_id=operation_id)

    assert error.value.status_http == 403
    assert [u.nombre for u in entorno.ubicaciones()] == ["Depósito"]
    assert entorno.movimientos() == []
    assert (
        db_session.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    ), "El rechazo por permiso no deja reserva del operation_id."


# --- INV-01 y modo offline ----------------------------------------------------------


def test_una_falla_de_dominio_revierte_tambien_la_reserva_y_la_auditoria(
    entorno: Entorno,
) -> None:
    operation_id = uuid4()
    linea = {"producto_id": str(entorno.producto_id), "cantidad_base": 5, "costo_unitario": "0"}

    with pytest.raises(CostoInvalidoError):
        entorno.enviar(
            INICIAL, entorno.contenido_inicial(lineas=[linea]), operation_id=operation_id
        )

    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )
    assert entorno.auditorias(operation_id) == 0


@pytest.mark.parametrize("tipo", [CREAR, MODIFICAR, INICIAL])
def test_el_lote_rechaza_los_comandos_de_stock_enviados_sin_conexion(
    entorno: Entorno, tipo: str
) -> None:
    """`02` §6.5: el bus real, no solo el catálogo, rechaza el modo `OFFLINE` con
    un código estable y sin efectos."""
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=tipo,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=entorno.contenido_inicial(),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.movimientos() == []
    assert (
        entorno.sesion.scalar(
            select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
        )
        == 0
    )
