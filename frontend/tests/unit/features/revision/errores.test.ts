import { describe, expect, it } from 'vitest'

import {
  ErrorDeRevision,
  PermisoRequeridoRevisionError,
  RecursoNoEncontradoRevisionError,
  errorDesdeRespuesta,
  mensajeDeErrorDeRevision,
} from '../../../../src/features/revision/errores'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../../src/features/stock/errores'

/**
 * Change 25, tarea 17.1 (`design.md` D12, textos aprobados en 0.2; cita SYN-07, SYN-08, SEG-06,
 * INV-21): los errores de la revision con su texto aprobado y `RECHAZOS_PENDIENTES` en el texto de
 * errores de stock (D9 = B). Los textos de Lote 5 se caracterizan aqui (la implementacion fue primero).
 */
function respuesta(status: number, cuerpo: unknown): Response {
  return { ok: false, status, json: async () => cuerpo } as unknown as Response
}

describe('errorDesdeRespuesta (revisión)', () => {
  it('un 403 es el error de permiso (SEG-06)', async () => {
    const error = await errorDesdeRespuesta(respuesta(403, { title: 'Sin permiso' }))

    expect(error).toBeInstanceOf(PermisoRequeridoRevisionError)
    expect(error.message).toBe('Sin permiso')
  })

  it('un 404 es el recurso no encontrado, sin distinguir ajeno de inexistente (INV-21)', async () => {
    const error = await errorDesdeRespuesta(respuesta(404, { title: 'No existe' }))

    expect(error).toBeInstanceOf(RecursoNoEncontradoRevisionError)
  })

  it('conserva el código estable del servidor', async () => {
    const error = await errorDesdeRespuesta(respuesta(409, { title: 'Ya resuelta', codigo: 'RECHAZO_YA_RESUELTO' }))

    expect([error.codigo, error.message]).toEqual(['RECHAZO_YA_RESUELTO', 'Ya resuelta'])
  })

  it('un cuerpo ilegible usa el código y el mensaje de reserva', async () => {
    const ilegible = { ok: false, status: 500, json: async () => Promise.reject(new Error('no json')) } as unknown as Response
    const error = await errorDesdeRespuesta(ilegible)

    expect([error.codigo, error.message]).toEqual(['ERROR_DESCONOCIDO', 'No se pudo completar la operación.'])
  })
})

describe('mensajeDeErrorDeRevision (D12, SYN-08)', () => {
  it.each([
    ['OBSERVACION_YA_RESUELTA', 'Alguno de los avisos ya lo resolvió otra persona. Actualizá la lista.'],
    ['OBSERVACIONES_INVALIDAS', 'Elegí entre 1 y 100 avisos.'],
    ['COMENTARIO_INVALIDO', 'Escribí un comentario de hasta 500 caracteres.'],
    ['RECHAZO_YA_RESUELTO', 'Esta operación ya la resolvió otra persona.'],
    ['VINCULO_INVALIDO', 'La operación elegida no corresponde a lo rechazado.'],
  ])('%s muestra el texto aprobado', (codigo, texto) => {
    expect(mensajeDeErrorDeRevision(new ErrorDeRevision(codigo, 'texto del servidor'))).toBe(texto)
  })

  it('el 404 muestra «No se encontró la operación.» y el 403 el aviso de permiso', () => {
    expect(mensajeDeErrorDeRevision(new RecursoNoEncontradoRevisionError('x'))).toBe('No se encontró la operación.')
    expect(mensajeDeErrorDeRevision(new PermisoRequeridoRevisionError('x'))).toBe('No tenés permiso para hacer esta operación.')
  })

  it('un código sin texto propio muestra el del servidor', () => {
    expect(mensajeDeErrorDeRevision(new ErrorDeRevision('CODIGO_NUEVO', 'Dijo el servidor'))).toBe('Dijo el servidor')
  })

  it('un corte de red (sin código de dominio) avisa que hace falta conexión', () => {
    expect(mensajeDeErrorDeRevision(new TypeError('Failed to fetch'))).toBe(
      'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.',
    )
  })
})

describe('RECHAZOS_PENDIENTES en los errores de stock (D9 = B, D12; RUT-05)', () => {
  it.each(['transferencia', 'ajuste', 'anulacion', 'ubicacion', 'jornada'] as const)(
    'muestra el texto aprobado en el contexto %s',
    (contexto) => {
      expect(mensajeDeErrorDeStock(new ErrorDeStock('RECHAZOS_PENDIENTES', 'texto del servidor'), contexto)).toBe(
        'Esta jornada tiene operaciones rechazadas sin resolver. Hay que resolverlas en «Revisión» antes de rendir.',
      )
    },
  )
})
