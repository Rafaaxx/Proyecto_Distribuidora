import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { esquemaMedioPago, type DatosDeMedioPago } from '../../../domain/configuracion/medioPago'
import type { MedioPagoAdmin } from '../../../features/configuracion/api'
import { useCrearMedioPago, useModificarMedioPago } from '../../../features/configuracion/useMediosPagoAdmin'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirErrorDeMedio, estaSinConexion } from './erroresDeMedios'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface MedioPagoDialogoProps {
  /** El medio que se edita; sin él, es un alta. */
  medio?: MedioPagoAdmin
  onCerrar: () => void
}

interface FormularioDeMedio {
  nombre: string
  requiere_referencia: boolean
}

/**
 * Alta y edición de un medio de pago (change 17b, tarea 8.1; D2, D3; TR-09). La edición es un
 * reemplazo completo: conserva el estado (`activo`) que el medio ya tenía; la baja y la
 * reactivación van por su propia confirmación. Sin conexión no se envía (`ONLINE` puro). El
 * reintento del mismo contenido reenvía el mismo `Operation-Id` (INV-06). El servidor valida igual.
 */
export function MedioPagoDialogo({ medio, onCerrar }: MedioPagoDialogoProps) {
  const crear = useCrearMedioPago()
  const modificar = useModificarMedioPago()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<FormularioDeMedio, unknown, DatosDeMedioPago>({
    resolver: zodResolver(esquemaMedioPago),
    defaultValues: { nombre: medio?.nombre ?? '', requiere_referencia: medio?.requiere_referencia ?? false },
  })
  const nombre = useWatch({ control, name: 'nombre' })
  const requiereReferencia = useWatch({ control, name: 'requiere_referencia' })
  const operationId = useOperationIdDeEnvio({ id: medio?.id ?? null, nombre: nombre.trim(), requiereReferencia })
  const enCurso = crear.isPending || modificar.isPending

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      if (medio) {
        await modificar.mutateAsync({
          medioPagoId: medio.id,
          ...datos,
          activo: medio.activo,
          operationId: operationId.obtener(),
        })
      } else {
        await crear.mutateAsync({ ...datos, operationId: operationId.obtener() })
      }
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError('root', { message: describirErrorDeMedio(falla) })
    }
  })

  return (
    <Dialogo abierto titulo={medio ? 'Editar medio de pago' : 'Nuevo medio de pago'} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="medio-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="medio-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        <Campo id="medio-referencia" etiqueta="Pide referencia" ayuda="mediosPago.requiereReferencia">
          <input id="medio-referencia" type="checkbox" className="h-4 w-4 self-start" {...register('requiere_referencia')} />
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
