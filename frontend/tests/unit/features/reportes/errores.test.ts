import { describe, expect, it } from 'vitest'

import {
  ErrorDeReportes,
  PermisoRequeridoReportesError,
  RecursoNoEncontradoReportesError,
  errorDesdeRespuesta,
  mensajeDeErrorDeReportes,
} from '../../../../src/features/reportes/errores'

/**
 * Change 26, tarea 9.1 (D1, D12; cita TR-04, SEG-06, INV-21): los errores de los reportes con el texto aprobado
 * en 0.2, traducidos por el código estable y no por el título.
 */
function respuesta(status: number, cuerpo: unknown): Response {
  return { ok: false, status, json: async () => cuerpo } as unknown as Response
}

describe('errorDesdeRespuesta (reportes)', () => {
  it('un 403 es el error de permiso (SEG-06)', async () => {
    const error = await errorDesdeRespuesta(respuesta(403, { title: 'Sin permiso' }))

    expect(error).toBeInstanceOf(PermisoRequeridoReportesError)
  })

  it('un 404 es el recurso no encontrado, sin distinguir ajeno de inexistente (INV-21)', async () => {
    const error = await errorDesdeRespuesta(respuesta(404, { title: 'No existe' }))

    expect(error).toBeInstanceOf(RecursoNoEncontradoReportesError)
  })

  it('un 422 conserva el código estable de dominio', async () => {
    const error = await errorDesdeRespuesta(respuesta(422, { title: 'x', codigo: 'PERIODO_DEMASIADO_LARGO' }))

    expect(error).toBeInstanceOf(ErrorDeReportes)
    expect(error.codigo).toBe('PERIODO_DEMASIADO_LARGO')
  })

  it('un cuerpo que no es JSON no rompe la traducción', async () => {
    const sinJson = {
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('no es json')
      },
    } as unknown as Response

    const error = await errorDesdeRespuesta(sinJson)

    expect(error.codigo).toBe('ERROR_DESCONOCIDO')
  })
})

describe('mensajeDeErrorDeReportes (D12)', () => {
  it('RANGO_DE_FECHAS_INVALIDO reutiliza el texto del estado de cuenta', () => {
    expect(mensajeDeErrorDeReportes(new ErrorDeReportes('RANGO_DE_FECHAS_INVALIDO', 'x'))).toBe(
      '"Desde" no puede ser posterior a "Hasta".',
    )
  })

  it('PERIODO_DEMASIADO_LARGO', () => {
    expect(mensajeDeErrorDeReportes(new ErrorDeReportes('PERIODO_DEMASIADO_LARGO', 'x'))).toBe(
      'El período no puede superar los 366 días.',
    )
  })

  it('el 404 de la jornada', () => {
    expect(mensajeDeErrorDeReportes(new RecursoNoEncontradoReportesError('x'))).toBe('No se encontró la jornada.')
  })

  it.each([
    ['un error de carga', new ErrorDeReportes('ERROR_DESCONOCIDO', 'x')],
    ['un 403', new PermisoRequeridoReportesError('x')],
    ['un fallo cualquiera', new Error('boom')],
    ['algo que no es un error', 'texto'],
  ])('%s muestra el texto de error de carga', (_nombre, error) => {
    expect(mensajeDeErrorDeReportes(error)).toBe('No se pudo cargar el reporte. Probá de nuevo.')
  })
})

