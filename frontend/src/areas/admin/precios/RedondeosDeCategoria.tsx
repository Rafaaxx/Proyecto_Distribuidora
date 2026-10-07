import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  DIRECCIONES_REDONDEO,
  ETIQUETA_DE_DIRECCION,
  esquemaRedondeoCategoria,
  type DatosRedondeoCategoria,
  type DatosRedondeoCategoriaEntrada,
} from '../../../domain/precios/listaSchema'
import { descripcionDeRedondeo } from '../../../domain/precios/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { RedondeoCategoria } from '../../../features/precios/api'
import { useDefinirRedondeoDeCategoria } from '../../../features/precios/hooks'
import { describirError } from './errores'
import { SelectorDeCategoriaDeRedondeo } from './SelectorDeEntidad'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

/**
 * Sobrescrituras de redondeo por categoría de una lista (change 13, tarea 13.1; PRC-14, D9).
 * Definir, editar y desactivar solo con `GESTIONAR_LISTAS`. A lo sumo una por categoría: definir
 * de nuevo la misma categoría actualiza la existente.
 */
export function RedondeosDeCategoria({
  listaId,
  redondeos,
}: {
  listaId: string
  redondeos: readonly RedondeoCategoria[]
}) {
  const definir = useDefinirRedondeoDeCategoria()
  const {
    register,
    handleSubmit,
    setError,
    reset,
    setValue,
    formState: { errors },
  } = useForm<DatosRedondeoCategoriaEntrada, unknown, DatosRedondeoCategoria>({
    resolver: zodResolver(esquemaRedondeoCategoria),
    defaultValues: { categoria_id: '', multiplo: '', direccion: 'ARRIBA' },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await definir.mutateAsync({
        listaId,
        categoriaId: datos.categoria_id,
        multiplo: datos.multiplo,
        direccion: datos.direccion,
        activo: true,
      })
      reset({ categoria_id: '', multiplo: '', direccion: 'ARRIBA' })
    } catch (error) {
      setError('root', { message: describirError(error).mensaje })
    }
  })

  const desactivar = async (redondeo: RedondeoCategoria) => {
    try {
      await definir.mutateAsync({
        listaId,
        categoriaId: redondeo.categoria_id,
        multiplo: redondeo.multiplo,
        direccion: redondeo.direccion as DatosRedondeoCategoria['direccion'],
        activo: false,
      })
    } catch (error) {
      setError('root', { message: describirError(error).mensaje })
    }
  }

  const editar = (redondeo: RedondeoCategoria) => {
    setValue('categoria_id', redondeo.categoria_id)
    setValue('multiplo', redondeo.multiplo)
    setValue('direccion', redondeo.direccion as DatosRedondeoCategoria['direccion'])
  }

  const columnas: ColumnaTabla<RedondeoCategoria>[] = [
    { clave: 'categoria', encabezado: 'Categoría', render: (r) => r.categoria_nombre ?? r.categoria_id },
    { clave: 'redondeo', encabezado: 'Redondeo', render: (r) => descripcionDeRedondeo(r.multiplo, r.direccion) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (r) => <Badge variante={r.activo ? 'positivo' : 'negativo'}>{r.activo ? 'Activo' : 'Inactivo'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (r) => (
        <SiTienePermiso permiso="GESTIONAR_LISTAS">
          <div className="flex gap-2">
            <Boton variante="secundario" onClick={() => editar(r)}>
              Editar redondeo
            </Boton>
            {r.activo && (
              <Boton variante="secundario" disabled={definir.isPending} onClick={() => void desactivar(r)}>
                Quitar redondeo
              </Boton>
            )}
          </div>
        </SiTienePermiso>
      ),
    },
  ]

  return (
    <section className="flex flex-col gap-3" aria-labelledby="titulo-redondeos">
      <h2 id="titulo-redondeos" className="text-base font-semibold text-primary">
        Redondeo por categoría
      </h2>
      <p className="text-sm text-primary/70">
        Una categoría puede redondear distinto de la lista (la sobrescritura activa de la categoría del producto
        manda).
      </p>
      {redondeos.length === 0 ? (
        <p className="text-sm text-primary/70">Ninguna categoría sobrescribe el redondeo de la lista.</p>
      ) : (
        <Card>
          <Tabla
            filas={[...redondeos]}
            columnas={columnas}
            obtenerClave={(r) => r.id}
            etiqueta="Redondeo por categoría"
          />
        </Card>
      )}
      <SiTienePermiso permiso="GESTIONAR_LISTAS">
        <Card>
          <form onSubmit={alEnviar} noValidate className="flex flex-wrap items-end gap-3">
            <Campo id="redondeo-categoria" etiqueta="Categoría del redondeo" error={errors.categoria_id?.message}>
              <SelectorDeCategoriaDeRedondeo id="redondeo-categoria" registro={register('categoria_id')} />
            </Campo>
            <Campo id="redondeo-multiplo" etiqueta="Múltiplo del redondeo" error={errors.multiplo?.message}>
              <input id="redondeo-multiplo" inputMode="decimal" className={CLASE_CONTROL} {...register('multiplo')} />
            </Campo>
            <Campo
              id="redondeo-direccion"
              etiqueta="Dirección del redondeo de la categoría"
              error={errors.direccion?.message}
            >
              <select id="redondeo-direccion" className={CLASE_CONTROL} {...register('direccion')}>
                {DIRECCIONES_REDONDEO.map((direccion) => (
                  <option key={direccion} value={direccion}>
                    {ETIQUETA_DE_DIRECCION[direccion]}
                  </option>
                ))}
              </select>
            </Campo>
            <Boton type="submit" disabled={definir.isPending}>
              Guardar redondeo
            </Boton>
          </form>
          {errors.root?.message && <Alert className="mt-3">{errors.root.message}</Alert>}
        </Card>
      </SiTienePermiso>
    </section>
  )
}
