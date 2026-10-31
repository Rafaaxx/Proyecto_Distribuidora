import { useState, type FormEvent, type ReactNode } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { useConectado } from '../../../lib/conexion'

/**
 * Pantallas del PIN de `/ruta` (change 21, D13, D14, D15). Solo presentación: las reglas viven en
 * `lib/sesionLocal/pin.ts`. El PIN nunca se registra ni se muestra.
 */
const CLASES_INPUT =
  'rounded-md border border-border px-2 py-2 text-center text-xl tracking-widest focus:outline-none focus:ring-2 focus:ring-primary/40'

interface CampoDePinProps {
  id: string
  etiqueta: string
  valor: string
  alCambiar: (valor: string) => void
  /** Pone el "(?)" del PIN al lado de la etiqueta. */
  conAyuda?: boolean
}

export function CampoDePin({ id, etiqueta, valor, alCambiar, conAyuda = false }: CampoDePinProps) {
  return (
    <Campo id={id} etiqueta={etiqueta} {...(conAyuda ? { ayuda: 'ruta.pin' as const } : {})}>
      <input
        id={id}
        type="password"
        inputMode="numeric"
        autoComplete="off"
        maxLength={6}
        className={CLASES_INPUT}
        value={valor}
        onChange={(e) => alCambiar(e.target.value)}
      />
    </Campo>
  )
}

function Marco({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-6 shadow-sm">
        <h1 className="mb-4 text-lg font-semibold text-primary">{titulo}</h1>
        {children}
      </div>
    </main>
  )
}

export interface DefinirPinProps {
  /** Devuelve el motivo del rechazo, o `null` si se guardó. */
  onDefinir: (pin: string, confirmacion: string) => Promise<string | null>
}

export function DefinirPinScreen({ onDefinir }: DefinirPinProps) {
  const conectado = useConectado()
  const [pin, setPin] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [motivo, setMotivo] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setGuardando(true)
    setMotivo(await onDefinir(pin, confirmacion))
    setGuardando(false)
  }

  return (
    <Marco titulo="Definí tu PIN">
      <p className="mb-3 text-sm">
        Es de 6 dígitos y te lo vamos a pedir cada vez que abras la aplicación, también sin señal.
      </p>
      {!conectado && <Alert className="mb-3">Definir el PIN requiere conexión.</Alert>}
      <form onSubmit={(e) => void enviar(e)} noValidate className="flex flex-col gap-4">
        <CampoDePin id="pin" etiqueta="PIN" valor={pin} alCambiar={setPin} conAyuda />
        <CampoDePin id="pin-repetido" etiqueta="Repetí el PIN" valor={confirmacion} alCambiar={setConfirmacion} />
        <Boton type="submit" disabled={guardando || !conectado} className="w-full">
          Guardar PIN
        </Boton>
        {motivo && <Alert>{motivo}</Alert>}
      </form>
    </Marco>
  )
}

export interface PedirPinProps {
  /** Devuelve el mensaje de error si el PIN no sirvió, o `null` si desbloqueó. */
  onDesbloquear: (pin: string) => Promise<string | null>
}

export function PedirPinScreen({ onDesbloquear }: PedirPinProps) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [verificando, setVerificando] = useState(false)

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setVerificando(true)
    const mensaje = await onDesbloquear(pin)
    setPin('')
    setError(mensaje)
    setVerificando(false)
  }

  return (
    <Marco titulo="Ingresá tu PIN">
      <form onSubmit={(e) => void enviar(e)} noValidate className="flex flex-col gap-4">
        <CampoDePin id="pin" etiqueta="PIN" valor={pin} alCambiar={setPin} conAyuda />
        <Boton type="submit" disabled={verificando} className="w-full">
          Desbloquear
        </Boton>
        {error && <Alert>{error}</Alert>}
      </form>
    </Marco>
  )
}
