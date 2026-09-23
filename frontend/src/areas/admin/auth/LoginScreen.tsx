import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { esquemaLogin, type DatosLogin } from '../../../domain/identidad/loginSchema'
import { useLogin } from './useLogin'

/**
 * Pantalla de inicio de sesión de `/admin` (tarea 13.4). React Hook Form +
 * Zod (`CLAUDE.md` §2); la validación vive en `domain/identidad/loginSchema.ts`,
 * este componente solo la conecta al formulario y muestra el resultado.
 */
export function LoginScreen() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<DatosLogin>({ resolver: zodResolver(esquemaLogin) })
  const login = useLogin()
  const navigate = useNavigate()

  const alEnviar = handleSubmit((datos) => {
    login.mutate(datos, {
      onSuccess: () => navigate('/admin/dispositivos'),
    })
  })

  const clasesInput =
    'rounded-md border border-border px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40'

  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-6 shadow-sm">
        <h1 className="mb-4 text-lg font-semibold text-primary">Iniciar sesión</h1>
        <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
          <Campo id="organizacionSlug" etiqueta="Organización" error={errors.organizacionSlug?.message}>
            <input
              id="organizacionSlug"
              autoComplete="organization"
              className={clasesInput}
              {...register('organizacionSlug')}
            />
          </Campo>

          <Campo id="usuario" etiqueta="Usuario" error={errors.usuario?.message}>
            <input id="usuario" autoComplete="username" className={clasesInput} {...register('usuario')} />
          </Campo>

          <Campo id="contrasena" etiqueta="Contraseña" error={errors.contrasena?.message}>
            <input
              id="contrasena"
              type="password"
              autoComplete="current-password"
              className={clasesInput}
              {...register('contrasena')}
            />
          </Campo>

          <Boton type="submit" disabled={login.isPending} className="w-full">
            Iniciar sesión
          </Boton>

          {login.isError && <Alert>{login.error.message}</Alert>}
        </form>
      </div>
    </main>
  )
}

export default LoginScreen
