import { describe, expect, it } from 'vitest'

import { AYUDAS } from '../../../src/ayuda/textos'

/**
 * Change 21, tarea 15.2 (spec `sistema/ayuda-contextual`, "Las pantallas de ruta explican el PIN,
 * los datos del día, el almacenamiento y la cartera"; `design.md` D21; ADR-051): los textos
 * aprobados el 2026-10-30, sin ejemplos, con su regla citada. La trazabilidad de los IDs la cubre
 * `trazabilidad.test.ts`.
 */
describe('textos de ayuda de ruta (tarea 15.2)', () => {
  it('ruta.pin: abre la aplicación con o sin señal, no es la contraseña y no pierde lo pendiente; no fija un número', () => {
    const { texto, reglas } = AYUDAS['ruta.pin']
    expect(texto).toBe(
      'El PIN abre la aplicación en este teléfono, con o sin señal. No es tu contraseña. Si lo errás varias veces seguidas, tenés que iniciar sesión con conexión y definir uno nuevo; lo que tengas pendiente no se pierde.',
    )
    // Los 10 intentos son una constante del código; el texto no depende de ningún parámetro.
    expect(texto).not.toMatch(/\d|intentos_pin_max|minutos|segundo plano/i)
    expect(reglas).toEqual(expect.arrayContaining(['SEG-03', 'SEG-04', 'ADR-011']))
  })

  it('ruta.datosDelDia: se descargan al abrir la jornada y actualizar requiere conexión', () => {
    const { texto, reglas } = AYUDAS['ruta.datosDelDia']
    expect(texto).toContain('Actualizar requiere conexión y no toca lo que tengas pendiente.')
    expect(reglas).toEqual(expect.arrayContaining(['SYN-11', 'ADR-006']))
  })

  it('ruta.almacenamiento: el navegador puede borrar los datos y qué hacer', () => {
    const { texto } = AYUDAS['ruta.almacenamiento']
    expect(texto).toContain('puede borrarlos si le falta espacio')
    expect(texto).toContain('Instalá la aplicación en la pantalla de inicio')
  })

  it('ruta.cartera: primero los asignados, se puede buscar y vender a cualquiera', () => {
    expect(AYUDAS['ruta.cartera'].texto).toBe(
      'Primero ves tus clientes asignados. Podés buscar y venderle a cualquier cliente de la organización.',
    )
  })

  it.each(['ruta.pin', 'ruta.datosDelDia', 'ruta.almacenamiento', 'ruta.cartera'] as const)(
    '%s no lleva ejemplo ni "Ver más" (D21: sin ejemplos)',
    (clave) => {
      const entrada: Record<string, unknown> = AYUDAS[clave]
      expect(entrada.ejemplo).toBeUndefined()
      expect(entrada.verMas).toBeUndefined()
      expect((entrada.reglas as string[]).length).toBeGreaterThan(0)
    },
  )
})
