import { describe, expect, it } from 'vitest'

import { AYUDAS } from '../../../src/ayuda/textos'

/**
 * Change 24, tarea 16.1 (spec `sistema/ayuda-contextual`, sus cuatro escenarios; `design.md` D12;
 * ADR-051): las siete claves nuevas y las dos revisadas con los textos aprobados en 0.2 (2026-11-04),
 * sin ejemplos y con su regla citada. Que cada ID citado exista (ADR-068 ya existe como
 * *Propuesto*) lo comprueba `trazabilidad.test.ts`.
 */
describe('textos de ayuda de la rendición de la jornada (change 24, tarea 16.1)', () => {
  it.each([
    [
      'stock.entregaDelDia',
      'Entrega del día',
      'El vendedor la hace desde el teléfono con «Terminar el día». Llega al sistema después de todo lo que vendió, anuló y cobró, así que cuando aparece no queda nada de esa jornada sin enviar.',
      ['RUT-05', 'ADR-068'],
    ],
    [
      'stock.rendicion',
      'Rendición',
      'Se cuenta lo que quedó en el vehículo, producto por producto. El sistema compara lo contado con lo que debería haber y registra cada diferencia en el stock. Solo se puede rendir cuando el vendedor terminó el día en el teléfono.',
      ['RUT-05', 'RUT-06', 'ADR-068'],
    ],
    [
      'stock.esperado',
      'Esperado',
      'Lo que debería haber en el vehículo según el sistema: lo que había al abrir, más lo cargado, menos lo vendido, más lo anulado, más o menos otros movimientos. Si cambia mientras contás, el sistema te pide revisarlo.',
      ['RUT-07', 'STK-04', 'ADR-068'],
    ],
    [
      'stock.diferenciaRendicion',
      'Diferencia',
      'Contado menos esperado. Un faltante baja el stock y un sobrante lo sube; queda registrado como diferencia de rendición, sin cambiar el costo promedio.',
      ['RUT-06', 'CST-12', 'ADR-068'],
    ],
    [
      'stock.resumenJornada',
      'Resumen de la jornada',
      'Qué pasó en la jornada: el stock al abrir, lo cargado, lo vendido y anulado, lo esperado, lo contado y las diferencias, y lo cobrado por medio de pago. Lo que llegó después de la rendición se muestra aparte y no entra en el conteo.',
      ['RUT-07', 'ADR-068'],
    ],
    [
      'stock.remanente',
      'Devolver el remanente',
      'Pasa lo que quedó en el vehículo a un depósito al cerrar la jornada. Es una transferencia común: se ve en Transferencias y se puede anular.',
      ['RUT-08', 'STK-07', 'ADR-068'],
    ],
    [
      'ruta.terminarDia',
      'Terminar el día',
      'Avisa al sistema que terminaste de vender. Después no podés vender, anular ventas ni cobrar en esta jornada. Lo que falta enviar se envía primero, también si ahora no tenés señal. Con eso tu supervisor puede rendir la jornada.',
      ['RUT-05', 'ADR-068'],
    ],
  ] as const)('%s lleva el texto aprobado, cita sus reglas, sin ejemplo ni «Ver más»', (clave, titulo, texto, reglas) => {
    const entrada: { titulo: string; texto: string; ejemplo?: string; verMas?: string; reglas: readonly string[] } = AYUDAS[clave]
    expect(entrada.titulo).toBe(titulo)
    expect(entrada.texto).toBe(texto)
    expect([...entrada.reglas]).toEqual(reglas)
    expect(entrada.ejemplo).toBeUndefined()
    expect(entrada.verMas).toBeUndefined()
  })

  it.each([
    [
      'stock.tomaActual',
      "Muestra qué jornada tiene tomada esta ubicación. Mientras la jornada está abierta, solo ese vendedor (desde su dispositivo) puede mover el stock. Cuando pasa a rendición, solo la rendición registra las diferencias y devuelve el remanente al cerrar, además de quien tiene el permiso 'Liberar ubicación'.",
      ['STK-09', 'RUT-01', 'RUT-06', 'RUT-08'],
    ],
    [
      'ruta.sincronizar',
      'Envía al sistema las ventas, anulaciones y cobranzas sin enviar de tu usuario y la entrega del día, en el orden en que las hiciste. Se hace sola al abrir la aplicación o volver a ella, al volver la señal, después de cada operación y cada 2 minutos. Enviar dos veces lo mismo no lo duplica.',
      ['SYN-02', 'SYN-03', 'INV-06', 'RUT-05'],
    ],
  ] as const)('%s, revisada, lleva el texto aprobado y sin ejemplo', (clave, texto, reglas) => {
    const entrada: { texto: string; ejemplo?: string; reglas: readonly string[] } = AYUDAS[clave]
    expect(entrada.texto).toBe(texto)
    expect([...entrada.reglas]).toEqual(reglas)
    expect(entrada.ejemplo).toBeUndefined()
  })
})
