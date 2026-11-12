import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { derivarPin } from '../../../../src/lib/sesionLocal/derivacion'
import {
  cambiarPin,
  definirPin,
  desbloquearConPin,
  hayPinDefinido,
  INTENTOS_DESBLOQUEO_MAX,
  ITERACIONES_PIN,
  intentosFallidos,
  validarPinNuevo,
} from '../../../../src/lib/sesionLocal/pin'

/**
 * Change 21, tareas 8.1 y 8.2 (spec `identidad/sesion-local`; `design.md` D13, D15; SEG-03,
 * SEG-04, ADR-011, ADR-055, SYN-09): el PIN se guarda solo derivado, los fallos se cuentan en la
 * base local y, al llegar al máximo, se borra la derivación sin tocar los datos maestros.
 */
async function meta(clave: string): Promise<string | undefined> {
  return (await baseLocal.meta.get(clave))?.valor
}

async function fijarMaximoDeIntentos(max: number): Promise<void> {
  await baseLocal.configuracion.put({ clave: 'organizacion', intentos_pin_max: max } as never)
}

describe('PIN de desbloqueo: alta (tarea 8.1)', () => {
  beforeEach(async () => {
    await baseLocal.meta.clear()
    await baseLocal.configuracion.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it.each(['482915', '907314'])('acepta el PIN válido %s', (pin) => {
    expect(validarPinNuevo(pin, pin)).toEqual({ ok: true })
  })

  it.each([
    ['111111', /iguales/i],
    ['123456', /seguidos/i],
    ['654321', /seguidos/i],
    ['000000', /iguales/i],
    ['345678', /seguidos/i],
  ])('rechaza el PIN trivial %s', (pin, motivo) => {
    const r = validarPinNuevo(pin, pin)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.motivo).toMatch(motivo)
  })

  it.each(['12345', '1234567', '48291a', '', '48 915'])('rechaza %j: deben ser exactamente 6 dígitos', (pin) => {
    const r = validarPinNuevo(pin, pin)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.motivo).toMatch(/6 dígitos/)
  })

  it('rechaza dos PIN distintos', () => {
    const r = validarPinNuevo('482915', '482916')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.motivo).toMatch(/no coinciden/i)
  })

  it('guarda hash, sal de 32 bytes e iteraciones 600 000, nunca el PIN', async () => {
    const r = await definirPin('482915', '482915')
    expect(r).toEqual({ ok: true })

    const sal = await meta('pin_sal')
    const hash = await meta('pin_hash')
    expect(ITERACIONES_PIN).toBe(600_000)
    expect(await meta('pin_iteraciones')).toBe('600000')
    expect(sal).toMatch(/^[0-9a-f]{64}$/)
    expect(hash).toBe(await derivarPin('482915', sal ?? '', 600_000))

    const todo = JSON.stringify(await baseLocal.meta.toArray())
    expect(todo).not.toContain('482915')
    expect(await hayPinDefinido()).toBe(true)
  }, 15_000)

  it('cada alta usa una sal distinta', async () => {
    await definirPin('482915', '482915')
    const primera = await meta('pin_sal')
    await definirPin('482915', '482915')
    expect(await meta('pin_sal')).not.toBe(primera)
  }, 15_000)

  it('un PIN inválido no guarda nada', async () => {
    const r = await definirPin('111111', '111111')
    expect(r.ok).toBe(false)
    expect(await hayPinDefinido()).toBe(false)
    expect(await baseLocal.meta.count()).toBe(0)
  })

  it('ninguna petición lleva el PIN (no se llama a fetch)', async () => {
    const espia = vi.fn()
    vi.stubGlobal('fetch', espia)
    await definirPin('482915', '482915')
    await desbloquearConPin('482915')
    expect(espia).not.toHaveBeenCalled()
  }, 15_000)
})

