import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { mensajeDeErrorDePin, ofreceMiPin, validarPinNuevo } from '../../../domain/identidad/pin'
import { ErrorDePin } from '../../../features/identidad/pinApi'
import { usePermisos } from '../../../features/identidad/usePermisos'
import {
  useDefinirMiPin,
  useEstadoDeMiPin,
  useSecretoEfimero,
  type SecretosDeMiPin,
} from '../../../features/identidad/usePin'
import { generarOperationId } from '../../../lib/api/operationId'

const TITULO = 'Mi PIN'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MENSAJE_DE_RED = 'No se pudo guardar el PIN. Podés reintentar: se reenvía la misma operación.'

/**
 * "Mi PIN" (change 18b, tarea 14.3; spec `identidad/pin-de-autorizacion`; `design.md` D21 parte B;
 * SEG-05, ADR-011, ADR-019, ADR-018): cada supervisor define su propio PIN de autorización
 * reautenticándose con su contraseña. Solo con algún permiso de autorización (ADR-027). La
 * contraseña y el PIN se escriben enmascarados, viven solo en el formulario y se borran al enviar
 * y al cancelar: no se guardan en el navegador. El servidor valida igual y decide si el PIN es
 * fácil de adivinar y cuándo se bloquean los intentos de contraseña.
 */
export function MiPinScreen() {
  const permisos = usePermisos()
  if (permisos.estado === 'cargando') return null
  if (!ofreceMiPin(permisos.tiene)) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <p className="text-sm text-primary/70">Tu rol no permite autorizar excepciones, así que no usa PIN de autorización.</p>
      </main>
    )
  }
  return <MiPinContenido />
}

function MiPinContenido() {
  const estado = useEstadoDeMiPin()
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="flex items-center gap-1 text-sm text-primary/70">
        Es el PIN con el que aprobás descuentos y excesos de crédito en la pantalla de otra persona.
        <Ayuda clave="cuenta.miPin" />
      </p>
      {estado.isPending && <p>Cargando…</p>}
      {estado.isError && <Alert>No se pudo obtener el estado de tu PIN.</Alert>}
      {estado.isSuccess && !estado.data.puede_definir && (
        <p className="text-sm text-primary/70">Tu rol no permite autorizar excepciones, así que no usa PIN de autorización.</p>
      )}
      {estado.isSuccess && estado.data.puede_definir && (
        <>
          <p className="text-sm text-primary" data-testid="pin-definido">
            PIN definido: <strong>{estado.data.tiene_pin_autorizacion ? 'Sí' : 'No'}</strong>
          </p>
          <FormularioDeMiPin tienePin={estado.data.tiene_pin_autorizacion} />
        </>
      )}
    </main>
  )
}

function FormularioDeMiPin({ tienePin }: { tienePin: boolean }) {
  // Estos estados son la única copia de los secretos en pantalla; se borran al enviar y al cancelar.
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  const [repeticion, setRepeticion] = useState('')
  const [operationId, setOperationId] = useState(generarOperationId)
  const [errorLocal, setErrorLocal] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)
  const secretos = useSecretoEfimero<SecretosDeMiPin>()
  const definir = useDefinirMiPin(() => secretos.ref.current)

  const limpiar = () => {
    setPassword('')
    setPin('')
    setRepeticion('')
  }

  const enviar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    setGuardado(false)
    setErrorLocal(null)
    definir.reset() // cada envío muestra solo el problema actual, no el rechazo anterior
    const validacion = validarPinNuevo(pin, repeticion)
    if (!validacion.valido) {
      setErrorLocal(validacion.mensaje)
      return
    }
    if (password === '') {
      setErrorLocal('Escribí tu contraseña actual.')
      return
    }
    setErrorLocal(null)
    const entregados: SecretosDeMiPin = { pin, passwordActual: password }
    limpiar() // los secretos salen de la pantalla apenas se entregan
    try {
      await secretos.usar(entregados, () => definir.mutateAsync({ operationId }))
      setGuardado(true)
      setOperationId(generarOperationId()) // el próximo cambio es otra operación
    } catch {
      // El rechazo queda en `definir.error` y se muestra abajo. El Operation-Id se conserva:
      // un rechazo no deja fila de comando y el reintento con los datos corregidos se procesa.
    }
  }

  const mensajeDelServidor =
    definir.error instanceof ErrorDePin
      ? mensajeDeErrorDePin(definir.error.codigo, definir.error.message)
      : definir.error
        ? MENSAJE_DE_RED
        : null

  return (
    <Card className="flex flex-col gap-3">
      <form onSubmit={(evento) => void enviar(evento)} className="flex flex-col gap-3" autoComplete="off" data-testid="formulario-mi-pin">
        <h2 className="text-base font-semibold text-primary">{tienePin ? 'Cambiar mi PIN' : 'Definir mi PIN'}</h2>
        <Campo id="mi-pin-password" etiqueta="Tu contraseña actual">
          <input
            id="mi-pin-password"
            type="password"
            autoComplete="off"
            className={`${CLASE_CONTROL} w-64`}
            value={password}
            onChange={(evento) => setPassword(evento.target.value)}
          />
        </Campo>
        <Campo id="mi-pin-nuevo" etiqueta="PIN nuevo">
          <input
            id="mi-pin-nuevo"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            className={`${CLASE_CONTROL} w-40`}
            value={pin}
            onChange={(evento) => setPin(evento.target.value)}
          />
        </Campo>
        <Campo id="mi-pin-repeticion" etiqueta="Repetí el PIN">
          <input
            id="mi-pin-repeticion"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            className={`${CLASE_CONTROL} w-40`}
            value={repeticion}
            onChange={(evento) => setRepeticion(evento.target.value)}
          />
        </Campo>
        {errorLocal && <Alert>{errorLocal}</Alert>}
        {mensajeDelServidor && <Alert>{mensajeDelServidor}</Alert>}
        {guardado && !mensajeDelServidor && (
          <p role="status" className="text-sm text-primary">
            Listo: tu PIN quedó guardado. El anterior ya no sirve.
          </p>
        )}
        <div className="flex gap-2">
          <Boton type="submit" disabled={definir.isPending}>
            Guardar mi PIN
          </Boton>
          <Boton variante="secundario" onClick={limpiar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Card>
  )
}

export default MiPinScreen
