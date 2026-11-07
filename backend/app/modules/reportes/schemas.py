"""Esquemas Pydantic de salida de `reportes` (change 26; `design.md` D3).

Los importes y las cantidades decimales viajan como string (INV-03, `CLAUDE.md` §4); las unidades
base y los conteos, como enteros. Costo vendido, utilidad y el bloque `sin_costo` son `null` sin
`VER_UTILIDAD` (REP-04).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_serializer

from app.core.money import redondear_importe
from app.modules.reportes.domain.armado import CifrasDeAjuste, CifrasDeVentas, SinCosto
from app.modules.reportes.domain.paginacion import Sobre
from app.modules.reportes.domain.periodo import Periodo
from app.modules.reportes.queries import (
    DetalleDeJornada,
    FilaDeDiferenciasDeRendicion,
    FilaDeJornada,
    FilaDeMotivo,
    FilaDeObservaciones,
    FilaDeProductoAjustado,
    FilaDeVendedor,
    FilaPorDia,
    FilaPorProducto,
    FilaPorVendedor,
    ReporteDeAjustes,
    ReporteDeObservaciones,
    ReporteDeRendiciones,
    ReporteDeVentas,
)
from app.modules.reportes.repository import (
    AnuladasCrudas,
    ClientesConSaldoCrudos,
    CobranzasCrudas,
    ContadorCrudo,
    DineroCrudo,
    PresentacionVendidaCruda,
    ProveedoresConSaldoCrudos,
    TotalCrudo,
    VentaAnuladaCruda,
)


def importe_a_texto(valor: Decimal) -> str:
    """Un importe como string con 2 decimales (INV-03): `"31250.00"`."""
    return str(redondear_importe(valor))


class SobreDePaginaResponse(BaseModel):
    """Dónde está una página dentro de su lista (D14): el tamaño es fijo en el servidor y
    `paginas` es 0 sin filas. Cada lista paginada suma su `filas` en una subclase."""

    pagina: int
    tamano: int
    total_filas: int
    paginas: int


def _datos_del_sobre[T](sobre: Sobre[T]) -> dict[str, int]:
    return {
        "pagina": sobre.pagina,
        "tamano": sobre.tamano,
        "total_filas": sobre.total_filas,
        "paginas": sobre.paginas,
    }


class PeriodoResponse(BaseModel):
    desde: date
    hasta: date
    zona_horaria: str


class SinCostoResponse(BaseModel):
    """Las líneas vendidas sin costo (ADR-054): fuera del costo vendido y de la utilidad."""

    lineas: int
    importe_neto: str


class CifrasDeVentasResponse(BaseModel):
    cantidad_ventas: int
    cajas_equivalentes: str
    unidades_base: int
    importe_bruto: str
    importe_descuento: str
    importe_neto: str
    importe_iva: str
    total: str
    costo_vendido: str | None
    utilidad: str | None
    sin_costo: SinCostoResponse | None


class VentasPorDiaResponse(CifrasDeVentasResponse):
    fecha: date


class VentasPorVendedorResponse(CifrasDeVentasResponse):
    vendedor_id: UUID
    vendedor_nombre: str


class PresentacionVendidaResponse(BaseModel):
    """El detalle de un producto por presentación vendida (REP-03, VTA-02)."""

    presentacion_id: UUID
    nombre: str
    unidades_presentacion: int
    cantidad: int
    unidades_base: int


class VentasPorProductoResponse(BaseModel):
    """Sin costo ni utilidad: la utilidad por producto es REP-06 (etapa 2)."""

    producto_id: UUID
    codigo: str
    nombre: str
    cajas_equivalentes: str
    unidades_base: int
    importe_neto: str
    presentaciones: list[PresentacionVendidaResponse]


class VentaAnuladaResponse(BaseModel):
    venta_id: UUID
    numero: str
    occurred_at: datetime
    cliente_id: UUID
    cliente_nombre: str
    vendedor_id: UUID
    vendedor_nombre: str
    total: str
    anulada_en: datetime | None
    motivo: str | None
    devuelve_dinero: bool | None


class VentasPorDiaPaginaResponse(SobreDePaginaResponse):
    filas: list[VentasPorDiaResponse]


class VentasPorProductoPaginaResponse(SobreDePaginaResponse):
    filas: list[VentasPorProductoResponse]


class VentasAnuladasPaginaResponse(SobreDePaginaResponse):
    filas: list[VentaAnuladaResponse]


class AnuladasResponse(BaseModel):
    """`cantidad` y `total` son los de todo el período; `ventas` es la página pedida."""

    cantidad: int
    total: str
    ventas: VentasAnuladasPaginaResponse


class ReporteDeVentasResponse(BaseModel):
    periodo: PeriodoResponse
    ve_utilidad: bool
    resumen: CifrasDeVentasResponse
    por_dia: VentasPorDiaPaginaResponse
    por_vendedor: list[VentasPorVendedorResponse]
    por_producto: VentasPorProductoPaginaResponse
    anuladas: AnuladasResponse


def _sin_costo(sin_costo: SinCosto | None) -> SinCostoResponse | None:
    if sin_costo is None:
        return None
    return SinCostoResponse(
        lineas=sin_costo.lineas, importe_neto=importe_a_texto(sin_costo.importe_neto)
    )


def _opcional(valor: Decimal | None) -> str | None:
    return None if valor is None else importe_a_texto(valor)


def _cifras(cifras: CifrasDeVentas) -> dict[str, object]:
    return {
        "cantidad_ventas": cifras.cantidad_ventas,
        "cajas_equivalentes": str(cifras.cajas_equivalentes),
        "unidades_base": cifras.unidades_base,
        "importe_bruto": importe_a_texto(cifras.importe_bruto),
        "importe_descuento": importe_a_texto(cifras.importe_descuento),
        "importe_neto": importe_a_texto(cifras.importe_neto),
        "importe_iva": importe_a_texto(cifras.importe_iva),
        "total": importe_a_texto(cifras.total),
        "costo_vendido": _opcional(cifras.costo_vendido),
        "utilidad": _opcional(cifras.utilidad),
        "sin_costo": _sin_costo(cifras.sin_costo),
    }


def periodo_response(periodo: Periodo) -> PeriodoResponse:
    return PeriodoResponse(
        desde=periodo.desde, hasta=periodo.hasta, zona_horaria=periodo.zona_horaria
    )


def _por_dia(fila: FilaPorDia) -> VentasPorDiaResponse:
    return VentasPorDiaResponse(fecha=fila.fecha, **_cifras(fila.cifras))  # type: ignore[arg-type]


def _por_vendedor(fila: FilaPorVendedor) -> VentasPorVendedorResponse:
    return VentasPorVendedorResponse(
        vendedor_id=fila.vendedor_id,
        vendedor_nombre=fila.vendedor_nombre,
        **_cifras(fila.cifras),  # type: ignore[arg-type]
    )


def _presentacion(presentacion: PresentacionVendidaCruda) -> PresentacionVendidaResponse:
    return PresentacionVendidaResponse(
        presentacion_id=presentacion.presentacion_id,
        nombre=presentacion.nombre,
        unidades_presentacion=presentacion.unidades_presentacion,
        cantidad=presentacion.cantidad,
        unidades_base=presentacion.unidades_base,
    )


def _por_producto(fila: FilaPorProducto) -> VentasPorProductoResponse:
    return VentasPorProductoResponse(
        producto_id=fila.producto_id,
        codigo=fila.codigo,
        nombre=fila.nombre,
        cajas_equivalentes=str(fila.cifras.cajas_equivalentes),
        unidades_base=fila.cifras.unidades_base,
        importe_neto=importe_a_texto(fila.cifras.importe_neto),
        presentaciones=[_presentacion(p) for p in fila.presentaciones],
    )


def _anulada(venta: VentaAnuladaCruda) -> VentaAnuladaResponse:
    return VentaAnuladaResponse(
        venta_id=venta.venta_id,
        numero=venta.numero,
        occurred_at=venta.occurred_at,
        cliente_id=venta.cliente_id,
        cliente_nombre=venta.cliente_nombre,
        vendedor_id=venta.vendedor_id,
        vendedor_nombre=venta.vendedor_nombre,
        total=importe_a_texto(venta.total),
        anulada_en=venta.anulada_en,
        motivo=venta.motivo,
        devuelve_dinero=venta.devuelve_dinero,
    )


def _anuladas(anuladas: AnuladasCrudas) -> AnuladasResponse:
    return AnuladasResponse(
        cantidad=anuladas.cantidad,
        total=importe_a_texto(anuladas.total),
        ventas=VentasAnuladasPaginaResponse(
            filas=[_anulada(venta) for venta in anuladas.ventas.filas],
            **_datos_del_sobre(anuladas.ventas),
        ),
    )


def reporte_de_ventas_response(reporte: ReporteDeVentas) -> ReporteDeVentasResponse:
    return ReporteDeVentasResponse(
        periodo=periodo_response(reporte.periodo),
        ve_utilidad=reporte.ve_utilidad,
        resumen=CifrasDeVentasResponse(**_cifras(reporte.resumen)),  # type: ignore[arg-type]
        por_dia=VentasPorDiaPaginaResponse(
            filas=[_por_dia(fila) for fila in reporte.por_dia.filas],
            **_datos_del_sobre(reporte.por_dia),
        ),
        por_vendedor=[_por_vendedor(fila) for fila in reporte.por_vendedor],
        por_producto=VentasPorProductoPaginaResponse(
            filas=[_por_producto(fila) for fila in reporte.por_producto.filas],
            **_datos_del_sobre(reporte.por_producto),
        ),
        anuladas=_anuladas(reporte.anuladas),
    )


# --- Rendiciones (change 26, grupo 4; RUT-07) -------------------------------------------------


class TotalResponse(BaseModel):
    cantidad: int
    total: str


class MedioCobradoResponse(BaseModel):
    medio_pago_id: UUID
    nombre: str | None
    total: str


class CobranzasResponse(BaseModel):
    cantidad: int
    total: str
    por_medio: list[MedioCobradoResponse]


class DineroResponse(BaseModel):
    """Ventas vigentes, anuladas y cobranzas confirmadas por medio de pago (RUT-07)."""

    ventas: TotalResponse
    anuladas: TotalResponse
    cobranzas: CobranzasResponse


class JornadaDeRendicionResponse(BaseModel):
    """Una jornada del período. `despues_de_la_rendicion` es nulo mientras no se rindió;
    `faltantes`, `sobrantes` y `valor_de_diferencias` son nulos «sin conteo» y el valor, además,
    sin `VER_COSTOS`."""

    jornada_id: UUID
    vendedor_id: UUID
    vendedor_nombre: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    estado: str
    en_curso: bool
    abierta_en: datetime
    rendida_en: datetime | None
    cerrada_en: datetime | None
    liberada_en: datetime | None
    con_conteo: bool
    ventas: TotalResponse
    anuladas: TotalResponse
    cobranzas: CobranzasResponse
    despues_de_la_rendicion: DineroResponse | None
    faltantes: int | None
    sobrantes: int | None
    valor_de_diferencias: str | None


class VendedorDeRendicionResponse(BaseModel):
    vendedor_id: UUID
    vendedor_nombre: str
    jornadas: int
    ventas: TotalResponse
    anuladas: TotalResponse
    cobranzas: CobranzasResponse
    faltantes: int
    sobrantes: int
    valor_de_diferencias: str | None


class JornadasPaginaResponse(SobreDePaginaResponse):
    filas: list[JornadaDeRendicionResponse]


class ReporteDeRendicionesResponse(BaseModel):
    periodo: PeriodoResponse
    ve_costos: bool
    jornadas: JornadasPaginaResponse
    por_vendedor: list[VendedorDeRendicionResponse]


def _total(total: TotalCrudo) -> TotalResponse:
    return TotalResponse(cantidad=total.cantidad, total=importe_a_texto(total.total))


def _cobranzas(cobranzas: CobranzasCrudas) -> CobranzasResponse:
    return CobranzasResponse(
        cantidad=cobranzas.cantidad,
        total=importe_a_texto(cobranzas.total),
        por_medio=[
            MedioCobradoResponse(
                medio_pago_id=m.medio_pago_id, nombre=m.nombre, total=importe_a_texto(m.total)
            )
            for m in cobranzas.por_medio
        ],
    )


def _dinero(dinero: DineroCrudo) -> DineroResponse:
    return DineroResponse(
        ventas=_total(dinero.ventas),
        anuladas=_total(dinero.anuladas),
        cobranzas=_cobranzas(dinero.cobranzas),
    )


def _jornada_de_rendicion(fila: FilaDeJornada) -> JornadaDeRendicionResponse:
    j = fila.jornada
    return JornadaDeRendicionResponse(
        jornada_id=j.jornada_id,
        vendedor_id=j.vendedor_id,
        vendedor_nombre=j.vendedor_nombre,
        ubicacion_id=j.ubicacion_id,
        ubicacion_nombre=j.ubicacion_nombre,
        estado=j.estado,
        en_curso=j.estado == "ABIERTA",
        abierta_en=j.abierta_en,
        rendida_en=j.rendida_en,
        cerrada_en=j.cerrada_en,
        liberada_en=j.liberada_en,
        con_conteo=j.con_conteo,
        ventas=_total(j.dinero.ventas),
        anuladas=_total(j.dinero.anuladas),
        cobranzas=_cobranzas(j.dinero.cobranzas),
        despues_de_la_rendicion=(
            None if j.despues_de_la_rendicion is None else _dinero(j.despues_de_la_rendicion)
        ),
        faltantes=None if j.diferencias is None else j.diferencias.faltantes,
        sobrantes=None if j.diferencias is None else j.diferencias.sobrantes,
        valor_de_diferencias=_opcional(fila.valor_de_diferencias),
    )


def _vendedor_de_rendicion(fila: FilaDeVendedor) -> VendedorDeRendicionResponse:
    v = fila.vendedor
    return VendedorDeRendicionResponse(
        vendedor_id=v.vendedor_id,
        vendedor_nombre=v.vendedor_nombre,
        jornadas=v.jornadas,
        ventas=_total(v.dinero.ventas),
        anuladas=_total(v.dinero.anuladas),
        cobranzas=_cobranzas(v.dinero.cobranzas),
        faltantes=v.diferencias.faltantes,
        sobrantes=v.diferencias.sobrantes,
        valor_de_diferencias=_opcional(fila.valor_de_diferencias),
    )


def reporte_de_rendiciones_response(reporte: ReporteDeRendiciones) -> ReporteDeRendicionesResponse:
    return ReporteDeRendicionesResponse(
        periodo=periodo_response(reporte.periodo),
        ve_costos=reporte.ve_costos,
        jornadas=JornadasPaginaResponse(
            filas=[_jornada_de_rendicion(fila) for fila in reporte.jornadas.filas],
            **_datos_del_sobre(reporte.jornadas),
        ),
        por_vendedor=[_vendedor_de_rendicion(fila) for fila in reporte.por_vendedor],
    )


# El detalle de una jornada: la misma forma que `GET /stock/jornadas/{id}/resumen` (change 24),
# porque la pantalla reutiliza el componente de ese resumen. `reportes` no importa los esquemas de
# `stock` (contrato de import-linter): se repite la forma y se arma desde el resumen de su
# `service.py`. Sin `VER_COSTOS` las claves de valor no se establecen y la ruta las omite.


class LineaDelResumenDeReporteResponse(BaseModel):
    producto_id: UUID
    # Resueltos en SQL por `reportes`: quien lee reportes no tiene el permiso del catálogo.
    producto_codigo: str | None
    producto_nombre: str | None
    unidades_referencia: int | None
    nombre_referencia: str | None
    al_abrir: int
    ingresos: int
    ventas: int
    anulaciones: int
    otros: int
    esperado: int
    contado: int | None
    diferencia: int | None
    valor_diferencia: Decimal | None = None

    @field_serializer("valor_diferencia")
    def _serializar_valor(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class TotalDeResumenResponse(BaseModel):
    cantidad: int
    total: Decimal

    @field_serializer("total")
    def _serializar_total(self, valor: Decimal) -> str:
        return str(valor)


class MedioDeResumenResponse(BaseModel):
    medio_pago_id: UUID
    nombre: str | None
    total: Decimal

    @field_serializer("total")
    def _serializar_total(self, valor: Decimal) -> str:
        return str(valor)


class CobranzasDeResumenResponse(BaseModel):
    cantidad: int
    total: Decimal
    por_medio: list[MedioDeResumenResponse]

    @field_serializer("total")
    def _serializar_total(self, valor: Decimal) -> str:
        return str(valor)


class DineroDeResumenResponse(BaseModel):
    ventas: TotalDeResumenResponse
    anuladas: TotalDeResumenResponse
    cobranzas: CobranzasDeResumenResponse
    cobranzas_anuladas: CobranzasDeResumenResponse


class ResumenDeJornadaDeReporteResponse(BaseModel):
    jornada_id: UUID
    estado: str
    con_conteo: bool
    rendida_en: datetime | None
    lineas: list[LineaDelResumenDeReporteResponse]
    dinero: DineroDeResumenResponse
    despues_de_la_rendicion: DineroDeResumenResponse | None
    valor_de_diferencias: Decimal | None = None

    @field_serializer("valor_de_diferencias")
    def _serializar_valor(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


_CAMPOS_DE_LINEA = (
    "producto_id",
    "al_abrir",
    "ingresos",
    "ventas",
    "anulaciones",
    "otros",
    "esperado",
    "contado",
    "diferencia",
)


def resumen_de_jornada_de_reporte_response(
    detalle: DetalleDeJornada, *, ve_costos: bool
) -> ResumenDeJornadaDeReporteResponse:
    """Sin `ve_costos` los campos de valor no se establecen (la ruta los omite)."""
    resumen = detalle.resumen
    lineas: list[LineaDelResumenDeReporteResponse] = []
    for linea in resumen.lineas:
        datos = {campo: getattr(linea, campo) for campo in _CAMPOS_DE_LINEA}
        producto = detalle.productos.get(linea.producto_id)
        datos["producto_codigo"] = None if producto is None else producto.codigo
        datos["producto_nombre"] = None if producto is None else producto.nombre
        datos["unidades_referencia"] = None if producto is None else producto.unidades_referencia
        datos["nombre_referencia"] = None if producto is None else producto.nombre_referencia
        if ve_costos:
            datos["valor_diferencia"] = linea.valor_diferencia
        lineas.append(LineaDelResumenDeReporteResponse.model_validate(datos))
    campos: dict[str, object] = {
        "jornada_id": resumen.jornada_id,
        "estado": resumen.estado,
        "con_conteo": resumen.con_conteo,
        "rendida_en": resumen.rendida_en,
        "lineas": lineas,
        "dinero": DineroDeResumenResponse.model_validate(resumen.dinero, from_attributes=True),
        "despues_de_la_rendicion": (
            None
            if resumen.despues_de_la_rendicion is None
            else DineroDeResumenResponse.model_validate(
                resumen.despues_de_la_rendicion, from_attributes=True
            )
        ),
    }
    if ve_costos:
        campos["valor_de_diferencias"] = resumen.valor_de_diferencias
    return ResumenDeJornadaDeReporteResponse.model_validate(campos)


# --- Observaciones por vendedor (change 26, grupo 5; SYN-06, SYN-07) --------------------------


class ContadorResponse(BaseModel):
    total: int
    pendientes: int


class AvisoPorCodigoResponse(BaseModel):
    codigo: str
    total: int
    pendientes: int


class ObservacionesDeVendedorResponse(BaseModel):
    """Solo cantidades: el detalle de cada aviso sigue en «Revisión» (`design.md` D9).
    `excesos_de_credito_detectados` es el aviso `EXCESO_CREDITO_DETECTADO_SYNC` (CRE-09), que
    también figura en `avisos_por_codigo`."""

    vendedor_id: UUID
    vendedor_nombre: str
    ventas_sin_conexion: int
    avisos: ContadorResponse
    avisos_por_codigo: list[AvisoPorCodigoResponse]
    rechazadas: ContadorResponse
    excesos_de_credito_detectados: ContadorResponse


class ReporteDeObservacionesResponse(BaseModel):
    periodo: PeriodoResponse
    vendedores: list[ObservacionesDeVendedorResponse]


def _contador(contador: ContadorCrudo) -> ContadorResponse:
    return ContadorResponse(total=contador.total, pendientes=contador.pendientes)


def _observaciones_de_vendedor(fila: FilaDeObservaciones) -> ObservacionesDeVendedorResponse:
    v = fila.operaciones
    return ObservacionesDeVendedorResponse(
        vendedor_id=v.vendedor_id,
        vendedor_nombre=v.vendedor_nombre,
        ventas_sin_conexion=v.ventas_sin_conexion,
        avisos=_contador(v.avisos),
        avisos_por_codigo=[
            AvisoPorCodigoResponse(
                codigo=a.codigo, total=a.contador.total, pendientes=a.contador.pendientes
            )
            for a in v.avisos_por_codigo
        ],
        rechazadas=_contador(v.rechazadas),
        excesos_de_credito_detectados=_contador(fila.excesos_de_credito_detectados),
    )


def reporte_de_observaciones_response(
    reporte: ReporteDeObservaciones,
) -> ReporteDeObservacionesResponse:
    return ReporteDeObservacionesResponse(
        periodo=periodo_response(reporte.periodo),
        vendedores=[_observaciones_de_vendedor(fila) for fila in reporte.vendedores],
    )


# --- Ajustes por motivo (change 26, grupo 6; STK-03, RUT-06) ----------------------------------


class CifrasDeAjusteResponse(BaseModel):
    """Unidades base que entraron y salieron; los valores (string) y las unidades sin costo solo
    existen con `VER_COSTOS` (`null` sin él)."""

    entradas: int
    salidas: int
    valor_de_entradas: str | None
    valor_de_salidas: str | None
    unidades_sin_costo: int | None


class ProductoAjustadoResponse(CifrasDeAjusteResponse):
    producto_id: UUID
    codigo: str
    nombre: str


class MotivoDeAjusteResponse(CifrasDeAjusteResponse):
    motivo_id: UUID
    motivo_nombre: str
    ajustes: int
    productos: list[ProductoAjustadoResponse]


class DiferenciasDeRendicionResponse(CifrasDeAjusteResponse):
    """La fila «Diferencias de rendición» (RUT-06): sin motivo, con las mismas columnas."""

    productos: list[ProductoAjustadoResponse]


class ReporteDeAjustesResponse(BaseModel):
    periodo: PeriodoResponse
    ve_costos: bool
    motivos: list[MotivoDeAjusteResponse]
    diferencias_de_rendicion: DiferenciasDeRendicionResponse
    ajustes_anulados: int


def _cifras_de_ajuste(cifras: CifrasDeAjuste) -> dict[str, object]:
    return {
        "entradas": cifras.entradas,
        "salidas": cifras.salidas,
        "valor_de_entradas": _opcional(cifras.valor_de_entradas),
        "valor_de_salidas": _opcional(cifras.valor_de_salidas),
        "unidades_sin_costo": cifras.unidades_sin_costo,
    }


def _producto_ajustado(fila: FilaDeProductoAjustado) -> ProductoAjustadoResponse:
    return ProductoAjustadoResponse(
        producto_id=fila.producto_id,
        codigo=fila.codigo,
        nombre=fila.nombre,
        **_cifras_de_ajuste(fila.cifras),  # type: ignore[arg-type]
    )


def _motivo_de_ajuste(fila: FilaDeMotivo) -> MotivoDeAjusteResponse:
    return MotivoDeAjusteResponse(
        motivo_id=fila.motivo_id,
        motivo_nombre=fila.nombre,
        ajustes=fila.ajustes,
        productos=[_producto_ajustado(p) for p in fila.productos],
        **_cifras_de_ajuste(fila.cifras),  # type: ignore[arg-type]
    )


def _diferencias_de_rendicion(fila: FilaDeDiferenciasDeRendicion) -> DiferenciasDeRendicionResponse:
    return DiferenciasDeRendicionResponse(
        productos=[_producto_ajustado(p) for p in fila.productos],
        **_cifras_de_ajuste(fila.cifras),  # type: ignore[arg-type]
    )


def reporte_de_ajustes_response(reporte: ReporteDeAjustes) -> ReporteDeAjustesResponse:
    return ReporteDeAjustesResponse(
        periodo=periodo_response(reporte.periodo),
        ve_costos=reporte.ve_costos,
        motivos=[_motivo_de_ajuste(fila) for fila in reporte.motivos],
        diferencias_de_rendicion=_diferencias_de_rendicion(reporte.diferencias_de_rendicion),
        ajustes_anulados=reporte.ajustes_anulados,
    )


# --- Saldos de clientes y proveedores (change 26, grupo 7; CC-04, INV-13) ---------------------


class ClienteConSaldoResponse(BaseModel):
    """Un cliente con su saldo actual; `disponible` es el límite menos el saldo (`null` sin
    límite)."""

    cliente_id: UUID
    codigo: str | None
    nombre: str
    razon_social: str | None
    vendedor_id: UUID | None
    vendedor_nombre: str | None
    estado: str
    limite_credito: str | None
    saldo: str
    disponible: str | None


class ClientesConSaldoPaginaResponse(SobreDePaginaResponse):
    filas: list[ClienteConSaldoResponse]


class VendedorConClientesResponse(BaseModel):
    id: UUID
    nombre: str


class ReporteDeSaldosDeClientesResponse(BaseModel):
    """`total_adeudado` suma los saldos positivos y `total_a_favor` los negativos (negativo), de
    todo lo filtrado y no de la página. `vendedores` son todos los que tienen clientes asignados,
    por nombre, sin importar la página ni los filtros."""

    clientes: ClientesConSaldoPaginaResponse
    vendedores: list[VendedorConClientesResponse]
    total_adeudado: str
    total_a_favor: str


class ProveedorConSaldoResponse(BaseModel):
    proveedor_id: UUID
    nombre: str
    estado: str
    saldo: str


class ProveedoresConSaldoPaginaResponse(SobreDePaginaResponse):
    filas: list[ProveedorConSaldoResponse]


class ReporteDeSaldosDeProveedoresResponse(BaseModel):
    proveedores: ProveedoresConSaldoPaginaResponse
    total_adeudado: str
    total_a_favor: str


def _importe_o_nulo(valor: Decimal | None) -> str | None:
    return None if valor is None else importe_a_texto(valor)


def reporte_de_saldos_de_clientes_response(
    reporte: ClientesConSaldoCrudos,
) -> ReporteDeSaldosDeClientesResponse:
    return ReporteDeSaldosDeClientesResponse(
        clientes=ClientesConSaldoPaginaResponse(
            filas=[
                ClienteConSaldoResponse(
                    cliente_id=c.cliente_id,
                    codigo=c.codigo,
                    nombre=c.nombre,
                    razon_social=c.razon_social,
                    vendedor_id=c.vendedor_id,
                    vendedor_nombre=c.vendedor_nombre,
                    estado=c.estado,
                    limite_credito=_importe_o_nulo(c.limite_credito),
                    saldo=importe_a_texto(c.saldo),
                    disponible=_importe_o_nulo(c.disponible),
                )
                for c in reporte.clientes.filas
            ],
            **_datos_del_sobre(reporte.clientes),
        ),
        vendedores=[
            VendedorConClientesResponse(id=v.vendedor_id, nombre=v.vendedor_nombre)
            for v in reporte.vendedores
        ],
        total_adeudado=importe_a_texto(reporte.totales.adeudado),
        total_a_favor=importe_a_texto(reporte.totales.a_favor),
    )


def reporte_de_saldos_de_proveedores_response(
    reporte: ProveedoresConSaldoCrudos,
) -> ReporteDeSaldosDeProveedoresResponse:
    return ReporteDeSaldosDeProveedoresResponse(
        proveedores=ProveedoresConSaldoPaginaResponse(
            filas=[
                ProveedorConSaldoResponse(
                    proveedor_id=p.proveedor_id,
                    nombre=p.nombre,
                    estado=p.estado,
                    saldo=importe_a_texto(p.saldo),
                )
                for p in reporte.proveedores.filas
            ],
            **_datos_del_sobre(reporte.proveedores),
        ),
        total_adeudado=importe_a_texto(reporte.totales.adeudado),
        total_a_favor=importe_a_texto(reporte.totales.a_favor),
    )
