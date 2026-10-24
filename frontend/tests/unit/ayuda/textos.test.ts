import { describe, expect, it } from 'vitest'

import { AYUDAS, TEMAS, type ClaveDeAyuda, type TemaDeAyuda } from '../../../src/ayuda/textos'

/**
 * Forma del archivo único de textos de ayuda (spec `ayuda-contextual`,
 * requisito "El texto es corto, trae un ejemplo y cita su regla"; ADR-051).
 * La existencia de cada ID en `docs/` la comprueba `trazabilidad.test.ts`.
 */
const claves = Object.keys(AYUDAS) as ClaveDeAyuda[]
const temas = Object.keys(TEMAS) as TemaDeAyuda[]

describe('AYUDAS: cada entrada tiene título, texto y regla citada', () => {
  it('tiene las 58 claves aprobadas (27 del 16b, 5 de cobranzas, 5 de medios de pago y roles, 9 de ventas y 12 del 18b; la de "Operador" se eliminó)', () => {
    expect(claves).toHaveLength(58)
    expect(claves).not.toContain('descuentos.operador')
  })

  it.each(claves)('%s: título y texto no vacíos', (clave) => {
    const entrada = AYUDAS[clave]
    expect(entrada.titulo.trim()).not.toBe('')
    expect(entrada.texto.trim()).not.toBe('')
  })

  it.each(claves)('%s: cita al menos un ID con formato de regla o ADR', (clave) => {
    const { reglas } = AYUDAS[clave]
    expect(reglas.length).toBeGreaterThan(0)
    for (const id of reglas) {
      expect(id).toMatch(/^([A-Z]{2,3}-\d{2}|ADR-\d{3})$/)
    }
  })

  it('todo "verMas" apunta a un tema de TEMAS', () => {
    const conVerMas = claves.filter((clave) => 'verMas' in AYUDAS[clave])
    expect(conVerMas.length).toBeGreaterThan(0)
    for (const clave of conVerMas) {
      const entrada: { verMas?: string } = AYUDAS[clave]
      expect(temas).toContain(entrada.verMas)
    }
  })

  it('el texto de "Medida" conserva el ejemplo aprobado de 2,5 cajas', () => {
    expect(AYUDAS['descuentos.medida'].texto).toContain('15 botellas de un vino que viene x6 = 2,5 cajas')
  })
})

describe('TEMAS: páginas "Ver más"', () => {
  it('son exactamente cobranzas-observaciones, credito, descuentos, topes, precio y ventas-observaciones', () => {
    expect([...temas].sort()).toEqual([
      'cobranzas-observaciones',
      'credito',
      'descuentos',
      'precio',
      'topes',
      'ventas-observaciones',
    ])
  })

  it.each(temas)('%s: título, al menos una sección con párrafos y al menos un ID', (tema) => {
    const entrada = TEMAS[tema]
    expect(entrada.titulo.trim()).not.toBe('')
    expect(entrada.reglas.length).toBeGreaterThan(0)
    expect(entrada.secciones.length).toBeGreaterThan(0)
    for (const seccion of entrada.secciones) {
      expect(seccion.titulo.trim()).not.toBe('')
      expect(seccion.parrafos.length).toBeGreaterThan(0)
    }
  })
})

