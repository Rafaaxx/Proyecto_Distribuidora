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
      'La venta ya está confirmada y guardada en el teléfono. Se envía sola cuando haya señal, o con «Sincronizar»; hasta entonces no se borra.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-01', 'SYN-09']))
  })

  it('ruta.creditoSinSenal: deuda de la última actualización + lo vendido y cobrado desde el teléfono después (revisada en el 22c y en el 22d)', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.creditoSinSenal']
    expect(titulo).toBe('Crédito del cliente')
    expect(texto).toBe(
      'Se calcula con la deuda de la última actualización de datos, más lo que le vendiste y menos lo que le cobraste y le anulaste desde el teléfono después.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['CRE-08', 'CRE-09', 'ADR-065', 'ADR-066']))
    expect(AYUDAS['ruta.creditoSinSenal'].verMas).toBe('credito')
  })

  it('ruta.stockDelVehiculo: el de la última actualización menos lo vendido y más lo anulado desde el teléfono después (revisada en el 22c y en el 22d)', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.stockDelVehiculo']
    expect(titulo).toBe('Stock del vehículo')
    expect(texto).toBe(
      'Es el stock de la última actualización de datos menos lo que vendiste y más lo que anulaste desde el teléfono después. Si no alcanza, la venta no se confirma: actualizá los datos con señal.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['STK-06', 'RUT-04', 'ADR-065', 'ADR-066']))
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


/**
 * Change 22b, tarea 12.1 (spec `sistema/ayuda-contextual`, "La sincronización del área de ruta
 * explica sus estados"; `design.md` D13; ADR-051, ADR-064): cuatro claves nuevas con los textos
 * aprobados el 2026-11-01, sin ejemplos. Los IDs citados existen (`trazabilidad.test.ts`).
 */
describe('textos de ayuda de la sincronización (change 22b, tarea 12.1)', () => {
  it('ruta.sincronizar: qué envía, cuándo se hace sola y que reenviar no duplica; no habla del botón', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.sincronizar']
    expect(titulo).toBe('Sincronizar')
    expect(texto).toBe(
      'Envía al sistema las ventas, anulaciones y cobranzas sin enviar de tu usuario, en el orden en que las hiciste. Se hace sola al abrir la aplicación o volver a ella, al volver la señal, después de cada operación y cada 2 minutos. Enviar dos veces lo mismo no lo duplica.',
    )
    expect(texto).not.toMatch(/bot[oó]n|tocá|apretá/i)
    expect(reglas).toEqual(expect.arrayContaining(['SYN-02', 'SYN-03', 'INV-06']))
  })

  it('ruta.ventaConObservaciones: se aceptó, administración revisa y no hay nada que hacer', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.ventaConObservaciones']
    expect(titulo).toBe('Con observaciones')
    expect(texto).toBe(
      'El sistema aceptó la venta y anotó algo para que administración lo revise. En el detalle de la venta ves qué anotó. La venta vale igual; no tenés que hacer nada.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-04', 'SYN-05', 'SYN-08']))
  })

  it('ruta.ventaRechazada: problema de datos, sigue en el teléfono, no se reenvía sola y se avisa', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.ventaRechazada']
    expect(titulo).toBe('Rechazada')
    expect(texto).toBe(
      'El sistema no aceptó la venta por un problema de datos, no por stock ni por crédito. En el detalle ves el motivo. Sigue guardada, no se vuelve a enviar sola y el teléfono la sigue descontando del stock y de la cuenta del cliente: avisá a administración.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-06', 'SYN-09', 'ADR-065']))
  })

  it('ruta.versionMinima: ya no confirma ventas nuevas, las guardadas se siguen enviando', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.versionMinima']
    expect(titulo).toBe('Versión desactualizada')
    expect(texto).toBe(
      'Esta versión de la aplicación ya no puede confirmar ventas ni cobranzas nuevas. Lo guardado se sigue enviando. Actualizá la aplicación para seguir.',
    )
    expect(reglas).toEqual(['ADR-064', 'ADR-067'])
  })

  it.each(['ruta.sincronizar', 'ruta.ventaConObservaciones', 'ruta.ventaRechazada', 'ruta.versionMinima'] as const)(
    '%s no lleva ejemplo ni "Ver más"',
    (clave) => {
      const entrada: Record<string, unknown> = AYUDAS[clave]
      expect(entrada.ejemplo).toBeUndefined()
      expect(entrada.verMas).toBeUndefined()
    },
  )
})

/**
 * Change 22c, tarea 10.1 (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican los
 * disponibles locales y las observaciones»; D9; ADR-051, ADR-065): una clave nueva y cuatro
 * revisadas, con los textos aprobados el 2026-11-02, sin ejemplos.
 */
