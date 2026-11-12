/**
 * Formularios de configuración del descuento manual y del crédito por defecto de la organización
 * (change 18b, tarea 14.1; D13, D14; CRE-03, CRE-06, ADR-032). Lógica pura de lo que escribe el
 * usuario: la tolerancia (tipo + valor, juntos o los dos vacíos) como la espera el servidor. El
 * servidor valida igual (TR-10). Los importes nunca pasan por `number` (INV-03).
 */

import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

export const POLITICAS_DE_CREDITO = ['ADVERTIR', 'AUTORIZAR', 'BLOQUEAR'] as const
export type PoliticaDeCredito = (typeof POLITICAS_DE_CREDITO)[number]

export const ETIQUETAS_DE_POLITICA: Record<PoliticaDeCredito, string> = {
  ADVERTIR: 'Advertir: avisa y deja confirmar',
  AUTORIZAR: 'Autorizar: pide permiso o PIN de un supervisor',
  BLOQUEAR: 'Bloquear: no deja confirmar',
}

/** Lo que se elige en el formulario: sin tolerancia, un importe o un porcentaje del límite. */
export type TipoDeToleranciaElegido = '' | 'IMPORTE' | 'PORCENTAJE'

export const ETIQUETAS_DE_TIPO_DE_TOLERANCIA: Record<TipoDeToleranciaElegido, string> = {
  '': 'Sin tolerancia',
  IMPORTE: 'Importe en pesos',
  PORCENTAJE: 'Porcentaje del límite',
}

export interface ToleranciaDelFormulario {
  tipo: TipoDeToleranciaElegido
  /** Lo que escribió el usuario (`"20000"`, `"2,5"`). */
  valor: string
}

export type ResultadoDeTolerancia =
  | { valida: true; tipo: 'IMPORTE' | 'PORCENTAJE' | null; valor: string | null }
  | { valida: false; mensaje: string }

const NUMERO_ESCRITO = /^\d+([.,]\d{1,2})?$/
const MENSAJE_DE_VALOR = 'Ingresá un valor de cero o más, con hasta dos decimales.'

/**
 * La tolerancia como la recibe el servidor: tipo y valor juntos, o los dos nulos (CRE-06). El
 * porcentaje se escribe en puntos (`2,5` = 2,50 % del límite) y no puede pasar de 100.
 */
export function leerTolerancia(formulario: ToleranciaDelFormulario): ResultadoDeTolerancia {
  if (formulario.tipo === '') return { valida: true, tipo: null, valor: null }
  const escrito = formulario.valor.trim()
  if (!NUMERO_ESCRITO.test(escrito)) return { valida: false, mensaje: MENSAJE_DE_VALOR }
  const valor = redondearImporte(parsearImporteDesdeApi(escrito.replace(',', '.')))
  if (formulario.tipo === 'PORCENTAJE' && valor.greaterThan(100)) {
    return { valida: false, mensaje: 'El porcentaje del límite no puede pasar de 100.' }
  }
  return { valida: true, tipo: formulario.tipo, valor: valor.toFixed(2) }
}

/** El formulario de la tolerancia a partir de lo que guarda el servidor. */
export function toleranciaParaElFormulario(tipo: string | null, valor: string | null): ToleranciaDelFormulario {
  if ((tipo !== 'IMPORTE' && tipo !== 'PORCENTAJE') || valor === null) return { tipo: '', valor: '' }
  return { tipo, valor: valor.replace('.', ',') }
}
