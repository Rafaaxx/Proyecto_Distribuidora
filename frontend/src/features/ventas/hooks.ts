import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import type { CredencialDePin } from '../../domain/ventas/autorizacionDeVenta'
import type { VentaConfirmarDatos } from '../../domain/ventas/formularioVenta'
import { useMutacionConOperationId } from '../compras/hooks'
import {
  buscarPreciosParaVender,
  confirmarVenta,
  listarVentas,
  listarVersionesElegibles,
  listarDescuentosAplicables,
  obtenerContextoDeVenta,
  obtenerCreditoParaVender,
  obtenerNumeracion,
  obtenerVenta,
  type VentaConfirmarResultado,
} from './api'
import { clavesVentas, type ContextoDePrecios, type FiltrosVentas } from './claves'

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
