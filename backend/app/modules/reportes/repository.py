"""Consultas de solo lectura de los reportes (SQLAlchemy Core; `design.md` D6 del change 26).

Toda consulta filtra por `organizacion_id` (INV-21) y suma en la base (`02` §14, REP-01): ninguna
cifra se calcula en Python. Los importes y las cantidades salen de los valores congelados de cada
operación, nunca de precios ni costos actuales (REP-05, INV-10). No escribe ni toma bloqueos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    Numeric,
    Subquery,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    select,
)
from sqlalchemy.orm import Session

from app.modules.catalogo.models import Presentacion, Producto
from app.modules.clientes.models import Cliente
from app.modules.cobranzas.models import Cobranza, CobranzaMedio
from app.modules.configuracion.models import MedioPago, Motivo
from app.modules.cuentas_corrientes.models import SaldoCuenta
from app.modules.identidad.models import Usuario
from app.modules.proveedores.models import Proveedor
from app.modules.reportes.domain.armado import (
    CifrasCrudasDeAjuste,
    CifrasCrudasDeVentas,
    ProductoVendidoCrudo,
)
from app.modules.reportes.domain.paginacion import (
    TAMANO_DE_PAGINA,
    Sobre,
    armar_sobre,
    desplazamiento_de,
)
from app.modules.stock.models import (
    AjusteStock,
    AjusteStockLinea,
    Jornada,
    Rendicion,
    RendicionLinea,
    StockMovimiento,
    Ubicacion,
)
from app.modules.sync.models import Comando, ComandoRechazado, Observacion
from app.modules.ventas.models import Venta, VentaAnulacion, VentaLinea

ESTADO_CONFIRMADA = "CONFIRMADA"
ESTADO_ANULADA = "ANULADA"

# Punto de extensión de la facturación (`design.md` D5): la utilidad de una línea es
# `importe_neto - costo_total - IVA absorbido asignado` (REP-04). `ajuste_iva_absorbido` lo crea el
# módulo de facturación (`03` §13); mientras no exista, el IVA absorbido asignado es cero en toda
# línea. Cuando exista, esta ÚNICA expresión pasa a ser la suma de sus ajustes por línea.
IVA_ABSORBIDO_POR_LINEA = literal(Decimal("0.00"), Numeric(14, 2))


@dataclass(frozen=True)
class FilaPorDiaCruda:
    fecha: date
    cifras: CifrasCrudasDeVentas


@dataclass(frozen=True)
class FilaPorVendedorCruda:
    vendedor_id: UUID
    vendedor_nombre: str
    cifras: CifrasCrudasDeVentas


@dataclass(frozen=True)
class PresentacionVendidaCruda:
    presentacion_id: UUID
    nombre: str
    unidades_presentacion: int
    cantidad: int
    unidades_base: int


@dataclass(frozen=True)
class ProductoCrudo:
    producto_id: UUID
    codigo: str
    nombre: str
    cifras: ProductoVendidoCrudo
    presentaciones: list[PresentacionVendidaCruda]


@dataclass(frozen=True)
class VentaAnuladaCruda:
    venta_id: UUID
    numero: str
    occurred_at: datetime
    cliente_id: UUID
    cliente_nombre: str
    vendedor_id: UUID
    vendedor_nombre: str
    total: Decimal
    anulada_en: datetime | None
    motivo: str | None
    devuelve_dinero: bool | None


@dataclass(frozen=True)
class AnuladasCrudas:
    cantidad: int
    total: Decimal
    ventas: Sobre[VentaAnuladaCruda]


def _filtros_de_ventas(
    organizacion_id: UUID,
    *,
    estado: str,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
) -> list[ColumnElement[bool]]:
    """Las ventas del período: de la organización, en el estado dado, con `occurred_at` en
    `[inicio, fin)` (REP-02, TR-04) y, si se pide, de un vendedor."""
    filtros: list[ColumnElement[bool]] = [
        Venta.organizacion_id == organizacion_id,
        Venta.estado == estado,
        Venta.occurred_at >= inicio,
        Venta.occurred_at < fin,
    ]
    if vendedor_id is not None:
        filtros.append(Venta.usuario_id == vendedor_id)
    return filtros


def _lineas_por_venta(organizacion_id: UUID, filtros: list[ColumnElement[bool]]) -> Subquery:
    """Las líneas de las ventas filtradas, sumadas por venta con sus valores congelados.

    Cajas equivalentes de una línea = `cantidad_base / unidades_referencia` de ESA línea
    (congelado, PRC-23, REP-05), en `numeric` exacto. La utilidad y el costo se suman solo sobre
    las líneas con costo; las que no lo tienen se cuentan aparte (ADR-054, VTA-05).
    """
    sin_costo = VentaLinea.costo_total.is_(None)
    utilidad_de_linea = case(
        (
            VentaLinea.costo_total.is_not(None),
            VentaLinea.importe_neto - VentaLinea.costo_total - IVA_ABSORBIDO_POR_LINEA,
        ),
        else_=None,
    )
    return (
        select(
            VentaLinea.venta_id.label("venta_id"),
            func.sum(VentaLinea.cantidad_base).label("unidades_base"),
            func.sum(
                cast(VentaLinea.cantidad_base, Numeric) / VentaLinea.unidades_referencia
            ).label("cajas"),
            func.sum(VentaLinea.importe_bruto).label("bruto"),
            func.sum(VentaLinea.importe_descuento).label("descuento"),
            func.sum(VentaLinea.costo_total).label("costo"),
            func.sum(utilidad_de_linea).label("utilidad"),
            func.count().filter(sin_costo).label("lineas_sin_costo"),
            func.sum(VentaLinea.importe_neto).filter(sin_costo).label("neto_sin_costo"),
        )
        .join(
            Venta,
            and_(
                Venta.organizacion_id == VentaLinea.organizacion_id,
                Venta.id == VentaLinea.venta_id,
            ),
        )
        .where(VentaLinea.organizacion_id == organizacion_id, *filtros)
        .group_by(VentaLinea.venta_id)
        .subquery("lineas")
    )


def _columnas_de_cifras(lineas: Subquery) -> list[Any]:
    """Las sumas de un nivel (resumen, día o vendedor): la cabecera de la venta aporta cantidad,
    neto, IVA y total (los que concilian con el listado, INV-14); las líneas, el resto."""

    def suma(columna: Any) -> Any:
        return func.coalesce(func.sum(columna), 0)

    return [
        func.count(Venta.id).label("cantidad_ventas"),
        suma(lineas.c.cajas).label("cajas"),
        suma(lineas.c.unidades_base).label("unidades_base"),
        suma(lineas.c.bruto).label("bruto"),
        suma(lineas.c.descuento).label("descuento"),
        suma(Venta.total_neto).label("neto"),
        suma(Venta.total_iva).label("iva"),
        suma(Venta.total).label("total"),
        suma(lineas.c.costo).label("costo"),
        suma(lineas.c.utilidad).label("utilidad"),
        suma(lineas.c.lineas_sin_costo).label("lineas_sin_costo"),
        suma(lineas.c.neto_sin_costo).label("neto_sin_costo"),
    ]


def _cifras_de(fila: Any) -> CifrasCrudasDeVentas:
    return CifrasCrudasDeVentas(
        cantidad_ventas=int(fila.cantidad_ventas),
        cajas_equivalentes=Decimal(fila.cajas),
        unidades_base=int(fila.unidades_base),
        importe_bruto=Decimal(fila.bruto),
        importe_descuento=Decimal(fila.descuento),
        importe_neto=Decimal(fila.neto),
        importe_iva=Decimal(fila.iva),
        total=Decimal(fila.total),
        costo_vendido=Decimal(fila.costo),
        utilidad=Decimal(fila.utilidad),
        lineas_sin_costo=int(fila.lineas_sin_costo),
        neto_sin_costo=Decimal(fila.neto_sin_costo),
    )


def _ventas_con_lineas(lineas: Subquery) -> Any:
    return Venta.__table__.outerjoin(lineas, lineas.c.venta_id == Venta.id)


def resumen_de_ventas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
) -> CifrasCrudasDeVentas:
    """Las cifras de todas las ventas `CONFIRMADA` del período (una sola fila, ceros si no hay)."""
    filtros = _filtros_de_ventas(
        organizacion_id, estado=ESTADO_CONFIRMADA, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    lineas = _lineas_por_venta(organizacion_id, filtros)
    consulta = (
        select(*_columnas_de_cifras(lineas)).select_from(_ventas_con_lineas(lineas)).where(*filtros)
    )
    return _cifras_de(sesion.execute(consulta).one())


def ventas_por_dia(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    zona_horaria: str,
    pagina: int,
) -> Sobre[FilaPorDiaCruda]:
    """Las mismas cifras por fecha de negocio (`occurred_at` en la zona de la organización,
    TR-04), de la más reciente a la más vieja, de a `TAMANO_DE_PAGINA` días (D14)."""
    filtros = _filtros_de_ventas(
        organizacion_id, estado=ESTADO_CONFIRMADA, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    lineas = _lineas_por_venta(organizacion_id, filtros)
    fecha = cast(func.timezone(zona_horaria, Venta.occurred_at), Date).label("fecha")
    consulta = (
        select(fecha, *_columnas_de_cifras(lineas))
        .select_from(_ventas_con_lineas(lineas))
        .where(*filtros)
        .group_by(fecha)
        .order_by(fecha.desc())
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    )
    total_filas = sesion.execute(
        select(func.count()).select_from(
            select(fecha).select_from(Venta.__table__).where(*filtros).group_by(fecha).subquery()
        )
    ).scalar_one()
    filas = [
        FilaPorDiaCruda(fecha=fila.fecha, cifras=_cifras_de(fila))
        for fila in sesion.execute(consulta)
    ]
    return armar_sobre(filas, pagina=pagina, total_filas=int(total_filas))


def ventas_por_vendedor(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
) -> list[FilaPorVendedorCruda]:
    """Las mismas cifras por usuario de la venta, por neto descendente."""
    filtros = _filtros_de_ventas(
        organizacion_id, estado=ESTADO_CONFIRMADA, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    lineas = _lineas_por_venta(organizacion_id, filtros)
    desde = _ventas_con_lineas(lineas).join(
        Usuario.__table__,
        and_(Usuario.organizacion_id == Venta.organizacion_id, Usuario.id == Venta.usuario_id),
    )
    consulta = (
        select(
            Venta.usuario_id.label("vendedor_id"),
            Usuario.nombre.label("vendedor_nombre"),
            *_columnas_de_cifras(lineas),
        )
        .select_from(desde)
        .where(*filtros)
        .group_by(Venta.usuario_id, Usuario.nombre)
        .order_by(func.sum(Venta.total_neto).desc(), Usuario.nombre, Venta.usuario_id)
    )
    return [
        FilaPorVendedorCruda(
            vendedor_id=fila.vendedor_id,
            vendedor_nombre=fila.vendedor_nombre,
            cifras=_cifras_de(fila),
        )
        for fila in sesion.execute(consulta)
    ]


def ventas_por_producto(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    pagina: int,
) -> Sobre[ProductoCrudo]:
    """Las ventas `CONFIRMADA` del período por producto, por neto descendente (REP-03, D4), de a
    `TAMANO_DE_PAGINA` productos (D14); el detalle por presentación es solo el de la página.

    Las cajas equivalentes de cada línea usan SUS `unidades_referencia` congeladas (PRC-23,
    REP-05); se suman exactas en `numeric` y se redondean una sola vez al armar. El detalle agrupa
    por presentación y por las `unidades_presentacion` congeladas, con el nombre actual de la
    presentación.
    """
    filtros = _filtros_de_ventas(
        organizacion_id, estado=ESTADO_CONFIRMADA, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    de_ventas = VentaLinea.__table__.join(
        Venta.__table__,
        and_(
            Venta.organizacion_id == VentaLinea.organizacion_id,
            Venta.id == VentaLinea.venta_id,
        ),
    )
    neto = func.sum(VentaLinea.importe_neto)
    productos = sesion.execute(
        select(
            VentaLinea.producto_id,
            Producto.codigo,
            Producto.nombre,
            func.sum(
                cast(VentaLinea.cantidad_base, Numeric) / VentaLinea.unidades_referencia
            ).label("cajas"),
            func.sum(VentaLinea.cantidad_base).label("unidades_base"),
            neto.label("neto"),
        )
        .select_from(de_ventas)
        .join(
            Producto,
            and_(
                Producto.organizacion_id == VentaLinea.organizacion_id,
                Producto.id == VentaLinea.producto_id,
            ),
        )
        .where(VentaLinea.organizacion_id == organizacion_id, *filtros)
        .group_by(VentaLinea.producto_id, Producto.codigo, Producto.nombre)
        .order_by(neto.desc(), Producto.nombre, VentaLinea.producto_id)
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    ).all()
    total_filas = sesion.execute(
        select(func.count(func.distinct(VentaLinea.producto_id)))
        .select_from(de_ventas)
        .where(VentaLinea.organizacion_id == organizacion_id, *filtros)
    ).scalar_one()
    detalle = sesion.execute(
        select(
            VentaLinea.producto_id,
            VentaLinea.presentacion_id,
            Presentacion.nombre,
            VentaLinea.unidades_presentacion,
            func.sum(VentaLinea.cantidad).label("cantidad"),
            func.sum(VentaLinea.cantidad_base).label("unidades_base"),
        )
        .select_from(de_ventas)
        .join(
            Presentacion,
            and_(
                Presentacion.organizacion_id == VentaLinea.organizacion_id,
                Presentacion.id == VentaLinea.presentacion_id,
            ),
        )
        .where(
            VentaLinea.organizacion_id == organizacion_id,
            VentaLinea.producto_id.in_([fila.producto_id for fila in productos]),
            *filtros,
        )
        .group_by(
            VentaLinea.producto_id,
            VentaLinea.presentacion_id,
            Presentacion.nombre,
            VentaLinea.unidades_presentacion,
        )
        .order_by(
            VentaLinea.unidades_presentacion.desc(), Presentacion.nombre, VentaLinea.presentacion_id
        )
    ).all()
    presentaciones: dict[UUID, list[PresentacionVendidaCruda]] = {}
    for fila in detalle:
        presentaciones.setdefault(fila.producto_id, []).append(
            PresentacionVendidaCruda(
                presentacion_id=fila.presentacion_id,
                nombre=fila.nombre,
                unidades_presentacion=int(fila.unidades_presentacion),
                cantidad=int(fila.cantidad),
                unidades_base=int(fila.unidades_base),
            )
        )
    filas = [
        ProductoCrudo(
            producto_id=fila.producto_id,
            codigo=fila.codigo,
            nombre=fila.nombre,
            cifras=ProductoVendidoCrudo(
                cajas_equivalentes=Decimal(fila.cajas),
                unidades_base=int(fila.unidades_base),
                importe_neto=Decimal(fila.neto),
            ),
            presentaciones=presentaciones.get(fila.producto_id, []),
        )
        for fila in productos
    ]
    return armar_sobre(filas, pagina=pagina, total_filas=int(total_filas))


def ventas_anuladas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    pagina: int,
) -> AnuladasCrudas:
    """Las ventas `ANULADA` cuyo `occurred_at` cae en el período (D2: por la fecha de la venta,
    aunque la anulación sea posterior): cantidad y total sumados en la base sobre todo el período,
    y la página pedida de a `TAMANO_DE_PAGINA`, la más reciente primero (D14)."""
    filtros = _filtros_de_ventas(
        organizacion_id, estado=ESTADO_ANULADA, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    totales = sesion.execute(
        select(func.count(Venta.id), func.coalesce(func.sum(Venta.total), 0)).where(*filtros)
    ).one()
    detalle = (
        select(
            Venta.id,
            Venta.numero,
            Venta.occurred_at,
            Venta.cliente_id,
            Cliente.nombre.label("cliente_nombre"),
            Venta.usuario_id,
            Usuario.nombre.label("vendedor_nombre"),
            Venta.total,
            VentaAnulacion.occurred_at.label("anulada_en"),
            Motivo.nombre.label("motivo"),
            VentaAnulacion.devuelve_dinero,
        )
        .select_from(Venta)
        .join(
            Cliente,
            and_(Cliente.organizacion_id == Venta.organizacion_id, Cliente.id == Venta.cliente_id),
        )
        .join(
            Usuario,
            and_(Usuario.organizacion_id == Venta.organizacion_id, Usuario.id == Venta.usuario_id),
        )
        .outerjoin(
            VentaAnulacion,
            and_(
                VentaAnulacion.organizacion_id == Venta.organizacion_id,
                VentaAnulacion.venta_id == Venta.id,
            ),
        )
        .outerjoin(
            Motivo,
            and_(
                Motivo.organizacion_id == VentaAnulacion.organizacion_id,
                Motivo.id == VentaAnulacion.motivo_id,
            ),
        )
        .where(*filtros)
        .order_by(Venta.occurred_at.desc(), Venta.id.desc())
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    )
    ventas = [
        VentaAnuladaCruda(
            venta_id=fila.id,
            numero=fila.numero,
            occurred_at=fila.occurred_at,
            cliente_id=fila.cliente_id,
            cliente_nombre=fila.cliente_nombre,
            vendedor_id=fila.usuario_id,
            vendedor_nombre=fila.vendedor_nombre,
            total=fila.total,
            anulada_en=fila.anulada_en,
            motivo=fila.motivo,
            devuelve_dinero=fila.devuelve_dinero,
        )
        for fila in sesion.execute(detalle)
    ]
    cantidad = int(totales[0])
    return AnuladasCrudas(
        cantidad=cantidad,
        total=Decimal(totales[1]),
        ventas=armar_sobre(ventas, pagina=pagina, total_filas=cantidad),
    )


# --- Rendiciones por jornada y por vendedor (change 26, grupo 4; RUT-07) ---------------------


@dataclass(frozen=True)
class TotalCrudo:
    cantidad: int
    total: Decimal


@dataclass(frozen=True)
class MedioCobradoCrudo:
    medio_pago_id: UUID
    nombre: str | None
    total: Decimal


@dataclass(frozen=True)
class CobranzasCrudas:
    cantidad: int
    total: Decimal
    por_medio: list[MedioCobradoCrudo]


@dataclass(frozen=True)
class DineroCrudo:
    """Ventas vigentes, ventas anuladas y cobranzas confirmadas, sumadas en la base."""

    ventas: TotalCrudo
    anuladas: TotalCrudo
    cobranzas: CobranzasCrudas


@dataclass(frozen=True)
class DiferenciasCrudas:
    """Faltantes y sobrantes en unidades base y el valor de las diferencias (las líneas sin costo
    unitario no suman, como en el resumen de la jornada)."""

    faltantes: int
    sobrantes: int
    valor: Decimal


@dataclass(frozen=True)
class JornadaCruda:
    jornada_id: UUID
    vendedor_id: UUID
    vendedor_nombre: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    estado: str
    abierta_en: datetime
    rendida_en: datetime | None
    cerrada_en: datetime | None
    liberada_en: datetime | None
    con_conteo: bool
    dinero: DineroCrudo
    despues_de_la_rendicion: DineroCrudo | None
    diferencias: DiferenciasCrudas | None


@dataclass(frozen=True)
class VendedorDeRendicionCruda:
    vendedor_id: UUID
    vendedor_nombre: str
    jornadas: int
    dinero: DineroCrudo
    diferencias: DiferenciasCrudas


_SIN_TOTAL = TotalCrudo(0, Decimal("0.00"))
_SIN_DINERO = DineroCrudo(_SIN_TOTAL, _SIN_TOTAL, CobranzasCrudas(0, Decimal("0.00"), []))
_SIN_DIFERENCIAS = DiferenciasCrudas(0, 0, Decimal("0.00"))

# La rendición de una jornada (a lo sumo una): su momento de registro es el corte de lo tardío.
_CON_RENDICION = and_(
    Rendicion.organizacion_id == Jornada.organizacion_id, Rendicion.jornada_id == Jornada.id
)


def _tardia(momento: Any) -> ColumnElement[bool]:
    """Lo registrado después de la rendición (RUT-07, ADR-068); sin rendición, nada es tardío."""
    return and_(Rendicion.registered_at.is_not(None), momento > Rendicion.registered_at)


def _de_la_jornada(columna: Any) -> ColumnElement[bool]:
    """La condición de unir una fila con `jornada` por su `jornada_id` (FK compuesta)."""
    return and_(Jornada.organizacion_id == columna.class_.organizacion_id, Jornada.id == columna)


def _filtros_de_jornadas(
    organizacion_id: UUID,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    estado: str | None,
) -> list[ColumnElement[bool]]:
    """Las jornadas abiertas en `[inicio, fin)` (TR-04), de cualquier estado (D7)."""
    filtros: list[ColumnElement[bool]] = [
        Jornada.organizacion_id == organizacion_id,
        Jornada.abierta_en >= inicio,
        Jornada.abierta_en < fin,
    ]
    if vendedor_id is not None:
        filtros.append(Jornada.usuario_id == vendedor_id)
    if estado is not None:
        filtros.append(Jornada.estado == estado)
    return filtros


def _totales_por_grupo(
    sesion: Session, consulta: Any, tardia: ColumnElement[bool], suma: Any
) -> dict[UUID, tuple[TotalCrudo, TotalCrudo]]:
    """Cantidad y suma por grupo, separando lo registrado antes y después de la rendición."""
    filas = sesion.execute(
        consulta.add_columns(
            func.count().filter(~tardia).label("cantidad"),
            func.coalesce(func.sum(suma).filter(~tardia), 0).label("total"),
            func.count().filter(tardia).label("cantidad_tardia"),
            func.coalesce(func.sum(suma).filter(tardia), 0).label("total_tardio"),
        )
    )
    return {
        fila[0]: (
            TotalCrudo(int(fila.cantidad), Decimal(fila.total)),
            TotalCrudo(int(fila.cantidad_tardia), Decimal(fila.total_tardio)),
        )
        for fila in filas
    }


def _dinero_por_grupo(
    organizacion_id: UUID,
    sesion: Session,
    filtros: list[ColumnElement[bool]],
    grupo: Any,
) -> dict[UUID, tuple[DineroCrudo, DineroCrudo]]:
    """Ventas vigentes, anuladas (por la jornada de la anulación) y cobranzas confirmadas por
    medio de pago de cada grupo (`Jornada.id` o `Jornada.usuario_id`), separando lo registrado
    antes (primer elemento) y después (segundo) de la rendición. Todo se suma en la base."""
    vigentes = _totales_por_grupo(
        sesion,
        select(grupo)
        .select_from(Venta)
        .join(Jornada, _de_la_jornada(Venta.jornada_id))
        .outerjoin(Rendicion, _CON_RENDICION)
        .where(Venta.organizacion_id == organizacion_id, Venta.estado == ESTADO_CONFIRMADA)
        .where(*filtros)
        .group_by(grupo),
        _tardia(Venta.registered_at),
        Venta.total,
    )
    anuladas = _totales_por_grupo(
        sesion,
        select(grupo)
        .select_from(VentaAnulacion)
        .join(
            Venta,
            and_(
                Venta.organizacion_id == VentaAnulacion.organizacion_id,
                Venta.id == VentaAnulacion.venta_id,
            ),
        )
        .join(Jornada, _de_la_jornada(VentaAnulacion.jornada_id))
        .outerjoin(Rendicion, _CON_RENDICION)
        .where(VentaAnulacion.organizacion_id == organizacion_id)
        .where(*filtros)
        .group_by(grupo),
        _tardia(VentaAnulacion.registered_at),
        Venta.total,
    )
    cobranzas = _totales_por_grupo(
        sesion,
        select(grupo)
        .select_from(Cobranza)
        .join(Jornada, _de_la_jornada(Cobranza.jornada_id))
        .outerjoin(Rendicion, _CON_RENDICION)
        .where(Cobranza.organizacion_id == organizacion_id, Cobranza.estado == ESTADO_CONFIRMADA)
        .where(*filtros)
        .group_by(grupo),
        _tardia(Cobranza.registered_at),
        Cobranza.importe,
    )
    tardia_del_medio = _tardia(Cobranza.registered_at)
    medios = sesion.execute(
        select(
            grupo,
            tardia_del_medio.label("tardia"),
            CobranzaMedio.medio_pago_id,
            MedioPago.nombre,
            func.sum(CobranzaMedio.importe).label("total"),
        )
        .select_from(CobranzaMedio)
        .join(
            Cobranza,
            and_(
                Cobranza.organizacion_id == CobranzaMedio.organizacion_id,
                Cobranza.id == CobranzaMedio.cobranza_id,
            ),
        )
        .join(Jornada, _de_la_jornada(Cobranza.jornada_id))
        .outerjoin(Rendicion, _CON_RENDICION)
        .outerjoin(
            MedioPago,
            and_(
                MedioPago.organizacion_id == CobranzaMedio.organizacion_id,
                MedioPago.id == CobranzaMedio.medio_pago_id,
            ),
        )
        .where(Cobranza.organizacion_id == organizacion_id, Cobranza.estado == ESTADO_CONFIRMADA)
        .where(*filtros)
        .group_by(grupo, tardia_del_medio, CobranzaMedio.medio_pago_id, MedioPago.nombre)
        .order_by(MedioPago.nombre, CobranzaMedio.medio_pago_id)
    )
    por_medio: dict[tuple[UUID, bool], list[MedioCobradoCrudo]] = {}
    for fila in medios:
        por_medio.setdefault((fila[0], bool(fila.tardia)), []).append(
            MedioCobradoCrudo(fila.medio_pago_id, fila.nombre, Decimal(fila.total))
        )

    def armar(clave: UUID, momento: int, tardia: bool) -> DineroCrudo:
        sin_totales = (_SIN_TOTAL, _SIN_TOTAL)
        cobrado = cobranzas.get(clave, sin_totales)[momento]
        return DineroCrudo(
            ventas=vigentes.get(clave, sin_totales)[momento],
            anuladas=anuladas.get(clave, sin_totales)[momento],
            cobranzas=CobranzasCrudas(
                cobrado.cantidad, cobrado.total, por_medio.get((clave, tardia), [])
            ),
        )

    claves = {*vigentes, *anuladas, *cobranzas}
    return {clave: (armar(clave, 0, False), armar(clave, 1, True)) for clave in claves}


def _valor_de_la_diferencia() -> ColumnElement[Decimal]:
    """El valor de una línea de rendición: la misma expresión que el resumen de la jornada
    (`stock`), redondeada por línea; sin costo unitario no hay valor."""
    return case(
        (RendicionLinea.diferencia == 0, Decimal("0.00")),
        else_=func.round(RendicionLinea.diferencia * RendicionLinea.costo_unitario, 2),
    )


def _diferencias_por_grupo(
    organizacion_id: UUID,
    sesion: Session,
    filtros: list[ColumnElement[bool]],
    grupo: Any,
) -> dict[UUID, DiferenciasCrudas]:
    filas = sesion.execute(
        select(
            grupo,
            func.coalesce(
                func.sum(case((RendicionLinea.diferencia < 0, -RendicionLinea.diferencia))), 0
            ).label("faltantes"),
            func.coalesce(
                func.sum(case((RendicionLinea.diferencia > 0, RendicionLinea.diferencia))), 0
            ).label("sobrantes"),
            func.coalesce(func.sum(_valor_de_la_diferencia()), 0).label("valor"),
        )
        .select_from(RendicionLinea)
        .join(
            Rendicion,
            and_(
                Rendicion.organizacion_id == RendicionLinea.organizacion_id,
                Rendicion.id == RendicionLinea.rendicion_id,
            ),
        )
        .join(
            Jornada,
            and_(
                Jornada.organizacion_id == Rendicion.organizacion_id,
                Jornada.id == Rendicion.jornada_id,
            ),
        )
        .where(RendicionLinea.organizacion_id == organizacion_id, *filtros)
        .group_by(grupo)
    )
    return {
        fila[0]: DiferenciasCrudas(int(fila.faltantes), int(fila.sobrantes), Decimal(fila.valor))
        for fila in filas
    }


def jornadas_del_periodo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    estado: str | None,
    pagina: int,
) -> Sobre[JornadaCruda]:
    """Las jornadas abiertas en el período con su dinero y sus diferencias, de la más reciente a la
    más vieja, de a `TAMANO_DE_PAGINA` (RUT-07, D7, D14). El dinero y las diferencias se suman en
    la base solo para las jornadas de la página."""
    filtros = _filtros_de_jornadas(
        organizacion_id, inicio=inicio, fin=fin, vendedor_id=vendedor_id, estado=estado
    )
    total_filas = sesion.execute(select(func.count(Jornada.id)).where(*filtros)).scalar_one()
    filas = sesion.execute(
        select(
            Jornada,
            Usuario.nombre.label("vendedor_nombre"),
            Ubicacion.nombre.label("ubicacion_nombre"),
            Rendicion.id.label("rendicion_id"),
        )
        .select_from(Jornada)
        .join(
            Usuario,
            and_(
                Usuario.organizacion_id == Jornada.organizacion_id,
                Usuario.id == Jornada.usuario_id,
            ),
        )
        .join(
            Ubicacion,
            and_(
                Ubicacion.organizacion_id == Jornada.organizacion_id,
                Ubicacion.id == Jornada.ubicacion_id,
            ),
        )
        .outerjoin(Rendicion, _CON_RENDICION)
        .where(*filtros)
        .order_by(Jornada.abierta_en.desc(), Jornada.id.desc())
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    ).all()
    de_la_pagina = [*filtros, Jornada.id.in_([fila.Jornada.id for fila in filas])]
    dinero = _dinero_por_grupo(organizacion_id, sesion, de_la_pagina, Jornada.id)
    diferencias = _diferencias_por_grupo(organizacion_id, sesion, de_la_pagina, Jornada.id)
    resultado: list[JornadaCruda] = []
    for fila in filas:
        jornada = fila.Jornada
        con_conteo = fila.rendicion_id is not None
        antes, despues = dinero.get(jornada.id, (_SIN_DINERO, _SIN_DINERO))
        resultado.append(
            JornadaCruda(
                jornada_id=jornada.id,
                vendedor_id=jornada.usuario_id,
                vendedor_nombre=fila.vendedor_nombre,
                ubicacion_id=jornada.ubicacion_id,
                ubicacion_nombre=fila.ubicacion_nombre,
                estado=jornada.estado,
                abierta_en=jornada.abierta_en,
                rendida_en=jornada.rendida_en,
                cerrada_en=jornada.cerrada_en,
                liberada_en=jornada.liberada_en,
                con_conteo=con_conteo,
                dinero=antes,
                despues_de_la_rendicion=despues if con_conteo else None,
                diferencias=(diferencias.get(jornada.id, _SIN_DIFERENCIAS) if con_conteo else None),
            )
        )
    return armar_sobre(resultado, pagina=pagina, total_filas=int(total_filas))


def totales_por_vendedor(
    organizacion_id: UUID,
    sesion: Session,
    *,
    inicio: datetime,
    fin: datetime,
    vendedor_id: UUID | None,
    estado: str | None,
) -> list[VendedorDeRendicionCruda]:
    """Los totales de las jornadas del período por vendedor, sumados en la base; por nombre."""
    filtros = _filtros_de_jornadas(
        organizacion_id, inicio=inicio, fin=fin, vendedor_id=vendedor_id, estado=estado
    )
    dinero = _dinero_por_grupo(organizacion_id, sesion, filtros, Jornada.usuario_id)
    diferencias = _diferencias_por_grupo(organizacion_id, sesion, filtros, Jornada.usuario_id)
    filas = sesion.execute(
        select(Jornada.usuario_id, Usuario.nombre, func.count(Jornada.id).label("jornadas"))
        .select_from(Jornada)
        .join(
            Usuario,
            and_(
                Usuario.organizacion_id == Jornada.organizacion_id,
                Usuario.id == Jornada.usuario_id,
            ),
        )
        .where(*filtros)
        .group_by(Jornada.usuario_id, Usuario.nombre)
        .order_by(Usuario.nombre, Jornada.usuario_id)
    )
    return [
        VendedorDeRendicionCruda(
            vendedor_id=fila.usuario_id,
            vendedor_nombre=fila.nombre,
            jornadas=int(fila.jornadas),
            dinero=dinero.get(fila.usuario_id, (_SIN_DINERO, _SIN_DINERO))[0],
            diferencias=diferencias.get(fila.usuario_id, _SIN_DIFERENCIAS),
        )
        for fila in filas
    ]


def existe_jornada(organizacion_id: UUID, sesion: Session, jornada_id: UUID) -> bool:
    """Si la jornada existe en la organización (una ajena es como una inexistente, INV-21)."""
    return (
        sesion.scalar(
            select(Jornada.id).where(
                Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id
            )
        )
        is not None
    )


@dataclass(frozen=True)
class ProductoDeResumenCrudo:
    """Código, nombre y presentación de referencia de un producto del detalle de una jornada."""

    codigo: str
    nombre: str
    unidades_referencia: int | None
    nombre_referencia: str | None


def productos_para_resumen(
    organizacion_id: UUID, sesion: Session, producto_ids: set[UUID]
) -> dict[UUID, ProductoDeResumenCrudo]:
    """Código, nombre y referencia (CAT-08) de los productos pedidos, filtrados por organización
    (INV-21). Un producto sin presentación de referencia viaja sin ella."""
    if not producto_ids:
        return {}
    filas = sesion.execute(
        select(
            Producto.id,
            Producto.codigo,
            Producto.nombre,
            Presentacion.unidades_base,
            Presentacion.nombre.label("nombre_referencia"),
        )
        .select_from(Producto)
        .outerjoin(
            Presentacion,
            and_(
                Presentacion.organizacion_id == Producto.organizacion_id,
                Presentacion.producto_id == Producto.id,
                Presentacion.es_referencia.is_(True),
            ),
        )
        .where(Producto.organizacion_id == organizacion_id, Producto.id.in_(producto_ids))
    ).all()
    return {
        fila.id: ProductoDeResumenCrudo(
            codigo=fila.codigo,
            nombre=fila.nombre,
            unidades_referencia=fila.unidades_base,
            nombre_referencia=fila.nombre_referencia,
        )
        for fila in filas
    }


# --- Observaciones y rechazos por vendedor (change 26, grupo 5; SYN-06, SYN-07) --------------


@dataclass(frozen=True)
class ContadorCrudo:
    """Cuántos hay en total y cuántos siguen pendientes de resolver."""

    total: int
    pendientes: int


@dataclass(frozen=True)
class AvisoPorCodigoCrudo:
    codigo: str
    contador: ContadorCrudo


@dataclass(frozen=True)
class OperacionesDeVendedorCrudas:
    vendedor_id: UUID
    vendedor_nombre: str
    ventas_sin_conexion: int
    avisos: ContadorCrudo
    avisos_por_codigo: list[AvisoPorCodigoCrudo]
    rechazadas: ContadorCrudo


def operaciones_sin_conexion_por_vendedor(
    organizacion_id: UUID, sesion: Session, *, inicio: datetime, fin: datetime
) -> list[OperacionesDeVendedorCrudas]:
    """Por vendedor con operaciones en `[inicio, fin)` (por el `occurred_at` del comando, TR-04):
    ventas confirmadas sin conexión, avisos (de las observaciones de sus comandos, en total y por
    código) y operaciones rechazadas, con cuántos siguen pendientes. Todo se cuenta en la base;
    solo cantidades, el detalle de cada aviso sigue en «Revisión» (D9)."""
    ventas = {
        fila.usuario_id: int(fila.cantidad)
        for fila in sesion.execute(
            select(Venta.usuario_id, func.count().label("cantidad"))
            .where(
                Venta.organizacion_id == organizacion_id,
                Venta.estado == ESTADO_CONFIRMADA,
                Venta.modo_confirmacion == "OFFLINE",
                Venta.occurred_at >= inicio,
                Venta.occurred_at < fin,
            )
            .group_by(Venta.usuario_id)
        )
    }
    de_avisos = (
        select(
            Comando.usuario_id,
            func.count().label("total"),
            func.count().filter(Observacion.estado == "PENDIENTE").label("pendientes"),
        )
        .select_from(Observacion)
        .join(
            Comando,
            and_(
                Comando.organizacion_id == Observacion.organizacion_id,
                Comando.id == Observacion.comando_id,
            ),
        )
        .where(
            Observacion.organizacion_id == organizacion_id,
            Comando.occurred_at >= inicio,
            Comando.occurred_at < fin,
        )
    )
    avisos = {
        fila.usuario_id: ContadorCrudo(int(fila.total), int(fila.pendientes))
        for fila in sesion.execute(de_avisos.group_by(Comando.usuario_id))
    }
    avisos_por_codigo: dict[UUID, list[AvisoPorCodigoCrudo]] = {}
    for fila in sesion.execute(
        de_avisos.add_columns(Observacion.codigo)
        .group_by(Comando.usuario_id, Observacion.codigo)
        .order_by(Observacion.codigo)
    ):
        avisos_por_codigo.setdefault(fila.usuario_id, []).append(
            AvisoPorCodigoCrudo(fila.codigo, ContadorCrudo(int(fila.total), int(fila.pendientes)))
        )
    rechazadas = {
        fila.usuario_id: ContadorCrudo(int(fila.total), int(fila.pendientes))
        for fila in sesion.execute(
            select(
                ComandoRechazado.usuario_id,
                func.count().label("total"),
                func.count().filter(ComandoRechazado.estado == "PENDIENTE").label("pendientes"),
            )
            .where(
                ComandoRechazado.organizacion_id == organizacion_id,
                ComandoRechazado.occurred_at >= inicio,
                ComandoRechazado.occurred_at < fin,
            )
            .group_by(ComandoRechazado.usuario_id)
        )
    }
    vendedores = {*ventas, *avisos, *rechazadas}
    if not vendedores:
        return []
    sin_contar = ContadorCrudo(0, 0)
    nombres = sesion.execute(
        select(Usuario.id, Usuario.nombre)
        .where(Usuario.organizacion_id == organizacion_id, Usuario.id.in_(vendedores))
        .order_by(Usuario.nombre, Usuario.id)
    )
    return [
        OperacionesDeVendedorCrudas(
            vendedor_id=fila.id,
            vendedor_nombre=fila.nombre,
            ventas_sin_conexion=ventas.get(fila.id, 0),
            avisos=avisos.get(fila.id, sin_contar),
            avisos_por_codigo=avisos_por_codigo.get(fila.id, []),
            rechazadas=rechazadas.get(fila.id, sin_contar),
        )
        for fila in nombres
    ]


# --- Ajustes de stock por motivo (change 26, grupo 6; STK-03, RUT-06) -------------------------

TIPO_DIFERENCIA_RENDICION = "DIFERENCIA_RENDICION"


@dataclass(frozen=True)
class ProductoAjustadoCrudo:
    producto_id: UUID
    codigo: str
    nombre: str
    cifras: CifrasCrudasDeAjuste


@dataclass(frozen=True)
class MotivoDeAjusteCrudo:
    motivo_id: UUID
    nombre: str
    ajustes: int
    cifras: CifrasCrudasDeAjuste
    productos: list[ProductoAjustadoCrudo]


@dataclass(frozen=True)
class DiferenciasDeRendicionCrudas:
    cifras: CifrasCrudasDeAjuste
    productos: list[ProductoAjustadoCrudo]


@dataclass(frozen=True)
class AjustesCrudos:
    motivos: list[MotivoDeAjusteCrudo]
    diferencias_de_rendicion: DiferenciasDeRendicionCrudas
    ajustes_anulados: int


def _columnas_de_ajuste(cantidad: Any, costo: Any) -> list[Any]:
    """Las sumas de un nivel de ajustes sobre `cantidad_base` (con signo) y `costo_unitario`:
    unidades que entraron y salieron, el valor exacto de cada sentido (solo las líneas con costo)
    y las unidades sin costo. El redondeo del valor se hace una vez, al armar (TR-03)."""
    return [
        func.coalesce(func.sum(cantidad).filter(cantidad > 0), 0).label("entradas"),
        func.coalesce(func.sum(-cantidad).filter(cantidad < 0), 0).label("salidas"),
        func.coalesce(func.sum(cantidad * costo).filter(cantidad > 0), 0).label("valor_entradas"),
        func.coalesce(func.sum(-cantidad * costo).filter(cantidad < 0), 0).label("valor_salidas"),
        func.coalesce(func.sum(func.abs(cantidad)).filter(costo.is_(None)), 0).label(
            "unidades_sin_costo"
        ),
    ]


def _cifras_de_ajuste(fila: Any) -> CifrasCrudasDeAjuste:
    return CifrasCrudasDeAjuste(
        entradas=int(fila.entradas),
        salidas=int(fila.salidas),
        valor_de_entradas=Decimal(fila.valor_entradas),
        valor_de_salidas=Decimal(fila.valor_salidas),
        unidades_sin_costo=int(fila.unidades_sin_costo),
    )


def _productos_ajustados(sesion: Session, consulta: Any) -> dict[Any, list[ProductoAjustadoCrudo]]:
    """El detalle por producto de un nivel: `consulta` ya trae las sumas y el filtro; acá se le
    agrega el producto (código y nombre) y se agrupa por `(nivel, producto)`."""
    productos: dict[Any, list[ProductoAjustadoCrudo]] = {}
    for fila in sesion.execute(consulta):
        productos.setdefault(fila[0], []).append(
            ProductoAjustadoCrudo(
                producto_id=fila.producto_id,
                codigo=fila.codigo,
                nombre=fila.nombre,
                cifras=_cifras_de_ajuste(fila),
            )
        )
    return productos


def ajustes_por_motivo(
    organizacion_id: UUID, sesion: Session, *, inicio: datetime, fin: datetime
) -> AjustesCrudos:
    """Los ajustes `CONFIRMADA` con `occurred_at` en `[inicio, fin)` agrupados por motivo y, dentro
    de cada uno, por producto; los movimientos `DIFERENCIA_RENDICION` del período en una fila
    aparte; y cuántos ajustes anulados hubo (no suman). Todo se suma en la base."""
    en_el_periodo = [
        AjusteStock.organizacion_id == organizacion_id,
        AjusteStock.occurred_at >= inicio,
        AjusteStock.occurred_at < fin,
    ]
    con_lineas = AjusteStock.__table__.join(
        AjusteStockLinea.__table__,
        and_(
            AjusteStockLinea.organizacion_id == AjusteStock.organizacion_id,
            AjusteStockLinea.ajuste_id == AjusteStock.id,
        ),
    )
    cantidad, costo = AjusteStockLinea.cantidad_base, AjusteStockLinea.costo_unitario
    columnas = _columnas_de_ajuste(cantidad, costo)
    por_motivo = sesion.execute(
        select(
            AjusteStock.motivo_id,
            Motivo.nombre,
            func.count(AjusteStock.id.distinct()).label("ajustes"),
            *columnas,
        )
        .select_from(con_lineas)
        .join(
            Motivo,
            and_(
                Motivo.organizacion_id == AjusteStock.organizacion_id,
                Motivo.id == AjusteStock.motivo_id,
            ),
        )
        .where(*en_el_periodo, AjusteStock.estado == ESTADO_CONFIRMADA)
        .group_by(AjusteStock.motivo_id, Motivo.nombre)
        .order_by(Motivo.nombre, AjusteStock.motivo_id)
    ).all()
    productos = _productos_ajustados(
        sesion,
        select(
            AjusteStock.motivo_id,
            AjusteStockLinea.producto_id,
            Producto.codigo,
            Producto.nombre,
            *columnas,
        )
        .select_from(con_lineas)
        .join(
            Producto,
            and_(
                Producto.organizacion_id == AjusteStockLinea.organizacion_id,
                Producto.id == AjusteStockLinea.producto_id,
            ),
        )
        .where(*en_el_periodo, AjusteStock.estado == ESTADO_CONFIRMADA)
        .group_by(
            AjusteStock.motivo_id, AjusteStockLinea.producto_id, Producto.codigo, Producto.nombre
        )
        .order_by(Producto.nombre, AjusteStockLinea.producto_id),
    )
    anulados = sesion.scalar(
        select(func.count(AjusteStock.id)).where(
            *en_el_periodo, AjusteStock.estado == ESTADO_ANULADA
        )
    )
    return AjustesCrudos(
        motivos=[
            MotivoDeAjusteCrudo(
                motivo_id=fila.motivo_id,
                nombre=fila.nombre,
                ajustes=int(fila.ajustes),
                cifras=_cifras_de_ajuste(fila),
                productos=productos.get(fila.motivo_id, []),
            )
            for fila in por_motivo
        ],
        diferencias_de_rendicion=_diferencias_de_rendicion(
            organizacion_id, sesion, inicio=inicio, fin=fin
        ),
        ajustes_anulados=int(anulados or 0),
    )


def _diferencias_de_rendicion(
    organizacion_id: UUID, sesion: Session, *, inicio: datetime, fin: datetime
) -> DiferenciasDeRendicionCrudas:
    """Los `DIFERENCIA_RENDICION` del período (con signo, sin motivo, RUT-06): el total y el
    detalle por producto, con las mismas columnas que un motivo."""
    en_el_periodo = [
        StockMovimiento.organizacion_id == organizacion_id,
        StockMovimiento.tipo == TIPO_DIFERENCIA_RENDICION,
        StockMovimiento.occurred_at >= inicio,
        StockMovimiento.occurred_at < fin,
    ]
    columnas = _columnas_de_ajuste(StockMovimiento.cantidad_base, StockMovimiento.costo_unitario)
    total = sesion.execute(select(*columnas).where(*en_el_periodo)).one()
    detalle = sesion.execute(
        select(StockMovimiento.producto_id, Producto.codigo, Producto.nombre, *columnas)
        .select_from(StockMovimiento)
        .join(
            Producto,
            and_(
                Producto.organizacion_id == StockMovimiento.organizacion_id,
                Producto.id == StockMovimiento.producto_id,
            ),
        )
        .where(*en_el_periodo)
        .group_by(StockMovimiento.producto_id, Producto.codigo, Producto.nombre)
        .order_by(Producto.nombre, StockMovimiento.producto_id)
    )
    return DiferenciasDeRendicionCrudas(
        cifras=_cifras_de_ajuste(total),
        productos=[
            ProductoAjustadoCrudo(
                producto_id=fila.producto_id,
                codigo=fila.codigo,
                nombre=fila.nombre,
                cifras=_cifras_de_ajuste(fila),
            )
            for fila in detalle
        ],
    )


# --- Saldos de clientes y proveedores (change 26, grupo 7; CC-04, INV-13, `design.md` D8) -----

CUENTA_CLIENTE = "CLIENTE"
CUENTA_PROVEEDOR = "PROVEEDOR"
SALDO_DEUDORES = "DEUDORES"
SALDO_A_FAVOR = "A_FAVOR"
SALDO_CON_SALDO = "CON_SALDO"
SALDO_TODOS = "TODOS"
_CERO = literal(Decimal("0.00"), Numeric(14, 2))
_ESCAPE_LIKE = "\\"


@dataclass(frozen=True)
class ClienteConSaldoCrudo:
    cliente_id: UUID
    codigo: str | None
    nombre: str
    razon_social: str | None
    vendedor_id: UUID | None
    vendedor_nombre: str | None
    estado: str
    limite_credito: Decimal | None
    saldo: Decimal
    disponible: Decimal | None


@dataclass(frozen=True)
class ProveedorConSaldoCrudo:
    proveedor_id: UUID
    nombre: str
    estado: str
    saldo: Decimal


@dataclass(frozen=True)
class TotalesDeSaldosCrudos:
    """Lo adeudado (suma de los saldos positivos) y lo a favor (suma de los negativos)."""

    adeudado: Decimal
    a_favor: Decimal


@dataclass(frozen=True)
class VendedorConClientesCrudo:
    vendedor_id: UUID
    vendedor_nombre: str


@dataclass(frozen=True)
class ClientesConSaldoCrudos:
    clientes: Sobre[ClienteConSaldoCrudo]
    totales: TotalesDeSaldosCrudos
    vendedores: list[VendedorConClientesCrudo]


@dataclass(frozen=True)
class ProveedoresConSaldoCrudos:
    proveedores: Sobre[ProveedorConSaldoCrudo]
    totales: TotalesDeSaldosCrudos


def _patron_literal(texto: str) -> str:
    """Patrón de `ILIKE` que busca `texto` tal cual: `%`, `_` y la barra no son comodines."""
    escapado = (
        texto.replace(_ESCAPE_LIKE, _ESCAPE_LIKE * 2)
        .replace("%", _ESCAPE_LIKE + "%")
        .replace("_", _ESCAPE_LIKE + "_")
    )
    return f"%{escapado}%"


def _filtro_de_saldo(saldo: Any, filtro: str) -> list[ColumnElement[bool]]:
    if filtro == SALDO_DEUDORES:
        return [saldo > 0]
    if filtro == SALDO_A_FAVOR:
        return [saldo < 0]
    if filtro == SALDO_CON_SALDO:
        return [saldo != 0]
    return []


def _totales_de_saldos(sesion: Session, base: Subquery) -> tuple[int, TotalesDeSaldosCrudos]:
    """En la base, sobre todo lo filtrado (no sobre la página): la cantidad de filas y la suma de
    los saldos positivos y la de los negativos."""
    fila = sesion.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((base.c.saldo > 0, base.c.saldo), else_=_CERO)), _CERO),
            func.coalesce(func.sum(case((base.c.saldo < 0, base.c.saldo), else_=_CERO)), _CERO),
        ).select_from(base)
    ).one()
    return int(fila[0]), TotalesDeSaldosCrudos(adeudado=fila[1], a_favor=fila[2])


def vendedores_con_clientes(
    organizacion_id: UUID, sesion: Session
) -> list[VendedorConClientesCrudo]:
    """Los vendedores con algún cliente asignado en la organización, por nombre: no depende de
    la página ni de los filtros del reporte (para el desplegable de «Vendedor»)."""
    filas = sesion.execute(
        select(Usuario.id, Usuario.nombre)
        .where(
            Usuario.organizacion_id == organizacion_id,
            exists().where(
                Cliente.organizacion_id == Usuario.organizacion_id,
                Cliente.vendedor_id == Usuario.id,
            ),
        )
        .order_by(Usuario.nombre, Usuario.id)
    ).all()
    return [VendedorConClientesCrudo(vendedor_id=f.id, vendedor_nombre=f.nombre) for f in filas]


def saldos_de_clientes(
    organizacion_id: UUID,
    sesion: Session,
    *,
    saldo: str,
    vendedor_id: UUID | None,
    estado: str | None,
    texto: str | None,
    pagina: int,
) -> ClientesConSaldoCrudos:
    """El saldo actual de cada cliente desde `saldo_cuenta` (sin fila, cero) con su disponible
    (límite menos saldo; nulo sin límite), por saldo descendente de a `TAMANO_DE_PAGINA` (D14), y
    los totales de todo lo filtrado."""
    saldo_actual = func.coalesce(SaldoCuenta.saldo, _CERO)
    consulta = (
        select(
            Cliente.id.label("cliente_id"),
            Cliente.codigo,
            Cliente.nombre,
            Cliente.razon_social,
            Cliente.vendedor_id,
            Usuario.nombre.label("vendedor_nombre"),
            Cliente.estado,
            Cliente.limite_credito,
            saldo_actual.label("saldo"),
            (Cliente.limite_credito - saldo_actual).label("disponible"),
        )
        .select_from(Cliente)
        .outerjoin(
            SaldoCuenta,
            and_(
                SaldoCuenta.organizacion_id == Cliente.organizacion_id,
                SaldoCuenta.cuenta_tipo == CUENTA_CLIENTE,
                SaldoCuenta.entidad_id == Cliente.id,
            ),
        )
        .outerjoin(
            Usuario,
            and_(
                Usuario.organizacion_id == Cliente.organizacion_id,
                Usuario.id == Cliente.vendedor_id,
            ),
        )
        .where(Cliente.organizacion_id == organizacion_id, *_filtro_de_saldo(saldo_actual, saldo))
    )
    if vendedor_id is not None:
        consulta = consulta.where(Cliente.vendedor_id == vendedor_id)
    if estado is not None:
        consulta = consulta.where(Cliente.estado == estado)
    if texto:
        patron = _patron_literal(texto)
        consulta = consulta.where(
            Cliente.nombre.ilike(patron, escape=_ESCAPE_LIKE)
            | Cliente.razon_social.ilike(patron, escape=_ESCAPE_LIKE)
            | Cliente.codigo.ilike(patron, escape=_ESCAPE_LIKE)
        )
    total_filas, totales = _totales_de_saldos(sesion, consulta.subquery())
    filas = sesion.execute(
        consulta.order_by(saldo_actual.desc(), Cliente.nombre, Cliente.id)
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    ).all()
    clientes = [
        ClienteConSaldoCrudo(
            cliente_id=f.cliente_id,
            codigo=f.codigo,
            nombre=f.nombre,
            razon_social=f.razon_social,
            vendedor_id=f.vendedor_id,
            vendedor_nombre=f.vendedor_nombre,
            estado=f.estado,
            limite_credito=f.limite_credito,
            saldo=f.saldo,
            disponible=f.disponible,
        )
        for f in filas
    ]
    return ClientesConSaldoCrudos(
        clientes=armar_sobre(clientes, pagina=pagina, total_filas=total_filas),
        totales=totales,
        vendedores=vendedores_con_clientes(organizacion_id, sesion),
    )


def saldos_de_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    saldo: str,
    estado: str | None,
    texto: str | None,
    pagina: int,
) -> ProveedoresConSaldoCrudos:
    """El saldo actual de cada proveedor desde `saldo_cuenta` (sin fila, cero), por saldo
    descendente de a `TAMANO_DE_PAGINA` (D14), y los totales de todo lo filtrado. El estado es
    `ACTIVO` o `INACTIVO` según `activo`."""
    saldo_actual = func.coalesce(SaldoCuenta.saldo, _CERO)
    estado_de_proveedor = case((Proveedor.activo.is_(True), "ACTIVO"), else_="INACTIVO")
    consulta = (
        select(
            Proveedor.id.label("proveedor_id"),
            Proveedor.nombre,
            estado_de_proveedor.label("estado"),
            saldo_actual.label("saldo"),
        )
        .select_from(Proveedor)
        .outerjoin(
            SaldoCuenta,
            and_(
                SaldoCuenta.organizacion_id == Proveedor.organizacion_id,
                SaldoCuenta.cuenta_tipo == CUENTA_PROVEEDOR,
                SaldoCuenta.entidad_id == Proveedor.id,
            ),
        )
        .where(Proveedor.organizacion_id == organizacion_id, *_filtro_de_saldo(saldo_actual, saldo))
    )
    if estado is not None:
        consulta = consulta.where(Proveedor.activo.is_(estado == "ACTIVO"))
    if texto:
        consulta = consulta.where(
            Proveedor.nombre.ilike(_patron_literal(texto), escape=_ESCAPE_LIKE)
        )
    total_filas, totales = _totales_de_saldos(sesion, consulta.subquery())
    filas = sesion.execute(
        consulta.order_by(saldo_actual.desc(), Proveedor.nombre, Proveedor.id)
        .limit(TAMANO_DE_PAGINA)
        .offset(desplazamiento_de(pagina))
    ).all()
    proveedores = [
        ProveedorConSaldoCrudo(
            proveedor_id=f.proveedor_id, nombre=f.nombre, estado=f.estado, saldo=f.saldo
        )
        for f in filas
    ]
    return ProveedoresConSaldoCrudos(
        proveedores=armar_sobre(proveedores, pagina=pagina, total_filas=total_filas),
        totales=totales,
    )
