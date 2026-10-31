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
  it('tiene las 84 claves aprobadas (27 del 16b, 5 de cobranzas, 5 de medios de pago y roles, 9 de ventas, 12 del 18b, 6 de la anulación de venta del 19, 4 de la nota de venta del 20 y 6 de usuarios, roles y cartera del 20b y 6 de motivos, alícuotas y redondeo por defecto del 20c y 4 del área de ruta del 21; la de "Operador" y la de compartir la nota se eliminaron)', () => {
    expect(claves).toHaveLength(84)
    expect(claves).not.toContain('descuentos.operador')
    expect(claves).not.toContain('ventas.compartirNota')
    expect(claves).toEqual(
      expect.arrayContaining([
        'ventas.notaDeVenta',
        'ventas.notaAnulada',
        'configuracion.notaMuestraSaldo',
        'configuracion.notaDatosOrganizacion',
      ]),
    )
  })

  // Change 20, spec `sistema/ayuda-contextual` (VTA-13, CRE-02, ADR-008, ADR-058, ADR-059): sin ejemplos.
  it('la ayuda de la nota explica que es interna, que no es factura y que sale igual al reimprimirla', () => {
    const { texto, reglas } = AYUDAS['ventas.notaDeVenta']
    expect(texto).toMatch(/comprobante interno/i)
    expect(texto).toMatch(/no es una factura/i)
    expect(texto).toMatch(/sale igual que la original/i)
    expect(reglas).toEqual(expect.arrayContaining(['VTA-13', 'ADR-008']))
  })

  it('la ayuda de "mostrar saldo" dice que es el de la venta y que no va al consumidor final ni a una anulada', () => {
    const { texto, reglas } = AYUDAS['configuracion.notaMuestraSaldo']
    expect(texto).toMatch(/momento de la venta/i)
    expect(texto).toMatch(/consumidor final/i)
    expect(texto).toMatch(/anulada/i)
    expect(reglas).toEqual(expect.arrayContaining(['VTA-13', 'CRE-02']))
  })

  it('la ayuda de la nota anulada nombra la marca, la fecha y el motivo', () => {
    const { texto, reglas } = AYUDAS['ventas.notaAnulada']
    expect(texto).toMatch(/marca ANULADA/)
    expect(texto).toMatch(/fecha/i)
    expect(texto).toMatch(/motivo/i)
    expect(reglas).toEqual(expect.arrayContaining(['ADR-058', 'ADR-059']))
  })

  it('los cuatro textos de la nota no llevan ejemplo', () => {
    for (const clave of ['ventas.notaDeVenta', 'ventas.notaAnulada', 'configuracion.notaMuestraSaldo', 'configuracion.notaDatosOrganizacion'] as const) {
      expect(AYUDAS[clave]).not.toHaveProperty('ejemplo')
    }
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

describe('ayuda de la anulación de venta (change 19, D18; textos aprobados el 2026-10-24, sin ejemplos)', () => {
  const clavesDeAnulacion = [
    'ventas.anulacion',
    'ventas.devolverDinero',
    'ventas.motivoAnulacion',
    'ventas.consumidorFinalAnulacion',
    'ventas.reingresoUbicacion',
    'ventas.costoAnulacion',
  ] as const

  it('las seis claves existen y citan las reglas aprobadas', () => {
    expect(clavesDeAnulacion.map((clave) => [clave, [...AYUDAS[clave].reglas]])).toEqual([
      ['ventas.anulacion', ['VTA-20', 'VTA-21', 'INV-19', 'TR-06']],
      ['ventas.devolverDinero', ['VTA-22', 'COB-05', 'ADR-058']],
      ['ventas.motivoAnulacion', ['VTA-20', 'AUD-01', 'AUD-02']],
      ['ventas.consumidorFinalAnulacion', ['CLI-03', 'VTA-22', 'ADR-058']],
      ['ventas.reingresoUbicacion', ['VTA-21', 'STK-09', 'ADR-058']],
      ['ventas.costoAnulacion', ['VTA-21', 'CST-11', 'CST-13']],
    ])
  })

  it.each([
    ['ventas.anulacion', 'Anular una venta', 'Deja la venta sin efecto: la mercadería vuelve a la ubicación de donde salió y al cliente se le descuenta de su cuenta el total de la venta. No se borra: queda como anulada, con el motivo y quién la anuló. Se anula entera y una sola vez.'],
    ['ventas.devolverDinero', '¿Devolvés lo que cobraste?', 'Si le devolvés al cliente lo que pagó con esta venta, el cobro también se anula y su cuenta queda como antes de la venta. Si no se lo devolvés, ese pago le queda a favor para lo próximo que compre.'],
    ['ventas.motivoAnulacion', 'Motivo', 'Elegí por qué anulás. Queda guardado en la venta y en la auditoría.'],
    ['ventas.consumidorFinalAnulacion', 'Consumidor final', 'Al cliente sin nombre siempre se le devuelve lo que pagó: no tiene cuenta donde dejarle saldo a favor.'],
    ['ventas.reingresoUbicacion', 'Adónde vuelve la mercadería', 'Vuelve a la ubicación de donde salió. Si esa camioneta está ahora en la jornada de otro vendedor, solo puede anular quien tiene permiso para mover una ubicación tomada.'],
    ['ventas.costoAnulacion', 'Costo de lo que vuelve', 'La mercadería vuelve al mismo costo con que salió en la venta, y el costo promedio del producto se recalcula como en una compra.'],
  ] as const)('%s lleva el título y el texto aprobados, sin ejemplo', (clave, titulo, texto) => {
    const entrada: { titulo: string; texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(entrada.titulo).toBe(titulo)
    expect(entrada.texto).toBe(texto)
    expect(entrada.ejemplo).toBeUndefined()
  })

  it('"Anular una cobranza" aclara que el cobro de una venta se anula anulando la venta, y conserva su texto', () => {
    const { texto, reglas } = AYUDAS['cobranzas.anulacion']
    expect(texto).toContain('El cobro de una venta se anula anulando la venta.')
    expect(texto).toContain('Se anula entero; si te equivocaste en un medio, anulalo y cargalo de nuevo.')
    expect(reglas).toEqual(['COB-05', 'CC-02'])
  })
})

describe('ayuda de usuarios, roles y cartera (change 20b, D18; textos aprobados el 2026-10-28, sin ejemplos)', () => {
  const clavesDelTwentyB = [
    'usuarios.baja',
    'usuarios.cambioDeRol',
    'usuarios.topePropio',
    'usuarios.contrasena',
    'roles.baja',
    'clientes.vendedor',
  ] as const

  it('las seis claves existen y citan reglas; "Mi contraseña" no tiene clave', () => {
    expect(clavesDelTwentyB.map((clave) => [clave, [...AYUDAS[clave].reglas]])).toEqual([
      ['usuarios.baja', ['ADR-028', 'ADR-053']],
      ['usuarios.cambioDeRol', ['ADR-017', 'ADR-011']],
      ['usuarios.topePropio', ['DSC-06']],
      ['usuarios.contrasena', ['ADR-018', 'ADR-057']],
      ['roles.baja', ['ADR-028']],
      ['clientes.vendedor', ['ADR-052', 'CLI-03']],
    ])
    expect(claves.filter((clave) => clave.toLowerCase().includes('micontrasena'))).toEqual([])
  })

  it.each([
    ['usuarios.baja', 'Al dar de baja a un usuario deja de poder entrar y se cierran sus sesiones. Si tiene una jornada abierta, su teléfono puede subir lo que vendió o cobró sin conexión, pero no puede operar. No se puede dar de baja al último usuario que administra usuarios y roles, ni a uno mismo.'],
    ['usuarios.cambioDeRol', 'El cambio rige desde la próxima acción del usuario. Si el rol nuevo no puede autorizar excepciones, se borra su PIN de autorización.'],
    ['usuarios.topePropio', 'Si el usuario tiene tope propio, reemplaza al de su rol, sea mayor o menor. Vacío: rige el del rol. Solo tiene efecto si su rol tiene descuento manual.'],
    ['usuarios.contrasena', 'La contraseña nueva cierra sus sesiones abiertas y desbloquea el inicio de sesión si estaba bloqueado.'],
    ['roles.baja', 'Un rol con usuarios activos no se puede dar de baja: primero cambiales el rol. Un rol de baja no se puede asignar.'],
    ['clientes.vendedor', 'Los vendedores ven primero sus clientes asignados y pueden buscar en todos. Un vendedor sin clientes asignados ve todos.'],
  ] as const)('%s lleva el texto exacto de D18, sin ejemplo', (clave, texto) => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS[clave]
    expect(entrada.texto).toBe(texto)
    expect(entrada.ejemplo).toBeUndefined()
  })

  it('"Último administrador" nombra también la baja de usuarios y de roles y el cambio de rol, sin ejemplo', () => {
    const entrada: { texto: string; ejemplo?: string } = AYUDAS['roles.ultimoAdministrador']
    expect(entrada.texto).toContain('dar de baja a ese usuario o a su rol')
    expect(entrada.texto).toContain('cambiarle el rol')
    expect(entrada.ejemplo).toBeUndefined()
  })
})

describe('AYUDAS: motivos, alícuotas y redondeo por defecto (change 20c, D14, aprobados el 2026-10-30; sin ejemplos)', () => {
  it.each([
    ['motivos.ambito', 'Cada motivo sirve para un solo tipo de operación: los de un ámbito solo se ofrecen en esa operación. El ámbito no se cambia después de crear el motivo.', ['TR-09', 'ADR-061']],
    ['motivos.nombre', 'Si le cambiás el nombre, las operaciones anteriores que lo usaron muestran el nombre nuevo. No puede haber dos motivos con el mismo nombre en un ámbito.', ['ADR-061']],
    ['motivos.baja', 'Deja de ofrecerse en operaciones nuevas. No se borra: las anteriores lo siguen mostrando y lo podés volver a activar. Cada ámbito tiene que conservar al menos un motivo activo.', ['CAT-05', 'TR-06', 'ADR-061']],
    ['alicuotas.valor', 'El porcentaje no se cambia una vez creada la alícuota. Si cambia la tasa, creá una nueva, pasá los productos a ella y dá de baja la anterior. Las compras y ventas ya hechas conservan el porcentaje con que se hicieron.', ['TR-02', 'CAT-01', 'ADR-061']],
    ['alicuotas.baja', 'Deja de ofrecerse al crear o editar productos. No se puede dar de baja mientras la use un producto activo, ni si es la última activa.', ['CAT-05', 'ADR-061']],
    ['configuracion.redondeoPorDefecto', 'Es el redondeo que aparece cargado al crear una lista de precios nueva; en cada lista lo podés cambiar. Cambiarlo no modifica las listas que ya existen ni sus precios. Sin definir, la lista nueva empieza con el redondeo vacío.', ['PRC-01', 'PRC-14', 'ADR-061']],
  ] as const)('%s lleva el texto aprobado, cita sus reglas, sin ejemplo ni "Ver más"', (clave, texto, reglas) => {
    const entrada: { texto: string; ejemplo?: string; verMas?: string; reglas: readonly string[] } = AYUDAS[clave]
    expect(entrada.texto).toBe(texto)
    expect([...entrada.reglas]).toEqual(reglas)
    expect(entrada.ejemplo).toBeUndefined()
    expect(entrada.verMas).toBeUndefined()
  })
})
