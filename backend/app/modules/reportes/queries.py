"""Casos de uso de lectura de los reportes (change 26): período, consulta y armado según permisos.

Las cifras salen sumadas de la base (`repository.py`); acá solo se resuelve el período con el reloj
inyectable (TR-04) y se arma cada fila según los permisos de quien consulta (REP-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.modules.identidad import service as identidad_service
from app.modules.reportes import repository
from app.modules.reportes.domain.armado import (
    CifrasDeAjuste,
    CifrasDeVentas,
    ProductoVendido,
    armar_cifras_de_ajuste,
    armar_cifras_de_ventas,
    armar_producto_vendido,
    armar_valor_con_costos,
)
from app.modules.reportes.domain.errores import RecursoNoEncontradoError
from app.modules.reportes.domain.paginacion import Sobre
from app.modules.reportes.domain.periodo import Periodo, resolver_periodo
from app.modules.reportes.repository import (
    AnuladasCrudas,
    ClientesConSaldoCrudos,
    ContadorCrudo,
    JornadaCruda,
    OperacionesDeVendedorCrudas,
    PresentacionVendidaCruda,
    ProductoAjustadoCrudo,
    ProductoDeResumenCrudo,
    ProveedoresConSaldoCrudos,
    VendedorDeRendicionCruda,
)
from app.modules.stock import service as stock_service


@dataclass(frozen=True)
class FilaPorDia:
    fecha: date
    cifras: CifrasDeVentas


@dataclass(frozen=True)
class FilaPorVendedor:
    vendedor_id: UUID
    vendedor_nombre: str
    cifras: CifrasDeVentas


@dataclass(frozen=True)
class FilaPorProducto:
    producto_id: UUID
    codigo: str
    nombre: str
    cifras: ProductoVendido
    presentaciones: list[PresentacionVendidaCruda]


@dataclass(frozen=True)
class ReporteDeVentas:
    periodo: Periodo
    ve_utilidad: bool
    resumen: CifrasDeVentas
    por_dia: Sobre[FilaPorDia]
    por_vendedor: list[FilaPorVendedor]
    por_producto: Sobre[FilaPorProducto]
    anuladas: AnuladasCrudas


def resolver_periodo_de_la_organizacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    desde: date | None,
    hasta: date | None,
) -> Periodo:
    """El período aplicado: sus fechas de negocio salen de la zona de la organización y del reloj
    inyectable (TR-04, `design.md` D1)."""
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    hoy = identidad_service.fecha_de_negocio(organizacion_id, sesion, reloj)
    if organizacion is None or hoy is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    return resolver_periodo(desde, hasta, hoy=hoy, zona_horaria=organizacion.zona_horaria)


def _sobre_con[T, U](sobre: Sobre[T], filas: list[U]) -> Sobre[U]:
    """El mismo sobre (página y totales) con las filas ya armadas según los permisos."""
    return Sobre(
        filas=filas,
        pagina=sobre.pagina,
        tamano=sobre.tamano,
        total_filas=sobre.total_filas,
        paginas=sobre.paginas,
    )


def obtener_reporte_de_ventas(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    desde: date | None,
    hasta: date | None,
    vendedor_id: UUID | None,
    ve_utilidad: bool,
    pagina_por_dia: int = 1,
    pagina_por_producto: int = 1,
    pagina_anuladas: int = 1,
) -> ReporteDeVentas:
    """`GET /reportes/ventas`: resumen, por día y por vendedor de las ventas `CONFIRMADA` del
    período, y las anuladas aparte (REP-01, REP-02, REP-04). Por día, por producto y las anuladas
    viajan en páginas de 50, cada una por su lado (D14); lo demás, sobre todo el período."""
    periodo = resolver_periodo_de_la_organizacion(
        organizacion_id, sesion, reloj, desde=desde, hasta=hasta
    )
    inicio, fin = periodo.inicio, periodo.fin
    resumen = repository.resumen_de_ventas(
        organizacion_id, sesion, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    por_dia = repository.ventas_por_dia(
        organizacion_id,
        sesion,
        inicio=inicio,
        fin=fin,
        vendedor_id=vendedor_id,
        zona_horaria=periodo.zona_horaria,
        pagina=pagina_por_dia,
    )
    por_vendedor = repository.ventas_por_vendedor(
        organizacion_id, sesion, inicio=inicio, fin=fin, vendedor_id=vendedor_id
    )
    por_producto = repository.ventas_por_producto(
        organizacion_id,
        sesion,
        inicio=inicio,
        fin=fin,
        vendedor_id=vendedor_id,
        pagina=pagina_por_producto,
    )
    anuladas = repository.ventas_anuladas(
        organizacion_id,
        sesion,
        inicio=inicio,
        fin=fin,
        vendedor_id=vendedor_id,
        pagina=pagina_anuladas,
    )
    return ReporteDeVentas(
        periodo=periodo,
        ve_utilidad=ve_utilidad,
        resumen=armar_cifras_de_ventas(resumen, ve_utilidad=ve_utilidad),
        por_dia=_sobre_con(
            por_dia,
            [
                FilaPorDia(f.fecha, armar_cifras_de_ventas(f.cifras, ve_utilidad=ve_utilidad))
                for f in por_dia.filas
            ],
        ),
        por_vendedor=[
            FilaPorVendedor(
                f.vendedor_id,
                f.vendedor_nombre,
                armar_cifras_de_ventas(f.cifras, ve_utilidad=ve_utilidad),
            )
            for f in por_vendedor
        ],
        por_producto=_sobre_con(
            por_producto,
            [
                FilaPorProducto(
                    f.producto_id,
                    f.codigo,
                    f.nombre,
                    armar_producto_vendido(f.cifras),
                    f.presentaciones,
                )
                for f in por_producto.filas
            ],
        ),
        anuladas=anuladas,
    )


# --- Rendiciones (change 26, grupo 4; RUT-07, `design.md` D7) -------------------------------


@dataclass(frozen=True)
class FilaDeJornada:
    """Una jornada del reporte; el valor de las diferencias solo con `VER_COSTOS` (REP-04)."""

    jornada: JornadaCruda
    valor_de_diferencias: Decimal | None


@dataclass(frozen=True)
class FilaDeVendedor:
    vendedor: VendedorDeRendicionCruda
    valor_de_diferencias: Decimal | None


@dataclass(frozen=True)
class ReporteDeRendiciones:
    periodo: Periodo
    ve_costos: bool
    jornadas: Sobre[FilaDeJornada]
    por_vendedor: list[FilaDeVendedor]


def obtener_reporte_de_rendiciones(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    desde: date | None,
    hasta: date | None,
    vendedor_id: UUID | None,
    estado: str | None,
    ve_costos: bool,
    pagina: int = 1,
) -> ReporteDeRendiciones:
    """`GET /reportes/rendiciones`: las jornadas abiertas en el período, de cualquier estado, con
    sus cifras sumadas en la base y en páginas de 50 (D14), y los totales por vendedor de todas
    las jornadas del filtro (RUT-07, D7)."""
    periodo = resolver_periodo_de_la_organizacion(
        organizacion_id, sesion, reloj, desde=desde, hasta=hasta
    )
    jornadas = repository.jornadas_del_periodo(
        organizacion_id,
        sesion,
        inicio=periodo.inicio,
        fin=periodo.fin,
        vendedor_id=vendedor_id,
        estado=estado,
        pagina=pagina,
    )
    vendedores = repository.totales_por_vendedor(
        organizacion_id,
        sesion,
        inicio=periodo.inicio,
        fin=periodo.fin,
        vendedor_id=vendedor_id,
        estado=estado,
    )
    return ReporteDeRendiciones(
        periodo=periodo,
        ve_costos=ve_costos,
        jornadas=_sobre_con(
            jornadas,
            [
                FilaDeJornada(
                    j,
                    armar_valor_con_costos(
                        None if j.diferencias is None else j.diferencias.valor, ve_costos=ve_costos
                    ),
                )
                for j in jornadas.filas
            ],
        ),
        por_vendedor=[
            FilaDeVendedor(v, armar_valor_con_costos(v.diferencias.valor, ve_costos=ve_costos))
            for v in vendedores
        ],
    )


@dataclass(frozen=True)
class DetalleDeJornada:
    """El resumen de RUT-07 con el código, el nombre y la referencia de cada producto, para que
    quien lee reportes no necesite el catálogo."""

    resumen: stock_service.ResumenDeJornada
    productos: dict[UUID, ProductoDeResumenCrudo]


def obtener_resumen_de_jornada(
    organizacion_id: UUID, sesion: Session, *, jornada_id: UUID, ve_costos: bool
) -> DetalleDeJornada:
    """`GET /reportes/rendiciones/{jornada_id}`: el resumen de RUT-07 de `stock` (una sola
    implementación de la regla) con los productos resueltos en SQL. Una jornada ajena o
    inexistente es 404 (INV-21)."""
    if not repository.existe_jornada(organizacion_id, sesion, jornada_id):
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")
    resumen = stock_service.obtener_resumen_de_jornada(
        organizacion_id, sesion, jornada_id=jornada_id, con_costos=ve_costos
    )
    productos = repository.productos_para_resumen(
        organizacion_id, sesion, {linea.producto_id for linea in resumen.lineas}
    )
    return DetalleDeJornada(resumen=resumen, productos=productos)


# --- Observaciones por vendedor (change 26, grupo 5; SYN-06, SYN-07, `design.md` D9) ---------

CODIGO_EXCESO_CREDITO_DETECTADO_SYNC = "EXCESO_CREDITO_DETECTADO_SYNC"


@dataclass(frozen=True)
class FilaDeObservaciones:
    operaciones: OperacionesDeVendedorCrudas
    excesos_de_credito_detectados: ContadorCrudo


@dataclass(frozen=True)
class ReporteDeObservaciones:
    periodo: Periodo
    vendedores: list[FilaDeObservaciones]


def obtener_reporte_de_observaciones(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    desde: date | None,
    hasta: date | None,
) -> ReporteDeObservaciones:
    """`GET /reportes/observaciones`: por vendedor, las ventas sin conexión, los avisos y las
    operaciones rechazadas del período (SYN-06, SYN-07, D9). Los excesos de crédito detectados al
    sincronizar son el aviso de ese código (CRE-09)."""
    periodo = resolver_periodo_de_la_organizacion(
        organizacion_id, sesion, reloj, desde=desde, hasta=hasta
    )
    vendedores = repository.operaciones_sin_conexion_por_vendedor(
        organizacion_id, sesion, inicio=periodo.inicio, fin=periodo.fin
    )
    sin_excesos = ContadorCrudo(0, 0)
    return ReporteDeObservaciones(
        periodo=periodo,
        vendedores=[
            FilaDeObservaciones(
                v,
                next(
                    (
                        a.contador
                        for a in v.avisos_por_codigo
                        if a.codigo == CODIGO_EXCESO_CREDITO_DETECTADO_SYNC
                    ),
                    sin_excesos,
                ),
            )
            for v in vendedores
        ],
    )


# --- Ajustes por motivo (change 26, grupo 6; STK-03, RUT-06, `design.md` D10) ----------------


@dataclass(frozen=True)
class FilaDeProductoAjustado:
    producto_id: UUID
    codigo: str
    nombre: str
    cifras: CifrasDeAjuste


@dataclass(frozen=True)
class FilaDeMotivo:
    motivo_id: UUID
    nombre: str
    ajustes: int
    cifras: CifrasDeAjuste
    productos: list[FilaDeProductoAjustado]


@dataclass(frozen=True)
class FilaDeDiferenciasDeRendicion:
    cifras: CifrasDeAjuste
    productos: list[FilaDeProductoAjustado]


@dataclass(frozen=True)
class ReporteDeAjustes:
    periodo: Periodo
    ve_costos: bool
    motivos: list[FilaDeMotivo]
    diferencias_de_rendicion: FilaDeDiferenciasDeRendicion
    ajustes_anulados: int


def _productos_armados(
    productos: list[ProductoAjustadoCrudo], *, ve_costos: bool
) -> list[FilaDeProductoAjustado]:
    return [
        FilaDeProductoAjustado(
            p.producto_id,
            p.codigo,
            p.nombre,
            armar_cifras_de_ajuste(p.cifras, ve_costos=ve_costos),
        )
        for p in productos
    ]


def obtener_reporte_de_ajustes(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    desde: date | None,
    hasta: date | None,
    ve_costos: bool,
) -> ReporteDeAjustes:
    """`GET /reportes/ajustes`: los ajustes confirmados por motivo y producto, las diferencias de
    rendición aparte y los ajustes anulados (no suman). Los valores solo con `VER_COSTOS`
    (STK-03, RUT-06, REP-04)."""
    periodo = resolver_periodo_de_la_organizacion(
        organizacion_id, sesion, reloj, desde=desde, hasta=hasta
    )
    crudos = repository.ajustes_por_motivo(
        organizacion_id, sesion, inicio=periodo.inicio, fin=periodo.fin
    )
    return ReporteDeAjustes(
        periodo=periodo,
        ve_costos=ve_costos,
        motivos=[
            FilaDeMotivo(
                m.motivo_id,
                m.nombre,
                m.ajustes,
                armar_cifras_de_ajuste(m.cifras, ve_costos=ve_costos),
                _productos_armados(m.productos, ve_costos=ve_costos),
            )
            for m in crudos.motivos
        ],
        diferencias_de_rendicion=FilaDeDiferenciasDeRendicion(
            armar_cifras_de_ajuste(crudos.diferencias_de_rendicion.cifras, ve_costos=ve_costos),
            _productos_armados(crudos.diferencias_de_rendicion.productos, ve_costos=ve_costos),
        ),
        ajustes_anulados=crudos.ajustes_anulados,
    )


# --- Saldos de clientes y proveedores (change 26, grupo 7; CC-04, INV-13, D8) ----------------


def obtener_saldos_de_clientes(
    organizacion_id: UUID,
    sesion: Session,
    *,
    saldo: str,
    vendedor_id: UUID | None,
    estado: str | None,
    texto: str | None,
    pagina: int = 1,
) -> ClientesConSaldoCrudos:
    """`GET /reportes/saldos/clientes`: saldo actual de cada cliente con filtros, disponible y
    los totales adeudado y a favor de todo lo filtrado, en páginas de 50 (D14). Todo sale de
    `saldo_cuenta`, en la base."""
    return repository.saldos_de_clientes(
        organizacion_id,
        sesion,
        saldo=saldo,
        vendedor_id=vendedor_id,
        estado=estado,
        texto=texto,
        pagina=pagina,
    )


def obtener_saldos_de_proveedores(
    organizacion_id: UUID,
    sesion: Session,
    *,
    saldo: str,
    estado: str | None,
    texto: str | None,
    pagina: int = 1,
) -> ProveedoresConSaldoCrudos:
    """`GET /reportes/saldos/proveedores`: saldo actual de cada proveedor con filtros y totales,
    en páginas de 50 (D14)."""
    return repository.saldos_de_proveedores(
        organizacion_id, sesion, saldo=saldo, estado=estado, texto=texto, pagina=pagina
    )
