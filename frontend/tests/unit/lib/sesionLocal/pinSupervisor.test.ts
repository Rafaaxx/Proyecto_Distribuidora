import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../../src/lib/dispositivo/db'
import {
  autorizadoresConPermiso,
  INTENTOS_PIN_MAX_POR_DEFECTO,
  verificarPinDeSupervisor,
} from '../../../../src/lib/sesionLocal/pinSupervisor'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 22a, tarea 9.1 (spec `identidad/pin-de-autorizacion`, "El PIN de un supervisor se
 * verifica en el teléfono con límite de intentos"; `design.md` D10 = B; SEG-05, ADR-055,
 * `02` §12.4): el PIN del supervisor se verifica en el teléfono contra la derivación del
 * bootstrap; los fallos se cuentan por par (usuario, autorizador); al llegar a
 * `intentos_pin_max` el PIN queda bloqueado hasta el próximo bootstrap, NO por tiempo (no se
 * guardan ni comparan horas); el PIN nunca se guarda.
 */
interface CasoDeVector {
  id: string
  pin: string
  sal_hex: string
  iteraciones: number
  hash_hex: string
}

const aqui = dirname(fileURLToPath(import.meta.url))
const VECTOR = JSON.parse(
  readFileSync(join(aqui, '..', '..', '..', '..', '..', 'shared', 'fixtures', 'pin', 'derivacion.json'), 'utf-8'),
) as { casos: CasoDeVector[] }
const RAPIDO = VECTOR.casos.find((c) => c.id === 'PIN-DERIV-03') as CasoDeVector
const LENTO = VECTOR.casos.find((c) => c.id === 'PIN-DERIV-01') as CasoDeVector

const USUARIO = '00000000-0000-7000-8000-000000000001'
const SUP01 = '00000000-0000-7000-8000-0000000000a1'
const SUP02 = '00000000-0000-7000-8000-0000000000a2'
const SIN_PERMISO = '00000000-0000-7000-8000-0000000000a3'
const PIN_MALO = '358126'

async function sembrar(maximo = 5, derivacion: CasoDeVector = RAPIDO): Promise<void> {
  await baseLocal.configuracion.put({ clave: 'organizacion', intentos_pin_max: maximo } as never)
  await baseLocal.autorizadores.bulkPut([
    {
      id: SUP01,
      nombre: 'sup01',
      permisos: ['AUTORIZAR_DESCUENTO', 'SUPERAR_CREDITO'],
      pin_hash: derivacion.hash_hex,
      pin_sal: derivacion.sal_hex,
      iteraciones: derivacion.iteraciones,
    },
    {
      id: SUP02,
      nombre: 'sup02',
      permisos: ['AUTORIZAR_DESCUENTO'],
      pin_hash: RAPIDO.hash_hex,
      pin_sal: RAPIDO.sal_hex,
      iteraciones: RAPIDO.iteraciones,
    },
    {
      id: SIN_PERMISO,
      nombre: 'sup03',
      permisos: ['AUTORIZAR_DESCUENTO'],
      pin_hash: RAPIDO.hash_hex,
      pin_sal: RAPIDO.sal_hex,
      iteraciones: RAPIDO.iteraciones,
    },
  ])
}

function intentar(autorizadorId: string, pin: string, permiso = 'AUTORIZAR_DESCUENTO') {
  return verificarPinDeSupervisor({ usuarioId: USUARIO, autorizadorId, permisoRequerido: permiso, pin })
}

async function fallar(autorizadorId: string, veces: number): Promise<void> {
  for (let i = 0; i < veces; i += 1) await intentar(autorizadorId, PIN_MALO)
}

