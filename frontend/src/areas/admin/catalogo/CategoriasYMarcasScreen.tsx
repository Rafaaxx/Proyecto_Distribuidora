import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'

import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  esquemaNombreCategoriaOMarca,
  type DatosNombreCategoriaOMarca,
} from '../../../domain/catalogo/categoriaMarcaSchema'
import type { Categoria, Marca } from '../../../features/catalogo/api'
import { ErrorDeCatalogo, PermisoRequeridoCatalogoError } from '../../../features/catalogo/errores'
import { useCategorias, useMarcas } from '../../../features/catalogo/useListados'
import {
  useCrearCategoria,
  useCrearMarca,
  useModificarCategoria,
  useModificarMarca,
} from '../../../features/catalogo/useMutacionesCatalogo'

/**
 * Gestión de categorías y marcas de `/admin/catalogo` (tarea 10.6):
 * listar, crear, renombrar y desactivar/reactivar. `ProductoFormScreen`
 * (tarea 10.5) filtra estos mismos listados a solo `activo` para sus
 * selectores (CAT-05: "los inactivos no se ofrecen en nuevas
 * operaciones").
 */
export function CategoriasYMarcasScreen() {
  return (
    <main className="flex flex-col gap-8">
      <PageHeader titulo="Categorías y marcas" />
      <SeccionCategorias />
      <SeccionMarcas />
    </main>
  )
}

interface FormularioNombreProps {
  valorInicial?: string
  etiquetaBoton: string
  onEnviar: (nombre: string) => Promise<void>
}

function FormularioNombre({ valorInicial = '', etiquetaBoton, onEnviar }: FormularioNombreProps) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<DatosNombreCategoriaOMarca>({
    resolver: zodResolver(esquemaNombreCategoriaOMarca),
    defaultValues: { nombre: valorInicial },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await onEnviar(datos.nombre)
    } catch (error) {
      const mensaje =
        error instanceof ErrorDeCatalogo ? error.message : 'No se pudo completar la operación.'
      setError('nombre', { message: mensaje })
    }
  })

  return (
    <form onSubmit={alEnviar} noValidate className="flex items-end gap-2">
      <Campo id="nombre-formulario" etiqueta="Nombre" error={errors.nombre?.message}>
        <input
          id="nombre-formulario"
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register('nombre')}
        />
      </Campo>
      <Boton type="submit" disabled={isSubmitting}>
        {etiquetaBoton}
      </Boton>
    </form>
  )
}

