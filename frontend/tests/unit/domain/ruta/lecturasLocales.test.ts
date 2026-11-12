import { describe, expect, it } from 'vitest'

import {
  disponibleDeCredito,
  filtrarYOrdenarClientes,
  precioDePresentacion,
  stockEnCajasYUnidades,
  versionVigente,
} from '../../../../src/domain/ruta/lecturasLocales'
import type { ClienteLocal, PrecioLocal, VersionLocal } from '../../../../src/lib/dispositivo/db'

/**
 * Change 21, tarea 7.1 (D6, D19; PRC-20, PRC-22, CAT-08, `01` §19, INV-03, INV-04): lecturas
 * locales puras sobre las filas de Dexie.
 */
function version(
  numero: number,
  desde: string,
  hasta: string | null,
  estado = 'PUBLICADA',
): VersionLocal {
  return { id: `v${numero}`, lista_id: 'L', numero, estado, vigencia_desde: desde, vigencia_hasta: hasta }
}

describe('versión vigente de una lista en un momento (PRC-20)', () => {
  const v1 = version(1, '2026-10-01T00:00:00Z', '2026-10-30T14:00:00Z')
  const v2 = version(2, '2026-10-30T14:00:00Z', null)

  it('elige la vigente al momento', () => {
    expect(versionVigente([v1, v2], new Date('2026-10-30T13:59:59Z'))?.id).toBe('v1')
  })

  it('incluye la programada que entra en vigencia (desde inclusive, hasta exclusive)', () => {
    expect(versionVigente([v1, v2], new Date('2026-10-30T14:00:00Z'))?.id).toBe('v2')
    expect(versionVigente([v1, v2], new Date('2026-10-30T14:05:00Z'))?.id).toBe('v2')
  })

  it('sin ninguna vigente, devuelve null ("sin precio")', () => {
    expect(versionVigente([v2], new Date('2026-10-01T00:00:00Z'))).toBeNull()
    expect(versionVigente([], new Date('2026-10-01T00:00:00Z'))).toBeNull()
  })

  it('ignora las versiones que no están publicadas', () => {
    const anulada = version(3, '2026-10-01T00:00:00Z', null, 'ANULADA')
    expect(versionVigente([anulada], new Date('2026-10-30T00:00:00Z'))).toBeNull()
  })

  // El bootstrap manda el estado DERIVADO del servidor (VIGENTE / PROGRAMADA / HISTORICA), no
  // 'PUBLICADA': todas son publicadas y no anuladas. Si el cliente exigiera 'PUBLICADA', ninguna
  // presentación tendría precio (observación 2 de la prueba manual 20.2).
  it.each(['VIGENTE', 'PROGRAMADA', 'HISTORICA'])(
    'acepta una versión que el servidor marca como %s',
    (estado) => {
      const v = version(1, '2026-10-01T00:00:00Z', null, estado)
      expect(versionVigente([v], new Date('2026-10-05T00:00:00Z'))?.id).toBe('v1')
    },
  )

  it('ignora los borradores', () => {
    const borrador = version(4, '2026-10-01T00:00:00Z', null, 'BORRADOR')
    expect(versionVigente([borrador], new Date('2026-10-30T00:00:00Z'))).toBeNull()
  })

  it('con vigencias superpuestas toma la de mayor número', () => {
    const a = version(1, '2026-10-01T00:00:00Z', null)
    const b = version(2, '2026-10-02T00:00:00Z', null)
    expect(versionVigente([b, a], new Date('2026-10-05T00:00:00Z'))?.id).toBe('v2')
  })
})

describe('precio por presentación con el motor compartido (PRC-22, INV-03)', () => {
  const precio: PrecioLocal = {
    version_id: 'v1',
    producto_id: 'p',
    precio_referencia: '48000.00',
    unidades_referencia: 6,
  }

  it('caja de 6 a 48000.00 es 48000.00 y la unidad es 8000.00', () => {
    expect(precioDePresentacion(precio, 6)).toBe('48000.00')
    expect(precioDePresentacion(precio, 1)).toBe('8000.00')
  })

  it('no inventa decimales binarios: 1/3 de 100.00 redondea half-up a dos decimales', () => {
    const p: PrecioLocal = { ...precio, precio_referencia: '100.00', unidades_referencia: 3 }
    expect(precioDePresentacion(p, 1)).toBe('33.33')
    expect(precioDePresentacion({ ...p, precio_referencia: '4300.00' }, 1)).toBe('1433.33')
  })

  it('producto sin precio en la versión: null', () => {
    expect(precioDePresentacion(undefined, 1)).toBeNull()
  })
})

