import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla } from '../../../components/ui/Table'
import { PermisoRequeridoCatalogoError } from '../../../features/catalogo/errores'
import { useCategorias, useMarcas, useProductos } from '../../../features/catalogo/useListados'
import type { Producto } from '../../../features/catalogo/api'

/**
 * Listado de productos de `/admin/catalogo` (tarea 10.4). Búsqueda por
 * texto, filtro por categoría/marca/activo y "cargar más" (cursor,
 * `useInfiniteQuery` de `useListados.ts`, tarea 10.2). Ante
 * `PERMISO_REQUERIDO` (403 de `GET /catalogo/productos`, D9) muestra el
 * mismo criterio que `DispositivosScreen`: la interfaz solo refleja la
 * respuesta real del servidor, nunca una copia local del permiso.
 */
export function ProductosListScreen() {
  const [texto, setTexto] = useState('')
  const [categoriaId, setCategoriaId] = useState('')
  const [marcaId, setMarcaId] = useState('')
  const [soloActivos, setSoloActivos] = useState(true)

  const categorias = useCategorias()
  const marcas = useMarcas()
  const productos = useProductos({
    texto: texto.trim() || undefined,
    categoriaId: categoriaId || undefined,
    marcaId: marcaId || undefined,
    activo: soloActivos ? true : undefined,
  })

  const opcionesCategoria = categorias.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const opcionesMarca = marcas.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const filas = productos.data?.pages.flatMap((pagina) => pagina.items) ?? []

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Productos"
        acciones={
          <Link to="/admin/catalogo/categorias-y-marcas" className="text-sm text-primary/70 hover:text-primary hover:underline">
            Categorías y marcas
          </Link>
        }
      />

      <form
        className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface p-3"
        onSubmit={(evento) => evento.preventDefault()}
        role="search"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-texto" className="text-sm text-primary">
            Buscar
          </label>
          <input
            id="filtro-texto"
            type="search"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Código o nombre"
            className="rounded-md border border-border px-2 py-1 text-sm"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-categoria" className="text-sm text-primary">
            Categoría
          </label>
          <select
            id="filtro-categoria"
            value={categoriaId}
            onChange={(evento) => setCategoriaId(evento.target.value)}
            className="rounded-md border border-border px-2 py-1 text-sm"
          >
            <option value="">Todas</option>
            {opcionesCategoria.map((categoria) => (
              <option key={categoria.id} value={categoria.id}>
                {categoria.nombre}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-marca" className="text-sm text-primary">
            Marca
          </label>
          <select
            id="filtro-marca"
            value={marcaId}
            onChange={(evento) => setMarcaId(evento.target.value)}
            className="rounded-md border border-border px-2 py-1 text-sm"
          >
            <option value="">Todas</option>
            {opcionesMarca.map((marca) => (
              <option key={marca.id} value={marca.id}>
                {marca.nombre}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-2 text-sm text-primary">
          <input
            type="checkbox"
            checked={soloActivos}
            onChange={(evento) => setSoloActivos(evento.target.checked)}
          />
          Solo activos
        </label>

        <Link
          to="/admin/catalogo/productos/nuevo"
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Nuevo producto
        </Link>
      </form>

      {productos.isPending && <p className="text-sm text-primary/70">Cargando…</p>}

      {productos.isError &&
        (productos.error instanceof PermisoRequeridoCatalogoError ? (
          <p className="text-sm text-primary/70">No tenés permiso para gestionar el catálogo.</p>
        ) : (
          <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            No se pudieron obtener los productos.
          </p>
        ))}

      {productos.isSuccess && (
        <Card className="overflow-x-auto p-0">
          <Tabla<Producto>
            filas={filas}
            obtenerClave={(producto) => producto.id}
            columnas={[
              {
                clave: 'codigo',
                encabezado: 'Código',
                render: (p) => (
                  <Link to={`/admin/catalogo/productos/${p.id}`} className="block hover:underline">
                    {p.codigo}
                  </Link>
                ),
              },
              {
                clave: 'nombre',
                encabezado: 'Nombre',
                render: (p) => (
                  <Link to={`/admin/catalogo/productos/${p.id}`} className="block hover:underline">
                    {p.nombre}
                  </Link>
                ),
              },
              {
                clave: 'activo',
                encabezado: 'Estado',
                render: (p) => (
                  <Badge variante={p.activo ? 'positivo' : 'neutral'}>{p.activo ? 'Activo' : 'Inactivo'}</Badge>
                ),
              },
              {
                clave: 'editar',
                encabezado: '',
                render: (p) => (
                  <Link
                    to={`/admin/catalogo/productos/${p.id}`}
                    className="text-sm text-primary/70 hover:text-primary hover:underline"
                  >
                    Editar
                  </Link>
                ),
              },
            ]}
          />

          {filas.length === 0 && (
            <p className="px-3 py-3 text-sm text-primary/70">No hay productos que coincidan con la búsqueda.</p>
          )}

          {productos.hasNextPage && (
            <div className="p-3">
              <Boton
                variante="secundario"
                onClick={() => void productos.fetchNextPage()}
                disabled={productos.isFetchingNextPage}
              >
                Cargar más
              </Boton>
            </div>
          )}
        </Card>
      )}
    </main>
  )
}

export default ProductosListScreen
