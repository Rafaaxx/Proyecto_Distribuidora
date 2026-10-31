import { Boton } from '../../../components/ui/Button'

/**
 * Aviso tras el login de otro usuario con ventas sin enviar del anterior (change 22a, `design.md`
 * D16; SEG-03, SYN-09, `02` §6.4): quedan guardadas en el teléfono y no se borran. Solo
 * presentación; el texto lo arma `sync/ventasPendientes.ts`.
 */
export interface AvisoDePendientesDeOtroProps {
  avisos: readonly string[]
  onContinuar: () => void
}

export function AvisoDePendientesDeOtro({ avisos, onContinuar }: AvisoDePendientesDeOtroProps) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-6 shadow-sm">
        <h1 className="mb-3 text-lg font-semibold text-primary">Ventas sin enviar</h1>
        <div className="mb-4 flex flex-col gap-2">
          {avisos.map((aviso) => (
            <p key={aviso} className="text-sm text-primary">
              {aviso}
            </p>
          ))}
        </div>
        <Boton className="w-full" onClick={onContinuar}>
          Continuar
        </Boton>
      </div>
    </main>
  )
}
