import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  DIRECCIONES_REDONDEO,
  ETIQUETA_DE_DIRECCION,
  esquemaListaEdicion,
  type DatosListaEdicion,
  type DatosListaEdicionEntrada,
} from '../../../domain/precios/listaSchema'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ErrorDePrecios } from '../../../features/precios/errores'
import { useCrearLista, useListaDetalle, useModificarLista } from '../../../features/precios/hooks'
import { campoDeListaParaCodigo } from '../../../features/precios/mapaErrorACampo'
import { describirError } from './errores'
import { PreciosSinPermiso, SIN_PERMISO_PARA_GESTIONAR_LISTAS } from './PreciosSinPermiso'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const EXPLICACION_DE_LISTA_EN_USO =
  'No se puede desactivar: la lista es la predeterminada de la organización o está asignada a clientes. Elegí otra predeterminada o reasigná esos clientes primero.'

/**
 * Alta y edición de una lista de precios (change 13, tarea 13.1; PRC-01, D9, D11). Sin
 * `listaId` en la ruta (`/admin/precios/nueva`) es el alta; con `listaId`
 * (`/admin/precios/:listaId/editar`), la edición. Solo con `GESTIONAR_LISTAS`: sin permiso los
 * formularios no se montan. El servidor valida igual (SEG-06).
 */
export function ListaFormScreen() {
  const { listaId } = useParams<{ listaId?: string }>()
  return (
    <SiTienePermiso
      permiso="GESTIONAR_LISTAS"
      fallback={<PreciosSinPermiso titulo="Lista de precios" mensaje={SIN_PERMISO_PARA_GESTIONAR_LISTAS} />}
    >
      {listaId ? <ListaEdicion listaId={listaId} /> : <ListaAlta />}
    </SiTienePermiso>
  )
}

interface FormularioDeListaProps {
  valores: DatosListaEdicionEntrada
  esEdicion: boolean
  enviando: boolean
  textoDelBoton: string
  rutaDeSalida: string
  /** Guarda la lista; rechaza con el error de la mutación. */
  onGuardar: (datos: DatosListaEdicion) => Promise<void>
}

function FormularioDeLista({
  valores,
  esEdicion,
  enviando,
  textoDelBoton,
  rutaDeSalida,
  onGuardar,
}: FormularioDeListaProps) {
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<DatosListaEdicionEntrada, unknown, DatosListaEdicion>({
    resolver: zodResolver(esquemaListaEdicion),
    values: valores,
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await onGuardar(datos)
    } catch (error) {
      const { codigo, mensaje } = describirError(error)
      const campo = codigo === null ? null : campoDeListaParaCodigo(codigo)
      if (campo === 'activo') {
        // La lista sigue como estaba: el formulario vuelve a su estado guardado.
        setValue('activo', valores.activo)
        setError('activo', { message: EXPLICACION_DE_LISTA_EN_USO })
        return
      }
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <Card>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="nombre" className={CLASE_CONTROL} {...register('nombre')} />
        </Campo>
        <Campo id="redondeo_multiplo" etiqueta="Múltiplo de redondeo" error={errors.redondeo_multiplo?.message}>
          <input id="redondeo_multiplo" inputMode="decimal" className={CLASE_CONTROL} {...register('redondeo_multiplo')} />
        </Campo>
        <Campo id="redondeo_direccion" etiqueta="Dirección del redondeo" error={errors.redondeo_direccion?.message}>
          <select id="redondeo_direccion" className={CLASE_CONTROL} {...register('redondeo_direccion')}>
            {DIRECCIONES_REDONDEO.map((direccion) => (
              <option key={direccion} value={direccion}>
                {ETIQUETA_DE_DIRECCION[direccion]}
              </option>
            ))}
          </select>
        </Campo>
        {esEdicion && (
          <Campo id="activo" etiqueta="Activa" error={errors.activo?.message}>
            <input id="activo" type="checkbox" className="h-4 w-4 self-start" {...register('activo')} />
          </Campo>
        )}
        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <div className="flex gap-2">
          <Boton type="submit" disabled={enviando}>
            {textoDelBoton}
          </Boton>
          <Link to={rutaDeSalida} className="text-sm text-primary/70 hover:text-primary">
            {esEdicion ? 'Volver' : 'Cancelar'}
          </Link>
        </div>
      </form>
    </Card>
  )
}

function ListaAlta() {
  const navigate = useNavigate()
  const crear = useCrearLista()

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nueva lista de precios" />
      <FormularioDeLista
        valores={{ nombre: '', redondeo_multiplo: '100', redondeo_direccion: 'ARRIBA', activo: true }}
        esEdicion={false}
        enviando={crear.isPending}
        textoDelBoton="Crear lista"
        rutaDeSalida="/admin/precios"
        onGuardar={async ({ nombre, redondeo_multiplo, redondeo_direccion }) => {
          const lista = await crear.mutateAsync({ nombre, redondeo_multiplo, redondeo_direccion })
          navigate(`/admin/precios/${lista.id}`)
        }}
      />
    </main>
  )
}

function ListaEdicion({ listaId }: { listaId: string }) {
  const navigate = useNavigate()
  const lista = useListaDetalle(listaId)
  const modificar = useModificarLista()

  if (lista.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }
  if (lista.isError) {
    const noExiste = lista.error instanceof ErrorDePrecios && lista.error.estado === 404
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Lista de precios" />
        <Alert>{noExiste ? 'No se encontró la lista.' : 'No se pudo obtener la lista.'}</Alert>
      </main>
    )
  }

  const detalle = lista.data
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={detalle.nombre} />
      <FormularioDeLista
        valores={{
          nombre: detalle.nombre,
          redondeo_multiplo: detalle.redondeo_multiplo,
          redondeo_direccion: detalle.redondeo_direccion as DatosListaEdicionEntrada['redondeo_direccion'],
          activo: detalle.activo,
        }}
        esEdicion
        enviando={modificar.isPending}
        textoDelBoton="Guardar cambios"
        rutaDeSalida={`/admin/precios/${listaId}`}
        onGuardar={async (datos) => {
          await modificar.mutateAsync({ listaId, ...datos })
          navigate(`/admin/precios/${listaId}`)
        }}
      />
    </main>
  )
}

export default ListaFormScreen
