"""Rutas de lectura de los reportes de la etapa 1 (change 26; `design.md` D6, D11).

Todas son `GET` y exigen `VER_REPORTES` (la de saldos de proveedores suma la regla compuesta de
D8 cuando se agrega). Ninguna escribe ni toma bloqueos (REP-01). `organizacion_id` sale siempre del
token (INV-21); el reloj es inyectable para que la fecha de negocio de hoy se pueda fijar en
pruebas (`02` §9, TR-04).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.core.autenticacion import (
    ContextoAutenticado,
    requiere_algun_permiso,
    requiere_permiso,
)
from app.core.clock import Clock, SystemClock
from app.modules.identidad import service as identidad_service
from app.modules.reportes import queries
from app.modules.reportes.schemas import (
    ConsistenciaResponse,
    ReporteDeAjustesResponse,
    ReporteDeObservacionesResponse,
    ReporteDeRendicionesResponse,
    ReporteDeSaldosDeClientesResponse,
    ReporteDeSaldosDeProveedoresResponse,
    ReporteDeVentasResponse,
    ResumenDeJornadaDeReporteResponse,
    consistencia_response,
    reporte_de_ajustes_response,
    reporte_de_observaciones_response,
    reporte_de_rendiciones_response,
    reporte_de_saldos_de_clientes_response,
    reporte_de_saldos_de_proveedores_response,
    reporte_de_ventas_response,
    resumen_de_jornada_de_reporte_response,
)

# La página de una lista (D14): desde 1; 0 o negativo es 422. Una posterior a la última no es error.
Pagina = Annotated[int, Query(ge=1)]

PERMISO_VER_REPORTES = "VER_REPORTES"
PERMISO_VER_UTILIDAD = "VER_UTILIDAD"
PERMISO_VER_COSTOS = "VER_COSTOS"

router = APIRouter(prefix="/reportes", tags=["reportes"])

PERMISO_VER_CONSISTENCIA = "VER_CONSISTENCIA"

# El aviso de consistencia (change 28, D5) es una lectura que compone nombres de varios módulos
# por sus `service.py`, igual que los reportes; cuelga de `/sistema`, no de `/reportes`.
router_sistema = APIRouter(prefix="/sistema", tags=["sistema"])


def obtener_reloj() -> Clock:
    """El reloj de los reportes: el del sistema, sustituible con `dependency_overrides`."""
    return SystemClock()


def _tiene_permiso(contexto: ContextoAutenticado, sesion: Session, codigo: str) -> bool:
    permisos = identidad_service.listar_permisos_del_usuario(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    return codigo in permisos


@router.get("/ventas", response_model=ReporteDeVentasResponse)
def reporte_de_ventas(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    reloj: Annotated[Clock, Depends(obtener_reloj)],
    desde: date | None = None,
    hasta: date | None = None,
    vendedor_id: UUID | None = None,
    pagina_por_dia: Pagina = 1,
    pagina_por_producto: Pagina = 1,
    pagina_anuladas: Pagina = 1,
) -> ReporteDeVentasResponse:
    """Ventas del período (REP-01 a REP-05): resumen, por día y por vendedor de las `CONFIRMADA`,
    y las `ANULADA` aparte. «Por día» (la fecha más reciente primero), «Por producto» y las
    anuladas (la más reciente primero) viajan en páginas de 50, cada una por su lado (D14); lo
    demás, y la cantidad y el total de anuladas, son los de todo el período.
    Costo vendido y utilidad solo con `VER_UTILIDAD` (`null` sin él).
    Sin fechas, el mes en curso; un rango invertido es 422 `RANGO_DE_FECHAS_INVALIDO` y más de
    366 días, 422 `PERIODO_DEMASIADO_LARGO`."""
    reporte = queries.obtener_reporte_de_ventas(
        contexto.organizacion_id,
        sesion,
        reloj,
        desde=desde,
        hasta=hasta,
        vendedor_id=vendedor_id,
        ve_utilidad=_tiene_permiso(contexto, sesion, PERMISO_VER_UTILIDAD),
        pagina_por_dia=pagina_por_dia,
        pagina_por_producto=pagina_por_producto,
        pagina_anuladas=pagina_anuladas,
    )
    return reporte_de_ventas_response(reporte)


@router.get("/rendiciones", response_model=ReporteDeRendicionesResponse)
def reporte_de_rendiciones(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    reloj: Annotated[Clock, Depends(obtener_reloj)],
    desde: date | None = None,
    hasta: date | None = None,
    vendedor_id: UUID | None = None,
    estado: Literal["ABIERTA", "EN_RENDICION", "CERRADA", "LIBERADA"] | None = None,
    pagina: Pagina = 1,
) -> ReporteDeRendicionesResponse:
    """Rendiciones (RUT-07): las jornadas abiertas en el período (la más reciente primero, en
    páginas de 50, D14), de cualquier estado, con lo
    vendido, anulado y cobrado, lo registrado después de la rendición aparte y las diferencias del
    conteo («sin conteo» si no hay rendición), y los totales por vendedor. El valor de las
    diferencias solo con `VER_COSTOS` (`null` sin él)."""
    reporte = queries.obtener_reporte_de_rendiciones(
        contexto.organizacion_id,
        sesion,
        reloj,
        desde=desde,
        hasta=hasta,
        vendedor_id=vendedor_id,
        estado=estado,
        ve_costos=_tiene_permiso(contexto, sesion, PERMISO_VER_COSTOS),
        pagina=pagina,
    )
    return reporte_de_rendiciones_response(reporte)


@router.get(
    "/rendiciones/{jornada_id}",
    response_model=ResumenDeJornadaDeReporteResponse,
    response_model_exclude_unset=True,
)
def detalle_de_rendicion(
    jornada_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ResumenDeJornadaDeReporteResponse:
    """El resumen de RUT-07 de una jornada, con la misma implementación que el detalle de
    jornadas (`stock`) pero con `VER_REPORTES`. El valor de las diferencias (string) solo con
    `VER_COSTOS`. 404 si la jornada es ajena o no existe."""
    ve_costos = _tiene_permiso(contexto, sesion, PERMISO_VER_COSTOS)
    detalle = queries.obtener_resumen_de_jornada(
        contexto.organizacion_id, sesion, jornada_id=jornada_id, ve_costos=ve_costos
    )
    return resumen_de_jornada_de_reporte_response(detalle, ve_costos=ve_costos)


@router.get("/observaciones", response_model=ReporteDeObservacionesResponse)
def reporte_de_observaciones(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    reloj: Annotated[Clock, Depends(obtener_reloj)],
    desde: date | None = None,
    hasta: date | None = None,
) -> ReporteDeObservacionesResponse:
    """Observaciones por vendedor (SYN-06, SYN-07): ventas sin conexión, avisos por código (total
    y pendientes), operaciones rechazadas y excesos de crédito detectados al sincronizar, por el
    momento del comando. Solo cantidades: el detalle sigue en «Revisión»."""
    reporte = queries.obtener_reporte_de_observaciones(
        contexto.organizacion_id, sesion, reloj, desde=desde, hasta=hasta
    )
    return reporte_de_observaciones_response(reporte)


@router.get("/ajustes", response_model=ReporteDeAjustesResponse)
def reporte_de_ajustes(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    reloj: Annotated[Clock, Depends(obtener_reloj)],
    desde: date | None = None,
    hasta: date | None = None,
) -> ReporteDeAjustesResponse:
    """Ajustes por motivo (STK-03, RUT-06): los ajustes confirmados agrupados por motivo y
    producto, las diferencias de rendición en una fila aparte y la cantidad de ajustes anulados
    (no suman). El valor de cada sentido y las unidades sin costo solo con `VER_COSTOS` (`null`
    sin él)."""
    reporte = queries.obtener_reporte_de_ajustes(
        contexto.organizacion_id,
        sesion,
        reloj,
        desde=desde,
        hasta=hasta,
        ve_costos=_tiene_permiso(contexto, sesion, PERMISO_VER_COSTOS),
    )
    return reporte_de_ajustes_response(reporte)


FiltroDeSaldo = Literal["DEUDORES", "A_FAVOR", "CON_SALDO", "TODOS"]


@router.get("/saldos/clientes", response_model=ReporteDeSaldosDeClientesResponse)
def reporte_de_saldos_de_clientes(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    saldo: FiltroDeSaldo = "CON_SALDO",
    vendedor_id: UUID | None = None,
    estado: Literal["ACTIVO", "SUSPENDIDO", "INACTIVO"] | None = None,
    texto: str | None = None,
    pagina: Pagina = 1,
) -> ReporteDeSaldosDeClientesResponse:
    """Saldos de clientes (CC-04, INV-13): el saldo actual de `saldo_cuenta` (cero sin movimientos)
    con el límite y el disponible, ordenados por saldo descendente, y los totales adeudado y a
    favor de lo filtrado. Solo `VER_REPORTES`."""
    reporte = queries.obtener_saldos_de_clientes(
        contexto.organizacion_id,
        sesion,
        saldo=saldo,
        vendedor_id=vendedor_id,
        estado=estado,
        texto=texto,
        pagina=pagina,
    )
    return reporte_de_saldos_de_clientes_response(reporte)


@router.get(
    "/saldos/proveedores",
    response_model=ReporteDeSaldosDeProveedoresResponse,
    dependencies=[
        Depends(requiere_permiso(PERMISO_VER_REPORTES)),
        Depends(
            requiere_algun_permiso(
                "GESTIONAR_PROVEEDORES", "REGISTRAR_PAGO_PROVEEDOR", PERMISO_VER_UTILIDAD
            )
        ),
    ],
)
def reporte_de_saldos_de_proveedores(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_REPORTES))],
    sesion: Annotated[Session, Depends(get_session)],
    saldo: FiltroDeSaldo = "CON_SALDO",
    estado: Literal["ACTIVO", "INACTIVO"] | None = None,
    texto: str | None = None,
    pagina: Pagina = 1,
) -> ReporteDeSaldosDeProveedoresResponse:
    """Saldos de proveedores (CC-04, INV-13; D8 = B): `VER_REPORTES` y además
    `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`; sin la regla completa,
    403 `PERMISO_REQUERIDO`. Saldo actual, ordenado descendente, con los totales de lo filtrado."""
    reporte = queries.obtener_saldos_de_proveedores(
        contexto.organizacion_id, sesion, saldo=saldo, estado=estado, texto=texto, pagina=pagina
    )
    return reporte_de_saldos_de_proveedores_response(reporte)


@router_sistema.get("/consistencia", response_model=ConsistenciaResponse)
def consistencia_del_sistema(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_CONSISTENCIA))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ConsistenciaResponse:
    """El último resultado de la verificación de consistencia de la organización del token
    (ADR-015, `02` §7.6): momento de la corrida y, si hubo diferencias, el detalle con los nombres
    de cuentas, productos y ubicaciones. Solo lectura: nunca corrige un saldo. Sin ninguna corrida
    todavía, `resultado` y `ejecutada_en` vienen en `null`."""
    return consistencia_response(queries.obtener_consistencia(contexto.organizacion_id, sesion))
