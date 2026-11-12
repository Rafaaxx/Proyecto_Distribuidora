import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { formatearPorcentaje, parsearImporteDesdeApi } from '../../../lib/money'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import { textoDePorcentajeQueRige, type LineaConDescuentos } from '../../../domain/ventas/descuentosDeVenta'
import type { LineaVisible } from '../../../domain/ventas/pedido'
import { textoDeCantidadDeLinea } from '../../../domain/ventas/presentacion'

const CLASE_CANTIDAD = 'w-24 rounded-md border border-border px-2 py-1 text-sm'

export interface ItemDeVentaProps {
  productoId: string
  nombre: string
  cajas: number
  unidades: number
  admiteCajas: boolean
  admiteUnidadesSueltas: boolean
  lineas: readonly LineaVisible[]
  /** Mensaje del producto que no se puede vender como está pedido (sin precio, cantidad inválida). */
  error?: string
  /** Texto de aviso cuando lo pedido supera el stock de la ubicación. */
  avisoDeStock?: string
  /** Texto cuando el precio de este producto todavía no llegó o no se pudo leer. */
  estado?: string
  alCambiarCajas: (cajas: number) => void
  alCambiarUnidades: (unidades: number) => void
  alQuitar: () => void
  /** Descuentos de cada línea del producto, por identificador de línea (change 18b, D20). */
  descuentosPorLinea?: ReadonlyMap<string, LineaConDescuentos>
  /** Nombre de cada regla vigente, por identificador, para rotular los descuentos automáticos. */
  nombresDeReglas?: ReadonlyMap<string, string>
  /**
   * Porcentaje propio que escribió el usuario en cada línea, por identificador de línea (ADR-050:
   * el propio es de la línea, no del producto); `undefined` = no se ofrece.
   */
  porcentajesPropios?: Readonly<Record<string, string>>
  /** Mensaje de un porcentaje propio inválido, por identificador de línea. */
  erroresDePorcentajePropio?: Readonly<Record<string, string>>
  alCambiarPorcentajePropio?: (lineaId: string, texto: string) => void
}

/** Convierte lo tipeado en una cantidad entera; lo que no es un entero no negativo se toma como cero. */
function aCantidad(texto: string): number {
  return /^\d+$/.test(texto.trim()) ? Number(texto.trim()) : 0
}

function aTexto(cantidad: number): string {
  return cantidad === 0 ? '' : String(cantidad)
}

/**
 * Un producto del pedido: cajas y unidades sueltas (D8) y, debajo, las líneas que arman con su
 * bruto. Todo lo que se muestra viene calculado de `domain/ventas/`; acá solo se pinta.
 */
export function ItemDeVenta({
  productoId,
  nombre,
  cajas,
  unidades,
  admiteCajas,
  admiteUnidadesSueltas,
  lineas,
  error,
  avisoDeStock,
  estado,
  alCambiarCajas,
  alCambiarUnidades,
  alQuitar,
  descuentosPorLinea,
  nombresDeReglas,
  porcentajesPropios,
  erroresDePorcentajePropio,
  alCambiarPorcentajePropio,
}: ItemDeVentaProps) {
  return (
    <Card data-testid={`item-${productoId}`} className="flex flex-col gap-2 text-sm text-primary">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <span className="flex items-center gap-1 font-medium">
          {nombre}
          <Ayuda clave="ventas.cajasYUnidades" />
        </span>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span>Cajas</span>
            <input
              aria-label={`Cajas de ${nombre}`}
              className={CLASE_CANTIDAD}
              inputMode="numeric"
              placeholder="0"
              disabled={!admiteCajas}
              value={aTexto(cajas)}
              onChange={(evento) => alCambiarCajas(aCantidad(evento.target.value))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>Unidades sueltas</span>
            <input
              aria-label={`Unidades sueltas de ${nombre}`}
              className={CLASE_CANTIDAD}
              inputMode="numeric"
              placeholder="0"
              disabled={!admiteUnidadesSueltas}
              value={aTexto(unidades)}
              onChange={(evento) => alCambiarUnidades(aCantidad(evento.target.value))}
            />
          </label>
          <Boton variante="peligro" aria-label={`Quitar ${nombre}`} onClick={alQuitar}>
            Quitar
          </Boton>
        </div>
      </div>
      {estado && <p className="text-primary/70">{estado}</p>}
      {error && <p className="text-danger">{error}</p>}
      {avisoDeStock && <p className="text-danger">{avisoDeStock}</p>}
      <ul className="flex flex-col gap-1">
        {lineas.map((visible) => {
          const conDescuentos = descuentosPorLinea?.get(visible.linea.lineaId)
          const rige = conDescuentos ? textoDePorcentajeQueRige(conDescuentos.rige) : ''
          return (
            <li key={visible.linea.lineaId} className="flex flex-col gap-0.5">
              <div className="flex flex-wrap justify-between gap-2">
                <span>
                  {textoDeCantidadDeLinea({
                    cantidad: visible.linea.cantidad,
                    presentacion_nombre: visible.presentacionNombre,
                    cantidad_base: visible.cantidadBase,
                  })}
                </span>
                <span>{formatearMonto(visible.linea.importeBruto)}</span>
              </div>
              {porcentajesPropios !== undefined && alCambiarPorcentajePropio && (
                <label className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1">
                    Descuento propio %
                    <Ayuda clave="ventas.descuentoPropio" />
                  </span>
                  <input
                    aria-label={`Descuento propio de ${nombre} (${visible.presentacionNombre})`}
                    className={CLASE_CANTIDAD}
                    inputMode="decimal"
                    placeholder="0"
                    value={porcentajesPropios[visible.linea.lineaId] ?? ''}
                    onChange={(evento) => alCambiarPorcentajePropio(visible.linea.lineaId, evento.target.value)}
                  />
                </label>
              )}
              {erroresDePorcentajePropio?.[visible.linea.lineaId] && (
                <p className="text-danger">{erroresDePorcentajePropio[visible.linea.lineaId]}</p>
              )}
              {rige !== '' && (
                <p data-testid={`rige-${visible.linea.lineaId}`} className="text-primary/70">
                  Descuento manual que rige: {rige}
                </p>
              )}
              {conDescuentos?.descuentos.map((descuento, indice) => (
                <p
                  key={`${descuento.origen}-${String(indice)}`}
                  data-testid={`descuento-${visible.linea.lineaId}-${String(indice)}`}
                  className="text-primary/70"
                >
                  {descuento.origen === 'AUTOMATICO' ? 'Descuento automático' : 'Descuento manual'}
                  {descuento.origen === 'AUTOMATICO' &&
                    descuento.reglaId !== null &&
                    nombresDeReglas?.has(descuento.reglaId) === true &&
                    ` «${nombresDeReglas.get(descuento.reglaId) ?? ''}»`}
                  {descuento.porcentaje !== null && ` ${formatearPorcentaje(parsearImporteDesdeApi(descuento.porcentaje))}`}
                  {`: −${formatearMonto(descuento.importe)}`}
                </p>
              ))}
              {conDescuentos && conDescuentos.descuentos.length > 0 && (
                <p data-testid={`neto-${visible.linea.lineaId}`} className="font-medium">
                  Neto de la línea: {formatearMonto(conDescuentos.neto)}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
