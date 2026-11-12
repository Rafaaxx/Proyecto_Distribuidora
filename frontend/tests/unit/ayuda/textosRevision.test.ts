import { describe, expect, it } from 'vitest'

import { AYUDAS, TEMAS } from '../../../src/ayuda/textos'

/**
 * Change 25, tarea 18.1 (spec `sistema/ayuda-contextual`, sus cinco escenarios; `design.md` D13;
 * ADR-051): las siete claves nuevas y las revisadas con los textos aprobados en 0.2, sin ejemplos
 * y con sus reglas citadas. Que cada ID citado exista (ADR-069 ya existe como *Propuesto*) y que
 * cada clave usada exista lo comprueba `trazabilidad.test.ts` (SYN-08, ADR-051).
 */
describe('textos de ayuda de la revisión de observaciones y rechazos (change 25, tarea 18.1)', () => {
  it.each([
    [
      'revision.bandeja',
      'Observaciones',
      'Avisos que dejó el sistema sobre ventas, cobranzas y otras operaciones para que alguien los revise. La operación ya vale y revisarla no la cambia. Si hay que corregir algo, se hace con una operación nueva.',
      ['SYN-07', 'SYN-08'],
    ],
    [
      'revision.resolver',
      'Resolver',
      'Da por revisados los avisos elegidos, con un comentario que explica qué se hizo. Queda quién y cuándo. No cambia la operación y no se puede deshacer.',
      ['SYN-08'],
    ],
    [
      'revision.rechazadas',
      'Rechazadas',
      'Ventas, anulaciones, cobranzas y entregas del día que el teléfono envió y el sistema no aceptó por un problema de datos. No se registraron y no se vuelven a enviar. Si ocurrieron, cargalas con conexión y, salvo las anulaciones, vinculalas al resolver.',
      ['SYN-06', 'SYN-09', 'ADR-069'],
    ],
    [
      'revision.cuarentena',
      'Teléfono dado de baja',
      'Operaciones que llegaron de un teléfono dado de baja. No se registran ni se pueden volver a enviar. Si eran reales, cargalas con conexión y vinculalas al resolver.',
      ['SYN-06', 'ADR-069'],
    ],
    [
      'revision.vinculo',
      'Vincular con',
      'La venta o la cobranza que cargaste con conexión en lugar de la rechazada. Es opcional: si la operación no ocurrió, resolvé sin vincular.',
      ['SYN-08', 'ADR-069'],
    ],
    [
      'stock.rechazadasDeLaJornada',
      'Rechazadas de la jornada',
      'Operaciones de esta jornada que el teléfono envió y el sistema no aceptó. La jornada no se puede rendir hasta resolverlas todas. Si la operación ocurrió, cargala con conexión y vinculala al resolver: así la mercadería se descuenta una sola vez. Si no ocurrió, resolvela sin vincular.',
      ['RUT-05', 'RUT-06', 'SYN-06', 'SYN-08', 'ADR-069'],
    ],
    [
      'ruta.rechazoResuelto',
      'Resuelta por administración',
      'Administración ya revisó esta operación rechazada. Si cargó la venta en la oficina, el teléfono deja de descontarla.',
      ['SYN-09', 'CRE-08', 'ADR-069'],
    ],
  ] as const)('%s lleva el texto aprobado, cita sus reglas, sin ejemplo ni «Ver más»', (clave, titulo, texto, reglas) => {
    const entrada: { titulo: string; texto: string; ejemplo?: string; verMas?: string; reglas: readonly string[] } = AYUDAS[clave]
    expect(entrada.titulo).toBe(titulo)
    expect(entrada.texto).toBe(texto)
    expect([...entrada.reglas]).toEqual(reglas)
    expect(entrada.ejemplo).toBeUndefined()
    expect(entrada.verMas).toBeUndefined()
  })

  it('ruta.ventaRechazada, revisada, lleva el texto propuesto, cita ADR-069 y no tiene ejemplo', () => {
    const entrada: { texto: string; ejemplo?: string; reglas: readonly string[] } = AYUDAS['ruta.ventaRechazada']
    expect(entrada.texto).toBe(
      'El sistema no aceptó la venta por un problema de datos, no por stock ni por crédito. En el detalle ves el motivo. Sigue guardada y no se vuelve a enviar sola. El teléfono la sigue descontando del stock y de la cuenta del cliente hasta que administración la resuelva o termine la jornada: avisá a administración.',
    )
    expect([...entrada.reglas]).toEqual(['SYN-06', 'SYN-09', 'ADR-065', 'ADR-069'])
    expect(entrada.ejemplo).toBeUndefined()
  })

  it.each(['ventas.observaciones', 'cobranzas.observaciones'] as const)(
    '%s, revisada, agrega que administración los revisa en «Revisión» y sigue sin ejemplo',
    (clave) => {
      const entrada: { texto: string; ejemplo?: string; reglas: readonly string[] } = AYUDAS[clave]
      expect(entrada.texto).toContain('Administración los revisa en «Revisión».')
      expect(entrada.ejemplo).toBeUndefined()
      expect(entrada.reglas).toContain('SYN-08')
    },
  )
})

describe('temas «Ver más» revisados (change 25, tarea 18.1)', () => {
  const textoDe = (tema: keyof typeof TEMAS) =>
    TEMAS[tema].secciones.flatMap((s: { titulo: string; parrafos: readonly string[] }) => [s.titulo, ...s.parrafos]).join('\n')
  const seccion = (tema: keyof typeof TEMAS, titulo: string) =>
    TEMAS[tema].secciones.find((s: { titulo: string }) => s.titulo === titulo) as
      | { titulo: string; parrafos: readonly string[]; ejemplo?: string }
      | undefined

  it('ventas-observaciones suma «Llegó después de la rendición», «Producto desactivado» y «Qué hacer con los avisos», sin ejemplos', () => {
    for (const titulo of ['Llegó después de la rendición', 'Producto desactivado', 'Qué hacer con los avisos']) {
      const s = seccion('ventas-observaciones', titulo)
      expect(s, titulo).toBeDefined()
      expect(s?.parrafos.length).toBeGreaterThan(0)
      expect(s?.ejemplo).toBeUndefined()
    }
    expect(seccion('ventas-observaciones', 'Qué hacer con los avisos')?.parrafos.join(' ')).toContain('«Revisión»')
    expect([...TEMAS['ventas-observaciones'].reglas]).toContain('SYN-08')
  })

  it('cobranzas-observaciones suma «Llegó después de la rendición» y ya no dice que la bandeja llega más adelante', () => {
    const s = seccion('cobranzas-observaciones', 'Llegó después de la rendición')
    expect(s?.parrafos.length).toBeGreaterThan(0)
    expect(s?.ejemplo).toBeUndefined()
    const texto = textoDe('cobranzas-observaciones')
    expect(texto).not.toContain('más adelante')
    expect(texto).toContain('Se dan por revisados en «Revisión», con un comentario.')
    expect([...TEMAS['cobranzas-observaciones'].reglas]).toContain('SYN-08')
  })

  it('ningún tema ni ayuda nuevos cita un ID de regla inventado: todos pertenecen a las familias conocidas', () => {
    const ids = [
      ...Object.values(AYUDAS).flatMap((a) => a.reglas),
      ...Object.values(TEMAS).flatMap((t) => t.reglas),
    ]
    expect(ids.every((id) => /^(?:[A-Z]{2,4}-\d{2}|ADR-\d{3})$/.test(id))).toBe(true)
  })
})
