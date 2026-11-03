import { describe, expect, it } from 'vitest'

import { textoDePendientes } from '../../../../../src/areas/ruta/sincronizacion/presentacion'

/**
 * Change 22d, tarea 12.2 (`design.md` D10, aprobado en 0.2; cita SYN-09): «N ventas y M
 * anulaciones sin enviar». Solo ventas queda como en el 22a; solo anulaciones usa el singular y
 * el plural de «anulación».
 */
describe('textoDePendientes (D10, SYN-09)', () => {
  it.each([
    [0, 0, 'Todo enviado'],
    [1, 0, '1 venta sin enviar'],
    [3, 0, '3 ventas sin enviar'],
    [0, 1, '1 anulación sin enviar'],
    [0, 2, '2 anulaciones sin enviar'],
    [2, 1, '2 ventas y 1 anulación sin enviar'],
    [1, 3, '1 venta y 3 anulaciones sin enviar'],
  ])('%i ventas y %i anulaciones -> «%s»', (ventas, anulaciones, esperado) => {
    expect(textoDePendientes(ventas, anulaciones)).toBe(esperado)
  })
})
