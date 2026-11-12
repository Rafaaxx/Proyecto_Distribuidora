/**
 * Ejecuta contra `src/lib/huella.ts` los casos compartidos de
 * `shared/fixtures/calculo/huella-canonica.json` (`"motor": "huella"`).
 *
 * Spec `sistema/pipeline-de-comandos`, escenarios "El mismo contenido en
 * distinto orden produce la misma huella" y "Un contenido distinto produce
 * una huella distinta"; ADR-012 (extensión 2026-09-21, `design.md` D1).
 *
 * Los campos decimales del fixture viajan como `{"__decimal__": "<texto>",
 * "escala": 2|6}` porque JSON no tiene un tipo Decimal nativo: este arnés
 * los resuelve a un `string` ya cuantizado y formateado con
 * `src/lib/money.ts` (la única fuente de redondeo del frontend,
 * `CLAUDE.md` §4) *antes* de llamar a `calcularHuella`, igual que haría el
 * código real que arma el contenido de un comando (`src/lib/huella.ts` no
 * acepta un `Importe` de decimal.js como tipo de entrada -- ver su
 * docstring para el porqué).
 */

import { describe, expect, it } from 'vitest'

import { redondearCosto, redondearImporte } from '../../../src/lib/money'
import { calcularHuella, type ContenidoComando } from '../../../src/lib/huella'
import { descubrirCasos } from './cargador'

function resolverDecimales(nodo: unknown): ContenidoComando {
  if (Array.isArray(nodo)) {
    return nodo.map(resolverDecimales)
  }
  if (nodo !== null && typeof nodo === 'object') {
    const registro = nodo as Record<string, unknown>
    if ('__decimal__' in registro) {
      const texto = registro['__decimal__'] as string
      const escala = registro['escala'] as number
      if (escala === 2) return redondearImporte(texto).toFixed(2)
      if (escala === 6) return redondearCosto(texto).toFixed(6)
      throw new Error(`escala de fixture no soportada: ${String(escala)}`)
    }
    const resultado: Record<string, ContenidoComando> = {}
    for (const [clave, valor] of Object.entries(registro)) {
      resultado[clave] = resolverDecimales(valor)
    }
    return resultado
  }
  return nodo as ContenidoComando
}

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'huella')

// Guardia de deriva: si el fixture semilla dejara de tener casos de
// "huella", esta suite no debe quedar en silencio con 0 pruebas.
if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "huella" en ' +
      'shared/fixtures/calculo/ -- el arnés de huella.ts quedaría mudo',
  )
}

function buscar(id: string) {
  const caso = casos.find((c) => c.id === id)
  if (!caso) throw new Error(`Caso de fixture no encontrado: ${id}`)
  return caso
}

describe('casos compartidos de huella', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', async (_id, caso) => {
    const contenido = resolverDecimales(caso.entrada['contenido'])
    const esperado = (caso.salida_esperada as { huella: string }).huella

    const resultado = await calcularHuella(contenido as Record<string, ContenidoComando>)

    expect(resultado).toBe(esperado)
  })

  it('claves fuera de orden dan la misma huella (escenario: orden no importa)', async () => {
    const original = buscar('HUELLA-claves-fuera-de-orden-orden-original')
    const alterno = buscar('HUELLA-claves-fuera-de-orden-orden-alterno')

    const huellaOriginal = await calcularHuella(
      original.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    const huellaAlterna = await calcularHuella(
      alterno.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    expect(huellaOriginal).toBe(huellaAlterna)
  })

  it('NFC y NFD dan la misma huella', async () => {
    const original = buscar('HUELLA-texto-nfc')
    const alterno = buscar('HUELLA-texto-nfd')

    const huellaOriginal = await calcularHuella(
      original.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    const huellaAlterna = await calcularHuella(
      alterno.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    expect(huellaOriginal).toBe(huellaAlterna)
  })

  it('nulo y clave ausente dan huellas distintas', async () => {
    const conNulo = buscar('HUELLA-clave-con-valor-nulo')
    const ausente = buscar('HUELLA-clave-ausente')

    const huellaConNulo = await calcularHuella(
      conNulo.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    const huellaAusente = await calcularHuella(
      ausente.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    expect(huellaConNulo).not.toBe(huellaAusente)
  })

  it('el orden de un arreglo cambia la huella (los arreglos no se reordenan)', async () => {
    const original = buscar('HUELLA-arreglo-orden-importa-original')
    const invertido = buscar('HUELLA-arreglo-orden-importa-invertido')

    const huellaOriginal = await calcularHuella(
      original.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    const huellaInvertida = await calcularHuella(
      invertido.entrada['contenido'] as Record<string, ContenidoComando>,
    )
    expect(huellaOriginal).not.toBe(huellaInvertida)
  })

  it('un decimal normalizado a la escala de su columna da la misma huella', async () => {
    // "31250.00" y "31250.0" son el mismo importe (`design.md` D1): una vez
    // normalizados a la escala de NUMERIC(14,2) con redondearImporte y
    // formateados con toFixed(2), su huella es idéntica aunque el texto de
    // origen difiera.
    const dosDecimales = redondearImporte('31250.00').toFixed(2)
    const unDecimal = redondearImporte('31250.0').toFixed(2)

    expect(dosDecimales).toBe(unDecimal)
    expect(dosDecimales).toBe('31250.00')
    const huellaDos = await calcularHuella({ importe_total: dosDecimales })
    const huellaUno = await calcularHuella({ importe_total: unDecimal })
    expect(huellaDos).toBe(huellaUno)
  })

  it('rechaza un número no entero en el contenido (INV-03)', async () => {
    await expect(calcularHuella({ importe: 3.14 })).rejects.toThrow(TypeError)
  })
})
