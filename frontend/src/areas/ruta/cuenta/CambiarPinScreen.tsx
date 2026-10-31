import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { cambiarPin } from '../../../lib/sesionLocal/pin'
import { CampoDePin } from '../sesion/PantallasDePin'
import { useSesionRutaActiva } from '../sesion/contextoSesion'

/**
 * "Cambiar PIN" en `/ruta` (change 21, `design.md` D13, D15; SEG-03, SEG-04): con el PIN actual y
 * el nuevo dos veces, con o sin conexión (la derivación es local). Un actual incorrecto suma un
 * fallo del mismo contador del desbloqueo; al llegar al máximo se borra la derivación y se vuelve
 * al login. El PIN nunca se registra ni se envía a ningún lado.
 */
export function CambiarPinScreen() {
  const { alBloquearse } = useSesionRutaActiva()
  const [actual, setActual] = useState('')
  const [nuevo, setNuevo] = useState('')
  const [repetido, setRepetido] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState(false)
  const [guardando, setGuardando] = useState(false)

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setHecho(false)
    setError(null)
    setGuardando(true)
    const resultado = await cambiarPin(actual, nuevo, repetido)
    setGuardando(false)
    setActual('')

    switch (resultado.tipo) {
      case 'ok':
        setNuevo('')
        setRepetido('')
        setHecho(true)
        return
      case 'invalido':
        setError(resultado.motivo)
        return
      case 'incorrecto':
        setError(
          resultado.restantes === 1
            ? 'El PIN actual es incorrecto. Te queda 1 intento.'
            : `El PIN actual es incorrecto. Te quedan ${resultado.restantes} intentos.`,
        )
        return
      case 'bloqueado':
      case 'sin_pin':
        alBloquearse()
        return
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-primary">Cambiar PIN</h1>
        <Link to="/ruta/cuenta" className="text-sm underline">
          Volver a Mi cuenta
        </Link>
      </div>
      <Card>
        <form onSubmit={(e) => void enviar(e)} noValidate className="flex flex-col gap-4">
          <CampoDePin id="pin-actual" etiqueta="PIN actual" valor={actual} alCambiar={setActual} conAyuda />
          <CampoDePin id="pin-nuevo" etiqueta="PIN nuevo" valor={nuevo} alCambiar={setNuevo} />
          <CampoDePin id="pin-nuevo-repetido" etiqueta="Repetí el PIN nuevo" valor={repetido} alCambiar={setRepetido} />
          {error && <Alert>{error}</Alert>}
          {hecho && (
            <p role="status" className="text-sm text-primary">
              Listo: cambiaste tu PIN.
            </p>
          )}
          <Boton type="submit" disabled={guardando} className="w-full">
            Cambiar PIN
          </Boton>
        </form>
      </Card>
    </main>
  )
}

export default CambiarPinScreen
