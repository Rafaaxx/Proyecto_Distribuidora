import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { esquemaAltaDeUsuario, rolesAsignables, type DatosDeAltaDeUsuario } from '../../../domain/identidad/usuarios'
import { useSecretoEfimero } from '../../../features/identidad/usePin'
import { useRolesConPermisos } from '../../../features/identidad/useRoles'
import { useCrearUsuario } from '../../../features/identidad/useUsuariosAdmin'
import type { DatosDeAltaParaApi } from '../../../features/identidad/usuariosApi'
import { generarOperationId } from '../../../lib/api/operationId'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface FormularioDeAlta {
  usuario: string
  nombre: string
  email: string
  rol_id: string
  password: string
  confirmacion: string
}

const VALORES_INICIALES: FormularioDeAlta = { usuario: '', nombre: '', email: '', rol_id: '', password: '', confirmacion: '' }

/**
 * Alta de un usuario (change 20b, tarea 10.1; D9, D8; ADR-056). Contraseña con confirmación (la
 * confirmación es solo de interfaz). Los campos de contraseña se borran al enviar y la contraseña
 * viaja por una referencia efímera: no entra a la caché de consultas ni al almacenamiento. Como
 * un rechazo de este comando no deja fila de comando, el reintento con los datos corregidos
 * reenvía el mismo `Operation-Id` (INV-06). El rol se elige entre los activos.
 */
export function UsuarioAltaScreen() {
  const navigate = useNavigate()
  const roles = useRolesConPermisos()
  const secretos = useSecretoEfimero<DatosDeAltaParaApi>()
  const crear = useCrearUsuario(() => secretos.ref.current)
  const [operationId, setOperationId] = useState(generarOperationId)
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<FormularioDeAlta, unknown, DatosDeAltaDeUsuario>({
    resolver: zodResolver(esquemaAltaDeUsuario),
    defaultValues: VALORES_INICIALES,
  })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    // La contraseña sale de la pantalla apenas se entrega.
    setValue('password', '')
    setValue('confirmacion', '')
    try {
      const creado = await secretos.usar(datos, () => crear.mutateAsync({ operationId }))
      setOperationId(generarOperationId())
      navigate(`/admin/usuarios/${creado.id}`)
    } catch (falla) {
      setError('root', { message: describirErrorDeUsuarios(falla) })
    }
  })

  const rolesActivos = rolesAsignables(roles.data ?? [])

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Nuevo usuario"
        acciones={
          <Link to="/admin/usuarios" className="text-sm text-primary/70 hover:text-primary hover:underline">
            Volver al listado
          </Link>
        }
      />
      <Card>
        <form onSubmit={alEnviar} noValidate autoComplete="off" className="flex flex-col gap-4">
          <Campo id="alta-usuario" etiqueta="Nombre de usuario" error={errors.usuario?.message}>
            <input id="alta-usuario" autoComplete="off" className={CLASE_CONTROL} {...register('usuario')} />
          </Campo>
          <Campo id="alta-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
            <input id="alta-nombre" className={CLASE_CONTROL} {...register('nombre')} />
          </Campo>
          <Campo id="alta-email" etiqueta="Email (opcional)" error={errors.email?.message}>
            <input id="alta-email" type="email" className={CLASE_CONTROL} {...register('email')} />
          </Campo>
          <Campo id="alta-rol" etiqueta="Rol" error={errors.rol_id?.message}>
            <select id="alta-rol" className={CLASE_CONTROL} {...register('rol_id')}>
              <option value="">Elegí un rol</option>
              {rolesActivos.map((rol) => (
                <option key={rol.id} value={rol.id}>
                  {rol.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="alta-password" etiqueta="Contraseña" error={errors.password?.message}>
            <input id="alta-password" type="password" autoComplete="new-password" className={CLASE_CONTROL} {...register('password')} />
          </Campo>
          <Campo id="alta-confirmacion" etiqueta="Repetí la contraseña" error={errors.confirmacion?.message}>
            <input
              id="alta-confirmacion"
              type="password"
              autoComplete="new-password"
              className={CLASE_CONTROL}
              {...register('confirmacion')}
            />
          </Campo>
          {errors.root?.message && <Alert>{errors.root.message}</Alert>}
          <div className="flex gap-2">
            <Boton type="submit" disabled={crear.isPending}>
              Crear usuario
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default UsuarioAltaScreen