describe('textos de ayuda de la conciliación y las observaciones (change 22c, tarea 10.1)', () => {
  it('ruta.observacionesYRechazos: qué anotó el sistema, quién lo revisa y que una rechazada no se reenvía sola', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.observacionesYRechazos']
    expect(titulo).toBe('Observaciones y rechazos')
    expect(texto).toBe(
      'Muestra qué anotó el sistema en cada venta, anulación o cobranza enviada y por qué no aceptó las rechazadas. Las observaciones las revisa administración; no tenés que hacer nada. Lo rechazado no se vuelve a enviar solo.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-04', 'SYN-07', 'SYN-08', 'SYN-09']))
  })

  it.each([
    'ruta.observacionesYRechazos',
    'ruta.stockDelVehiculo',
    'ruta.creditoSinSenal',
    'ruta.ventaConObservaciones',
    'ruta.ventaRechazada',
  ] as const)('%s no lleva ejemplo', (clave) => {
    const entrada: Record<string, unknown> = AYUDAS[clave]
    expect(entrada.ejemplo).toBeUndefined()
  })

  it('las ayudas de stock y crédito ya no dicen «al abrir la jornada»', () => {
    expect(AYUDAS['ruta.stockDelVehiculo'].texto).not.toMatch(/al abrir la jornada/)
    expect(AYUDAS['ruta.creditoSinSenal'].texto).not.toMatch(/al abrir la jornada/)
  })
})

/**
 * Change 22d, tarea 14.1 (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican la
 * anulación y la jornada no abierta»; D12; ADR-051, ADR-066): tres claves nuevas y cuatro
 * revisadas, con los textos aprobados el 2026-11-03, sin ejemplos. Los IDs citados existen
 * (`trazabilidad.test.ts`; ADR-066 existe como *Propuesto*).
 */
describe('textos de ayuda de la anulación y la jornada no abierta (change 22d, tarea 14.1)', () => {
  it('ruta.anularVenta: deja sin efecto una venta de la jornada, también sin señal, entera y una sola vez', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.anularVenta']
    expect(titulo).toBe('Anular una venta')
    expect(texto).toBe(
      'Deja sin efecto una venta de tu jornada, también sin señal: la mercadería vuelve al stock del vehículo y al cliente se le descuenta el total de su cuenta. Se anula entera y una sola vez, y se envía al sistema como las ventas.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['VTA-20', 'VTA-21', 'VTA-24', 'ADR-066']))
  })

  it('ruta.anulacionRechazada: el motivo está en el detalle, la venta sigue vigente, no se reenvía sola', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.anulacionRechazada']
    expect(titulo).toBe('Anulación rechazada')
    expect(texto).toBe(
      'El sistema no aceptó la anulación. En el detalle ves el motivo. La venta sigue vigente: el teléfono la vuelve a descontar del stock y de la cuenta del cliente. No se vuelve a enviar sola: avisá a administración.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-06', 'SYN-09', 'VTA-24', 'ADR-066']))
  })

  it('ruta.jornadaNoAbierta: no se puede vender ni anular, lo vendido se envía y se abre otra jornada con señal', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.jornadaNoAbierta']
    expect(titulo).toBe('Jornada no abierta')
    expect(texto).toBe(
      'El sistema avisó que tu jornada ya no está abierta. No podés vender, anular ventas ni cobrar; lo que ya hiciste se sigue enviando. Para seguir, abrí una jornada nueva con señal.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['RUT-09', 'RUT-03', 'ADR-066']))
  })

  it.each(['ruta.anularVenta', 'ruta.anulacionRechazada', 'ruta.jornadaNoAbierta'] as const)(
    '%s no lleva ejemplo ni "Ver más"',
    (clave) => {
      const entrada: Record<string, unknown> = AYUDAS[clave]
      expect(entrada.ejemplo).toBeUndefined()
      expect(entrada.verMas).toBeUndefined()
    },
  )

  it('el stock y el crédito nombran lo anulado además de lo vendido', () => {
    expect(AYUDAS['ruta.stockDelVehiculo'].texto).toContain('más lo que anulaste')
    expect(AYUDAS['ruta.creditoSinSenal'].texto).toContain('menos lo que le cobraste y le anulaste')
  })

  it('«Sincronizar» y «Observaciones y rechazos» nombran las anulaciones', () => {
    expect(AYUDAS['ruta.sincronizar'].texto).toContain('ventas, anulaciones y cobranzas sin enviar')
    expect(AYUDAS['ruta.observacionesYRechazos'].texto).toContain('venta, anulación o cobranza enviada')
  })

  it('«Si no alcanza, la venta no se confirma: actualizá los datos con señal.» sigue en el stock', () => {
    expect(AYUDAS['ruta.stockDelVehiculo'].texto).toContain('Si no alcanza, la venta no se confirma: actualizá los datos con señal.')
  })
})

