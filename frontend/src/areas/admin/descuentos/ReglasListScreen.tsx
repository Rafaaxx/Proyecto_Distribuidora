import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { describirRegla, describirVigencia, ESTADOS_DE_REGLA, etiquetaDeEstadoDeRegla } from '../../../domain/descuentos/presentacion'
import type { ReglaDescuento } from '../../../features/descuentos/api'
import { useReglasDescuento } from '../../../features/descuentos/hooks'

const TITULO = 'Reglas de descuento'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

function varianteDeEstado(estado: string) {
  return estado === 'ACTIVA' ? 'positivo' : estado === 'VENCIDA' ? 'negativo' : 'neutral'
}

const COLUMNAS: ColumnaTabla<ReglaDescuento>[] = [
  {
    clave: 'nombre',
    encabezado: 'Nombre',
    render: (r) => (
      <Link to={`/admin/descuentos/${r.id}`} className="font-medium text-primary hover:underline">
        {r.nombre}
      </Link>
    ),
  },
  {
    clave: 'regla',
    encabezado: 'Regla',
    render: (r) => {
      const descripcion = describirRegla(r)
      return (
        <div className="flex flex-col">
          <span>{descripcion.resumen}</span>
          <span className="text-primary/70">{descripcion.alcance}</span>
        </div>
      )
    },
  },
  {
    clave: 'prioridad',
    encabezado: 'Prioridad y acumulación',
    render: (r) => {
      const descripcion = describirRegla(r)
      return (
        <div className="flex flex-col">
          <span>{descripcion.prioridad}</span>
          <span className="text-primary/70">{descripcion.acumulable}</span>
        </div>
      )
    },
  },
  { clave: 'vigencia', encabezado: 'Vigencia', render: (r) => describirVigencia(r.vigencia_desde, r.vigencia_hasta) },
  {
    clave: 'estado',
    encabezado: 'Estado',
    render: (r) => <Badge variante={varianteDeEstado(r.estado)}>{etiquetaDeEstadoDeRegla(r.estado)}</Badge>,
  },
]

/**
 * Listado de `/admin/descuentos` (change 16, tarea 15.2; spec `administracion-de-descuentos`).
 * Cada regla con su descripción legible, su prioridad, si es acumulable, su vigencia y su estado
 * (incluido `VENCIDA`, derivado por el servidor). El área ya exige `GESTIONAR_DESCUENTOS`.
 */
export function ReglasListScreen() {
  const [estado, setEstado] = useState('')
  const reglas = useReglasDescuento(estado === '' ? undefined : estado)

  const filas = reglas.data?.pages.flatMap((pagina) => pagina.items) ?? []

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <Link
            to="/admin/descuentos/nueva"
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Nueva regla
          </Link>
        }
      />
      <div className="flex items-center gap-2">
        <label htmlFor="filtro-estado" className="text-sm font-medium text-primary">
          Estado
        </label>
        <select id="filtro-estado" className={CLASE_CONTROL} value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="">Todos los estados</option>
          {ESTADOS_DE_REGLA.map((valor) => (
            <option key={valor} value={valor}>
              {etiquetaDeEstadoDeRegla(valor)}
            </option>
          ))}
        </select>
      </div>
      {reglas.isError && <Alert>No se pudieron obtener las reglas de descuento.</Alert>}
      {reglas.isPending && <p>Cargando…</p>}
      {reglas.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Todavía no hay reglas de descuento.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={COLUMNAS} obtenerClave={(r) => r.id} etiqueta={TITULO} />
        </Card>
      )}
      {reglas.hasNextPage && (
        <Boton variante="secundario" onClick={() => void reglas.fetchNextPage()} disabled={reglas.isFetchingNextPage}>
          Cargar más
        </Boton>
      )}
    </main>
  )
}

export default ReglasListScreen
