/**
 * Compartir y descargar la nota (change 20, tarea 3.1; ADR-008; `design.md` D9). "Compartir" usa
 * Web Share API solo si el navegador comparte archivos; "Descargar" está siempre (respaldo).
 */

import { guardarArchivo } from '../descarga'

export type ResultadoDeCompartir = 'compartida' | 'cancelada' | 'fallo'

export function nombreDeArchivoDeNota(numero: string): string {
  return `nota-de-venta-${numero}.pdf`
}

/** Verdadero solo si existe `canShare` y acepta archivos. */
export function puedeCompartirArchivos(archivo: File): boolean {
  return typeof navigator.canShare === 'function' && navigator.canShare({ files: [archivo] })
}

/**
 * Comparte la nota. `cancelada`: el usuario cerró el menú (`AbortError`), no hay nada más que hacer.
 * `fallo`: no se pudo compartir; quien llama avisa y ofrece la descarga.
 */
export async function compartirNota(pdf: Blob, numero: string): Promise<ResultadoDeCompartir> {
  const archivo = new File([pdf], nombreDeArchivoDeNota(numero), { type: 'application/pdf' })
  if (!puedeCompartirArchivos(archivo)) return 'fallo'
  try {
    await navigator.share({ files: [archivo], title: `Nota de venta ${numero}` })
    return 'compartida'
  } catch (error) {
    return error instanceof DOMException && error.name === 'AbortError' ? 'cancelada' : 'fallo'
  }
}

export function descargarNota(pdf: Blob, numero: string): void {
  guardarArchivo(pdf, nombreDeArchivoDeNota(numero))
}