/**
 * Change 23, tarea 12.1 (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican la
 * cobranza»; D12; ADR-051, ADR-067): cuatro claves nuevas y cinco revisadas, con los textos
 * aprobados el 2026-11-03, sin ejemplos. Los IDs citados existen (`trazabilidad.test.ts`; ADR-067
 * existe como *Propuesto*).
 */
describe('textos de ayuda de la cobranza de ruta (change 23, tarea 12.1)', () => {
  it('ruta.cobrar: registra un pago también sin señal, libera crédito en el teléfono y se anula desde la oficina', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.cobrar']
    expect(titulo).toBe('Cobrar a un cliente')
    expect(texto).toBe(
      'Registra un pago del cliente, también sin señal. Baja lo que debe en total y le libera crédito enseguida en el teléfono. Se envía al sistema como las ventas. Si te equivocaste, avisá a administración: la cobranza se anula desde la oficina.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['COB-01', 'COB-03', 'COB-04', 'COB-05', 'CRE-08', 'ADR-067']))
  })

  it('ruta.cobranzaRechazada: el motivo está en el detalle, el teléfono la deja de descontar y se avisa a administración', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.cobranzaRechazada']
    expect(titulo).toBe('Cobranza rechazada')
    expect(texto).toBe(
      'El sistema no aceptó la cobranza. En el detalle ves el motivo. El teléfono deja de descontarla de la cuenta del cliente. No se vuelve a enviar sola: avisá a administración.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['SYN-06', 'SYN-09', 'ADR-067']))
  })

  it('ruta.medios: se reparte el importe entre varios medios y la suma tiene que dar justo el importe', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.medios']
    expect(titulo).toBe('Medios de pago')
    expect(texto).toBe(
      'Cómo te pagó el cliente. Podés repartir el importe entre varios medios y la suma tiene que dar justo el importe. Algunos medios piden el número de la operación.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['COB-01', 'COB-02', 'INV-08']))
  })

  it('ruta.saldoDespuesDelCobro: lo que va a deber el cliente según el teléfono; si paga de más, le queda a favor', () => {
    const { titulo, texto, reglas } = AYUDAS['ruta.saldoDespuesDelCobro']
    expect(titulo).toBe('Saldo después del cobro')
    expect(texto).toBe(
      'Lo que el cliente va a deber después de este pago, según el teléfono. Si paga de más, le queda a favor.',
    )
    expect(reglas).toEqual(expect.arrayContaining(['COB-01', 'COB-03', 'CC-04', 'CRE-08']))
  })

  it.each(['ruta.cobrar', 'ruta.cobranzaRechazada', 'ruta.medios', 'ruta.saldoDespuesDelCobro'] as const)(
    '%s no lleva ejemplo ni "Ver más"',
    (clave) => {
      const entrada: Record<string, unknown> = AYUDAS[clave]
      expect(entrada.ejemplo).toBeUndefined()
      expect(entrada.verMas).toBeUndefined()
    },
  )

  it('las cinco revisadas nombran también las cobranzas y citan ADR-067', () => {
    expect(AYUDAS['ruta.creditoSinSenal'].texto).toBe(
      'Se calcula con la deuda de la última actualización de datos, más lo que le vendiste y menos lo que le cobraste y le anulaste desde el teléfono después.',
    )
    expect(AYUDAS['ruta.creditoSinSenal'].reglas).toEqual(expect.arrayContaining(['CRE-08', 'CRE-09', 'ADR-065', 'ADR-066', 'ADR-067']))
    expect(AYUDAS['ruta.sincronizar'].texto).toContain('ventas, anulaciones y cobranzas sin enviar')
    expect(AYUDAS['ruta.observacionesYRechazos'].texto).toContain('venta, anulación o cobranza enviada')
    expect(AYUDAS['ruta.jornadaNoAbierta'].texto).toContain('No podés vender, anular ventas ni cobrar')
    expect(AYUDAS['ruta.jornadaNoAbierta'].reglas).toEqual(expect.arrayContaining(['RUT-09', 'RUT-03', 'ADR-066', 'ADR-067']))
    expect(AYUDAS['ruta.versionMinima'].texto).toContain('ventas ni cobranzas nuevas')
    expect(AYUDAS['ruta.versionMinima'].reglas).toEqual(expect.arrayContaining(['ADR-064', 'ADR-067']))
  })
})
