/**
 * Cómo se nombra y a dónde lleva cada operación de la bandeja de `/admin/revision` (change 25, tarea 13.2;
 * D3, D4, D11; SEG-06). Lógica pura, sin React. «Ver» se ofrece solo a quien puede abrir la pantalla de la
 * operación: ocultarlo es una comodidad, el servidor sigue validando cada petición.
 */

import type { CodigoPermiso } from '../identidad/permisos'

interface DatosDeTipo {
  etiqueta: string
  ruta: (id: string) => string
  /** Con cualquiera de estos permisos se abre la pantalla de la operación. */
  permisos: readonly CodigoPermiso[]
}

const TIPOS: Record<string, DatosDeTipo> = {
  VENTA: { etiqueta: 'Venta', ruta: (id) => `/admin/ventas/${id}`, permisos: ['VENDER', 'ANULAR_VENTA'] },
  COBRANZA: {
    etiqueta: 'Cobranza',
    ruta: (id) => `/admin/cobranzas/${id}`,
    permisos: ['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA'],
  },
  COMPRA: {
    etiqueta: 'Compra',
    ruta: (id) => `/admin/compras/${id}`,
    permisos: ['REGISTRAR_COMPRA', 'ANULAR_COMPRA'],
  },
  TRANSFERENCIA: {
    etiqueta: 'Transferencia',
    ruta: (id) => `/admin/stock/transferencias/${id}`,
    permisos: ['TRANSFERIR_STOCK'],
  },
  AJUSTE_STOCK: {
    etiqueta: 'Ajuste de stock',
    ruta: (id) => `/admin/stock/ajustes/${id}`,
    permisos: ['AJUSTAR_STOCK'],
  },
}

/** Los tipos de operación por los que se filtra la bandeja, en el orden en que se ofrecen. */
export const OPCIONES_DE_TIPO: readonly { valor: string; etiqueta: string }[] = Object.entries(TIPOS).map(
  ([valor, datos]) => ({ valor, etiqueta: datos.etiqueta }),
)

export function etiquetaDeTipoDeOperacion(tipo: string): string {
  return TIPOS[tipo]?.etiqueta ?? tipo
}

/** El título del resumen de la operación; sin resumen (sin puerto del módulo dueño), «Operación {tipo}». */
export function tituloDeOperacion(tipo: string, resumen: { titulo: string } | null): string {
  return resumen?.titulo ?? `Operación ${etiquetaDeTipoDeOperacion(tipo)}`
}

/** La pantalla de la operación, o `null` si el tipo no tiene. */
export function rutaDeOperacion(tipo: string, id: string): string | null {
  return TIPOS[tipo]?.ruta(id) ?? null
}

/** `tiene` es el predicado de permisos de la sesión. */
export function puedeVerOperacion(tipo: string, tiene: (permiso: CodigoPermiso) => boolean): boolean {
  const permisos = TIPOS[tipo]?.permisos ?? []
  return permisos.some((permiso) => tiene(permiso))
}
