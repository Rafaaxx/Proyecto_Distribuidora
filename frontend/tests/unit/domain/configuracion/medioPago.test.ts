import { describe, expect, it } from 'vitest'

import { esquemaMedioPago, mensajeDeErrorDeMedioPago } from '../../../../src/domain/configuracion/medioPago'

/**
 * Validación del formulario de un medio de pago (change 17b, D2, D3) y mensajes en palabras
 * simples de los rechazos del servidor. Solo UX: el servidor valida igual.
 */

describe('esquemaMedioPago', () => {
  it('recorta el nombre y conserva la marca de referencia', () => {
    const resultado = esquemaMedioPago.safeParse({ nombre: '  Mercado Pago  ', requiere_referencia: true })

    expect(resultado.success && resultado.data).toEqual({ nombre: 'Mercado Pago', requiere_referencia: true })
  })

  it.each(['', '   '])('rechaza el nombre vacío %j', (nombre) => {
    const resultado = esquemaMedioPago.safeParse({ nombre, requiere_referencia: false })

    expect(resultado.success).toBe(false)
  })
})

describe('mensajeDeErrorDeMedioPago', () => {
  it('explica el nombre repetido, el nombre inválido y el último medio activo', () => {
    expect(mensajeDeErrorDeMedioPago('NOMBRE_DUPLICADO', 'x')).toMatch(/ya hay un medio de pago con ese nombre/i)
    expect(mensajeDeErrorDeMedioPago('NOMBRE_INVALIDO', 'x')).toMatch(/escribí un nombre/i)
    expect(mensajeDeErrorDeMedioPago('ULTIMO_MEDIO_ACTIVO', 'x')).toMatch(/al menos un medio de pago activo/i)
  })

  it('otro código muestra lo que dijo el servidor', () => {
    expect(mensajeDeErrorDeMedioPago('OTRO', 'Mensaje del servidor')).toBe('Mensaje del servidor')
  })
})
