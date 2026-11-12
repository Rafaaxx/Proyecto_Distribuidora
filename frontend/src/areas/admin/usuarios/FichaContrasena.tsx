import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { esquemaContrasenaDeUsuario } from '../../../domain/identidad/usuarios'
import { useSecretoEfimero } from '../../../features/identidad/usePin'
import { useRestablecerContrasena } from '../../../features/identidad/useUsuariosAdmin'
import { generarOperationId } from '../../../lib/api/operationId'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeContrasena {
  contrasena: string
  confirmacion: string
}

/**
 * Restablecer la contraseña de un usuario (change 20b, D8; ADR-018, ADR-056, ADR-057). La
 * contraseña se escribe enmascarada, viaja por una referencia efímera (no entra a la caché de
 * consultas ni al almacenamiento) y los campos se borran al enviar. Un rechazo de este comando no
 * deja fila de comando: el reintento con los datos corregidos reenvía el mismo `Operation-Id`.
 */
export function FichaContrasena({ usuarioId }: { usuarioId: string }) {
  const secretos = useSecretoEfimero<string>()
  const restablecer = useRestablecerContrasena(() => secretos.ref.current)
  const [operationId, setOperationId] = useState(generarOperationId)
  const [hecho, setHecho] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormularioDeContrasena, unknown, { contrasena: string }>({
    resolver: zodResolver(esquemaContrasenaDeUsuario),
    defaultValues: { contrasena: '', confirmacion: '' },
  })

  const alEnviar = handleSubmit(async ({ contrasena }) => {
    setHecho(false)
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    reset({ contrasena: '', confirmacion: '' }) // la contraseña sale de la pantalla apenas se entrega
    try {
      await secretos.usar(contrasena, () => restablecer.mutateAsync({ usuarioId, operationId }))
      setOperationId(generarOperationId())
      setHecho(true)
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <Card>
      <form onSubmit={alEnviar} noValidate autoComplete="off" className="flex flex-col gap-3" aria-label="Restablecer contraseña">
        <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
          Contraseña <Ayuda clave="usuarios.contrasena" />
        </h2>
        <Campo id="ficha-contrasena" etiqueta="Contraseña nueva" error={errors.contrasena?.message}>
          <input
            id="ficha-contrasena"
            type="password"
            autoComplete="new-password"
            className={CLASE_CONTROL}
            {...register('contrasena')}
          />
        </Campo>
        <Campo id="ficha-contrasena-confirmacion" etiqueta="Repetí la contraseña nueva" error={errors.confirmacion?.message}>
          <input
            id="ficha-contrasena-confirmacion"
            type="password"
            autoComplete="new-password"
            className={CLASE_CONTROL}
            {...register('confirmacion')}
          />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        {hecho && !errors.root && (
          <p role="status" className="text-sm text-primary">
            Listo: la contraseña quedó cambiada y sus sesiones abiertas se cerraron.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={restablecer.isPending}>
            Restablecer contraseña
          </Boton>
        </div>
      </form>
    </Card>
  )
}
