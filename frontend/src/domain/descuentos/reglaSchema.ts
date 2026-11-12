import { z } from 'zod'

import { aImporte, esDecimalNoNegativo, normalizarDecimal } from '../precios/decimales'
import { construirVigencia, instante } from '../precios/publicacionSchema'
import {
  ACCIONES,
  MEDIDAS,
  OPERADORES,
  TIPOS_ALCANCE,
  TIPOS_REGLA,
  type AccionTipo,
  type Medida,
  type Operador,
  type TipoAlcance,
  type TipoRegla,
} from './tipos'

/**
 * Validación del formulario de regla de descuento (change 16, tarea 14.1; DSC-01 a DSC-04,
 * TR-01, TR-02, INV-03, INV-04; `design.md` D5, D8, D16). Mismas reglas que
 * `backend/app/modules/descuentos/domain/reglas.py`, solo para avisar antes de enviar: el
 * servidor valida igual. La persona escribe el porcentaje como porcentaje (`12,5`); el comando
 * lleva la fracción de seis decimales como cadena (`"0.125000"`). Nada pasa por `number` salvo la
 * prioridad, que es un entero sin dinero.
 */

export { fraccionDesdePorcentaje, porcentajeDesdeFraccion } from '../precios/reglaSchema'
import { fraccionDesdePorcentaje } from '../precios/reglaSchema'

const DECIMALES_DE_PORCENTAJE = 4
const PRIORIDAD_MAXIMA = 2147483647
const UMBRAL_MAXIMO = '10000000000'
const IMPORTE_MAXIMO = '1000000000000'

const DECIMALES_DE_UMBRAL: Record<string, number> = { CAJAS_EQUIVALENTES: 4, IMPORTE_BRUTO: 2 }

export interface AlcanceDeFormulario {
  tipo: string
  entidad_id: string
}

export interface DatosReglaDescuentoEntrada {
  nombre: string
  tipo: string
  medida: string
  operador: string
  umbral: string
  accion_tipo: string
  accion_valor: string
  prioridad: string
  acumulable: boolean
  alcances: AlcanceDeFormulario[]
  vigencia_desde: string
  vigencia_hasta: string
}

/** El contenido del comando `REGLA_DESCUENTO_CREAR` / `MODIFICAR` (un borrador se reemplaza completo). */
export interface ComandoDeRegla {
  nombre: string
  tipo: TipoRegla
  medida: Medida
  operador: Operador
  umbral: string
  accion_tipo: AccionTipo
  accion_valor: string
  prioridad: number
  acumulable: boolean
  alcances: { tipo: TipoAlcance; entidad_id: string }[]
  vigencia_desde: string | null
  vigencia_hasta: string | null
}

function enumDe(valores: readonly string[], mensaje: string) {
  return z.string().refine((valor) => valores.includes(valor), { message: mensaje })
}

const esquemaBase = z.object({
  nombre: z.string().transform((valor) => valor.trim()),
  tipo: enumDe(TIPOS_REGLA, 'Elegí sobre qué se mide la regla.'),
  medida: enumDe(MEDIDAS, 'Elegí qué se mide.'),
  operador: enumDe(OPERADORES, 'Elegí el operador.'),
  umbral: z.string().transform(normalizarDecimal),
  accion_tipo: enumDe(ACCIONES, 'Elegí la acción.'),
  accion_valor: z.string().transform(normalizarDecimal),
  prioridad: z.string().transform((valor) => valor.trim()),
  acumulable: z.boolean(),
  alcances: z.array(z.object({ tipo: z.string(), entidad_id: z.string() })),
  vigencia_desde: z.string(),
  vigencia_hasta: z.string(),
})

type Base = z.output<typeof esquemaBase>

function mensajeDeUmbral(medida: string): string {
  if (medida === 'UNIDADES_BASE') return 'En unidades base el umbral es un entero mayor que cero, sin decimales.'
  if (medida === 'IMPORTE_BRUTO') return 'Ingresá un importe mayor que cero, con hasta dos decimales.'
  return 'Ingresá una cantidad de cajas mayor que cero, con hasta cuatro decimales.'
}

function umbralValido(medida: string, umbral: string): boolean {
  const decimales = medida === 'UNIDADES_BASE' ? 0 : (DECIMALES_DE_UMBRAL[medida] ?? 4)
  const formato = decimales === 0 ? /^\d+$/.test(umbral) : esDecimalNoNegativo(umbral, decimales)
  return formato && aImporte(umbral).gt(0) && aImporte(umbral).lt(UMBRAL_MAXIMO)
}

