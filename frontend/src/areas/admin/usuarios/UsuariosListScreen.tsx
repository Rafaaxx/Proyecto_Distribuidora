import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { describirTope } from '../../../domain/identidad/topes'
import { useRolesConPermisos } from '../../../features/identidad/useRoles'
import { useUsuariosDetalle } from '../../../features/identidad/useUsuariosAdmin'
import type { FiltrosDeUsuarios, UsuarioDetalle } from '../../../features/identidad/usuariosApi'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

function estadoDeFiltro(valor: string | null): FiltrosDeUsuarios['estado'] {
  return valor === 'ACTIVO' || valor === 'INACTIVO' ? valor : undefined
}

/**
 * Listado de usuarios (change 20b, tarea 10.1; D16): nombre, usuario, rol, estado y tope propio,
 * con filtro por estado, rol y "solo con tope propio". Los filtros viven en la dirección, así
 * "Topes por rol" puede abrir el listado ya filtrado. Sin lógica de negocio.
 */
export function UsuariosListScreen() {
  const navigate = useNavigate()
  const [parametros, setParametros] = useSearchParams()
  const estado = estadoDeFiltro(parametros.get('estado'))
  const rolId = parametros.get('rol_id') ?? ''
  const conTopePropio = parametros.get('con_tope_propio') === 'true'

  const usuarios = useUsuariosDetalle({ estado, rolId: rolId || undefined, conTopePropio })
  const roles = useRolesConPermisos()

  const cambiarFiltro = (clave: string, valor: string | null) => {
    const siguientes = new URLSearchParams(parametros)
    if (valor === null || valor === '') siguientes.delete(clave)
    else siguientes.set(clave, valor)
    setParametros(siguientes, { replace: true })
  }

  const columnas: ColumnaTabla<UsuarioDetalle>[] = [
    {
      clave: 'nombre',
      encabezado: 'Nombre',
      render: (u) => (
        <Link to={`/admin/usuarios/${u.id}`} className="font-medium text-primary hover:underline">
          {u.nombre}
        </Link>
      ),
    },
    { clave: 'usuario', encabezado: 'Usuario', render: (u) => u.usuario },
    {
      clave: 'rol',
      encabezado: 'Rol',
      render: (u) => (
        <div className="flex items-center gap-2">
          <span>{u.rol_nombre}</span>
          {!u.rol_activo && <Badge variante="negativo">Rol de baja</Badge>}
        </div>
      ),
    },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (u) => (
        <Badge variante={u.estado === 'ACTIVO' ? 'positivo' : 'negativo'}>{u.estado === 'ACTIVO' ? 'Activo' : 'De baja'}</Badge>
      ),
    },
    {
      clave: 'tope',
      encabezado: 'Tope propio',
      render: (u) => (u.tope_descuento_override === null ? '—' : describirTope(u.tope_descuento_override)),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Usuarios"
        acciones={
          <Link
            to="/admin/usuarios/nuevo"
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Nuevo usuario
          </Link>
        }
      />
      <form
        role="search"
        onSubmit={(evento) => evento.preventDefault()}
        className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface p-3"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-estado-usuarios" className="text-sm text-primary">
            Estado
          </label>
          <select
            id="filtro-estado-usuarios"
            className={CLASE_CONTROL}
            value={estado ?? ''}
            onChange={(evento) => cambiarFiltro('estado', evento.target.value)}
          >
            <option value="">Todos</option>
            <option value="ACTIVO">Activos</option>
            <option value="INACTIVO">De baja</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="filtro-rol-usuarios" className="text-sm text-primary">
            Rol
          </label>
          <select
            id="filtro-rol-usuarios"
            className={CLASE_CONTROL}
            value={rolId}
            onChange={(evento) => cambiarFiltro('rol_id', evento.target.value)}
          >
            <option value="">Todos los roles</option>
            {(roles.data ?? []).map((rol) => (
              <option key={rol.id} value={rol.id}>
                {rol.nombre}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 pb-1">
          <input
            id="filtro-tope-propio"
            type="checkbox"
            className="h-4 w-4"
            checked={conTopePropio}
            onChange={(evento) => cambiarFiltro('con_tope_propio', evento.target.checked ? 'true' : null)}
          />
          <label htmlFor="filtro-tope-propio" className="text-sm text-primary">
            Solo con tope propio
          </label>
        </div>
      </form>
      {usuarios.isPending && <p>Cargando…</p>}
      {usuarios.isError && <Alert>No se pudieron obtener los usuarios.</Alert>}
      {usuarios.isSuccess && usuarios.data.length === 0 && (
        <p className="text-sm text-primary/70">No hay usuarios que coincidan con el filtro.</p>
      )}
      {usuarios.isSuccess && usuarios.data.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <Tabla
            filas={usuarios.data}
            columnas={columnas}
            obtenerClave={(u) => u.id}
            onFilaClick={(u) => navigate(`/admin/usuarios/${u.id}`)}
            etiqueta="Usuarios"
          />
        </Card>
      )}
    </main>
  )
}

export default UsuariosListScreen
