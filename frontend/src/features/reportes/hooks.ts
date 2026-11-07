import { keepPreviousData, useQuery } from '@tanstack/react-query'

import {
  obtenerDetalleDeRendicion,
  obtenerReporteDeAjustes,
  obtenerReporteDeObservaciones,
  obtenerReporteDeRendiciones,
  obtenerReporteDeSaldosDeClientes,
  obtenerReporteDeSaldosDeProveedores,
  obtenerReporteDeVentas,
} from './api'
import {
  clavesReportes,
  type FiltrosDePeriodo,
  type FiltrosDeRendiciones,
  type FiltrosDeSaldosDeClientes,
  type FiltrosDeSaldosDeProveedores,
  type FiltrosDeVentas,
} from './claves'

/**
 * Lecturas de los reportes (change 26). TanStack Query solo en `/admin` (`CLAUDE.md` §2). `habilitado` es el
 * permiso (`VER_REPORTES`): sin él no se pide nada (SEG-06). Un rechazo de dominio (período inválido) no se
 * reintenta: el reporte se vuelve a pedir al cambiar el filtro. Al cambiar un filtro se sigue viendo el reporte
 * anterior mientras llega el nuevo.
 */
export function useReporteDeVentas(filtros: FiltrosDeVentas, habilitado = true) {
  return useQuery({
    queryKey: clavesReportes.ventas(filtros),
    queryFn: () => obtenerReporteDeVentas(filtros),
    enabled: habilitado,
    retry: false,
    placeholderData: keepPreviousData,
  })
}

export function useReporteDeRendiciones(filtros: FiltrosDeRendiciones) {
  return useQuery({
    queryKey: clavesReportes.rendiciones(filtros),
    queryFn: () => obtenerReporteDeRendiciones(filtros),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

/** El resumen de una jornada desde el reporte; sin id no se pide nada. */
export function useDetalleDeRendicion(jornadaId: string | undefined) {
  return useQuery({
    queryKey: clavesReportes.detalleDeRendicion(jornadaId ?? ''),
    queryFn: () => obtenerDetalleDeRendicion(jornadaId as string),
    enabled: jornadaId !== undefined && jornadaId !== '',
    retry: false,
  })
}

export function useReporteDeObservaciones(filtros: FiltrosDePeriodo) {
  return useQuery({
    queryKey: clavesReportes.observaciones(filtros),
    queryFn: () => obtenerReporteDeObservaciones(filtros),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

export function useReporteDeAjustes(filtros: FiltrosDePeriodo) {
  return useQuery({
    queryKey: clavesReportes.ajustes(filtros),
    queryFn: () => obtenerReporteDeAjustes(filtros),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

export function useReporteDeSaldosDeClientes(filtros: FiltrosDeSaldosDeClientes) {
  return useQuery({
    queryKey: clavesReportes.saldosDeClientes(filtros),
    queryFn: () => obtenerReporteDeSaldosDeClientes(filtros),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

/** `habilitado` es la regla compuesta de D8 = B: sin ella no se pide nada (SEG-06). */
export function useReporteDeSaldosDeProveedores(filtros: FiltrosDeSaldosDeProveedores, habilitado: boolean) {
  return useQuery({
    queryKey: clavesReportes.saldosDeProveedores(filtros),
    queryFn: () => obtenerReporteDeSaldosDeProveedores(filtros),
    enabled: habilitado,
    retry: false,
    placeholderData: keepPreviousData,
  })
}