describe('ayuda de cobranzas (change 17, D20; variante 5b)', () => {
  const clavesDeCobranzas = [
    'cobranzas.medios',
    'cobranzas.saldoAFavor',
    'cobranzas.jornada',
    'cobranzas.anulacion',
    'cobranzas.observaciones',
  ] as const

  it('las cinco claves existen y citan las reglas aprobadas', () => {
    expect(clavesDeCobranzas.map((clave) => [clave, [...AYUDAS[clave].reglas]])).toEqual([
      ['cobranzas.medios', ['COB-01', 'COB-02', 'INV-08']],
      ['cobranzas.saldoAFavor', ['COB-03', 'CC-04']],
      ['cobranzas.jornada', ['RUT-07']],
      ['cobranzas.anulacion', ['COB-05', 'CC-02']],
      ['cobranzas.observaciones', ['SYN-05', 'SYN-07', 'SYN-10', 'RUT-09']],
    ])
  })

  it.each([
    ['cobranzas.medios', '$30.000 en efectivo y $20.000 por transferencia (n.º 0042)'],
    ['cobranzas.saldoAFavor', 'debe $150.000 y paga $160.000 → le quedan $10.000 a favor'],
    ['cobranzas.jornada', 'Juan cobra $50.000 en Kiosco La Esquina desde la camioneta 2'],
    ['cobranzas.anulacion', 'un cheque de $20.000 de Almacén Don Pedro vuelve rechazado'],
  ] as const)('%s trae su ejemplo aprobado', (clave, fragmento) => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(`${entrada.texto} ${entrada.ejemplo ?? ''}`).toContain(fragmento)
  })

  it('las observaciones quedan en un panel corto con "Ver más" al tema cobranzas-observaciones (5b)', () => {
    const entrada: { texto: string; verMas?: string } = AYUDAS['cobranzas.observaciones']
    expect(entrada.verMas).toBe('cobranzas-observaciones')
    expect(entrada.texto).toContain('porque la plata ya se cobró')
    expect(entrada.texto.split('.').length).toBeLessThanOrEqual(4)
  })

  it('el tema explica las cinco marcas con su ejemplo y avisa que la bandeja llega más adelante', () => {
    const tema = TEMAS['cobranzas-observaciones']
    const titulos = tema.secciones.map((seccion) => seccion.titulo)

    expect(tema.titulo).toBe('Avisos de los pagos cargados sin señal')
    expect(titulos).toEqual(
      expect.arrayContaining(['Medio inactivo', 'Falta la referencia', 'Permiso revocado', 'Jornada liberada', 'Cliente no habilitado']),
    )
    const marcas = tema.secciones.filter((seccion) => seccion.titulo !== 'Por qué el pago se toma igual' && seccion.titulo !== 'Qué hacer con los avisos')
    expect(marcas).toHaveLength(5)
    for (const marca of marcas) {
      expect(marca.ejemplo?.startsWith('Ej.:')).toBe(true)
    }
    expect(tema.secciones.flatMap((seccion) => seccion.parrafos).join(' ')).toContain('La bandeja para darlos por revisados llega más adelante')
  })
})

