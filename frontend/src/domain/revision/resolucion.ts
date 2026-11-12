/**
 * Reglas y textos de la resolución de observaciones y rechazos (change 25, tareas 13.2 y 15.2; D1, D7, D11, D12;
 * SYN-08). Lógica pura, sin React. El servidor valida y es la autoridad (`COMENTARIO_INVALIDO`); acá solo se evita
 * un pedido que se sabe inválido.
 */

import { formatearFechaHora } from '../../lib/fecha'

export const LIMITE_DE_COMENTARIO = 500

/** El comentario recortado, o `null` si está vacío o supera el límite. */
export function comentarioDeResolucion(texto: string): string | null {
  const recortado = texto.trim()
  return recortado.length >= 1 && recortado.length <= LIMITE_DE_COMENTARIO ? recortado : null
}

function avisos(cantidad: number): string {
  return cantidad === 1 ? '1 aviso' : `${String(cantidad)} avisos`
}

/** «Resolver {N} avisos». */
export function textoDeResolverAvisos(cantidad: number): string {
  return `Resolver ${avisos(cantidad)}`
}

/** «¿Resolver {N} avisos con este comentario? No se puede deshacer.» */
export function textoDeConfirmacionDeAvisos(cantidad: number): string {
  return `¿Resolver ${avisos(cantidad)} con este comentario? No se puede deshacer.`
}

export interface ResolucionDeAviso {
  resuelto_por_nombre?: string | null
  resuelto_en?: string | null
  comentario?: string | null
}

/**
 * «Resuelta por {usuario} el {fecha}: {comentario}». Lo que el servidor no informó se omite, nunca se inventa.
 */
export function textoDeResolucion(resolucion: ResolucionDeAviso): string {
  const por = resolucion.resuelto_por_nombre ? ` por ${resolucion.resuelto_por_nombre}` : ''
  const cuando = resolucion.resuelto_en ? ` el ${formatearFechaHora(resolucion.resuelto_en)}` : ''
  const comentario = resolucion.comentario ? `: ${resolucion.comentario}` : ''
  return `Resuelta${por}${cuando}${comentario}`
}
