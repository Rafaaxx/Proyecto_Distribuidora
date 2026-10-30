import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { esquemaEdicionDeUsuario, type DatosDeEdicionDeUsuario } from '../../../domain/identidad/usuarios'
import { useModificarUsuario } from '../../../features/identidad/useUsuariosAdmin'
import type { UsuarioDetalle } from '../../../features/identidad/usuariosApi'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeDatos {
  nombre: string
  email: string
}

/** Nombre y email del usuario (change 20b, D9). El nombre de inicio de sesión no se cambia. */
export function FichaDatos({ usuario }: { usuario: UsuarioDetalle }) {
  const modificar = useModificarUsuario()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors, isSubmitSuccessful },
  } = useForm<FormularioDeDatos, unknown, DatosDeEdicionDeUsuario>({
    resolver: zodResolver(esquemaEdicionDeUsuario),
    defaultValues: { nombre: usuario.nombre, email: usuario.email ?? '' },
  })
  const escrito = useWatch({ control })
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, nombre: escrito.nombre?.trim(), email: escrito.email?.trim() })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await modificar.mutateAsync({ usuarioId: usuario.id, ...datos, operationId: operationId.obtener() })
      operationId.completar()
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  return (
    <Card>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-3" aria-label="Datos del usuario">
        <h2 className="text-base font-semibold text-primary">Datos</h2>
        <p className="text-sm text-primary/70">Nombre de usuario: {usuario.usuario} (no se puede cambiar).</p>
        <Campo id="ficha-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="ficha-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        <Campo id="ficha-email" etiqueta="Email (opcional)" error={errors.email?.message}>
          <input id="ficha-email" type="email" className={CLASE_CONTROL} {...register('email')} />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        {isSubmitSuccessful && !errors.root && (
          <p role="status" className="text-sm text-primary">
            Listo: los datos quedaron guardados.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={modificar.isPending}>
            Guardar datos
          </Boton>
        </div>
      </form>
    </Card>
  )
}
