import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { filasDelPinDeAutorizacion, mensajeDeErrorDePin, validarPinNuevo, type FilaDelPin } from '../../../domain/identidad/pin'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ErrorDePin } from '../../../features/identidad/pinApi'
import { useRolesConPermisos } from '../../../features/identidad/useRoles'
import { useRotarPin, useSecretoEfimero, useUsuarios } from '../../../features/identidad/usePin'
import { generarOperationId } from '../../../lib/api/operationId'

const TITULO = 'PIN de autorización'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MENSAJE_DE_RED = 'No se pudo guardar el PIN. Podés reintentar: se reenvía la misma operación.'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar usuarios, roles y permisos.</p>
    </main>
  )
}

/**
 * PIN de autorización de los supervisores (change 18b, tarea 14.2; spec
 * `identidad/pin-de-autorizacion`; `design.md` D21 parte A; SEG-05, ADR-011, ADR-019). Lista a los
 * usuarios activos cuyo rol permite autorizar excepciones, con "PIN definido: sí/no" (nunca el PIN
 * ni su derivación), y permite definir o cambiar el de cada uno con `ADMIN_USUARIOS` (ADR-027). El
 * PIN se escribe dos veces, enmascarado, y no se guarda en el navegador. El servidor valida igual
 * (SEG-06), incluido que no sea fácil de adivinar.
 */
export function PinAutorizacionScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_USUARIOS" fallback={<SinPermiso />}>
      <PinListado />
    </SiTienePermiso>
  )
}

function PinListado() {
  const usuarios = useUsuarios()
  const roles = useRolesConPermisos()
  const [elegido, setElegido] = useState<FilaDelPin | null>(null)
  const filas = usuarios.data && roles.data ? filasDelPinDeAutorizacion(usuarios.data, roles.data) : []

  const columnas: ColumnaTabla<FilaDelPin>[] = [
    { clave: 'usuario', encabezado: 'Usuario', render: (f) => <span className="font-medium text-primary">{f.nombre}</span> },
    { clave: 'rol', encabezado: 'Rol', render: (f) => f.rol },
    {
      clave: 'pin',
      encabezado: 'PIN definido',
      render: (f) => <Badge variante={f.tienePin ? 'positivo' : 'negativo'}>{f.tienePin ? 'Sí' : 'No'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (f) => (
        <Boton variante="secundario" aria-label={`${f.tienePin ? 'Cambiar' : 'Definir'} el PIN de ${f.nombre}`} onClick={() => setElegido(f)}>
          {f.tienePin ? 'Cambiar PIN' : 'Definir PIN'}
        </Boton>
      ),
    },
  ]

  const hayError = usuarios.isError || roles.isError
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="flex items-center gap-1 text-sm text-primary/70">
        El PIN permite que un supervisor apruebe descuentos y excesos de crédito en la pantalla de otra persona.
        <Ayuda clave="roles.pinAutorizacion" />
      </p>
      {(usuarios.isPending || roles.isPending) && !hayError && <p>Cargando…</p>}
      {hayError && <Alert>No se pudieron obtener los usuarios.</Alert>}
      {usuarios.isSuccess && roles.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Ningún usuario activo tiene un rol que permita autorizar.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(f) => f.usuarioId} etiqueta={TITULO} />
        </Card>
      )}
      <Dialogo abierto={elegido !== null} titulo={`PIN de ${elegido?.nombre ?? ''}`} onCerrar={() => setElegido(null)}>
        {elegido !== null && <DefinirPinFormulario fila={elegido} onCerrar={() => setElegido(null)} />}
      </Dialogo>
    </main>
  )
}

function DefinirPinFormulario({ fila, onCerrar }: { fila: FilaDelPin; onCerrar: () => void }) {
  // Estos tres estados mueren con el diálogo: el PIN no sobrevive a cerrarlo ni a enviarlo.
  const [pin, setPin] = useState('')
  const [repeticion, setRepeticion] = useState('')
  const [operationId] = useState(generarOperationId)
  const secreto = useSecretoEfimero<string>()
  const rotar = useRotarPin(() => secreto.ref.current ?? '')
  const [errorLocal, setErrorLocal] = useState<string | null>(null)

  const enviar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    setErrorLocal(null)
    rotar.reset() // cada envío muestra solo el problema actual, no el rechazo anterior
    const validacion = validarPinNuevo(pin, repeticion)
    if (!validacion.valido) {
      setErrorLocal(validacion.mensaje)
      return
    }
    setErrorLocal(null)
    const elegido = pin
    setPin('')
    setRepeticion('') // el PIN sale de la pantalla apenas se entrega
    try {
      await secreto.usar(elegido, () => rotar.mutateAsync({ usuarioId: fila.usuarioId, operationId }))
      onCerrar()
    } catch {
      // El rechazo queda en `rotar.error` y se muestra abajo.
    }
  }

  const mensajeDelServidor =
    rotar.error instanceof ErrorDePin ? mensajeDeErrorDePin(rotar.error.codigo, rotar.error.message) : rotar.error ? MENSAJE_DE_RED : null

  return (
    <form onSubmit={(evento) => void enviar(evento)} className="flex flex-col gap-3" autoComplete="off" data-testid="formulario-de-pin">
      <p className="text-sm text-primary">
        {fila.tienePin
          ? `Vas a cambiar el PIN de ${fila.nombre}: el anterior deja de servir.`
          : `Vas a definir el PIN de ${fila.nombre}.`}
      </p>
      <Campo id="pin-nuevo" etiqueta="PIN nuevo">
        <input
          id="pin-nuevo"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          className={`${CLASE_CONTROL} w-40`}
          value={pin}
          onChange={(evento) => setPin(evento.target.value)}
        />
      </Campo>
      <Campo id="pin-repeticion" etiqueta="Repetí el PIN">
        <input
          id="pin-repeticion"
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
      <div className="flex gap-2">
        <Boton type="submit" disabled={rotar.isPending}>
          Guardar PIN
        </Boton>
        <Boton variante="secundario" onClick={onCerrar}>
          Cancelar
        </Boton>
      </div>
    </form>
  )
}

export default PinAutorizacionScreen
