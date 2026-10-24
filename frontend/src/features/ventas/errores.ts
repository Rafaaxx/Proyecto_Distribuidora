import type { DescuentoDeLinea } from '../../domain/ventas/descuentosDeVenta'
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

export type CampoDeVenta = 'cliente' | 'ubicacion' | 'lineas' | 'numero' | 'lista' | 'cobranza' | 'descuento' | 'credito'

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
  // Change 18b: descuentos y crédito (los de autorización van al diálogo, no a un campo).
  DESCUENTO_MANUAL_DESHABILITADO: 'descuento',
  DESCUENTO_MANUAL_INVALIDO: 'descuento',
  MOTIVO_REQUERIDO: 'descuento',
  TOTALES_INCONSISTENTES: 'descuento',
  EXCESO_CREDITO_SIN_ACEPTAR: 'credito',
  CREDITO_EXCEDIDO: 'credito',
}

/**
 * Los rechazos de la autorización con PIN (change 18b, D2, D3, D18): se muestran en el diálogo
 * de autorización, que borra el PIN escrito. `AUTORIZACION_REQUERIDA` y
 * `AUTORIZACION_CREDITO_REQUERIDA` son la credencial que faltaba.
 */
const CODIGOS_DE_AUTORIZACION = new Set([
  'PIN_INCORRECTO',
  'PIN_BLOQUEADO',
  'AUTORIZACION_REQUERIDA',
  'AUTORIZACION_CREDITO_REQUERIDA',
  'AUTORIZADOR_SIN_PERMISO',
])

export function esErrorDeAutorizacion(error: ErrorDeVentas): boolean {
  return CODIGOS_DE_AUTORIZACION.has(error.codigo)
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

function esDescuentoDelServidor(valor: unknown): valor is { origen: string; regla_id: string | null; porcentaje: string | null; importe: string } {
  if (typeof valor !== 'object' || valor === null) return false
  const d = valor as Record<string, unknown>
  return (
    (d.origen === 'AUTOMATICO' || d.origen === 'MANUAL') &&
    (d.regla_id === null || esTexto(d.regla_id)) &&
    (d.porcentaje === null || esTexto(d.porcentaje)) &&
    esTexto(d.importe)
  )
}

/**
 * Los descuentos que resolvió el servidor en un `DESCUENTO_DIFIERE` (DSC-09, D11), por línea;
 * `null` si el detalle no viene completo.
 */
export function descuentosDelServidorDe(error: ErrorDeVentas): Map<string, DescuentoDeLinea[]> | null {
  if (error.codigo !== 'DESCUENTO_DIFIERE') return null
  const { lineas } = error.extension
  if (!Array.isArray(lineas)) return null
  const porLinea = new Map<string, DescuentoDeLinea[]>()
  for (const linea of lineas as unknown[]) {
    if (typeof linea !== 'object' || linea === null) return null
    const { linea_id: lineaId, descuentos } = linea as Record<string, unknown>
    if (!esTexto(lineaId) || !Array.isArray(descuentos) || !descuentos.every(esDescuentoDelServidor)) return null
    porLinea.set(
      lineaId,
      descuentos.map((d) => ({ origen: d.origen as DescuentoDeLinea['origen'], reglaId: d.regla_id, porcentaje: d.porcentaje, importe: d.importe })),
    )
  }
  return porLinea
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
  const codigo = esTexto(problema.codigo) ? problema.codigo : undefined
  // El 403 también lo usan el PIN incorrecto y la autorización que falta (change 18b): solo el
  // permiso del usuario es `PermisoRequeridoVentasError`.
  if (respuesta.status === 403 && (codigo === undefined || codigo === 'PERMISO_REQUERIDO')) {
    return new PermisoRequeridoVentasError(mensaje)
  }
  const medio = typeof problema.medio === 'number' ? problema.medio : null
  const extension = Object.fromEntries(Object.entries(problema).filter(([clave]) => !CLAVES_DEL_PROBLEMA.has(clave)))
  return new ErrorDeVentas(codigo ?? 'ERROR_DESCONOCIDO', mensaje, medio, extension)
}
