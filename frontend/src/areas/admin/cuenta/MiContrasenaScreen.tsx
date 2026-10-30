import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { esquemaMiContrasena, type DatosDeMiContrasena } from '../../../domain/identidad/usuarios'
import { useSecretoEfimero } from '../../../features/identidad/usePin'
import { useCambiarMiContrasena, type SecretosDeMiContrasena } from '../../../features/identidad/useUsuariosAdmin'
import { generarOperationId } from '../../../lib/api/operationId'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from '../usuarios/errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeMiContrasena {
  actual: string
  nueva: string
  confirmacion: string
}

const VACIO: FormularioDeMiContrasena = { actual: '', nueva: '', confirmacion: '' }

/**
 * "Mi contraseña" (change 20b, tarea 10.4; D20; ADR-018, ADR-056, ADR-057): cada usuario cambia la
 * suya reautenticándose con la actual. Disponible para todo usuario con sesión. Las contraseñas se
 * escriben enmascaradas, viven solo en el formulario, viajan por una referencia efímera y se borran
 * al enviar: no entran a la caché de consultas ni al almacenamiento. La confirmación es solo de
 * interfaz. Un rechazo no deja fila de comando, así que el reintento con los datos corregidos
 * reenvía el mismo `Operation-Id` (INV-06). El servidor cuenta la contraseña actual equivocada como
 * intento fallido de inicio de sesión y decide cuándo bloquear.
 */
export function MiContrasenaScreen() {
  const secretos = useSecretoEfimero<SecretosDeMiContrasena>()
  const cambiar = useCambiarMiContrasena(() => secretos.ref.current)
  const [operationId, setOperationId] = useState(generarOperationId)
  const [hecho, setHecho] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormularioDeMiContrasena, unknown, DatosDeMiContrasena>({
    resolver: zodResolver(esquemaMiContrasena),
    defaultValues: VACIO,
  })

  const alEnviar = handleSubmit(async (datos) => {
    setHecho(false)
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    reset(VACIO) // las contraseñas salen de la pantalla apenas se entregan
    try {
      await secretos.usar(datos, () => cambiar.mutateAsync({ operationId }))
      setOperationId(generarOperationId()) // el próximo cambio es otra operación
      setHecho(true)
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Mi contraseña" />
      <p className="text-sm text-primary/70">
        Cambiá la contraseña con la que entrás. Al cambiarla se cierran tus sesiones abiertas en otros dispositivos; esta sigue abierta.
      </p>
      <Card>
        <form onSubmit={alEnviar} noValidate autoComplete="off" className="flex flex-col gap-3" aria-label="Cambiar mi contraseña">
          <Campo id="mi-contrasena-actual" etiqueta="Tu contraseña actual" error={errors.actual?.message}>
            <input
              id="mi-contrasena-actual"
              type="password"
              autoComplete="current-password"
              className={`${CLASE_CONTROL} w-64`}
              {...register('actual')}
            />
          </Campo>
          <Campo id="mi-contrasena-nueva" etiqueta="Contraseña nueva" error={errors.nueva?.message}>
            <input
              id="mi-contrasena-nueva"
              type="password"
              autoComplete="new-password"
              className={`${CLASE_CONTROL} w-64`}
              {...register('nueva')}
            />
          </Campo>
          <Campo id="mi-contrasena-confirmacion" etiqueta="Repetí la contraseña nueva" error={errors.confirmacion?.message}>
            <input
              id="mi-contrasena-confirmacion"
              type="password"
              autoComplete="new-password"
              className={`${CLASE_CONTROL} w-64`}
              {...register('confirmacion')}
            />
          </Campo>
          {errors.root?.message && <Alert>{errors.root.message}</Alert>}
          {hecho && !errors.root && (
            <p role="status" className="text-sm text-primary">
              Listo: tu contraseña quedó cambiada y las demás sesiones abiertas se cerraron.
            </p>
          )}
          <div>
            <Boton type="submit" disabled={cambiar.isPending}>
              Cambiar mi contraseña
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default MiContrasenaScreen
