/**
 * Lógica pura del formulario de "Nueva venta" (change 18a, tarea 12.1; `design.md` D2, D3, D4,
 * D6, D8, D12; spec `administracion-de-ventas`). Nada de esto vive en los componentes
 * (`CLAUDE.md` §5). Los importes nunca pasan por `number` (INV-03). El servidor valida igual
 * (TR-10); esto es UX.
 */

import { z } from 'zod'

import type { components } from '../../api/schema.gen'
import { redondearImporte } from '../../lib/money'
import { esImporteValido, type MedioDePagoDeFormulario } from '../pagos-proveedores/formularioPago'
import type { DescuentoDeLinea } from './descuentosDeVenta'

const MAXIMO_DE_LINEAS = 200
const MAXIMO_DE_MEDIOS = 20
const MAXIMO_DE_OBSERVACION = 500
const PATRON_DE_NUMERO = /^.+-\d{6,}$/

/** La venta tal como la edita el usuario: todo texto. Las líneas se arman aparte (cajas + unidades). */
export interface FormularioDeVenta {
  clienteId: string
  /** Vacío cuando la venta va a la ubicación de la jornada abierta (D3). */
  ubicacionId: string
  numero: string
  /** Vacíos mientras se usa la lista y la versión que corresponden al cliente (D6). */
  listaId: string
  versionId: string
  motivoId: string
  observacionCobranza: string
  /** Vacío = sin cobranza en el acto. */
  medios: MedioDePagoDeFormulario[]
}

/** Una línea con lo que vio el usuario (D2): se envía como valores esperados. */
export interface LineaDelPedido {
  lineaId: string
  productoId: string
  presentacionId: string
  cantidad: number
  listaVersionId: string
  precioReferencia: string
  unidadesReferencia: number
  importeBruto: string
}

export interface ContextoDeVenta {
  /** Ids de los medios de pago que exigen referencia (`requiere_referencia`). */
  mediosQueRequierenReferencia: ReadonlySet<string>
  /** Falso cuando hay jornada abierta: la ubicación es la de la jornada (D3). */
  ubicacionObligatoria: boolean
}

export type VentaConfirmarDatos = components['schemas']['VentaConfirmarRequest']

/**
 * Esquema Zod del formulario: cliente, ubicación (si no hay jornada), número `PPP-NNNNNN`,
 * de 1 a 200 líneas y de 0 a 20 medios con importe positivo de dos decimales como máximo y
 * referencia donde el medio la exige. La cantidad de líneas entra como dato aparte porque las
 * líneas no son campos del formulario.
 */
export function crearEsquemaDeVenta(contexto: ContextoDeVenta) {
  const medio = z
    .object({
      medioPagoId: z.string().min(1, 'Elegí un medio de pago.'),
      importe: z.string().refine(esImporteValido, 'Ingresá un importe mayor que cero, con hasta dos decimales.'),
      referencia: z.string(),
    })
    .refine((m) => !contexto.mediosQueRequierenReferencia.has(m.medioPagoId) || m.referencia.trim() !== '', {
      path: ['referencia'],
      message: 'La referencia es obligatoria para este medio de pago.',
    })

  return z.object({
    clienteId: z.string().min(1, 'Elegí un cliente.'),
    ubicacionId: contexto.ubicacionObligatoria ? z.string().min(1, 'Elegí la ubicación.') : z.string(),
    numero: z.string().regex(PATRON_DE_NUMERO, 'El número tiene que ser como V01-000042.'),
    listaId: z.string(),
    versionId: z.string(),
    motivoId: z.string(),
    observacionCobranza: z.string().max(MAXIMO_DE_OBSERVACION, 'La observación admite hasta 500 caracteres.'),
    medios: z.array(medio).max(MAXIMO_DE_MEDIOS, 'Una cobranza admite hasta 20 medios.'),
    cantidadDeLineas: z
      .number()
      .int()
      .min(1, 'Cargá al menos un producto.')
      .max(MAXIMO_DE_LINEAS, 'Una venta admite hasta 200 líneas.'),
  })
}

/** El esquema pasa con estas líneas. */
export function puedeConfirmarVenta(
  formulario: FormularioDeVenta,
  lineas: readonly LineaDelPedido[],
  contexto: ContextoDeVenta,
): boolean {
  return crearEsquemaDeVenta(contexto).safeParse({ ...formulario, cantidadDeLineas: lineas.length }).success
}

function textoONulo(texto: string): string | null {
  const recortado = texto.trim()
  return recortado === '' ? null : recortado
}

/** Descuentos y crédito que se suman al cuerpo de la venta (change 18b, D1); todo opcional. */
export interface DescuentosYCreditoDeVenta {
  /** Fracción de texto o nulo. */
  descuentoGeneral: string | null
  /** Solo si hay descuento manual. */
  motivoDescuentoId: string | null
  descuentoAutorizadorId: string | null
  /** ADVERTIR: el usuario aceptó vender con exceso (CRE-04). */
  aceptaExceso: boolean
  /** AUTORIZAR: el supervisor del crédito (CRE-05). */
  creditoAutorizadorId: string | null
  /** Por línea: su porcentaje propio y los descuentos que vio el usuario (DSC-09). */
  porLinea: ReadonlyMap<string, { propio: string | null; descuentos: readonly DescuentoDeLinea[] }>
}

function credito(extras: DescuentosYCreditoDeVenta): VentaConfirmarDatos['credito'] {
  if (!extras.aceptaExceso && extras.creditoAutorizadorId === null) return undefined
  return {
    acepta_exceso: extras.aceptaExceso,
    ...(extras.creditoAutorizadorId === null ? {} : { autorizador_id: extras.creditoAutorizadorId }),
  }
}

