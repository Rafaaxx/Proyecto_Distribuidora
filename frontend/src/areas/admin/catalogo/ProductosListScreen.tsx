import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { PermisoRequeridoCatalogoError } from '../../../features/catalogo/errores'
import { useCategorias, useMarcas, useProductos } from '../../../features/catalogo/useListados'
import type { Producto } from '../../../features/catalogo/api'

const SIN_PERMISO_DE_CATALOGO = 'No tenés permiso para gestionar el catálogo.'

/**
 * Listado de productos de `/admin/catalogo` (tarea 10.4). Búsqueda por
 * texto, filtro por categoría/marca/activo y "cargar más" (cursor,
 * `useInfiniteQuery` de `useListados.ts`, tarea 10.2).
 *
 * Qué se muestra lo decide **solo** la consulta de sesión `['yo']`, con el
 * mecanismo compartido `<SiTienePermiso>` (tarea 8.2 del change 06b,
 * `design.md` D4-A / **B2**): sin `GESTIONAR_CATALOGO` los hijos no se
 * montan, así que la pantalla no pide productos, categorías ni marcas para
 * averiguar si el usuario puede verlos.
 *
 * El 403 del servidor (`PermisoRequeridoCatalogoError`) se sigue
 * tratando, pero **solo como red de seguridad**: pasa cuando el permiso se
 * quitó del rol entre dos renovaciones del access token. En ese caso se
 * muestra la falta de permiso sin listado ni acciones de escritura, y no un
 * error genérico (SEG-06: el servidor sigue validando cada petición).
 */
export function ProductosListScreen() {
  return (
    <SiTienePermiso permiso="GESTIONAR_CATALOGO" fallback={<CatalogoSinPermiso />}>
      <ProductosListado />
    </SiTienePermiso>
  )
}

/** Estado sin permiso (y red de seguridad del 403): mismo texto en los dos
 * casos, para que el mensaje no revele por qué el usuario no ve la
 * pantalla. */
function CatalogoSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Productos" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_CATALOGO}</p>
    </main>
  )
}

/** Componente interno: es el único que consulta y filtra. Al vivir dentro
 * de `<SiTienePermiso>`, sin permiso nunca se monta y por eso no dispara
 * ninguna consulta (**B2**). */
function ProductosListado() {
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

  if (productos.isError) {
    if (productos.error instanceof PermisoRequeridoCatalogoError) {
      return <CatalogoSinPermiso />
    }
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Productos" />
        <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          No se pudieron obtener los productos.
        </p>
      </main>
    )
  }

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