function cliente(parcial: Partial<ClienteLocal> & { nombre: string }): ClienteLocal {
  return {
    id: parcial.nombre,
    codigo: null,
    razon_social: null,
    documento_tipo: null,
    documento_numero: null,
    direccion: '',
    telefono: null,
    estado: 'ACTIVO',
    lista_precio_id: null,
    es_consumidor_final: false,
    en_cartera: false,
    saldo: '0.00',
    credito: { limite: null, politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null },
    ...parcial,
  }
}

describe('lista de clientes: cartera y consumidor final primero, búsqueda en todos (01 §19)', () => {
  const lista = [
    cliente({ nombre: 'Zeta', en_cartera: true, codigo: 'C9' }),
    cliente({ nombre: 'Árbol' }),
    cliente({ nombre: 'Consumidor final', es_consumidor_final: true }),
    cliente({ nombre: 'Beta', en_cartera: true, documento_numero: '20-12345678-9' }),
    cliente({ nombre: 'Carlos', razon_social: 'Distri Norte', codigo: 'C5' }),
  ]

  it('sin búsqueda: consumidor final, luego cartera, luego el resto, cada grupo por nombre', () => {
    expect(filtrarYOrdenarClientes(lista, '').map((c) => c.nombre)).toEqual([
      'Consumidor final',
      'Beta',
      'Zeta',
      'Árbol',
      'Carlos',
    ])
  })

  it('busca por nombre sin distinguir mayúsculas ni tildes, también fuera de la cartera', () => {
    expect(filtrarYOrdenarClientes(lista, 'arbol').map((c) => c.nombre)).toEqual(['Árbol'])
  })

  it('busca por código y por documento (con o sin guiones)', () => {
    expect(filtrarYOrdenarClientes(lista, 'c5').map((c) => c.nombre)).toEqual(['Carlos'])
    expect(filtrarYOrdenarClientes(lista, '12345678').map((c) => c.nombre)).toEqual(['Beta'])
    expect(filtrarYOrdenarClientes(lista, '20123456789').map((c) => c.nombre)).toEqual(['Beta'])
  })

  it('busca en la razón social y devuelve vacío si nada coincide', () => {
    expect(filtrarYOrdenarClientes(lista, 'norte').map((c) => c.nombre)).toEqual(['Carlos'])
    expect(filtrarYOrdenarClientes(lista, 'zzz')).toEqual([])
  })
})

describe('disponible de crédito = límite - saldo (INV-03)', () => {
  it('resta exacto sin pasar por number', () => {
    expect(disponibleDeCredito('10000.00', '1500.50')).toBe('8499.50')
    expect(disponibleDeCredito('0.30', '0.10')).toBe('0.20')
  })

  it('sin límite devuelve null', () => {
    expect(disponibleDeCredito(null, '500.00')).toBeNull()
  })

  it('puede ser negativo cuando el saldo supera el límite', () => {
    expect(disponibleDeCredito('1000.00', '1200.00')).toBe('-200.00')
  })
})

describe('stock en cajas y unidades (INV-04)', () => {
  it('20 unidades base con cajas de 6 son 3 cajas y 2 unidades', () => {
    expect(stockEnCajasYUnidades(20, 6)).toEqual({ cajas: 3, unidades: 2 })
  })

  it('múltiplo exacto y menos que una caja', () => {
    expect(stockEnCajasYUnidades(12, 6)).toEqual({ cajas: 2, unidades: 0 })
    expect(stockEnCajasYUnidades(5, 6)).toEqual({ cajas: 0, unidades: 5 })
  })

  it('sin caja de más de una unidad todo son unidades', () => {
    expect(stockEnCajasYUnidades(7, 1)).toEqual({ cajas: 0, unidades: 7 })
  })
})
