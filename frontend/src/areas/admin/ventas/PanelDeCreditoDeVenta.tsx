import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Card } from '../../../components/ui/Card'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import { textoDeDecisionDeCredito, type PanelDeCredito } from '../../../domain/ventas/creditoDeVenta'

const ETIQUETAS_DE_POLITICA: Record<string, string> = {
  ADVERTIR: 'Advertir',
  AUTORIZAR: 'Autorizar',
  BLOQUEAR: 'Bloquear',
}

export interface PanelDeCreditoDeVentaProps {
  panel: PanelDeCredito
  aceptaExceso: boolean
  alCambiarAcepta: (acepta: boolean) => void
  /** Rechazo del servidor sobre el crédito (límite, saldo y exceso reales). */
  error?: string
}

/**
 * Crédito del cliente en "Nueva venta" (change 18b, D16, D20): límite, lo que debe, disponible,
 * saldo después de la venta, exceso y política, calculados con la gemela del motor `cre01`. El
 * servidor decide igual (TR-10). Sin lógica: todo viene de `domain/ventas/creditoDeVenta.ts`.
 */
export function PanelDeCreditoDeVenta({ panel, aceptaExceso, alCambiarAcepta, error }: PanelDeCreditoDeVentaProps) {
  const pideAceptar = panel.decision === 'pide-aceptar' || panel.decision === 'aceptado'
  return (
    <Card className="flex flex-col gap-2 text-sm text-primary" data-testid="panel-de-credito">
      <div className="flex items-center gap-1">
        <h2 className="text-base font-semibold">Crédito del cliente</h2>
        <Ayuda clave="ventas.credito" />
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5">
        <dt>Límite</dt>
        <dd data-testid="credito-limite">{panel.limite === null ? 'Sin límite' : formatearMonto(panel.limite)}</dd>
        <dt>Debe</dt>
        <dd data-testid="credito-saldo">{formatearMonto(panel.saldo)}</dd>
        <dt>Disponible</dt>
        <dd data-testid="credito-disponible">{panel.disponible === null ? '—' : formatearMonto(panel.disponible)}</dd>
        <dt>Queda debiendo tras la venta</dt>
        <dd data-testid="credito-resultante">{formatearMonto(panel.saldoResultante)}</dd>
        <dt>Se pasa del límite por</dt>
        <dd data-testid="credito-exceso">{formatearMonto(panel.exceso)}</dd>
        <dt className="flex items-center gap-1">
          Si se pasa
          <Ayuda clave="ventas.politicaCredito" />
        </dt>
        <dd data-testid="credito-politica">{ETIQUETAS_DE_POLITICA[panel.politica] ?? panel.politica}</dd>
      </dl>
      {panel.decision === 'bloqueado' ? (
        <Alert data-testid="credito-aviso">{textoDeDecisionDeCredito(panel)}</Alert>
      ) : (
        <p data-testid="credito-aviso" className={panel.decision === 'sin-exceso' || panel.decision === 'sin-control' ? 'text-primary/70' : ''}>
          {textoDeDecisionDeCredito(panel)}
        </p>
      )}
      {pideAceptar && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={aceptaExceso} onChange={(evento) => alCambiarAcepta(evento.target.checked)} />
          <span>Confirmo vender con exceso</span>
        </label>
      )}
      {error && <Alert>{error}</Alert>}
    </Card>
  )
}
