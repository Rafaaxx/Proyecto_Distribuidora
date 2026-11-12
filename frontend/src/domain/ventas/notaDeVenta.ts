/**
 * Contenido de la nota de venta (change 20, tareas 1.2 a 1.4; VTA-13, VTA-02, VTA-04, CAT-08,
 * PRC-22, CLI-03, CRE-02, ADR-008, ADR-045, ADR-058, ADR-059; `design.md` D1, D4, D5, D7, D12, D14).
 *
 * Función pura sin pdfmake ni React: recibe un tipo neutro con los valores congelados de la venta
 * (lo arma un adaptador desde la API, y el 22a lo hará desde Dexie) y devuelve el contenido ya
 * formateado. Los importes son `decimal.js` desde `lib/money.ts`; ninguno pasa por `number`.
 */

import { formatearFechaHoraEnZona } from '../../lib/fecha'
import { formatearPorcentaje, parsearImporteDesdeApi, redondearImporte, type Importe } from '../../lib/money'
import { formatearMonto } from '../cuentas-corrientes/presentacion'
import { calcularBrutoDelPedido } from './calculoDeVenta'
import { textoDeCantidadDeLinea } from './presentacion'

/** Nombre y leyenda de ADR-008 (`design.md` D12): un solo lugar. */
export const TITULO_DE_NOTA = 'Nota de venta'
export const LEYENDA_DE_NOTA = 'Documento no válido como factura'

export interface OrganizacionDeNota {
  nombre: string
  cuit: string | null
  domicilio: string | null
  telefono: string | null
}

export interface ClienteDeNota {
  nombre: string
  razon_social: string | null
  documento_tipo: string | null
  documento_numero: string | null
  direccion: string | null
  es_consumidor_final: boolean
}

export interface LineaDeNota {
  producto_nombre: string
  presentacion_nombre: string | null
  cantidad: number
  unidades_presentacion: number
  precio_referencia: string
  unidades_referencia: number
  importe_bruto: string
  importe_descuento: string
  importe_neto: string
  alicuota: string
  importe_iva: string
}

export interface MedioDeNota {
  nombre: string
  importe: string
}

export interface CobranzaDeNota {
  importe: string
  medios: readonly MedioDeNota[]
}

export interface AnulacionDeNota {
  anulada_en: string
  motivo_nombre: string
  devuelve_dinero: boolean
}

export interface DatosDeNotaDeVenta {
  organizacion: OrganizacionDeNota
  zona_horaria: string
  muestra_saldo: boolean
  cliente: ClienteDeNota
  numero: string
  occurred_at: string
  vendedor_nombre: string
  modo_impositivo: 'A' | 'B' | 'C'
  estado: string
  lineas: readonly LineaDeNota[]
  total_neto: string
  total_iva: string
  total: string
  cobranza: CobranzaDeNota | null
  /** Saldo de la cuenta después de la venta (CRE-02), calculado por quien arma los datos; nulo si no corresponde. */
  saldo_resultante: string | null
  anulacion: AnulacionDeNota | null
}

export interface LineaDeContenido {
  cantidad: string
  producto: string
  precio: string
  bruto: string
  descuento: string
  importe: string
}

export interface TotalDeContenido {
  rotulo: string
  valor: string
  destacado: boolean
}

export interface ContenidoDeNota {
  titulo: string
  numero: string
  fechaHora: string
  vendedor: string
  organizacion: { nombre: string; renglones: string[] }
  cliente: { nombre: string; renglones: string[] }
  columnas: readonly string[]
  lineas: LineaDeContenido[]
  totales: TotalDeContenido[]
  cobranza: { rotulo: string; total: string | null; medios: { nombre: string; importe: string }[] }
  saldo: { rotulo: string; valor: string } | null
  anulacion: { marca: string; renglones: string[] } | null
  leyenda: string
}

const COLUMNAS_DE_NOTA = ['Cantidad', 'Producto', 'Precio', 'Bruto', 'Descuento', 'Importe'] as const

function sumar(valores: readonly string[]): Importe {
  return redondearImporte(valores.reduce((acumulado, valor) => acumulado.add(parsearImporteDesdeApi(valor)), parsearImporteDesdeApi('0')))
}

function renglonesDeCliente(cliente: ClienteDeNota): string[] {
  if (cliente.es_consumidor_final) return []
  const documento =
    cliente.documento_numero === null ? null : [cliente.documento_tipo, cliente.documento_numero].filter((parte) => parte !== null).join(' ')
  return [cliente.razon_social, documento, cliente.direccion].filter((renglon): renglon is string => renglon !== null)
}

function renglonesDeOrganizacion(organizacion: OrganizacionDeNota): string[] {
  return [
    organizacion.cuit === null ? null : `CUIT ${organizacion.cuit}`,
    organizacion.domicilio,
    organizacion.telefono === null ? null : `Tel. ${organizacion.telefono}`,
  ].filter((renglon): renglon is string => renglon !== null)
}

function lineaDeContenido(linea: LineaDeNota): LineaDeContenido {
  const presentacion = linea.presentacion_nombre
  const descuento = parsearImporteDesdeApi(linea.importe_descuento)
  return {
    cantidad: textoDeCantidadDeLinea({
      cantidad: linea.cantidad,
      presentacion_nombre: presentacion,
      cantidad_base: linea.cantidad * linea.unidades_presentacion,
    }),
    producto: presentacion === null ? linea.producto_nombre : `${linea.producto_nombre} · ${presentacion}`,
    precio: formatearMonto(
      calcularBrutoDelPedido(linea.precio_referencia, linea.unidades_referencia, linea.unidades_presentacion).toFixed(2),
    ),
    bruto: formatearMonto(linea.importe_bruto),
    descuento: descuento.isZero() ? '' : formatearMonto(linea.importe_descuento),
    importe: formatearMonto(linea.importe_neto),
  }
}

