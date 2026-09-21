import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

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

  return (
    <main>
      <h1>Iniciar sesión</h1>
      <form onSubmit={alEnviar} noValidate>
        <div>
          <label htmlFor="organizacionSlug">Organización</label>
          <input id="organizacionSlug" autoComplete="organization" {...register('organizacionSlug')} />
          {errors.organizacionSlug && <p role="alert">{errors.organizacionSlug.message}</p>}
        </div>

        <div>
          <label htmlFor="usuario">Usuario</label>
          <input id="usuario" autoComplete="username" {...register('usuario')} />
          {errors.usuario && <p role="alert">{errors.usuario.message}</p>}
        </div>

        <div>
          <label htmlFor="contrasena">Contraseña</label>
          <input
            id="contrasena"
            type="password"
            autoComplete="current-password"
            {...register('contrasena')}
          />
          {errors.contrasena && <p role="alert">{errors.contrasena.message}</p>}
        </div>

        <button type="submit" disabled={login.isPending}>
          Iniciar sesión
        </button>

        {login.isError && <p role="alert">{login.error.message}</p>}
      </form>
    </main>
  )
}

export default LoginScreen
