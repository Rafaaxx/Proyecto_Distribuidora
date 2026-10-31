import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import type { PersonaQueAutoriza } from './verificarSupervisores'

/**
 * Pide el PIN de cada supervisor que autoriza (change 22a, `design.md` D10; SEG-05). Solo
 * presentación: la verificación la hace `verificarSupervisores`. El PIN vive únicamente en el
 * estado de este diálogo y se descarta al cerrarlo; mientras se deriva se muestra "Verificando…".
 */
export interface DialogoDePinSupervisorProps {
  personas: readonly PersonaQueAutoriza[]
  verificando: boolean
  error: string | null
  onVerificar: (pins: Record<string, string>) => void
  onCancelar: () => void
}

export function DialogoDePinSupervisor({ personas, verificando, error, onVerificar, onCancelar }: DialogoDePinSupervisorProps) {
  const [pins, setPins] = useState<Record<string, string>>({})
  const completo = personas.every((p) => (pins[p.id] ?? '').length > 0)

  return (
    <Dialogo abierto titulo="PIN del supervisor" onCerrar={verificando ? () => undefined : onCancelar}>
      <form
        className="flex flex-col gap-3"
        onSubmit={(evento) => {
          evento.preventDefault()
          if (completo && !verificando) onVerificar(pins)
        }}
      >
        <p className="flex items-center gap-1 text-sm text-primary">
          El supervisor escribe su PIN en este teléfono.
          <Ayuda clave="ruta.pinSupervisor" />
        </p>
        {personas.map((persona) => (
          <div key={persona.id} className="flex flex-col gap-1">
            <label htmlFor={`pin-${persona.id}`} className="text-sm font-medium text-primary">
              PIN de {persona.nombre}
            </label>
            <input
              id={`pin-${persona.id}`}
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              className="w-full rounded-md border border-border px-2 py-2 text-center text-xl tracking-widest"
              value={pins[persona.id] ?? ''}
              onChange={(evento) => setPins((actuales) => ({ ...actuales, [persona.id]: evento.target.value }))}
            />
          </div>
        ))}
        {verificando && (
          <p role="status" className="text-sm text-primary">
            Verificando…
          </p>
        )}
        {error && <Alert>{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" disabled={verificando} onClick={onCancelar}>
            Cancelar
          </Boton>
          <Boton type="submit" disabled={!completo || verificando}>
            Verificar y confirmar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
