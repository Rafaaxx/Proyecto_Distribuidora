import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { esquemaMiContrasena, mensajeDeErrorDeUsuarios, type DatosDeMiContrasena } from '../../../domain/identidad/usuarios'
import { cambiarMiContrasena, ErrorDeApiUsuarios } from '../../../features/identidad/usuariosApi'
import { generarOperationId } from '../../../lib/api/operationId'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { useConectado } from '../../../lib/conexion'

/**
 * "Mi contraseña" en `/ruta` (change 21, `design.md` D19; ADR-060, ADR-018, INV-06). Misma regla
 * y mismo comando que en `/admin` (`CONTRASENA_PROPIA_CAMBIAR`, esquema de `domain/identidad`),
 * sin TanStack Query (es del área `/admin`). Solo con conexión. Las contraseñas viven en el
 * formulario, salen de la pantalla al enviar y no se guardan en ningún lado. Un corte de red
 * reenvía el mismo `Operation-Id` en el reintento.
 */
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-2 text-sm'
const AVISO_SIN_CONEXION = 'Cambiar la contraseña requiere conexión. Probá de nuevo cuando tengas señal.'
const MENSAJE_GENERICO = 'No se pudo cambiar la contraseña. Probá de nuevo en unos minutos.'

interface Formulario {
  actual: string
  nueva: string
  confirmacion: string
}

const VACIO: Formulario = { actual: '', nueva: '', confirmacion: '' }

function describirError(falla: unknown): string {
  if (esErrorDeRed(falla)) return AVISO_SIN_CONEXION
  if (falla instanceof ErrorDeApiUsuarios) return mensajeDeErrorDeUsuarios(falla.codigo, falla.message)
  return MENSAJE_GENERICO
}

export function MiContrasenaRutaScreen() {
  const conectado = useConectado()
  const [operationId, setOperationId] = useState(generarOperationId)
  const [hecho, setHecho] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Formulario, unknown, DatosDeMiContrasena>({ resolver: zodResolver(esquemaMiContrasena), defaultValues: VACIO })

  const alEnviar = handleSubmit(async (datos) => {
    setHecho(false)
    if (!navigator.onLine) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    reset(VACIO) // las contraseñas salen de la pantalla apenas se entregan
    setEnviando(true)
    try {
      await cambiarMiContrasena(datos.actual, datos.nueva, operationId)
      setOperationId(generarOperationId()) // el próximo cambio es otra operación
      setHecho(true)
    } catch (falla) {
      setError('root', { message: describirError(falla) })
    } finally {
      setEnviando(false)
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-primary">Mi contraseña</h1>
        <Link to="/ruta/cuenta" className="text-sm underline">
          Volver a Mi cuenta
        </Link>
      </div>
      <p className="text-sm text-primary/70">
        Cambiá la contraseña con la que entrás. Al cambiarla se cierran tus sesiones abiertas en otros dispositivos; esta sigue
        abierta.
      </p>
      {!conectado && <p className="text-sm text-primary/70">Cambiar la contraseña requiere conexión.</p>}
      <Card>
        <form onSubmit={alEnviar} noValidate autoComplete="off" className="flex flex-col gap-3" aria-label="Cambiar mi contraseña">
          <Campo id="mi-contrasena-actual" etiqueta="Tu contraseña actual" error={errors.actual?.message}>
            <input id="mi-contrasena-actual" type="password" autoComplete="current-password" className={CLASE_CONTROL} {...register('actual')} />
          </Campo>
          <Campo id="mi-contrasena-nueva" etiqueta="Contraseña nueva" error={errors.nueva?.message}>
            <input id="mi-contrasena-nueva" type="password" autoComplete="new-password" className={CLASE_CONTROL} {...register('nueva')} />
          </Campo>
          <Campo id="mi-contrasena-confirmacion" etiqueta="Repetí la contraseña nueva" error={errors.confirmacion?.message}>
            <input
              id="mi-contrasena-confirmacion"
              type="password"
              autoComplete="new-password"
              className={CLASE_CONTROL}
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
            <Boton type="submit" disabled={!conectado || enviando}>
              Cambiar mi contraseña
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default MiContrasenaRutaScreen
