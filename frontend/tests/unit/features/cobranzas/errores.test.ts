import { describe, expect, it } from 'vitest'

import {
  ErrorDeCobranzas,
  PermisoRequeridoCobranzasError,
  campoDelError,
  errorDesdeRespuesta,
} from '../../../../src/features/cobranzas/errores'

function respuesta(status: number, cuerpo: unknown): Response {
  return { ok: false, status, json: async () => cuerpo } as unknown as Response
}

describe('errorDesdeRespuesta (cobranzas)', () => {
  it('un 403 es el error de permiso (SEG-06)', async () => {
    const error = await errorDesdeRespuesta(respuesta(403, { title: 'Sin permiso' }))

    expect(error).toBeInstanceOf(PermisoRequeridoCobranzasError)
    expect(error.message).toBe('Sin permiso')
  })

  it('conserva el código estable y la posición del medio (TR-10)', async () => {
    const error = await errorDesdeRespuesta(respuesta(422, { title: 'Falta la referencia', codigo: 'REFERENCIA_OBLIGATORIA', medio: 1 }))

    expect([error.codigo, error.medio]).toEqual(['REFERENCIA_OBLIGATORIA', 1])
  })

  it('un cuerpo ilegible usa el mensaje y el código de reserva', async () => {
    const ilegible = { ok: false, status: 500, json: async () => Promise.reject(new Error('no json')) } as unknown as Response
    const error = await errorDesdeRespuesta(ilegible)

    expect([error.codigo, error.message, error.medio]).toEqual(['ERROR_DESCONOCIDO', 'No se pudo completar la operación.', null])
  })
})

describe('campoDelError', () => {
  it.each([
    ['CONSUMIDOR_FINAL_SIN_CUENTA', 'cliente'],
    ['IMPORTE_INVALIDO', 'importe'],
    ['MEDIOS_NO_SUMAN_IMPORTE', 'importe'],
    ['OBSERVACION_INVALIDA', 'observacion'],
    ['JORNADA_AJENA', null],
    ['COBRANZA_DUPLICADA', null],
  ])('%s va a %s', (codigo, campo) => {
    expect(campoDelError(new ErrorDeCobranzas(codigo, 'x'))).toBe(campo)
  })
})
