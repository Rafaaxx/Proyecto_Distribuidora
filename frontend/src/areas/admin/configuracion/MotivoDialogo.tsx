import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { esquemaMotivo, type AmbitoDeMotivo, type DatosDeMotivo } from '../../../domain/configuracion/catalogos'
import type { MotivoAdmin } from '../../../features/configuracion/api'
import { useCrearMotivo, useModificarMotivo } from '../../../features/configuracion/useMotivosAdmin'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirErrorDeMotivo, estaSinConexion } from './erroresDeCatalogos'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface MotivoDialogoProps {
  /** Ámbito donde se crea el motivo (el que muestra la lista). */
  ambito: AmbitoDeMotivo
  /** El motivo que se edita; sin él, es un alta. */
  motivo?: MotivoAdmin
  onCerrar: () => void
}

interface FormularioDeMotivo {
  nombre: string
}

/**
 * Alta y edición de un motivo (change 20c, tarea 7.2; D2, D3; TR-09). La edición es un reemplazo
 * completo de nombre y estado: conserva el `activo` que el motivo ya tenía y no toca el ámbito (que no
 * cambia después del alta). La baja y la reactivación van por su propia confirmación. Sin conexión no
 * se envía (`ONLINE` puro). El reintento del mismo contenido reenvía el mismo `Operation-Id` (INV-06).
 */
export function MotivoDialogo({ ambito, motivo, onCerrar }: MotivoDialogoProps) {
  const crear = useCrearMotivo()
  const modificar = useModificarMotivo()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<FormularioDeMotivo, unknown, DatosDeMotivo>({
    resolver: zodResolver(esquemaMotivo),
    defaultValues: { nombre: motivo?.nombre ?? '' },
  })
  const nombre = useWatch({ control, name: 'nombre' })
  const operationId = useOperationIdDeEnvio({ id: motivo?.id ?? null, ambito, nombre: nombre.trim() })
  const enCurso = crear.isPending || modificar.isPending

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      if (motivo) {
        await modificar.mutateAsync({
          motivoId: motivo.id,
          nombre: datos.nombre,
          activo: motivo.activo,
          operationId: operationId.obtener(),
        })
      } else {
        await crear.mutateAsync({ ambito, nombre: datos.nombre, operationId: operationId.obtener() })
      }
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError('root', { message: describirErrorDeMotivo(falla) })
    }
  })

  return (
    <Dialogo abierto titulo={motivo ? 'Editar motivo' : 'Nuevo motivo'} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="motivo-nombre" etiqueta="Nombre" ayuda="motivos.nombre" error={errors.nombre?.message}>
          <input id="motivo-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={enCurso}>
            Guardar
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