describe('verificación local del PIN de supervisor (tarea 9.1; D10 = B)', () => {
  beforeEach(async () => {
    await Promise.all([
      baseLocal.intentos_pin.clear(),
      baseLocal.autorizadores.clear(),
      baseLocal.configuracion.clear(),
      baseLocal.meta.clear(),
    ])
    await sembrar()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('el valor por defecto del máximo de intentos es 5 (ADR-055)', () => {
    expect(INTENTOS_PIN_MAX_POR_DEFECTO).toBe(5)
  })

  it('el PIN correcto verifica contra la derivación del vector compartido y devuelve el autorizador (SEG-05)', async () => {
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'ok', autorizadorId: SUP01 })
  })

  it('verifica también con las 600000 iteraciones del vector PIN-DERIV-01 (SEG-05, ADR-011)', async () => {
    await sembrar(5, LENTO)
    expect(await intentar(SUP01, LENTO.pin)).toEqual({ tipo: 'ok', autorizadorId: SUP01 })
    expect(await intentar(SUP01, RAPIDO.pin)).toMatchObject({ tipo: 'incorrecto' })
  }, 30_000)

  it('un PIN incorrecto suma un fallo para el par (usuario, autorizador) y informa los restantes', async () => {
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'incorrecto', restantes: 4 })
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'incorrecto', restantes: 3 })
    const fila = await baseLocal.intentos_pin.get([USUARIO, SUP01])
    expect(fila?.fallos).toBe(2)
    expect(fila?.bloqueado).toBe(false)
    expect(await baseLocal.intentos_pin.get([USUARIO, SUP02])).toBeUndefined()
  })

  it('la cuenta es por par: otro usuario del teléfono parte de cero con el mismo autorizador', async () => {
    await fallar(SUP01, 2)
    const otro = await verificarPinDeSupervisor({
      usuarioId: '00000000-0000-7000-8000-000000000002',
      autorizadorId: SUP01,
      permisoRequerido: 'AUTORIZAR_DESCUENTO',
      pin: PIN_MALO,
    })
    expect(otro).toEqual({ tipo: 'incorrecto', restantes: 4 })
  })

  it('con intentos_pin_max fallos el PIN queda bloqueado en el teléfono (SEG-05, 02 §12.4)', async () => {
    await fallar(SUP01, 4)
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'bloqueado' })
    const fila = await baseLocal.intentos_pin.get([USUARIO, SUP01])
    expect(fila).toMatchObject({ fallos: 5, bloqueado: true })
  })

  it('respeta un intentos_pin_max distinto de 5 tomado del bootstrap', async () => {
    await sembrar(3)
    await fallar(SUP01, 2)
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'bloqueado' })
  })

  it('durante el bloqueo un intento con el PIN correcto no verifica ni cuenta', async () => {
    await fallar(SUP01, 5)
    const derivar = vi.spyOn(globalThis.crypto.subtle, 'deriveBits')

    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'bloqueado' })
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'bloqueado' })

    expect(derivar).not.toHaveBeenCalled()
    expect((await baseLocal.intentos_pin.get([USUARIO, SUP01]))?.fallos).toBe(5)
  })

  it('adelantar el reloj del teléfono no levanta el bloqueo (D10 = B, no es por tiempo)', async () => {
    await fallar(SUP01, 5)
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2030-01-01T00:00:00Z'))
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'bloqueado' })
    vi.setSystemTime(new Date('2026-10-31T00:00:00Z'))
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'bloqueado' })
  })

  it('el estado no guarda ni compara horas ni el PIN', async () => {
    await fallar(SUP01, 2)
    const fila = await baseLocal.intentos_pin.get([USUARIO, SUP01])
    expect(Object.keys(fila ?? {}).sort()).toEqual(['autorizador_id', 'bloqueado', 'derivacion', 'fallos', 'usuario_id'])
    expect(fila?.derivacion).toBe(RAPIDO.hash_hex)

    await intentar(SUP01, RAPIDO.pin)
    for (const tabla of baseLocal.tables) {
      const contenido = JSON.stringify(await tabla.toArray())
      expect(contenido).not.toContain(RAPIDO.pin)
      expect(contenido).not.toContain(PIN_MALO)
    }
  })

  it('un acierto no reinicia la cuenta de fallos', async () => {
    await fallar(SUP01, 3)
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'ok', autorizadorId: SUP01 })
    expect((await baseLocal.intentos_pin.get([USUARIO, SUP01]))?.fallos).toBe(3)
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'incorrecto', restantes: 1 })
    expect(await intentar(SUP01, PIN_MALO)).toEqual({ tipo: 'bloqueado' })
  })

  it('un autorizador sin el permiso requerido no se verifica ni cuenta (CRE-06, DSC-06)', async () => {
    const derivar = vi.spyOn(globalThis.crypto.subtle, 'deriveBits')
    expect(await intentar(SIN_PERMISO, PIN_MALO, 'SUPERAR_CREDITO')).toEqual({ tipo: 'sin_permiso' })
    expect(await intentar(SIN_PERMISO, RAPIDO.pin, 'SUPERAR_CREDITO')).toEqual({ tipo: 'sin_permiso' })
    expect(derivar).not.toHaveBeenCalled()
    expect(await baseLocal.intentos_pin.count()).toBe(0)
  })

  it('un autorizador que no está en el bootstrap no se verifica ni cuenta', async () => {
    const r = await intentar('00000000-0000-7000-8000-0000000000ff', RAPIDO.pin)
    expect(r).toEqual({ tipo: 'sin_permiso' })
    expect(await baseLocal.intentos_pin.count()).toBe(0)
  })

  it('autorizadoresConPermiso ofrece solo a quienes tienen el permiso (CRE-06, DSC-06)', async () => {
    expect((await autorizadoresConPermiso('SUPERAR_CREDITO')).map((a) => a.id)).toEqual([SUP01])
    expect((await autorizadoresConPermiso('AUTORIZAR_DESCUENTO')).map((a) => a.id).sort()).toEqual(
      [SUP01, SUP02, SIN_PERMISO].sort(),
    )
  })

  it('intentos simultáneos no esquivan el límite', async () => {
    const resultados = await Promise.all(Array.from({ length: 8 }, () => intentar(SUP01, PIN_MALO)))
    expect(resultados.filter((r) => r.tipo === 'incorrecto')).toHaveLength(4)
    expect(resultados.filter((r) => r.tipo === 'bloqueado')).toHaveLength(4)
    expect((await baseLocal.intentos_pin.get([USUARIO, SUP01]))?.fallos).toBe(5)
  })

  it('cualquier bootstrap nuevo levanta el bloqueo y reinicia a cero las cuentas de todos los pares (ADR-055)', async () => {
    await fallar(SUP01, 5)
    await fallar(SUP02, 2)
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'bloqueado' })

    await aplicarBootstrap(bootstrapMinimo())

    expect(await baseLocal.intentos_pin.count()).toBe(0)
    expect(await intentar(SUP01, RAPIDO.pin)).toEqual({ tipo: 'ok', autorizadorId: SUP01 })
    expect(await intentar(SUP02, PIN_MALO)).toEqual({ tipo: 'incorrecto', restantes: 4 })
  })

  it('un bootstrap con otra derivación también reinicia la cuenta', async () => {
    await fallar(SUP01, 4)
    await aplicarBootstrap(bootstrapMinimo({ pin: { hash: LENTO.hash_hex, sal: LENTO.sal_hex, it: LENTO.iteraciones } }))
    expect(await baseLocal.intentos_pin.count()).toBe(0)
  })
})

