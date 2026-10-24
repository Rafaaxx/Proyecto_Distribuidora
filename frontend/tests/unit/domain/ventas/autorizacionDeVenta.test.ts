/**
 * Change 18b, tarea 13.1: quién tiene que autorizar la venta y con qué credenciales (DSC-06,
 * CRE-05, SEG-05; `design.md` D2, D4, D20). Una sola credencial por persona; el PIN no se
 * persiste en ningún almacenamiento.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  armarCredenciales,
  autorizacionesNecesarias,
  autorizadoresPara,
  completarSeleccion,
  faltaAlgunPin,
  formatoDePinValido,
  personasQueDebenPonerPin,
  type AutorizadorDeContexto,
} from '../../../../src/domain/ventas/autorizacionDeVenta'

const MARTA: AutorizadorDeContexto = {
  id: 'marta',
  nombre: 'Marta',
  puedeAutorizarDescuento: true,
  puedeSuperarCredito: true,
}
const JULIA: AutorizadorDeContexto = {
  id: 'julia',
  nombre: 'Julia',
  puedeAutorizarDescuento: false,
  puedeSuperarCredito: true,
}
const LUIS: AutorizadorDeContexto = {
  id: 'luis',
  nombre: 'Luis',
  puedeAutorizarDescuento: true,
  puedeSuperarCredito: false,
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('autorizacionesNecesarias', () => {
  it('descuento sobre el tope y crédito que pide autorizador: las dos', () => {
    expect(autorizacionesNecesarias({ estado: 'requiere-autorizador', tope: '0.05' }, 'pide-autorizador')).toEqual([
      'DESCUENTO',
      'CREDITO',
    ])
  })

  it('con permiso propio, dentro del tope o sin exceso no hay que pedir nada', () => {
    expect(autorizacionesNecesarias({ estado: 'permiso-propio', tope: '0.05' }, 'permiso-propio')).toEqual([])
    expect(autorizacionesNecesarias({ estado: 'dentro-del-tope', tope: '0.05' }, 'sin-exceso')).toEqual([])
    expect(autorizacionesNecesarias({ estado: 'sin-descuento' }, 'aceptado')).toEqual([])
  })

  it('solo una de las dos', () => {
    expect(autorizacionesNecesarias({ estado: 'requiere-autorizador', tope: '0.05' }, 'sin-exceso')).toEqual(['DESCUENTO'])
    expect(autorizacionesNecesarias({ estado: 'sin-descuento' }, 'pide-autorizador')).toEqual(['CREDITO'])
  })
})

describe('autorizadoresPara', () => {
  it('cada autorización se ofrece solo a quien tiene su permiso', () => {
    const todos = [MARTA, JULIA, LUIS]
    expect(autorizadoresPara('DESCUENTO', todos).map((a) => a.id)).toEqual(['marta', 'luis'])
    expect(autorizadoresPara('CREDITO', todos).map((a) => a.id)).toEqual(['marta', 'julia'])
  })
})

describe('personasQueDebenPonerPin (D4: una sola vez por persona)', () => {
  it('la misma persona para las dos autorizaciones pone el PIN una sola vez', () => {
    expect(personasQueDebenPonerPin(['DESCUENTO', 'CREDITO'], { DESCUENTO: 'marta', CREDITO: 'marta' })).toEqual(['marta'])
  })

  it('dos personas distintas ponen cada una el suyo, en el orden de las autorizaciones', () => {
    expect(personasQueDebenPonerPin(['DESCUENTO', 'CREDITO'], { DESCUENTO: 'luis', CREDITO: 'julia' })).toEqual([
      'luis',
      'julia',
    ])
  })

  it('una autorización sin elegir todavía no suma persona; la que no hace falta se ignora', () => {
    expect(personasQueDebenPonerPin(['DESCUENTO', 'CREDITO'], { DESCUENTO: 'luis' })).toEqual(['luis'])
    expect(personasQueDebenPonerPin(['CREDITO'], { DESCUENTO: 'luis', CREDITO: 'julia' })).toEqual(['julia'])
  })
})

describe('formatoDePinValido (ayuda local; el servidor valida igual)', () => {
  it.each(['123456', '482913', '12345678'])('"%s" tiene el formato', (pin) => {
    expect(formatoDePinValido(pin)).toBe(true)
  })
  it.each(['', '12345', '12345a', '12 456', '１２３４５６'])('"%s" no tiene el formato', (pin) => {
    expect(formatoDePinValido(pin)).toBe(false)
  })
})

describe('faltaAlgunPin / armarCredenciales', () => {
  it('falta cuando alguna persona no escribió un PIN con formato', () => {
    expect(faltaAlgunPin(['marta'], {})).toBe(true)
    expect(faltaAlgunPin(['marta'], { marta: '123' })).toBe(true)
    expect(faltaAlgunPin(['marta'], { marta: '482913' })).toBe(false)
    expect(faltaAlgunPin([], {})).toBe(false)
  })

  it('arma una credencial por persona, solo de las que deben ponerlo', () => {
    expect(armarCredenciales(['marta', 'julia'], { marta: '482913', julia: '115599', luis: '000111' })).toEqual([
      { autorizador_id: 'marta', pin: '482913' },
      { autorizador_id: 'julia', pin: '115599' },
    ])
  })

  it('el PIN no se persiste en ningún almacenamiento del navegador', () => {
    const local = vi.spyOn(Storage.prototype, 'setItem')
    const abrirIndexedDb = vi.fn()
    vi.stubGlobal('indexedDB', { open: abrirIndexedDb })

    const credenciales = armarCredenciales(['marta'], { marta: '482913' })
    personasQueDebenPonerPin(['DESCUENTO'], { DESCUENTO: 'marta' })
    faltaAlgunPin(['marta'], { marta: '482913' })

    expect(credenciales).toHaveLength(1)
    expect(local).not.toHaveBeenCalled()
    expect(abrirIndexedDb).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

describe('completarSeleccion (D4)', () => {
  const todos = [MARTA, JULIA, LUIS]

  it('si una persona puede dar las dos autorizaciones, se propone la misma para que ponga el PIN una vez', () => {
    expect(completarSeleccion(['DESCUENTO', 'CREDITO'], [MARTA], {})).toEqual({ DESCUENTO: 'marta', CREDITO: 'marta' })
    expect(completarSeleccion(['DESCUENTO', 'CREDITO'], todos, { DESCUENTO: 'marta' })).toEqual({
      DESCUENTO: 'marta',
      CREDITO: 'marta',
    })
  })

  it('si hay varias posibles y ninguna elegida, lo decide el usuario', () => {
    expect(completarSeleccion(['DESCUENTO'], todos, {})).toEqual({})
  })

  it('si solo una persona puede dar cada cosa, se propone a cada una', () => {
    expect(completarSeleccion(['DESCUENTO', 'CREDITO'], [LUIS, JULIA], {})).toEqual({
      DESCUENTO: 'luis',
      CREDITO: 'julia',
    })
  })

  it('lo ya elegido se conserva mientras siga siendo válido; si la persona ya no puede, se descarta', () => {
    expect(completarSeleccion(['CREDITO'], todos, { CREDITO: 'julia' })).toEqual({ CREDITO: 'julia' })
    expect(completarSeleccion(['CREDITO'], [MARTA], { CREDITO: 'luis' })).toEqual({ CREDITO: 'marta' })
  })

  it('sin nadie que pueda, no se propone a nadie', () => {
    expect(completarSeleccion(['CREDITO'], [LUIS], {})).toEqual({})
  })
})
