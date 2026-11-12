import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { esquemaLogin, type DatosLogin } from '../../../domain/identidad/loginSchema'
import { iniciarSesionConContrasena } from '../../../features/identidad/login'
import { useConectado } from '../../../lib/conexion'

/**
 * Inicio de sesión propio de `/ruta` (change 21, `design.md` D12; SEG-01, SEG-02, ADR-018).
 * Usa el mismo inicio de sesión del servidor que `/admin` (`features/identidad/login`) y envía el
 * identificador del dispositivo, sin importar nada de `areas/admin` ni usar TanStack Query.
 */
const NOMBRE_DISPOSITIVO_RUTA = 'Teléfono de ruta'

export type MotivoDeLogin = 'bloqueado' | 'sesion_vencida' | 'cerrada'

const TEXTO_DEL_MOTIVO: Record<MotivoDeLogin, string> = {
  bloqueado: 'Se agotaron los intentos del PIN. Iniciá sesión de nuevo para definir un PIN nuevo.',
  sesion_vencida: 'Tu sesión venció. Iniciá sesión de nuevo; tus datos en el teléfono se conservan.',
  cerrada: 'Cerraste la sesión.',
}

export interface LoginRutaScreenProps {
  onIniciada: () => void
  motivo?: MotivoDeLogin
}

export function LoginRutaScreen({ onIniciada, motivo }: LoginRutaScreenProps) {
  const conectado = useConectado()
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<DatosLogin>({ resolver: zodResolver(esquemaLogin) })

  const alEnviar = handleSubmit(async (datos) => {
    setEnviando(true)
    setError(null)
    try {
      await iniciarSesionConContrasena(datos, NOMBRE_DISPOSITIVO_RUTA)
      onIniciada()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo iniciar sesión.')
    } finally {
      setEnviando(false)
    }
  })

  const clasesInput =
    'rounded-md border border-border px-2 py-2 text-base focus:outline-none focus:ring-2 focus:ring-primary/40'

  return (
    <main className="flex min-h-dvh items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-6 shadow-sm">
        <h1 className="mb-2 text-lg font-semibold text-primary">Iniciar sesión</h1>
        {motivo && <p className="mb-3 text-sm text-primary">{TEXTO_DEL_MOTIVO[motivo]}</p>}
        {!conectado && (
          <Alert className="mb-3">Iniciar sesión requiere conexión. Volvé a intentar cuando tengas señal.</Alert>
        )}
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

          <Boton type="submit" disabled={!conectado || enviando} className="w-full">
            Iniciar sesión
          </Boton>

          {error && <Alert>{error}</Alert>}
        </form>
      </div>
    </main>
  )
}

export default LoginRutaScreen
