import type { ReactNode } from 'react'

/**
 * Diálogo base de `/admin` (tarea 10.1): usado por los formularios de
 * alta/edición (tarea 10.5, 10.6). `role="dialog"` + `aria-modal` para
 * accesibilidad; el cierre por Escape/click afuera queda a cargo de quien
 * lo usa si lo necesita -- ningún escenario de este change lo exige.
 */
export interface DialogoProps {
  abierto: boolean
  titulo: string
  onCerrar: () => void
  children: ReactNode
}

export function Dialogo({ abierto, titulo, onCerrar, children }: DialogoProps) {
  if (!abierto) {
    return null
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-md border border-border bg-surface p-4 shadow-lg"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-primary">{titulo}</h2>
          <button
            type="button"
            aria-label="Cerrar"
            onClick={onCerrar}
            className="rounded-md px-2 py-1 text-sm hover:bg-surface-muted"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export default Dialogo
