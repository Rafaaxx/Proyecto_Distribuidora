import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { CredencialDePin } from '../../domain/ventas/autorizacionDeVenta'
import type { VentaConfirmarDatos } from '../../domain/ventas/formularioVenta'
import { armarNotaDeVenta, NotaNoDisponibleParaModoC } from '../../domain/ventas/notaDeVenta'
import { generarPdfDeNota } from '../../lib/nota/pdf'
import { useMutacionConOperationId } from '../compras/hooks'
import { clavesCostoPromedio } from '../stock/claves'
import {
  anularVenta,
  buscarPreciosParaVender,
  confirmarVenta,
  listarVentas,
  listarVersionesElegibles,
  listarDescuentosAplicables,
  obtenerContextoDeVenta,
  obtenerCreditoParaVender,
  obtenerNotaDeVenta,
  obtenerNumeracion,
  obtenerVenta,
  type VentaAnularResultado,
  type VentaConfirmarResultado,
} from './api'
import { clavesVentas, type ContextoDePrecios, type FiltrosVentas } from './claves'
import { datosDeNotaDesdeApi } from './nota'

/**
 * Lecturas y escritura de ventas (change 18a, tarea 12.2). TanStack Query solo en `/admin`
 * (`CLAUDE.md` §2). Mismo mecanismo de `Operation-Id` que compras y cobranzas
 * (`useMutacionConOperationId`): se genera una vez por envío y el reintento automático ante un
 * error de RED reenvía exactamente el mismo valor (INV-06); un rechazo de dominio no se
 * reintenta. Desde `/admin` el comando de venta es `ONLINE`: no se encola nada.
 */

export function useVentas(filtros: FiltrosVentas = {}) {
  return useInfiniteQuery({
    queryKey: clavesVentas.listado(filtros),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) => listarVentas(filtros, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
  })
}

export function useVenta(ventaId: string | undefined) {
  return useQuery({
    queryKey: clavesVentas.detalle(ventaId ?? ''),
    queryFn: () => obtenerVenta(ventaId as string),
    enabled: ventaId !== undefined,
  })
}

/**
 * El buscador de productos: la búsqueda y la paginación las hace el servidor (`q`, cursor). No
 * pide nada sin cliente (la lista aplicable depende de él, PRC-20) ni con `habilitado` en falso.
 */
export function useBuscarPrecios(contexto: ContextoDePrecios, texto: string, habilitado: boolean) {
  return useInfiniteQuery({
    queryKey: clavesVentas.precios(contexto, texto),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      buscarPreciosParaVender({ ...contexto, texto, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina) => ultimaPagina.cursor_siguiente ?? undefined,
    enabled: habilitado && contexto.clienteId !== undefined,
  })
}

/**
 * Precio y stock vigentes de los productos del pedido, de a uno (`producto_id`): al cambiar la
 * lista, la versión o la ubicación se piden de nuevo con el contexto nuevo y el pedido nunca
 * muestra un precio de otra lista.
 */
export function usePreciosDeProductos(contexto: ContextoDePrecios, productoIds: readonly string[]) {
  return useQueries({
    queries: productoIds.map((productoId) => ({
      queryKey: clavesVentas.preciosDeProducto(contexto, productoId),
      queryFn: () => buscarPreciosParaVender({ ...contexto, productoId, limite: 1 }),
      enabled: contexto.clienteId !== undefined,
    })),
  })
}

/** Prefijo y último correlativo del dispositivo; se relee ante `NUMERO_DUPLICADO` (D4). */
export function useNumeracion() {
  return useQuery({ queryKey: clavesVentas.numeracion(), queryFn: obtenerNumeracion, staleTime: 0 })
}

/** Versiones elegibles de una lista; solo con `USAR_LISTA_ANTERIOR` y una lista elegida. */
export function useVersionesElegibles(listaId: string | undefined, habilitado: boolean) {
  return useQuery({
    queryKey: clavesVentas.versiones(listaId ?? ''),
    queryFn: () => listarVersionesElegibles(listaId as string),
    enabled: habilitado && listaId !== undefined && listaId !== '',
  })
}

type VariablesConfirmarVenta = VentaConfirmarDatos & { operationId?: string }

function useInvalidarTrasVender() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesVentas.raiz() })
    void queryClient.invalidateQueries({ queryKey: ['saldo-cliente'] })
    void queryClient.invalidateQueries({ queryKey: ['cobranzas'] })
    void queryClient.invalidateQueries({ queryKey: ['stock'] })
    void queryClient.invalidateQueries({ queryKey: ['cuentas-corrientes'] })
  }
}

type VariablesAnularVenta = {
  ventaId: string
  motivo_id: string
  observacion: string | null
  devuelve_dinero: boolean | null
  operationId?: string
}

/**
 * Anular mueve la venta, el saldo, la cobranza (si se devuelve el dinero), el stock y el estado
 * de cuenta (change 19): invalida lo mismo que confirmar, incluido el detalle y el listado.
 */
