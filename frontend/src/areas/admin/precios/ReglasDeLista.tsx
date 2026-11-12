import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { porcentajeDesdeFraccion } from '../../../domain/precios/reglaSchema'
import { etiquetaDeAlcance, etiquetaDeTipoDeMargen, textoDeFormula } from '../../../domain/precios/presentacion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { Regla } from '../../../features/precios/api'
import { useModificarRegla, useReglas } from '../../../features/precios/hooks'
import { describirError } from './errores'
import { ReglaDialogo } from './ReglaDialogo'

/**
 * Reglas de margen de una lista con la fórmula que aplica cada una (change 13, tarea 13.1;
 * PRC-12, PRC-13, D8). Crear, editar y desactivar solo con `GESTIONAR_LISTAS`.
 */
export function ReglasDeLista({ listaId }: { listaId: string }) {
  const reglas = useReglas(listaId)
  const modificar = useModificarRegla()
  const [dialogo, setDialogo] = useState<{ regla?: Regla } | null>(null)
  const [errorDeEnvio, setErrorDeEnvio] = useState<string | null>(null)

  const cambiarActividad = async (regla: Regla) => {
    setErrorDeEnvio(null)
    try {
      await modificar.mutateAsync({
        listaId,
        reglaId: regla.id,
        tipo: regla.tipo as 'MARKUP' | 'MARGEN_BRUTO',
        valor: regla.valor,
        activo: !regla.activo,
      })
    } catch (error) {
      setErrorDeEnvio(describirError(error).mensaje)
    }
  }

  const columnas: ColumnaTabla<Regla>[] = [
    { clave: 'alcance', encabezado: 'Se aplica a', render: (r) => etiquetaDeAlcance(r.alcance_tipo) },
    { clave: 'entidad', encabezado: 'Entidad', render: (r) => r.alcance_nombre ?? '—' },
    { clave: 'tipo', encabezado: 'Tipo', render: (r) => etiquetaDeTipoDeMargen(r.tipo) },
    { clave: 'valor', encabezado: 'Valor', render: (r) => `${porcentajeDesdeFraccion(r.valor)}%` },
    { clave: 'formula', encabezado: 'Fórmula', render: (r) => textoDeFormula(r.tipo, r.valor) },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (r) => <Badge variante={r.activo ? 'positivo' : 'negativo'}>{r.activo ? 'Activa' : 'Inactiva'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (r) => (
        <SiTienePermiso permiso="GESTIONAR_LISTAS">
          <div className="flex gap-2">
            <Boton variante="secundario" onClick={() => setDialogo({ regla: r })}>
              Editar
            </Boton>
            <Boton variante="secundario" disabled={modificar.isPending} onClick={() => void cambiarActividad(r)}>
              {r.activo ? 'Desactivar' : 'Activar'}
            </Boton>
          </div>
        </SiTienePermiso>
      ),
    },
  ]

  const filas = reglas.data?.items ?? []

  return (
    <section className="flex flex-col gap-3" aria-labelledby="titulo-reglas">
      <div className="flex items-center justify-between">
        <h2 id="titulo-reglas" className="text-base font-semibold text-primary">
          Reglas de margen
        </h2>
        <SiTienePermiso permiso="GESTIONAR_LISTAS">
          <Boton onClick={() => setDialogo({})}>Nueva regla</Boton>
        </SiTienePermiso>
      </div>
      {errorDeEnvio && <Alert>{errorDeEnvio}</Alert>}
      {reglas.isPending && <p className="text-sm">Cargando…</p>}
      {reglas.isError && <Alert>No se pudieron obtener las reglas.</Alert>}
      {reglas.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">
          Todavía no hay reglas de margen: sin una regla aplicable, un producto no recibe precio.
        </p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(r) => r.id} etiqueta="Reglas de margen" />
        </Card>
      )}
      <ReglaDialogo
        listaId={listaId}
        regla={dialogo?.regla}
        abierto={dialogo !== null}
        onCerrar={() => setDialogo(null)}
      />
    </section>
  )
}
