import type { ValoresDelServidor } from '../../domain/ventas/formularioVenta'

/**
 * Error de dominio de ventas tal como lo expone la API (Problem Details,
 * `backend/app/main.py::_domain_error_a_problem_details`): `codigo` es el campo estable
 * (`PRECIO_DIFIERE`, `NUMERO_DUPLICADO`, `CONSUMIDOR_FINAL_CONTADO`, ...). `extension` son los
 * campos extra del problema (`lineas` y `total` en `PRECIO_DIFIERE`, `productos` en
 * `PRODUCTO_SIN_PRECIO`); `medio` es el índice 0-based del medio de la cobranza que causó el
 * error, o `null`. Mismo criterio que `features/cobranzas/errores.ts`.
 */
export class ErrorDeVentas extends Error {
  readonly codigo: string
  readonly medio: number | null
  readonly extension: Readonly<Record<string, unknown>>

  constructor(codigo: string, mensaje: string, medio: number | null = null, extension: Record<string, unknown> = {}) {
    super(mensaje)
    this.name = 'ErrorDeVentas'
    this.codigo = codigo
    this.medio = medio
    this.extension = extension
  }
}

/** El 403: `VENDER`, `ANULAR_VENTA`, `USAR_LISTA_ANTERIOR` (SEG-06). */
export class PermisoRequeridoVentasError extends ErrorDeVentas {
  constructor(mensaje: string) {
    super('PERMISO_REQUERIDO', mensaje)
    this.name = 'PermisoRequeridoVentasError'
  }
}

export type CampoDeVenta = 'cliente' | 'ubicacion' | 'lineas' | 'numero' | 'lista' | 'cobranza'

const CAMPO_POR_CODIGO: Record<string, CampoDeVenta> = {
  CLIENTE_SUSPENDIDO: 'cliente',
  CLIENTE_INACTIVO: 'cliente',
  UBICACION_REQUERIDA: 'ubicacion',
  UBICACION_INACTIVA: 'ubicacion',
  UBICACION_TOMADA: 'ubicacion',
  JORNADA_AJENA: 'ubicacion',
  VENTA_SIN_LINEAS: 'lineas',
  LINEAS_INVALIDAS: 'lineas',
  LINEA_DUPLICADA: 'lineas',
  CANTIDAD_INVALIDA: 'lineas',
  PRODUCTO_INACTIVO: 'lineas',
  PRESENTACION_NO_VENDIBLE: 'lineas',
  PRODUCTO_SIN_PRECIO: 'lineas',
  STOCK_INSUFICIENTE: 'lineas',
  NUMERO_INVALIDO: 'numero',
  MOTIVO_INVALIDO: 'lista',
  VERSION_NO_PERMITIDA: 'lista',
  SIN_LISTA_APLICABLE: 'lista',
  LISTA_SIN_VERSION_VIGENTE: 'lista',
  CONSUMIDOR_FINAL_CONTADO: 'cobranza',
  MEDIOS_NO_SUMAN_IMPORTE: 'cobranza',
  OBSERVACION_INVALIDA: 'cobranza',
}

/** Campo del formulario al que pertenece el error; `null` es un error general (reloj, duplicada, ...). */
export function campoDelError(error: ErrorDeVentas): CampoDeVenta | null {
  return CAMPO_POR_CODIGO[error.codigo] ?? null
}

function esTexto(valor: unknown): valor is string {
  return typeof valor === 'string'
}

function esLineaDelServidor(valor: unknown): valor is ValoresDelServidor['lineas'][number] {
  if (typeof valor !== 'object' || valor === null) return false
  const linea = valor as Record<string, unknown>
  return (
    esTexto(linea.linea_id) &&
    esTexto(linea.lista_version_id) &&
    esTexto(linea.precio_referencia) &&
    typeof linea.unidades_referencia === 'number' &&
    esTexto(linea.importe_bruto)
  )
}

/** Los valores que resolvió el servidor en un `PRECIO_DIFIERE`; `null` si el detalle no viene completo. */
export function valoresDelServidorDe(error: ErrorDeVentas): ValoresDelServidor | null {
  if (error.codigo !== 'PRECIO_DIFIERE') return null
  const { lineas, total } = error.extension
  if (!Array.isArray(lineas) || !esTexto(total) || !lineas.every(esLineaDelServidor)) return null
  return { lineas, total }
}

/** Nombres de los productos sin precio de un `PRODUCTO_SIN_PRECIO` (D7). */
export function productosSinPrecioDe(error: ErrorDeVentas): string[] {
  const { productos } = error.extension
  if (!Array.isArray(productos)) return []
  return productos.flatMap((producto: unknown) => {
    const nombre = typeof producto === 'object' && producto !== null ? (producto as { nombre?: unknown }).nombre : undefined
    return esTexto(nombre) ? [nombre] : []
  })
}

const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo completar la operación.'
const CLAVES_DEL_PROBLEMA = new Set(['type', 'title', 'status', 'detail', 'instance', 'codigo', 'medio'])

/** Traduce una `Response` no-ok de la API de ventas al error de dominio. */
export async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeVentas> {
  let problema: Record<string, unknown> = {}
  try {
    problema = (await respuesta.json()) as Record<string, unknown>
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }

  const mensaje = esTexto(problema.title) ? problema.title : MENSAJE_GENERICO_DE_RESERVA
  if (respuesta.status === 403) return new PermisoRequeridoVentasError(mensaje)
  const medio = typeof problema.medio === 'number' ? problema.medio : null
  const extension = Object.fromEntries(Object.entries(problema).filter(([clave]) => !CLAVES_DEL_PROBLEMA.has(clave)))
  return new ErrorDeVentas(esTexto(problema.codigo) ? problema.codigo : 'ERROR_DESCONOCIDO', mensaje, medio, extension)
}
