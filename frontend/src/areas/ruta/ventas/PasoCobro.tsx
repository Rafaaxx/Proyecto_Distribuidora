import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { AVISO_DE_VERSION_MINIMA } from '../../../sync/versionMinima'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import type { CarritoDeRuta, MedioPagoLocal, VentaArmada } from '../../../domain/ruta/armadoDeVentaLocal'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { autorizadoresPara, type TipoDeAutorizacion } from '../../../domain/ventas/autorizacionDeVenta'
import { AVISO_CONSUMIDOR_FINAL_DE_CONTADO } from '../../../domain/ventas/calculoDeVenta'
import { textoDeDecisionDeCredito } from '../../../domain/ventas/creditoDeVenta'

/**
 * Paso 3 de la venta de ruta: cobro y confirmación (change 22a, `design.md` D6 a D10, D14; CLI-03,
 * VTA-11, CRE-04 a CRE-07, STK-06, SEG-05). Medios con referencia, saldo resultante, panel de
 * crédito del teléfono, supervisor que autoriza y "Vender igual". Solo pinta: todas las decisiones
 * salen de `armarVentaDeRuta`.
 */
const CLASE_CONTROL = 'w-full rounded-md border border-border px-2 py-2 text-sm'

const ROTULO_DE_AUTORIZACION: Record<TipoDeAutorizacion, string> = {
  DESCUENTO: 'Supervisor que autoriza el descuento',
  CREDITO: 'Supervisor que autoriza el crédito',
}

export interface PasoCobroProps {
  armada: VentaArmada
  carrito: CarritoDeRuta
  mediosPago: readonly MedioPagoLocal[]
  confirmando: boolean
  error: string | null
  alAgregarMedio: () => void
  alCambiarMedio: (indice: number, cambio: Partial<CarritoDeRuta['medios'][number]>) => void
  alQuitarMedio: (indice: number) => void
  alCambiarObservacion: (texto: string) => void
  alAceptarExceso: (acepta: boolean) => void
  alElegirSupervisor: (tipo: TipoDeAutorizacion, autorizadorId: string) => void
  alVenderIgual: (acepta: boolean) => void
  alConfirmar: () => void
  alVolver: () => void
}