function bootstrapMinimo(opciones: { pin?: { hash: string; sal: string; it: number } } = {}) {
  const pin = opciones.pin ?? { hash: RAPIDO.hash_hex, sal: RAPIDO.sal_hex, it: RAPIDO.iteraciones }
  const autorizador = (id: string, nombre: string, permisos: string[]) => ({
    id,
    nombre,
    permisos,
    pin_hash: pin.hash,
    pin_sal: pin.sal,
    iteraciones: pin.it,
  })
  return {
    generado_en: '2026-10-31T12:00:00Z',
    sesion: {
      usuario: { id: USUARIO, usuario: 'vendedor', nombre: 'Vendedor' },
      permisos: ['VENDER'],
      jornada: { id: '00000000-0000-7000-8000-000000000009' },
      numeracion: {},
    },
    contexto_venta: {},
    configuracion: { intentos_pin_max: 5 },
    productos: [],
    listas: [],
    clientes: [],
    reglas_descuento: [],
    stock: [],
    autorizadores: [
      autorizador(SUP01, 'sup01', ['AUTORIZAR_DESCUENTO', 'SUPERAR_CREDITO']),
      autorizador(SUP02, 'sup02', ['AUTORIZAR_DESCUENTO']),
    ],
    catalogos: { medios_pago: [], motivos: [], alicuotas: [] },
  } as never
}
