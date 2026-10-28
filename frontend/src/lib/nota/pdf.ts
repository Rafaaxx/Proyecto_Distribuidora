/**
 * Generación del PDF de la nota en el dispositivo (change 20, tarea 2.3; ADR-008; `design.md` D8).
 * pdfmake y sus fuentes (Roboto, `vfs_fonts`) se cargan con `import()` dinámico solo al generar la
 * nota: no pesan en el bundle inicial de `/admin`.
 */

import type { ContenidoDeNota } from '../../domain/ventas/notaDeVenta'
import { documentoDeNota } from './documento'

export const TIPO_DE_PDF = 'application/pdf'

export async function generarPdfDeNota(contenido: ContenidoDeNota): Promise<Blob> {
  const [modulo, fuentes] = await Promise.all([import('pdfmake/build/pdfmake'), import('pdfmake/build/vfs_fonts')])
  // Los módulos de pdfmake son CommonJS: sus funciones cuelgan de `default`.
  const pdfMake = modulo.default
  pdfMake.addVirtualFileSystem(fuentes.default)
  const pdf = await pdfMake.createPdf(documentoDeNota(contenido)).getBlob()
  return new Blob([pdf], { type: TIPO_DE_PDF })
}
