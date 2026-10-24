import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { avisoDeTope, type ContextoDeDescuento } from '../../../domain/ventas/descuentosDeVenta'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface MotivoDeDescuento {
  id: string
  nombre: string
}

export interface DescuentosDeLaVentaProps {
  contexto: ContextoDeDescuento
  motivos: readonly MotivoDeDescuento[]
  /** Lo que escribió el usuario en "Descuento a toda la venta" (en %). */
  general: string
  errorDelGeneral?: string
  alCambiarGeneral: (texto: string) => void
  /** Hay un descuento manual en alguna línea: recién ahí se pide el motivo. */
  hayDescuentoManual: boolean
  motivoId: string
  alCambiarMotivo: (motivoId: string) => void
  /** Falta elegir el motivo que la empresa exige. */
  faltaMotivo: boolean
  /** Rechazo del servidor sobre el descuento (deshabilitado, motivo, tope). */
  error?: string
}

/**
 * Bloque de descuento manual de "Nueva venta" (change 18b, D20): el aviso del tope de quien vende,
 * el porcentaje general y el motivo. Sin lógica: el tope, la necesidad de autorización y la
 * validación de los porcentajes viven en `domain/ventas/descuentosDeVenta.ts`.
 */
export function DescuentosDeLaVenta({
  contexto,
  motivos,
  general,
  errorDelGeneral,
  alCambiarGeneral,
  hayDescuentoManual,
  motivoId,
  alCambiarMotivo,
  faltaMotivo,
  error,
}: DescuentosDeLaVentaProps) {
  const puedeDarDescuento = contexto.habilitado && contexto.tienePermiso
  return (
    <Card className="flex flex-col gap-3" data-testid="bloque-descuentos">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold text-primary">Descuentos</h2>
      </div>
      <p className="flex items-center gap-1 text-sm text-primary" data-testid="aviso-de-tope">
        {avisoDeTope(contexto)}
        <Ayuda clave="ventas.topeDescuento" />
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-start gap-3">
        <Campo
          id="venta-descuento-general"
          etiqueta="Descuento a toda la venta (%)"
          ayuda="ventas.descuentoGeneral"
          error={errorDelGeneral}
        >
          <input
            id="venta-descuento-general"
            className={`${CLASE_CONTROL} w-32`}
            inputMode="decimal"
            placeholder="0"
            disabled={!puedeDarDescuento}
            value={general}
            onChange={(evento) => alCambiarGeneral(evento.target.value)}
          />
        </Campo>
        {hayDescuentoManual && (
          <Campo
            id="venta-motivo-descuento"
            etiqueta={contexto.motivoObligatorio ? 'Motivo del descuento (obligatorio)' : 'Motivo del descuento'}
            ayuda="ventas.motivoDescuento"
            error={faltaMotivo ? 'Elegí el motivo del descuento.' : undefined}
          >
            <select
              id="venta-motivo-descuento"
              className={CLASE_CONTROL}
              value={motivoId}
              onChange={(evento) => alCambiarMotivo(evento.target.value)}
            >
              <option value="">Elegí un motivo</option>
              {motivos.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nombre}
                </option>
              ))}
            </select>
          </Campo>
        )}
      </div>
      <p className="flex items-center gap-1 text-sm text-primary/70">
        Los descuentos automáticos de las reglas se calculan solos.
        <Ayuda clave="ventas.descuentosAutomaticos" />
      </p>
    </Card>
  )
}
