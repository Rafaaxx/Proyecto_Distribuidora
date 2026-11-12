import { useState } from 'react'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import {
  PERMISOS_DE_AUTORIZACION,
  agruparPorModulo,
  diferenciaDePermisos,
  llegaMasAdelante,
} from '../../../domain/identidad/roles'
import type { PermisoDeCatalogo, RolConPermisos } from '../../../features/identidad/rolesApi'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { ConfirmarCambioDePermisosDialogo } from './ConfirmarCambioDePermisosDialogo'

interface RolPermisosEditorProps {
  rol: RolConPermisos
  catalogo: PermisoDeCatalogo[]
  onCerrar: () => void
}

/**
 * Edición de los permisos de un rol (change 17b, tarea 9.1; D9). Los permisos van agrupados por
 * módulo, cada uno con su descripción y una casilla; los de funciones que todavía no existen llevan
 * la marca "llega más adelante". Guardar abre un resumen "Agrega / Quita" con confirmación. Sin
 * lógica de negocio: la diferencia y los avisos salen de `domain/identidad/roles.ts`.
 */
export function RolPermisosEditor({ rol, catalogo, onCerrar }: RolPermisosEditorProps) {
  const [marcados, setMarcados] = useState<Set<string>>(() => new Set(rol.permisos))
  const [confirmando, setConfirmando] = useState(false)
  const { yo } = usePermisos()
  const grupos = agruparPorModulo(catalogo)
  const nuevos = catalogo.map((p) => p.codigo).filter((codigo) => marcados.has(codigo))
  const { agrega, quita } = diferenciaDePermisos(rol.permisos, nuevos, catalogo)
  const hayCambios = agrega.length > 0 || quita.length > 0

  const alternar = (codigo: string) =>
    setMarcados((actuales) => {
      const siguientes = new Set(actuales)
      if (!siguientes.delete(codigo)) siguientes.add(codigo)
      return siguientes
    })

  return (
    <section aria-label={`Permisos de ${rol.nombre}`} className="flex flex-col gap-3">
      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
            Permisos de {rol.nombre} <Ayuda clave="roles.permisos" />
          </h2>
          <Boton variante="secundario" onClick={onCerrar}>
            Cerrar
          </Boton>
        </div>
        {grupos.map((grupo) => (
          <fieldset key={grupo.modulo} className="flex flex-col gap-1 rounded-md border border-border p-3">
            <legend className="px-1 text-sm font-medium text-primary">{grupo.etiqueta}</legend>
            <ul className="flex flex-col gap-1">
              {grupo.permisos.map((permiso) => (
                <li key={permiso.codigo} className="flex flex-wrap items-center gap-2 text-sm">
                  <input
                    id={`permiso-${permiso.codigo}`}
                    type="checkbox"
                    className="h-4 w-4"
                    checked={marcados.has(permiso.codigo)}
                    onChange={() => alternar(permiso.codigo)}
                  />
                  <label htmlFor={`permiso-${permiso.codigo}`} className="text-primary">
                    {permiso.descripcion}
                  </label>
                  {llegaMasAdelante(permiso.modulo) && (
                    <span className="rounded-md bg-surface-muted px-2 py-0.5 text-xs text-primary/70">llega más adelante</span>
                  )}
                  {permiso.codigo === 'ADMIN_USUARIOS' && <Ayuda clave="roles.ultimoAdministrador" />}
                  {PERMISOS_DE_AUTORIZACION.includes(permiso.codigo) && <Ayuda clave="roles.autorizacion" />}
                </li>
              ))}
            </ul>
          </fieldset>
        ))}
        <div>
          <Boton disabled={!hayCambios} onClick={() => setConfirmando(true)}>
            Guardar cambios
          </Boton>
        </div>
      </Card>
      {confirmando && (
        <ConfirmarCambioDePermisosDialogo
          rol={rol}
          catalogo={catalogo}
          nuevos={nuevos}
          esMiRol={yo?.rol.id === rol.id}
          onCerrar={() => setConfirmando(false)}
        />
      )}
    </section>
  )
}