describe('ayuda de ventas (change 18a, D22; textos aprobados el 2026-10-17 y el 2026-10-19)', () => {
  const reglasAprobadas = [
    ['ventas.cajasYUnidades', ['CAT-07', 'CAT-08', 'VTA-02', 'PRC-22']],
    ['ventas.precio', ['PRC-20', 'PRC-22', 'PRC-23']],
    ['ventas.listaAnterior', ['PRC-21', 'AUD-01']],
    ['ventas.cobranza', ['VTA-11', 'CC-05', 'COB-02']],
    ['ventas.consumidorFinal', ['CLI-03', 'ADR-054']],
    ['ventas.stock', ['STK-05', 'STK-01', 'ADR-054']],
    ['ventas.numero', ['VTA-06', 'ADR-008']],
    ['ventas.costo', ['VTA-05', 'INV-10']],
    ['ventas.observaciones', ['SYN-05', 'SYN-07', 'STK-06', 'ADR-054']],
  ] as const

  it('las nueve claves existen y citan las reglas aprobadas', () => {
    expect(reglasAprobadas.map(([clave]) => [clave, [...AYUDAS[clave].reglas]])).toEqual(
      reglasAprobadas.map(([clave, reglas]) => [clave, [...reglas]]),
    )
  })

  it.each([
    ['ventas.cajasYUnidades', 'Cargá cuántas cajas y cuántas unidades sueltas lleva el cliente.', '2 cajas + 3 botellas de Vino A (caja x6 a $12.500) = 15 botellas → $31.250.'],
    ['ventas.precio', 'Queda guardado en la venta: si mañana cambia la lista, esta venta no cambia.', 'Kiosco La Esquina usa la lista General: Vino A a $12.500 la caja.'],
    ['ventas.listaAnterior', 'pide un motivo y queda registrado quién lo hizo.', '«Precio acordado con el cliente»'],
    ['ventas.cobranza', 'Si paga de más, le queda saldo a favor.', 'queda debiendo $210.000.'],
    ['ventas.consumidorFinal', 'el pago tiene que ser igual al total.', 'Venta de $4.300 → cobrás $4.300.'],
    ['ventas.stock', 'salvo que tengas permiso para dejar el stock en negativo', 'Quedan 48 botellas y vendés 50 → queda en −2 y se marca.'],
    ['ventas.numero', 'No se repite nunca en la organización.', 'V03-000142 es la venta 142 del teléfono V03.'],
    ['ventas.costo', 'Queda fijo: si después el producto sube, esta venta no cambia.', '72 botellas a $1.050 de promedio → costo $75.600.'],
    ['ventas.observaciones', 'La venta se tomó igual porque la mercadería ya se entregó.', ''],
  ] as const)('%s trae el texto y el ejemplo aprobados', (clave, fragmentoDelTexto, fragmentoDelEjemplo) => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(entrada.texto).toContain(fragmentoDelTexto)
    if (fragmentoDelEjemplo !== '') expect(entrada.ejemplo).toContain(fragmentoDelEjemplo)
  })

  it('las observaciones llevan a "Ver más" (tema ventas-observaciones) con una explicación por cada uno de los diez avisos aprobados el 2026-10-20', () => {
    const entrada: { verMas?: string } = AYUDAS['ventas.observaciones']
    expect(entrada.verMas).toBe('ventas-observaciones')
    const secciones = TEMAS['ventas-observaciones'].secciones
    const avisos: readonly (readonly [string, string])[] = [
      ['Stock negativo', 'Se vendió más de lo que figuraba en la ubicación. El stock quedó por debajo de cero hasta que se corrija con un ajuste o una transferencia.'],
      ['Lista no vigente', 'El teléfono usó precios de una versión de lista que ya no regía al momento de la venta. La venta quedó con esos precios.'],
      ['Cliente no habilitado', 'El cliente estaba suspendido o inactivo cuando se hizo la venta.'],
      ['Consumidor final con deuda', 'Al consumidor final se le cobró un importe distinto del total. Su cuenta quedó con un saldo que no se puede cobrar después.'],
      ['Permiso revocado', 'Al vendedor le habían quitado el permiso de vender antes de que la venta llegara.'],
      ['Jornada liberada', 'Un supervisor liberó la jornada del vendedor antes de que la venta llegara.'],
      ['Ubicación tomada al sincronizar', 'Cuando la venta llegó, la ubicación estaba tomada por otra jornada o en rendición. El stock se descontó igual.'],
      ['Vendido sin costo', 'El producto no tenía costo cargado. La venta quedó sin costo y hay que revisarlo.'],
      ['Medio inactivo', 'Se cobró con un medio de pago que estaba desactivado.'],
      ['Falta la referencia', 'Se cobró con un medio que exige referencia, por ejemplo el número de transferencia, y no se cargó.'],
    ]
    for (const [nombre, explicacion] of avisos) {
      const seccion = secciones.find((s) => s.titulo === nombre)
      expect(seccion, nombre).toBeDefined()
      expect(seccion?.parrafos).toEqual([explicacion])
    }
    expect(secciones.map((s) => s.titulo)).not.toContain('Los avisos posibles')
    expect(secciones[0]?.titulo).toBe('Por qué la venta se toma igual')
    expect(secciones[0]?.parrafos).toEqual(['La venta se tomó igual porque la mercadería ya se entregó.'])
  })

  it('no se revisó la clave de cobranzas que se reutiliza para los medios', () => {
    expect(AYUDAS['cobranzas.medios'].texto).toContain('Podés repartir el total entre varios medios')
  })
})