describe('PIN de desbloqueo: intentos y cambio (tarea 8.2)', () => {
  beforeEach(async () => {
    await baseLocal.meta.clear()
    await baseLocal.configuracion.clear()
    await baseLocal.clientes.clear()
    await definirPin('482915', '482915')
  }, 15_000)

  it('el PIN correcto desbloquea y reinicia la cuenta', async () => {
    await desbloquearConPin('000001')
    await desbloquearConPin('000002')
    expect(await intentosFallidos()).toBe(2)
    expect(await desbloquearConPin('482915')).toEqual({ tipo: 'ok' })
    expect(await intentosFallidos()).toBe(0)
  }, 15_000)

  it('un PIN incorrecto suma un fallo y dice cuántos quedan (10 fijos: no dependen de la organización)', async () => {
    expect(await desbloquearConPin('000001')).toEqual({ tipo: 'incorrecto', restantes: 9 })
    expect(await desbloquearConPin('000002')).toEqual({ tipo: 'incorrecto', restantes: 8 })
    expect(await intentosFallidos()).toBe(2)
  }, 15_000)

  it('la cuenta sobrevive a una recarga: 3 fallos + recarga + el resto hasta 10 bloquea', async () => {
    for (let i = 0; i < 3; i += 1) await desbloquearConPin('000001')
    vi.resetModules()
    const recargado = await import('../../../../src/lib/sesionLocal/pin')
    expect(await recargado.intentosFallidos()).toBe(3)
    await baseLocal.meta.put({ clave: 'pin_intentos', valor: '8' })
    expect(await recargado.desbloquearConPin('000001')).toEqual({ tipo: 'incorrecto', restantes: 1 })
    expect(await recargado.desbloquearConPin('000001')).toEqual({ tipo: 'bloqueado' })
  }, 30_000)

  it('al llegar al máximo borra la derivación y deja intactos los datos maestros', async () => {
    await baseLocal.clientes.put({ id: 'c1', nombre: 'Cliente' } as never)
    await baseLocal.meta.put({ clave: 'dispositivo_id', valor: 'disp-1' })
    for (let i = 0; i < 9; i += 1) await desbloquearConPin('000001')
    expect(await intentosFallidos()).toBe(9)
    expect(await desbloquearConPin('000001')).toEqual({ tipo: 'bloqueado' })

    expect(await hayPinDefinido()).toBe(false)
    expect(await meta('pin_hash')).toBeUndefined()
    expect(await meta('pin_sal')).toBeUndefined()
    expect(await meta('pin_iteraciones')).toBeUndefined()
    expect(await baseLocal.clientes.count()).toBe(1)
    expect(await meta('dispositivo_id')).toBe('disp-1')
    expect(await desbloquearConPin('482915')).toEqual({ tipo: 'sin_pin' })
  }, 30_000)

  it('el máximo es una constante de 10 y no usa intentos_pin_max de la organización (ADR-062)', async () => {
    expect(INTENTOS_DESBLOQUEO_MAX).toBe(10)
    await fijarMaximoDeIntentos(2)
    expect(await desbloquearConPin('000001')).toEqual({ tipo: 'incorrecto', restantes: 9 })
    await fijarMaximoDeIntentos(50)
    await baseLocal.meta.put({ clave: 'pin_intentos', valor: '9' })
    expect(await desbloquearConPin('000001')).toEqual({ tipo: 'bloqueado' })
  }, 15_000)

  it('cambia el PIN con el actual correcto: el anterior deja de abrir', async () => {
    expect(await cambiarPin('482915', '907314', '907314')).toEqual({ tipo: 'ok' })
    expect(await desbloquearConPin('482915')).toMatchObject({ tipo: 'incorrecto' })
    expect(await desbloquearConPin('907314')).toEqual({ tipo: 'ok' })
  }, 30_000)

  it('el PIN actual incorrecto no cambia nada y suma un fallo', async () => {
    const hashAntes = await meta('pin_hash')
    expect(await cambiarPin('000001', '907314', '907314')).toEqual({ tipo: 'incorrecto', restantes: 9 })
    expect(await meta('pin_hash')).toBe(hashAntes)
    expect(await intentosFallidos()).toBe(1)
  }, 15_000)

  it('un PIN nuevo inválido no cambia nada ni suma fallo', async () => {
    const hashAntes = await meta('pin_hash')
    const r = await cambiarPin('482915', '111111', '111111')
    expect(r.tipo).toBe('invalido')
    expect(await meta('pin_hash')).toBe(hashAntes)
    expect(await intentosFallidos()).toBe(0)
  }, 15_000)

  it('cambiar el PIN con el actual correcto reinicia la cuenta de fallos', async () => {
    await desbloquearConPin('000001')
    await cambiarPin('482915', '907314', '907314')
    expect(await intentosFallidos()).toBe(0)
  }, 30_000)
})