export function PasoCobro(props: PasoCobroProps) {
  const { armada, carrito, mediosPago } = props
  const panel = armada.panelDeCredito
  const requiereReferencia = new Set(mediosPago.filter((m) => m.requiere_referencia).map((m) => m.id))

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {armada.contadoDeConsumidorFinal.aplica && (
        <p className="flex items-center gap-1 text-sm text-primary">
          {AVISO_CONSUMIDOR_FINAL_DE_CONTADO}
          <Ayuda clave="ventas.consumidorFinal" />
        </p>
      )}

      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-1">
          <h2 className="text-sm font-semibold text-primary">Cobro en el acto (opcional)</h2>
          <Ayuda clave="ventas.cobranza" />
        </div>
        {carrito.medios.map((medio, i) => {
          const n = i + 1
          return (
            <div key={n} className="flex min-w-0 flex-col gap-2 rounded-md border border-border p-2">
              <select
                aria-label={`Medio de cobro ${n}`}
                className={CLASE_CONTROL}
                value={medio.medioPagoId}
                onChange={(e) => props.alCambiarMedio(i, { medioPagoId: e.target.value })}
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
                onChange={(e) => props.alCambiarMedio(i, { importe: e.target.value })}
              />
              {requiereReferencia.has(medio.medioPagoId) && (
                <input
                  aria-label={`Referencia del medio ${n}`}
                  placeholder="Referencia"
                  className={CLASE_CONTROL}
                  value={medio.referencia}
                  onChange={(e) => props.alCambiarMedio(i, { referencia: e.target.value })}
                />
              )}
              <Boton variante="secundario" className="self-start" aria-label={`Quitar medio ${n}`} onClick={() => props.alQuitarMedio(i)}>
                Quitar
              </Boton>
            </div>
          )
        })}
        <Boton variante="secundario" className="self-start" onClick={props.alAgregarMedio}>
          Agregar medio de cobro
        </Boton>
        {carrito.medios.length > 0 && (
          <div className="flex flex-col gap-1">
            <label htmlFor="vender-observacion" className="text-xs text-primary/70">
              Observación del cobro (opcional)
            </label>
            <input
              id="vender-observacion"
              maxLength={500}
              className={CLASE_CONTROL}
              value={carrito.observacionCobranza}
              onChange={(e) => props.alCambiarObservacion(e.target.value)}
            />
          </div>
        )}
      </Card>

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="text-base font-semibold" data-testid="total-a-cobrar">
          Total: {formatearDinero(armada.total)}
        </p>
        <p data-testid="cobrado">Cobrado en el acto: {formatearDinero(armada.cobrado)}</p>
        {armada.saldoResultante !== null && (
          <p data-testid="saldo-resultante">Saldo después de la venta: {formatearDinero(armada.saldoResultante)}</p>
        )}
      </Card>

      {panel !== null && (
        <Card className="flex flex-col gap-2 text-sm text-primary" data-testid="panel-de-credito">
          <div className="flex items-center gap-1">
            <h2 className="text-sm font-semibold">Crédito del cliente</h2>
            <Ayuda clave="ruta.creditoSinSenal" />
          </div>
          <p>{textoDeDecisionDeCredito(panel)}</p>
          {(panel.decision === 'pide-aceptar' || panel.decision === 'aceptado') && (
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4" checked={carrito.aceptaExceso} onChange={(e) => props.alAceptarExceso(e.target.checked)} />
              Aceptar el exceso de crédito
            </label>
          )}
        </Card>
      )}

      {armada.autorizacionesNecesarias.length > 0 && (
        <Card className="flex flex-col gap-2">
          {armada.autorizacionesNecesarias.map((tipo) => {
            const posibles = autorizadoresPara(tipo, armada.autorizadores)
            return (
              <div key={tipo} className="flex flex-col gap-1">
                <div className="flex items-center gap-1">
                  <label htmlFor={`vender-supervisor-${tipo}`} className="text-sm font-medium text-primary">
                    {ROTULO_DE_AUTORIZACION[tipo]}
                  </label>
                  <Ayuda clave="ventas.autorizacion" />
                </div>
                <select
                  id={`vender-supervisor-${tipo}`}
                  className={CLASE_CONTROL}
                  value={armada.seleccion[tipo] ?? ''}
                  onChange={(e) => props.alElegirSupervisor(tipo, e.target.value)}
                >
                  <option value="">Elegí el supervisor</option>
                  {posibles.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.nombre}
                    </option>
                  ))}
                </select>
              </div>
            )
          })}
        </Card>
      )}

      {armada.stock.confirmacion === 'vender-igual' && (
        <Card className="flex flex-col gap-2 text-sm text-primary">
          <ul className="flex flex-col gap-1">
            {armada.stock.lineas.map((l) => (
              <li key={l.lineaId} className="font-medium text-danger">
                {l.aviso}
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-2">
            <input
              id="vender-igual"
              type="checkbox"
              className="h-4 w-4"
              checked={carrito.venderIgual}
              onChange={(e) => props.alVenderIgual(e.target.checked)}
            />
            <label htmlFor="vender-igual">Vender igual</label>
            <Ayuda clave="ruta.stockDelVehiculo" />
          </div>
        </Card>
      )}

      {armada.bloqueos.length > 0 && (
        <ul data-testid="bloqueos" className="flex flex-col gap-1 text-sm text-danger">
          {armada.bloqueos.map((texto) => (
            <li key={texto}>{texto}</li>
          ))}
        </ul>
      )}
      {props.error && (
        <Alert>
          {props.error}
          {props.error === AVISO_DE_VERSION_MINIMA && (
            <>
              {' '}
              <Ayuda clave="ruta.versionMinima" />
            </>
          )}
        </Alert>
      )}

      <div className="flex flex-col gap-2">
        <Boton disabled={!armada.puedeConfirmar || props.confirmando} onClick={props.alConfirmar}>
          Confirmar venta
        </Boton>
        <Boton variante="secundario" disabled={props.confirmando} onClick={props.alVolver}>
          Atrás
        </Boton>
      </div>
    </div>
  )
}
