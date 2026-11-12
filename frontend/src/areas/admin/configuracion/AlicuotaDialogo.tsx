import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import {
  esquemaAlicuota,
  fraccionAPorcentaje,
  type DatosDeAlicuota,
  type DatosDeAlicuotaEntrada,
} from '../../../domain/configuracion/catalogos'
import type { Alicuota } from '../../../features/configuracion/api'
import { useCrearAlicuota, useModificarAlicuota } from '../../../features/configuracion/useAlicuotasAdmin'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirErrorDeAlicuota, estaSinConexion } from './erroresDeCatalogos'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface AlicuotaDialogoProps {
  /** La alícuota que se edita; sin ella, es un alta. */
  alicuota?: Alicuota
  onCerrar: () => void
}

/**
 * Alta y edición de una alícuota de IVA (change 20c, tarea 7.3; D6, D7; TR-02, INV-03). El
 * porcentaje se escribe como porcentaje y viaja como fracción string de seis decimales; en una
 * alícuota existente se muestra y NO se edita (el servidor responde `VALOR_NO_MODIFICABLE`). La
 * edición es un reemplazo completo que conserva `activo`. Mismo `Operation-Id` al reintentar (INV-06).
 */
export function AlicuotaDialogo({ alicuota, onCerrar }: AlicuotaDialogoProps) {
  const crear = useCrearAlicuota()
  const modificar = useModificarAlicuota()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<DatosDeAlicuotaEntrada, unknown, DatosDeAlicuota>({
    resolver: zodResolver(esquemaAlicuota),
    defaultValues: {
      nombre: alicuota?.nombre ?? '',
      porcentaje: alicuota ? fraccionAPorcentaje(alicuota.valor) : '',
    },
  })
  const nombre = useWatch({ control, name: 'nombre' })
  const porcentaje = useWatch({ control, name: 'porcentaje' })
  const operationId = useOperationIdDeEnvio({ id: alicuota?.id ?? null, nombre: nombre.trim(), porcentaje: porcentaje.trim() })
  const enCurso = crear.isPending || modificar.isPending

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      if (alicuota) {
        await modificar.mutateAsync({
          alicuotaId: alicuota.id,
          nombre: datos.nombre,
          valor: alicuota.valor,
          activo: alicuota.activo,
          operationId: operationId.obtener(),
        })
      } else {
        await crear.mutateAsync({ ...datos, operationId: operationId.obtener() })
      }
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError('root', { message: describirErrorDeAlicuota(falla) })
    }
  })

  return (
    <Dialogo abierto titulo={alicuota ? 'Editar alícuota' : 'Nueva alícuota'} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="alicuota-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="alicuota-nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        <Campo id="alicuota-porcentaje" etiqueta="Porcentaje" ayuda="alicuotas.valor" error={errors.porcentaje?.message}>
          {alicuota ? (
            // Solo se muestra: el valor guardado sigue en el formulario y el servidor no admite cambiarlo (D6).
            <input id="alicuota-porcentaje" className={CLASE_CONTROL} disabled value={fraccionAPorcentaje(alicuota.valor)} readOnly />
          ) : (
            <input id="alicuota-porcentaje" inputMode="decimal" className={CLASE_CONTROL} {...register('porcentaje')} />
          )}
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