function SeccionCategorias() {
  const categorias = useCategorias()
  const crear = useCrearCategoria()
  const modificar = useModificarCategoria()
  const [creando, setCreando] = useState(false)
  const [enEdicion, setEnEdicion] = useState<Categoria | null>(null)

  if (categorias.isPending) {
    return <p>Cargando categorías…</p>
  }

  if (categorias.isError) {
    return (
      <p role="alert">
        {categorias.error instanceof PermisoRequeridoCatalogoError
          ? 'No tenés permiso para gestionar el catálogo.'
          : 'No se pudieron obtener las categorías.'}
      </p>
    )
  }

  const items = categorias.data.pages.flatMap((pagina) => pagina.items)

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-primary">Categorías</h2>
        <Boton variante="secundario" onClick={() => setCreando(true)}>
          Nueva categoría
        </Boton>
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 font-medium text-primary">Nombre</th>
              <th className="px-3 py-2 font-medium text-primary">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((categoria) => (
              <tr key={categoria.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2">{categoria.nombre}</td>
                <td className="px-3 py-2">
                  <Badge variante={categoria.activo ? 'positivo' : 'neutral'}>
                    {categoria.activo ? 'Activa' : 'Inactiva'}
                  </Badge>
                </td>
                <td className="flex gap-2 px-3 py-2">
                  <Boton variante="secundario" onClick={() => setEnEdicion(categoria)}>
                    Renombrar
                  </Boton>
                  <Boton
                    variante={categoria.activo ? 'peligro' : 'secundario'}
                    disabled={modificar.isPending}
                    onClick={() =>
                      modificar.mutate({ categoriaId: categoria.id, nombre: categoria.nombre, activo: !categoria.activo })
                    }
                  >
                    {categoria.activo ? 'Desactivar' : 'Reactivar'}
                  </Boton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {modificar.isError && (
        <p role="alert" className="text-sm text-danger">
          {modificar.error instanceof ErrorDeCatalogo ? modificar.error.message : 'No se pudo actualizar la categoría.'}
        </p>
      )}

      <Dialogo abierto={creando} titulo="Nueva categoría" onCerrar={() => setCreando(false)}>
        <FormularioNombre
          etiquetaBoton="Crear"
          onEnviar={async (nombre) => {
            await crear.mutateAsync({ nombre })
            setCreando(false)
          }}
        />
      </Dialogo>

      <Dialogo abierto={enEdicion !== null} titulo="Renombrar categoría" onCerrar={() => setEnEdicion(null)}>
        {enEdicion && (
          <FormularioNombre
            valorInicial={enEdicion.nombre}
            etiquetaBoton="Guardar"
            onEnviar={async (nombre) => {
              await modificar.mutateAsync({ categoriaId: enEdicion.id, nombre, activo: enEdicion.activo })
              setEnEdicion(null)
            }}
          />
        )}
      </Dialogo>
    </section>
  )
}

function SeccionMarcas() {
  const marcas = useMarcas()
  const crear = useCrearMarca()
  const modificar = useModificarMarca()
  const [creando, setCreando] = useState(false)
  const [enEdicion, setEnEdicion] = useState<Marca | null>(null)

  if (marcas.isPending) {
    return <p>Cargando marcas…</p>
  }

  if (marcas.isError) {
    return (
      <p role="alert">
        {marcas.error instanceof PermisoRequeridoCatalogoError
          ? 'No tenés permiso para gestionar el catálogo.'
          : 'No se pudieron obtener las marcas.'}
      </p>
    )
  }

  const items = marcas.data.pages.flatMap((pagina) => pagina.items)

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-primary">Marcas</h2>
        <Boton variante="secundario" onClick={() => setCreando(true)}>
          Nueva marca
        </Boton>
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 font-medium text-primary">Nombre</th>
              <th className="px-3 py-2 font-medium text-primary">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((marca) => (
              <tr key={marca.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2">{marca.nombre}</td>
                <td className="px-3 py-2">
                  <Badge variante={marca.activo ? 'positivo' : 'neutral'}>
                    {marca.activo ? 'Activa' : 'Inactiva'}
                  </Badge>
                </td>
                <td className="flex gap-2 px-3 py-2">
                  <Boton variante="secundario" onClick={() => setEnEdicion(marca)}>
                    Renombrar
                  </Boton>
                  <Boton
                    variante={marca.activo ? 'peligro' : 'secundario'}
                    disabled={modificar.isPending}
                    onClick={() => modificar.mutate({ marcaId: marca.id, nombre: marca.nombre, activo: !marca.activo })}
                  >
                    {marca.activo ? 'Desactivar' : 'Reactivar'}
                  </Boton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {modificar.isError && (
        <p role="alert" className="text-sm text-danger">
          {modificar.error instanceof ErrorDeCatalogo ? modificar.error.message : 'No se pudo actualizar la marca.'}
        </p>
      )}

      <Dialogo abierto={creando} titulo="Nueva marca" onCerrar={() => setCreando(false)}>
        <FormularioNombre
          etiquetaBoton="Crear"
          onEnviar={async (nombre) => {
            await crear.mutateAsync({ nombre })
            setCreando(false)
          }}
        />
      </Dialogo>

      <Dialogo abierto={enEdicion !== null} titulo="Renombrar marca" onCerrar={() => setEnEdicion(null)}>
        {enEdicion && (
          <FormularioNombre
            valorInicial={enEdicion.nombre}
            etiquetaBoton="Guardar"
            onEnviar={async (nombre) => {
              await modificar.mutateAsync({ marcaId: enEdicion.id, nombre, activo: enEdicion.activo })
              setEnEdicion(null)
            }}
          />
        )}
      </Dialogo>
    </section>
  )
}

export default CategoriasYMarcasScreen
