import { z } from 'zod'

/**
 * Vigencias de la publicación (change 13, tarea 12.1; PRC-02, D6). La persona carga fechas
 * con hora local (`<input type="datetime-local">`, `"2026-10-10T09:00"`) o las deja vacías:
 * sin `vigencia_desde` rige desde el momento de la publicación. La vigencia hasta debe ser
 * posterior a la desde (o al momento de publicar si no hay desde). Que la vigencia desde no
 * sea pasada (`VIGENCIA_INVALIDA`) y que no se repita (`VIGENCIA_DUPLICADA`) lo valida el
 * servidor, con su propio reloj.
 */

export interface VigenciaCargada {
  vigencia_desde: string
  vigencia_hasta: string
}

export interface VigenciaDeComando {
  vigencia_desde: string | null
  vigencia_hasta: string | null
}

function instante(texto: string): Date | null {
  if (texto === '') return null
  const fecha = new Date(texto)
  return Number.isNaN(fecha.getTime()) ? null : fecha
}

export function crearEsquemaDePublicacion(ahora: Date) {
  return z
    .object({ vigencia_desde: z.string(), vigencia_hasta: z.string() })
    .superRefine((datos, contexto) => {
      const desde = instante(datos.vigencia_desde)
      const hasta = instante(datos.vigencia_hasta)
      if (datos.vigencia_desde !== '' && desde === null) {
        contexto.addIssue({ code: 'custom', path: ['vigencia_desde'], message: 'Ingresá una fecha válida.' })
      }
      if (datos.vigencia_hasta !== '' && hasta === null) {
        contexto.addIssue({ code: 'custom', path: ['vigencia_hasta'], message: 'Ingresá una fecha válida.' })
        return
      }
      if (hasta !== null && hasta.getTime() <= (desde ?? ahora).getTime()) {
        contexto.addIssue({
          code: 'custom',
          path: ['vigencia_hasta'],
          message: 'La vigencia hasta debe ser posterior a la vigencia desde.',
        })
      }
    })
}

/** Las vigencias cargadas como instantes con zona (`toISOString`) o `null` si están vacías. */
export function construirVigencia(datos: VigenciaCargada): VigenciaDeComando {
  return {
    vigencia_desde: instante(datos.vigencia_desde)?.toISOString() ?? null,
    vigencia_hasta: instante(datos.vigencia_hasta)?.toISOString() ?? null,
  }
}