/** La venta es de modo C (IVA incluido): su nota es deuda de la etapa 4 (`design.md` D14, Q1, Q2). */
export class NotaNoDisponibleParaModoC extends Error {
  readonly codigo = 'NOTA_MODO_C_NO_DISPONIBLE'

  constructor() {
    super('La nota de venta todavía no está disponible para ventas con IVA incluido (modo C).')
    this.name = 'NotaNoDisponibleParaModoC'
  }
}

/** Alícuota congelada (fracción `numeric(9,6)`) como porcentaje: `"0.210000"` -> `"21 %"`. */
export function formatearAlicuota(fraccion: string): string {
  return formatearPorcentaje(parsearImporteDesdeApi(fraccion))
}

/** Modo B: una fila por alícuota presente, de mayor a menor, con la suma de los IVA de línea congelados. */
function filasDeIvaPorAlicuota(lineas: readonly LineaDeNota[]): TotalDeContenido[] {
  const porAlicuota = new Map<string, { alicuota: Importe; iva: Importe }>()
  for (const linea of lineas) {
    const alicuota = parsearImporteDesdeApi(linea.alicuota)
    const clave = alicuota.toFixed(6)
    const actual = porAlicuota.get(clave)
    const iva = parsearImporteDesdeApi(linea.importe_iva)
    porAlicuota.set(clave, { alicuota, iva: actual === undefined ? iva : actual.iva.add(iva) })
  }
  return [...porAlicuota.values()]
    .sort((a, b) => b.alicuota.comparedTo(a.alicuota))
    .map(({ alicuota, iva }) => ({
      rotulo: `IVA ${formatearPorcentaje(alicuota)}`,
      valor: formatearMonto(redondearImporte(iva).toFixed(2)),
      destacado: false,
    }))
}

const MARCA_DE_ANULADA = 'ANULADA'

/** D4: lo calcula quien arma los datos (CRE-02); acá solo se decide si se imprime y con qué rótulo. */
function saldoDeContenido(datos: DatosDeNotaDeVenta): ContenidoDeNota['saldo'] {
  if (!datos.muestra_saldo || datos.cliente.es_consumidor_final || datos.estado === 'ANULADA' || datos.saldo_resultante === null) {
    return null
  }
  const saldo = parsearImporteDesdeApi(datos.saldo_resultante)
  if (saldo.isNegative()) {
    return { rotulo: 'Saldo a favor del cliente después de esta venta', valor: formatearMonto(saldo.neg().toFixed(2)) }
  }
  return { rotulo: 'Saldo de la cuenta después de esta venta', valor: formatearMonto(saldo.toFixed(2)) }
}

/** D5: marca visible y constancia de la anulación (VTA-22: destino de lo cobrado). */
function anulacionDeContenido(datos: DatosDeNotaDeVenta): ContenidoDeNota['anulacion'] {
  if (datos.estado !== 'ANULADA') return null
  const anulacion = datos.anulacion
  if (anulacion === null) return { marca: MARCA_DE_ANULADA, renglones: [] }
  const renglones = [
    `Venta anulada el ${formatearFechaHoraEnZona(anulacion.anulada_en, datos.zona_horaria)}. Motivo: ${anulacion.motivo_nombre}.`,
  ]
  if (datos.cobranza !== null) {
    renglones.push(anulacion.devuelve_dinero ? 'Se devolvió lo cobrado.' : 'Lo cobrado quedó a favor del cliente.')
  }
  return { marca: MARCA_DE_ANULADA, renglones }
}

export function armarNotaDeVenta(datos: DatosDeNotaDeVenta): ContenidoDeNota {
  if (datos.modo_impositivo === 'C') throw new NotaNoDisponibleParaModoC()
  const descuentos = sumar(datos.lineas.map((linea) => linea.importe_descuento))
  const totales: TotalDeContenido[] = [
    { rotulo: 'Subtotal', valor: formatearMonto(sumar(datos.lineas.map((linea) => linea.importe_bruto)).toFixed(2)), destacado: false },
  ]
  if (!descuentos.isZero()) totales.push({ rotulo: 'Descuentos', valor: formatearMonto(descuentos.toFixed(2)), destacado: false })
  if (datos.modo_impositivo === 'B') {
    totales.push({ rotulo: 'Neto', valor: formatearMonto(datos.total_neto), destacado: false })
    totales.push(...filasDeIvaPorAlicuota(datos.lineas))
  }
  totales.push({ rotulo: 'Total', valor: formatearMonto(datos.total), destacado: true })

  return {
    titulo: TITULO_DE_NOTA,
    numero: datos.numero,
    fechaHora: formatearFechaHoraEnZona(datos.occurred_at, datos.zona_horaria),
    vendedor: datos.vendedor_nombre,
    organizacion: { nombre: datos.organizacion.nombre, renglones: renglonesDeOrganizacion(datos.organizacion) },
    cliente: { nombre: datos.cliente.nombre, renglones: renglonesDeCliente(datos.cliente) },
    columnas: COLUMNAS_DE_NOTA,
    lineas: datos.lineas.map(lineaDeContenido),
    totales,
    cobranza:
      datos.cobranza === null
        ? { rotulo: 'Sin cobro en el acto', total: null, medios: [] }
        : {
            rotulo: 'Cobrado',
            total: formatearMonto(datos.cobranza.importe),
            medios: datos.cobranza.medios.map((medio) => ({ nombre: medio.nombre, importe: formatearMonto(medio.importe) })),
          },
    saldo: saldoDeContenido(datos),
    anulacion: anulacionDeContenido(datos),
    leyenda: LEYENDA_DE_NOTA,
  }
}