export function useAnularVenta() {
  const queryClient = useQueryClient()
  const invalidarTrasVender = useInvalidarTrasVender()
  const invalidar = () => {
    invalidarTrasVender()
    // El reingreso con costo recalcula el costo promedio (CST-11).
    void queryClient.invalidateQueries({ queryKey: clavesCostoPromedio.raiz() })
  }
  return useMutacionConOperationId<VariablesAnularVenta, VentaAnularResultado>(
    (variables, operationId) =>
      anularVenta(
        variables.ventaId,
        {
          motivo_id: variables.motivo_id,
          observacion: variables.observacion,
          devuelve_dinero: variables.devuelve_dinero,
        },
        operationId,
      ),
    invalidar,
  )
}

/**
 * Tope, motivos y autorizadores de quien vende (D15). Se pide una vez por pantalla y se relee al
 * volver: los permisos y los PIN pueden cambiar entre venta y venta.
 */
export function useContextoDeVenta(habilitado: boolean) {
  return useQuery({
    queryKey: clavesVentas.contexto(),
    queryFn: obtenerContextoDeVenta,
    enabled: habilitado,
    staleTime: 0,
    retry: false,
  })
}

/**
 * Reglas de descuento vigentes ahora, para mostrar los automáticos antes de confirmar (DSC-05).
 * Se relee al volver: una regla puede pausarse o activarse entre venta y venta. Si falla, la
 * pantalla sigue sin ellos y el servidor decide (`DESCUENTO_DIFIERE`).
 */
export function useDescuentosAplicables(habilitado: boolean) {
  return useQuery({
    queryKey: clavesVentas.descuentosAplicables(),
    queryFn: listarDescuentosAplicables,
    enabled: habilitado,
    staleTime: 0,
    retry: false,
  })
}

/** Crédito del cliente elegido (D16); se vuelve a pedir cada vez que se confirma una venta. */
export function useCreditoParaVender(clienteId: string | undefined) {
  return useQuery({
    queryKey: clavesVentas.credito(clienteId ?? ''),
    queryFn: () => obtenerCreditoParaVender(clienteId as string),
    enabled: clienteId !== undefined && clienteId !== '',
    staleTime: 0,
    retry: false,
  })
}

/**
 * Confirmar mueve ventas, saldo del cliente, cobranzas, stock y su estado de cuenta.
 *
 * `leerCredenciales` entrega el PIN de quien autoriza SOLO en el momento de enviar: el PIN no
 * viaja en las variables de la mutación (TanStack Query las conserva en memoria) ni se guarda en
 * ningún almacenamiento (D2, D20). Quien llama lo tiene en una referencia que borra al terminar.
 */
export function useConfirmarVenta(leerCredenciales: () => readonly CredencialDePin[] = () => []) {
  const invalidar = useInvalidarTrasVender()
  return useMutacionConOperationId<VariablesConfirmarVenta, VentaConfirmarResultado>((variables, operationId) => {
    const datos: VentaConfirmarDatos & { operationId?: string } = { ...variables }
    delete datos.operationId
    return confirmarVenta(datos, operationId, leerCredenciales())
  }, invalidar)
}

export type EstadoDeNotaDeVenta =
  | { estado: 'cargando' }
  | { estado: 'error'; reintentar: () => void }
  | { estado: 'no-disponible' }
  | { estado: 'lista'; numero: string; anulada: boolean; generarPdf: () => Promise<Blob> }

/**
 * La nota de una venta (change 20, tarea 7.1; VTA-13, D14): lee los datos congelados y arma el
 * contenido; el PDF se genera solo al pedirlo (`generarPdf`), con pdfmake cargado en diferido. Una
 * venta de modo C expone `no-disponible` (deuda de la etapa 4), no un error genérico. Sin
 * `habilitada` no pide nada.
 */
export function useNotaDeVenta(ventaId: string | undefined, habilitada = true): EstadoDeNotaDeVenta {
  const consulta = useQuery({
    queryKey: clavesVentas.nota(ventaId ?? ''),
    queryFn: async () => datosDeNotaDesdeApi(await obtenerNotaDeVenta(ventaId as string)),
    enabled: habilitada && ventaId !== undefined,
  })
  const datos = consulta.data
  const armado = useMemo(() => {
    if (datos === undefined) return null
    try {
      return { contenido: armarNotaDeVenta(datos), noDisponible: false, fallo: false }
    } catch (error) {
      return { contenido: null, noDisponible: error instanceof NotaNoDisponibleParaModoC, fallo: !(error instanceof NotaNoDisponibleParaModoC) }
    }
  }, [datos])

  if (consulta.isError || armado?.fallo === true) return { estado: 'error', reintentar: () => void consulta.refetch() }
  if (datos === undefined || armado === null) return { estado: 'cargando' }
  if (armado.noDisponible || armado.contenido === null) return { estado: 'no-disponible' }
  const contenido = armado.contenido
  return {
    estado: 'lista',
    numero: datos.numero,
    anulada: datos.estado === 'ANULADA',
    generarPdf: () => generarPdfDeNota(contenido),
  }
}
