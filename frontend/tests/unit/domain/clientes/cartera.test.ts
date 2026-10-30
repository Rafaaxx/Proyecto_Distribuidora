/**
 * Change 20b, tarea 10.3 (D13, D14, D15; spec `clientes/cartera-de-clientes`; `01` §19, CLI-03):
 * reglas puras de las pantallas de cartera. Solo UX: el servidor valida igual (`VENDEDOR_INVALIDO`).
 */

import { describe, expect, it } from 'vitest'

import {
  etiquetaDeVendedor,
  filtrarVendedores,
  mensajeDeErrorDeClientes,
  puedeAsignarse,
} from '../../../../src/domain/clientes/cartera'

describe('etiquetaDeVendedor (D6, D15)', () => {
  it('sin vendedor', () => {
    expect(etiquetaDeVendedor({ vendedor_id: null })).toEqual({ texto: 'Sin vendedor', paraReasignar: false })
  })

  it('con vendedor válido muestra el nombre', () => {
    expect(etiquetaDeVendedor({ vendedor_id: 'u1', vendedor_nombre: 'Ana', vendedor_valido: true })).toEqual({
      texto: 'Ana',
      paraReasignar: false,
    })
  })

  it('con vendedor de baja o sin permiso lo marca para reasignar', () => {
    expect(etiquetaDeVendedor({ vendedor_id: 'u2', vendedor_nombre: 'Beto', vendedor_valido: false })).toEqual({
      texto: 'Beto (de baja o sin permiso)',
      paraReasignar: true,
    })
  })

  it('sin dato de validez no marca nada', () => {
    expect(etiquetaDeVendedor({ vendedor_id: 'u1', vendedor_nombre: 'Ana' }).paraReasignar).toBe(false)
  })
})

describe('puedeAsignarse (CLI-03, D15)', () => {
  it('el consumidor final no se asigna', () => {
    expect(puedeAsignarse({ es_consumidor_final: true })).toBe(false)
    expect(puedeAsignarse({ es_consumidor_final: false })).toBe(true)
  })
})

describe('mensajeDeErrorDeClientes (D15)', () => {
  it.each(['VENDEDOR_INVALIDO', 'CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR', 'PERMISO_REQUERIDO', 'RECURSO_NO_ENCONTRADO'])(
    'explica %s en palabras simples',
    (codigo) => {
      const mensaje = mensajeDeErrorDeClientes(codigo, 'texto del servidor')

      expect(mensaje).not.toBe('texto del servidor')
      expect(mensaje).not.toContain('_')
    },
  )

  it('conserva el mensaje del servidor con otro código o sin código', () => {
    expect(mensajeDeErrorDeClientes('OTRO', 'texto del servidor')).toBe('texto del servidor')
    expect(mensajeDeErrorDeClientes(null, 'texto del servidor')).toBe('texto del servidor')
  })
})

describe('filtrarVendedores (buscador por nombre, change 20b)', () => {
  const LISTA = [
    { id: 'u1', nombre: 'José Pérez' },
    { id: 'u2', nombre: 'Ana Gómez' },
    { id: 'u3', nombre: 'Beto Núñez' },
  ]

  it('sin texto (o solo espacios) devuelve toda la lista', () => {
    expect(filtrarVendedores(LISTA, '')).toEqual(LISTA)
    expect(filtrarVendedores(LISTA, '   ')).toEqual(LISTA)
  })

  it('ignora mayúsculas y acentos en ambos sentidos', () => {
    expect(filtrarVendedores(LISTA, 'JOSE').map((v) => v.id)).toEqual(['u1'])
    expect(filtrarVendedores(LISTA, 'gómez').map((v) => v.id)).toEqual(['u2'])
    expect(filtrarVendedores(LISTA, 'nunez').map((v) => v.id)).toEqual(['u3'])
  })

  it('busca en cualquier parte del nombre y devuelve vacío si nada coincide', () => {
    expect(filtrarVendedores(LISTA, 'ez').map((v) => v.id)).toEqual(['u1', 'u2', 'u3'])
    expect(filtrarVendedores(LISTA, 'zzz')).toEqual([])
  })

  it('conserva al vendedor ya elegido aunque no coincida', () => {
    expect(filtrarVendedores(LISTA, 'ana', 'u3').map((v) => v.id)).toEqual(['u2', 'u3'])
  })
})