/**
 * Cuerpo de `VENTA_CONFIRMAR` (`POST /ventas`): lo que el usuario vio (D2). `ubicacion_id` va
 * solo si no hay jornada abierta (D3); lista, versión y motivo, solo si se eligió otra (D6).
 */
export function construirSolicitudDeVenta(
  formulario: FormularioDeVenta,
  lineas: readonly LineaDelPedido[],
  total: string,
  ventaId: string,
  cobranzaId: string,
  enviarUbicacion: boolean,
  extras?: DescuentosYCreditoDeVenta,
): VentaConfirmarDatos {
  const cuerpo: VentaConfirmarDatos = {
    venta_id: ventaId,
    numero: formulario.numero.trim(),
    cliente_id: formulario.clienteId,
    ubicacion_id: enviarUbicacion ? textoONulo(formulario.ubicacionId) : null,
    lista_id: textoONulo(formulario.listaId),
    lista_version_id: textoONulo(formulario.versionId),
    motivo_lista_id: textoONulo(formulario.motivoId),
    lineas: lineas.map((linea) => ({
      linea_id: linea.lineaId,
      producto_id: linea.productoId,
      presentacion_id: linea.presentacionId,
      cantidad: linea.cantidad,
      lista_version_id: linea.listaVersionId,
      precio_referencia: linea.precioReferencia,
      unidades_referencia: linea.unidadesReferencia,
      importe_bruto: linea.importeBruto,
    })),
    total,
    cobranza:
      formulario.medios.length === 0
        ? null
        : {
            cobranza_id: cobranzaId,
            observacion: textoONulo(formulario.observacionCobranza),
            medios: formulario.medios.map((medio) => ({
              medio_pago_id: medio.medioPagoId,
              importe: redondearImporte(medio.importe.trim()).toFixed(2),
              referencia: textoONulo(medio.referencia),
            })),
          },
  }
  if (extras === undefined) return cuerpo
  const cabecera = credito(extras)
  return {
    ...cuerpo,
    ...(extras.descuentoGeneral === null ? {} : { descuento_manual_general: extras.descuentoGeneral }),
    ...(extras.motivoDescuentoId === null ? {} : { motivo_descuento_id: extras.motivoDescuentoId }),
    ...(extras.descuentoAutorizadorId === null ? {} : { descuento_autorizador_id: extras.descuentoAutorizadorId }),
    ...(cabecera === undefined ? {} : { credito: cabecera }),
    lineas: cuerpo.lineas.map((linea) => {
      const delPedido = extras.porLinea.get(linea.linea_id)
      if (delPedido === undefined) return linea
      return {
        ...linea,
        ...(delPedido.propio === null ? {} : { descuento_manual: delPedido.propio }),
        ...(delPedido.descuentos.length === 0
          ? {}
          : {
              descuentos: delPedido.descuentos.map((d) => ({
                origen: d.origen,
                regla_id: d.reglaId,
                porcentaje: d.porcentaje,
                importe: d.importe,
              })),
            }),
      }
    }),
  }
}

/** Valores de una línea tal como los resuelve el servidor (detalle de `PRECIO_DIFIERE`). */
export interface ValoresDelServidorDeLinea {
  linea_id: string
  lista_version_id: string
  precio_referencia: string
  unidades_referencia: number
  importe_bruto: string
}

export interface ValoresDelServidor {
  lineas: readonly ValoresDelServidorDeLinea[]
  total: string
}

/**
 * Reemplaza los valores esperados de cada línea por los del servidor, buscándola por
 * identificador (D2: no por posición). Una línea que el servidor no menciona queda como estaba.
 */
export function aplicarValoresDelServidor(
  lineas: readonly LineaDelPedido[],
  valores: ValoresDelServidor,
): { lineas: LineaDelPedido[]; total: string } {
  const porLinea = new Map(valores.lineas.map((valor) => [valor.linea_id, valor]))
  return {
    total: valores.total,
    lineas: lineas.map((linea) => {
      const valor = porLinea.get(linea.lineaId)
      if (valor === undefined) return linea
      return {
        ...linea,
        listaVersionId: valor.lista_version_id,
        precioReferencia: valor.precio_referencia,
        unidadesReferencia: valor.unidades_referencia,
        importeBruto: valor.importe_bruto,
      }
    }),
  }
}

export interface DiferenciaDeLinea {
  lineaId: string
  precioAnterior: string
  precioNuevo: string
  brutoAnterior: string
  brutoNuevo: string
  /** Cambió el precio, el bruto o la versión de la lista. */
  cambio: boolean
}

/** Por línea enviada, lo que vio el usuario contra lo que resolvió el servidor (para mostrarlo antes de reconfirmar). */
export function diferenciasConElServidor(
  lineas: readonly LineaDelPedido[],
  valores: ValoresDelServidor,
): DiferenciaDeLinea[] {
  const porLinea = new Map(valores.lineas.map((valor) => [valor.linea_id, valor]))
  return lineas.flatMap((linea) => {
    const valor = porLinea.get(linea.lineaId)
    if (valor === undefined) return []
    return [
      {
        lineaId: linea.lineaId,
        precioAnterior: linea.precioReferencia,
        precioNuevo: valor.precio_referencia,
        brutoAnterior: linea.importeBruto,
        brutoNuevo: valor.importe_bruto,
        cambio:
          linea.precioReferencia !== valor.precio_referencia ||
          linea.importeBruto !== valor.importe_bruto ||
          linea.listaVersionId !== valor.lista_version_id,
      },
    ]
  })
}
