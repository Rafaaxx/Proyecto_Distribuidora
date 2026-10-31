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

/**
 * Change 22a, tarea 15.1 (spec `sistema/ayuda-contextual`; `design.md` D17; ADR-051, ADR-063): las
 * cinco claves nuevas de la venta de ruta con los textos aprobados el 2026-10-31 (tarea 0.2), sin
 * ejemplos. Los IDs que citan existen (lo comprueba `trazabilidad.test.ts`).
 */
describe('textos de ayuda de la venta de ruta (change 22a, tarea 15.1)', () => {
  it('ruta.ventaSinEnviar: ya está confirmada y guardada, se envía con señal y no se borra', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.ventaSinEnviar']
    expect(titulo).toBe('Sin enviar')
    expect(texto).toBe(
      'La venta ya está confirmada y guardada en el teléfono. Se envía al sistema cuando haya señal; hasta entonces no se borra.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-01', 'SYN-09']))
  })

  it('ruta.creditoSinSenal: deuda del día + lo vendido y cobrado desde el teléfono, y el sistema lo recalcula', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.creditoSinSenal']
    expect(titulo).toBe('Crédito del cliente')
    expect(texto).toBe(
      'Se calcula con la deuda que bajó al abrir la jornada más lo que le vendiste y cobraste desde el teléfono. El sistema lo vuelve a calcular cuando recibe la venta.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['CRE-08', 'CRE-09']))
    expect(AYUDAS['ruta.creditoSinSenal'].verMas).toBe('credito')
  })

  it('ruta.stockDelVehiculo: si no alcanza la venta no se confirma y hay que actualizar con señal', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.stockDelVehiculo']
    expect(titulo).toBe('Stock del vehículo')
    expect(texto).toBe(
      'Es lo que bajó al abrir la jornada menos lo que vendiste desde el teléfono. Si no alcanza, la venta no se confirma: actualizá los datos con señal.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['STK-06', 'RUT-04']))
  })

  it('ruta.pinSupervisor: se escribe en el teléfono y se bloquea hasta actualizar los datos; no fija un número', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.pinSupervisor']
    expect(titulo).toBe('PIN del supervisor')
    expect(texto).toBe(
      'El supervisor escribe su PIN en tu teléfono; no hace falta señal. Después de varios intentos fallidos ese PIN queda bloqueado en este teléfono hasta que se actualicen los datos.',
    )
    expect(texto).not.toMatch(/\d/)
    expect(reglas).toEqual(expect.arrayContaining(['SEG-05']))
  })

  it('ruta.numeroDeVenta: lo pone el teléfono al confirmar', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.numeroDeVenta']
    expect(titulo).toBe('Número de venta')
    expect(texto).toBe(
      'El teléfono le pone el número al confirmar: el prefijo del teléfono y el siguiente número de sus ventas.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['VTA-06']))
  })

  it.each([
    'ruta.ventaSinEnviar',
    'ruta.creditoSinSenal',
    'ruta.stockDelVehiculo',
    'ruta.pinSupervisor',
    'ruta.numeroDeVenta',
  ] as const)('%s no lleva ejemplo ni "Ver más" (D17: sin ejemplos)', (clave) => {
    const entrada: Record<string, unknown> = AYUDAS[clave]
    expect(entrada.ejemplo).toBeUndefined()
    expect((entrada.reglas as string[]).length).toBeGreaterThan(0)
  })
})

