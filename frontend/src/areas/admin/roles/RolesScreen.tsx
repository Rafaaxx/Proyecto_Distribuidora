import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { RolConPermisos } from '../../../features/identidad/rolesApi'
import { useCatalogoDePermisos, useRolesConPermisos } from '../../../features/identidad/useRoles'
import { RolPermisosEditor } from './RolPermisosEditor'

const TITULO = 'Roles y permisos'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar usuarios, roles y permisos.</p>
    </main>
  )
}

/**
 * Roles y permisos (change 17b, tarea 9.1, gobernanza crítica, diseño D9-A; spec
 * `identidad/administracion-de-roles`; `01` §19, ADR-011, ADR-017, ADR-053). Lista los roles con su
 * estado, su cantidad de permisos y de usuarios activos; al elegir uno se editan sus permisos
 * agrupados por módulo. Con `ADMIN_USUARIOS` (ADR-027). Solo cambia los permisos de los roles
 * existentes: no crea, desactiva ni borra roles (D7). El servidor valida igual (SEG-06).
 */
export function RolesScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_USUARIOS" fallback={<SinPermiso />}>
      <RolesListado />
    </SiTienePermiso>
  )
}

function RolesListado() {
  const roles = useRolesConPermisos()
  const catalogo = useCatalogoDePermisos()
  const [elegidoId, setElegidoId] = useState<string | null>(null)
  const elegido = roles.data?.find((r) => r.id === elegidoId)

  const columnas: ColumnaTabla<RolConPermisos>[] = [
    { clave: 'rol', encabezado: 'Rol', render: (r) => <span className="font-medium text-primary">{r.nombre}</span> },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (r) => <Badge variante={r.activo ? 'positivo' : 'negativo'}>{r.activo ? 'Activo' : 'Inactivo'}</Badge>,
    },
    { clave: 'permisos', encabezado: 'Permisos', render: (r) => r.permisos.length },
    { clave: 'usuarios', encabezado: 'Usuarios activos', render: (r) => r.usuarios_activos },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (r) => (
        <Boton
          variante="secundario"
          aria-label={`Editar permisos de ${r.nombre}`}
          onClick={() => setElegidoId(r.id)}
        >
          Editar permisos
        </Boton>
      ),
    },
  ]

  const hayError = roles.isError || catalogo.isError

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <SiTienePermiso permiso="GESTIONAR_DESCUENTOS">
            <Link to="/admin/descuentos/topes" className="text-sm text-primary/70 hover:text-primary hover:underline">
              Topes por rol
            </Link>
          </SiTienePermiso>
        }
      />
      <p className="text-sm text-primary/70">
        Cada rol es una plantilla de permisos. Elegí un rol para ver y cambiar lo que pueden hacer sus usuarios.
      </p>
      {(roles.isPending || catalogo.isPending) && !hayError && <p>Cargando…</p>}
      {hayError && <Alert>No se pudieron obtener los roles y los permisos.</Alert>}
      {roles.isSuccess && roles.data.length === 0 && <p className="text-sm text-primary/70">No hay roles.</p>}
      {roles.isSuccess && roles.data.length > 0 && (
        <Card>
          <Tabla filas={roles.data} columnas={columnas} obtenerClave={(r) => r.id} etiqueta={TITULO} />
        </Card>
      )}
      {elegido && catalogo.isSuccess && (
        <RolPermisosEditor
          key={`${elegido.id}:${elegido.permisos.join(',')}`}
          rol={elegido}
          catalogo={catalogo.data}
          onCerrar={() => setElegidoId(null)}
        />
      )}
    </main>
  )
}

export default RolesScreen