describe('ayuda de descuentos, crédito y PIN (change 18b, D22; textos corregidos por el usuario el 2026-10-21)', () => {
  const reglasAprobadas = [
    ['ventas.descuentoGeneral', ['DSC-05', 'DSC-06']],
    ['ventas.descuentoPropio', ['DSC-05', 'DSC-08', 'ADR-050']],
    ['ventas.topeDescuento', ['DSC-06']],
    ['ventas.autorizacion', ['DSC-06', 'CRE-05', 'SEG-05']],
    ['ventas.motivoDescuento', ['DSC-06', 'DSC-08']],
    ['ventas.descuentosAutomaticos', ['DSC-05', 'DSC-09']],
    ['ventas.credito', ['CRE-01', 'CRE-02']],
    ['ventas.politicaCredito', ['CRE-03', 'CRE-04', 'CRE-05', 'CRE-07']],
    ['configuracion.descuentoManual', ['DSC-06']],
    ['configuracion.credito', ['CRE-03', 'CRE-06', 'ADR-032']],
    ['roles.pinAutorizacion', ['SEG-05', 'ADR-011', 'ADR-019']],
    ['cuenta.miPin', ['SEG-05', 'ADR-011', 'ADR-019']],
  ] as const

  it('las doce claves existen y citan las reglas aprobadas', () => {
    expect(reglasAprobadas.map(([clave]) => [clave, [...AYUDAS[clave].reglas]])).toEqual(
      reglasAprobadas.map(([clave, reglas]) => [clave, [...reglas]]),
    )
  })

  it.each([
    ['ventas.descuentoGeneral', 'ese reemplaza al general en esa línea: no se suman.', '$1.484,38 menos.'],
    ['ventas.descuentoPropio', 'No se puede poner 0 % para dejar una línea sin el general.', 'el vino lleva 10 % y el resto 5 %.'],
    ['ventas.topeDescuento', 'los descuentos automáticos no cuentan.', '5 % general y 8 % en un producto pide autorización.'],
    ['ventas.autorizacion', 'el PIN no se guarda y queda registrado quién autorizó.', 'la venta queda con Marta como autorizadora.'],
    ['ventas.credito', 'límite cero es solo de contado.', 'queda debiendo $210.000: se pasa $10.000.'],
    ['configuracion.credito', 'sin tolerancia, todo exceso sin señal pide permiso o PIN.', 'con $5.000 pide permiso o PIN.'],
  ] as const)('%s trae su texto y su ejemplo aprobados', (clave, fragmentoDelTexto, fragmentoDelEjemplo) => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(entrada.texto).toContain(fragmentoDelTexto)
    expect(entrada.ejemplo).toContain(fragmentoDelEjemplo)
  })

  it.each([
    ['ventas.motivoDescuento', 'uno solo por venta, que queda guardado en cada producto con descuento manual.'],
    ['ventas.descuentosAutomaticos', 'la venta no se confirma y se muestran los nuevos.'],
    ['ventas.politicaCredito', 'Bloquear: no se confirma; podés cobrar más o sacar productos.'],
    ['configuracion.descuentoManual', 'Exigir motivo: cada venta con descuento manual pide elegir un motivo.'],
    ['roles.pinAutorizacion', 'aprueba, en la pantalla de otro, un descuento o un exceso de crédito.'],
    ['cuenta.miPin', 'Cuando lo cambiás, el anterior deja de servir.'],
  ] as const)('%s trae su texto aprobado', (clave, fragmento) => {
    expect(AYUDAS[clave].texto).toContain(fragmento)
  })

  it('"Mi PIN" no lleva ejemplo (tal como lo aprobó el usuario)', () => {
    expect('ejemplo' in AYUDAS['cuenta.miPin']).toBe(false)
  })

  it('los "Ver más" apuntan a los temas aprobados: topes para el tope y el general, crédito para el crédito', () => {
    const verMas = (clave: ClaveDeAyuda): string | undefined => {
      const entrada: { verMas?: string } = AYUDAS[clave]
      return entrada.verMas
    }
    expect(verMas('ventas.descuentoGeneral')).toBe('topes')
    expect(verMas('ventas.topeDescuento')).toBe('topes')
    expect(verMas('ventas.credito')).toBe('credito')
    expect(verMas('ventas.politicaCredito')).toBe('credito')
  })

  it('el tema "credito" explica disponible, consumo, las tres políticas, la tolerancia sin señal y lo guardado', () => {
    const tema = TEMAS.credito
    expect(tema.titulo).toBe('Cómo funciona el crédito de los clientes')
    expect(tema.secciones.map((seccion) => seccion.titulo)).toEqual([
      'Cuánto crédito le queda',
      'Qué consume una venta',
      'Advertir',
      'Autorizar',
      'Bloquear',
      'Sin señal',
      'Qué queda guardado en la venta',
    ])
    for (let numero = 1; numero <= 10; numero += 1) {
      expect(tema.reglas).toContain(`CRE-${String(numero).padStart(2, '0')}`)
    }
  })

  it('el tema de avisos de ventas suma AUTORIZACION_OFFLINE y los avisos de crédito y descuento', () => {
    const titulos = TEMAS['ventas-observaciones'].secciones.map((seccion) => seccion.titulo)
    expect(titulos).toEqual(
      expect.arrayContaining([
        'Descuentos distintos',
        'Autorización sin señal',
        'Exceso de crédito advertido',
        'Exceso dentro de la tolerancia',
        'Exceso de crédito detectado al sincronizar',
      ]),
    )
    expect(TEMAS['ventas-observaciones'].reglas).toContain('ADR-055')
  })
})

describe('ClaveDeAyuda: el compilador rechaza una clave inexistente', () => {
  it('una clave mal escrita no compila (verificado por `npm run typecheck`)', () => {
    // @ts-expect-error `descuentos.medidda` no existe en AYUDAS
    const mala: ClaveDeAyuda = 'descuentos.medidda'
    expect(claves).not.toContain(mala)
  })
})
