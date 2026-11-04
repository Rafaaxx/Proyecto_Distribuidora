import { Boton } from '../../../components/ui/Button'
import type { MedioPagoLocal } from '../../../domain/ruta/armadoDeVentaLocal'
import type { MedioDePagoDeFormulario } from '../../../domain/pagos-proveedores/formularioPago'

/**
 * Editor de los medios de un cobro del teléfono (change 22a, D6; extraído en el change 23, D8
 * para que lo usen el cobro de una venta y la cobranza suelta): por cada medio, el medio de pago,
 * el importe y, donde el medio la exige, la referencia. Solo pinta: no valida nada; el armado y
 * las reglas son funciones puras de `domain/ruta/`.
 */
const CLASE_CONTROL = 'w-full rounded-md border border-border px-2 py-2 text-sm'

export interface MediosDeCobroProps {
  medios: readonly MedioDePagoDeFormulario[]
  mediosPago: readonly MedioPagoLocal[]
  alAgregar: () => void
  alCambiar: (indice: number, cambio: Partial<MedioDePagoDeFormulario>) => void
  alQuitar: (indice: number) => void
}

export function MediosDeCobro({ medios, mediosPago, alAgregar, alCambiar, alQuitar }: MediosDeCobroProps) {
  const requiereReferencia = new Set(mediosPago.filter((m) => m.requiere_referencia).map((m) => m.id))
  return (
    <>
      {medios.map((medio, i) => {
        const n = i + 1
        return (
          <div key={n} className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-2">
            <select
              aria-label={`Medio de cobro ${n}`}
              className={CLASE_CONTROL}
              value={medio.medioPagoId}
              onChange={(e) => alCambiar(i, { medioPagoId: e.target.value })}
            >
              <option value="">Elegí el medio</option>
              {mediosPago.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nombre}
                </option>
              ))}
            </select>
            <input
              aria-label={`Importe del medio ${n}`}
              inputMode="decimal"
              placeholder="Importe"
              className={CLASE_CONTROL}
              value={medio.importe}
              onChange={(e) => alCambiar(i, { importe: e.target.value })}
            />
            {requiereReferencia.has(medio.medioPagoId) && (
              <input
                aria-label={`Referencia del medio ${n}`}
                placeholder="Referencia"
                className={CLASE_CONTROL}
                value={medio.referencia}
                onChange={(e) => alCambiar(i, { referencia: e.target.value })}
              />
            )}
            <Boton variante="secundario" className="self-start" aria-label={`Quitar medio ${n}`} onClick={() => alQuitar(i)}>
              Quitar
            </Boton>
          </div>
        )
      })}
      <Boton variante="secundario" className="self-start" onClick={alAgregar}>
        Agregar medio de cobro
      </Boton>
    </>
  )
}
