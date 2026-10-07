import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, useWatch } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import {
  esquemaPrecioManual,
  precioParaApi,
  type DatosPrecioManual,
  type DatosPrecioManualEntrada,
} from '../../../domain/precios/precioManualSchema'
import { useFijarPrecioManual } from '../../../features/precios/hooks'
import { campoDePrecioParaCodigo } from '../../../features/precios/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'

export interface ProductoAFijar {
  productoId: string
  nombre: string
}

interface PrecioManualDialogoProps {
  listaId: string
  versionId: string
  producto: ProductoAFijar | null
  onCerrar: () => void
}

/**
 * Fija el precio manual de un producto en el borrador (change 13, tarea 13.2; D7): importe mayor
 * que cero con dos decimales, que no se redondea con la regla de la lista. El `Operation-Id` se
 * conserva mientras el importe no cambia y el envío no se completó (INV-06): el reintento tras
 * un error de red reenvía la misma operación. Sin conexión no se envía nada.
 */
export function PrecioManualDialogo({ listaId, versionId, producto, onCerrar }: PrecioManualDialogoProps) {
  if (producto === null) return null
  return (
    <FormularioDePrecio
      key={producto.productoId}
      listaId={listaId}
      versionId={versionId}
      producto={producto}
      onCerrar={onCerrar}
    />
  )
}

function FormularioDePrecio({
  listaId,
  versionId,
  producto,
  onCerrar,
}: Omit<PrecioManualDialogoProps, 'producto'> & { producto: ProductoAFijar }) {
  const fijar = useFijarPrecioManual()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<DatosPrecioManualEntrada, unknown, DatosPrecioManual>({
    resolver: zodResolver(esquemaPrecioManual),
    defaultValues: { precio_final: '' },
  })
  const escrito = useWatch({ control, name: 'precio_final' })
  const operationId = useOperationIdDeEnvio({ listaId, versionId, productoId: producto.productoId, precio: escrito })

  const alEnviar = handleSubmit(async (datos) => {
    if (estaSinConexion()) {
      setError('root', { message: AVISO_SIN_CONEXION })
      return
    }
    try {
      await fijar.mutateAsync({
        listaId,
        versionId,
        productoId: producto.productoId,
        precio_final: precioParaApi(datos.precio_final),
        operationId: operationId.obtener(),
      })
      operationId.completar()
      onCerrar()
    } catch (error) {
      const { codigo, mensaje } = describirError(error)
      const campo = codigo === null ? null : campoDePrecioParaCodigo(codigo)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <Dialogo abierto titulo={`Precio manual de ${producto.nombre}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary/70">
          El precio manual es el precio final de la lista por la presentación de referencia: no se redondea con la
          regla de la lista y se conserva al regenerar el borrador.
        </p>
        <Campo id="precio-manual" etiqueta="Precio manual" error={errors.precio_final?.message}>
          <input
            id="precio-manual"
            inputMode="decimal"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('precio_final')}
          />
        </Campo>
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={fijar.isPending}>
            Guardar precio
          </Boton>
          <Boton type="button" variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
