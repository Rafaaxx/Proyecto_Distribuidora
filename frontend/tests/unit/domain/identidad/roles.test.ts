import { describe, expect, it } from 'vitest'

import {
  agruparPorModulo,
  diferenciaDePermisos,
  etiquetaDeModulo,
  llegaMasAdelante,
  perdeLaAutorizacion,
  rolConfiereAutorizacion,
  type PermisoDelCatalogo,
} from '../../../../src/domain/identidad/roles'

/**
 * Reglas de la pantalla "Roles y permisos" (change 17b, D9; `01` §19, ADR-011, ADR-053). Dominio
 * puro: el componente solo dibuja lo que esto calcula.
 */

const CATALOGO: PermisoDelCatalogo[] = [
  { codigo: 'ADMIN_USUARIOS', descripcion: 'Usuarios, roles y permisos', modulo: 'identidad' },
  { codigo: 'ADMIN_CONFIGURACION', descripcion: 'Configuración de la organización', modulo: 'identidad' },
  { codigo: 'REGISTRAR_COBRANZA', descripcion: 'Registrar cobranzas', modulo: 'cobranzas' },
  { codigo: 'VENDER', descripcion: 'Confirmar ventas', modulo: 'ventas' },
  { codigo: 'ANULAR_COBRANZA', descripcion: 'Anular cobranzas', modulo: 'cobranzas' },
]

describe('diferenciaDePermisos', () => {
  it('lista lo que agrega y lo que quita, ordenado por el catálogo', () => {
    const resultado = diferenciaDePermisos(['ANULAR_COBRANZA', 'VENDER'], ['VENDER', 'ADMIN_USUARIOS', 'REGISTRAR_COBRANZA'], CATALOGO)

    expect(resultado).toEqual({
      agrega: ['ADMIN_USUARIOS', 'REGISTRAR_COBRANZA'],
      quita: ['ANULAR_COBRANZA'],
    })
  })

  it('sin cambios no agrega ni quita nada', () => {
    expect(diferenciaDePermisos(['VENDER'], ['VENDER'], CATALOGO)).toEqual({ agrega: [], quita: [] })
  })

  it('un código fuera del catálogo se conserva al final, para no esconder un cambio', () => {
    const resultado = diferenciaDePermisos([], ['PERMISO_RARO', 'VENDER'], CATALOGO)

    expect(resultado.agrega).toEqual(['VENDER', 'PERMISO_RARO'])
  })
})

describe('rolConfiereAutorizacion y perdeLaAutorizacion (ADR-011)', () => {
  it.each(['AUTORIZAR_DESCUENTO', 'SUPERAR_CREDITO', 'VENDER_CLIENTE_SUSPENDIDO', 'USAR_LISTA_ANTERIOR'])(
    '%s confiere autorización',
    (codigo) => {
      expect(rolConfiereAutorizacion([codigo])).toBe(true)
    },
  )

  it('sin ninguno de los cuatro no confiere autorización', () => {
    expect(rolConfiereAutorizacion(['VENDER', 'ANULAR_COBRANZA'])).toBe(false)
  })

  it('pierde la autorización solo si tenía alguno y se queda sin ninguno', () => {
    expect(perdeLaAutorizacion(['SUPERAR_CREDITO', 'VENDER'], ['VENDER'])).toBe(true)
    expect(perdeLaAutorizacion(['SUPERAR_CREDITO', 'USAR_LISTA_ANTERIOR'], ['USAR_LISTA_ANTERIOR'])).toBe(false)
    expect(perdeLaAutorizacion(['VENDER'], [])).toBe(false)
  })
})

describe('agruparPorModulo', () => {
  it('agrupa en el orden en que aparece cada módulo en el catálogo, con su etiqueta', () => {
    const grupos = agruparPorModulo(CATALOGO)

    expect(grupos.map((g) => g.modulo)).toEqual(['identidad', 'cobranzas', 'ventas'])
    expect(grupos[1]).toMatchObject({
      etiqueta: 'Cobranzas',
      permisos: [{ codigo: 'REGISTRAR_COBRANZA' }, { codigo: 'ANULAR_COBRANZA' }],
    })
  })

  it('un catálogo vacío no tiene grupos', () => {
    expect(agruparPorModulo([])).toEqual([])
  })
})

describe('etiquetaDeModulo', () => {
  it('traduce los módulos conocidos y pone mayúscula al desconocido', () => {
    expect(etiquetaDeModulo('facturacion')).toBe('Facturación')
    expect(etiquetaDeModulo('identidad')).toBe('Usuarios y organización')
    expect(etiquetaDeModulo('modulo_nuevo')).toBe('Modulo nuevo')
  })
})

describe('llegaMasAdelante', () => {
  it.each(['ventas', 'facturacion', 'reportes'])('el módulo %s todavía no tiene funciones', (modulo) => {
    expect(llegaMasAdelante(modulo)).toBe(true)
  })

  it.each(['cobranzas', 'stock', 'identidad'])('el módulo %s ya existe', (modulo) => {
    expect(llegaMasAdelante(modulo)).toBe(false)
  })
})