function accionValida(accionTipo: string, valor: string): boolean {
  if (accionTipo === 'PORCENTAJE') {
    return esDecimalNoNegativo(valor, DECIMALES_DE_PORCENTAJE) && aImporte(valor).gt(0) && aImporte(valor).lte(100)
  }
  return esDecimalNoNegativo(valor, 2) && aImporte(valor).gt(0) && aImporte(valor).lt(IMPORTE_MAXIMO)
}

function prioridadValida(prioridad: string): boolean {
  return /^\d{1,10}$/.test(prioridad) && Number(prioridad) >= 1 && Number(prioridad) <= PRIORIDAD_MAXIMA
}

function validarAlcances(datos: Base, agregar: (campo: string, mensaje: string) => void): void {
  if (datos.tipo === 'VOLUMEN_OPERACION') {
    if (datos.alcances.length > 0) agregar('alcances', 'Una regla sobre toda la venta no lleva alcances.')
    return
  }
  if (datos.alcances.length === 0) {
    agregar('alcances', 'Elegí al menos un producto, una categoría o una marca.')
    return
  }
  const vistos = new Set<string>()
  for (const alcance of datos.alcances) {
    if (!TIPOS_ALCANCE.includes(alcance.tipo) || alcance.entidad_id === '') {
      agregar('alcances', 'Elegí a qué se aplica cada alcance.')
      return
    }
    const clave = `${alcance.tipo}:${alcance.entidad_id}`
    if (vistos.has(clave)) {
      agregar('alcances', 'Un alcance está repetido.')
      return
    }
    vistos.add(clave)
  }
}

function validarVigencia(datos: Base, agregar: (campo: string, mensaje: string) => void): void {
  const desde = instante(datos.vigencia_desde)
  const hasta = instante(datos.vigencia_hasta)
  if (datos.vigencia_desde !== '' && desde === null) agregar('vigencia_desde', 'Ingresá una fecha válida.')
  if (datos.vigencia_hasta !== '' && hasta === null) {
    agregar('vigencia_hasta', 'Ingresá una fecha válida.')
    return
  }
  if (desde !== null && hasta !== null && hasta.getTime() <= desde.getTime()) {
    agregar('vigencia_hasta', 'La vigencia hasta debe ser posterior a la vigencia desde.')
  }
}

export const esquemaReglaDescuento = esquemaBase
  .superRefine((datos, contexto) => {
    const agregar = (campo: string, message: string) => contexto.addIssue({ code: 'custom', path: [campo], message })
    if (datos.nombre === '') agregar('nombre', 'Ingresá un nombre para la regla.')
    if (!umbralValido(datos.medida, datos.umbral)) agregar('umbral', mensajeDeUmbral(datos.medida))
    if (!accionValida(datos.accion_tipo, datos.accion_valor)) {
      agregar(
        'accion_valor',
        datos.accion_tipo === 'PORCENTAJE'
          ? 'Ingresá un porcentaje mayor que cero y hasta 100, con hasta cuatro decimales.'
          : 'Ingresá un importe mayor que cero, con hasta dos decimales.',
      )
    }
    if (!prioridadValida(datos.prioridad)) agregar('prioridad', 'La prioridad es un entero desde 1.')
    validarAlcances(datos, agregar)
    validarVigencia(datos, agregar)
  })
  .transform((datos): ComandoDeRegla => ({
    nombre: datos.nombre,
    tipo: datos.tipo as TipoRegla,
    medida: datos.medida as Medida,
    operador: datos.operador as Operador,
    umbral: datos.umbral,
    accion_tipo: datos.accion_tipo as AccionTipo,
    accion_valor: datos.accion_tipo === 'PORCENTAJE' ? fraccionDesdePorcentaje(datos.accion_valor) : datos.accion_valor,
    prioridad: Number(datos.prioridad),
    acumulable: datos.acumulable,
    alcances: datos.alcances.map((a) => ({ tipo: a.tipo as TipoAlcance, entidad_id: a.entidad_id })),
    ...construirVigencia({ vigencia_desde: datos.vigencia_desde, vigencia_hasta: datos.vigencia_hasta }),
  }))

export type DatosReglaDescuento = ComandoDeRegla
