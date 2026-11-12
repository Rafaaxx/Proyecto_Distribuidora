import { useEffect, useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import type { Alicuota } from '../../../features/configuracion/api'
import { useAlicuotas } from '../../../features/configuracion/useAlicuotas'
import { useModificarAlicuota } from '../../../features/configuracion/useAlicuotasAdmin'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearPorcentaje, parsearImporteDesdeApi } from '../../../lib/money'
import { AlicuotaDialogo } from './AlicuotaDialogo'
import { CambioDeEstadoDeCatalogoDialogo } from './CambioDeEstadoDeCatalogoDialogo'
import { describirErrorDeAlicuota } from './erroresDeCatalogos'

const TITULO = 'Alícuotas de IVA'

type Accion = { tipo: 'nueva' } | { tipo: 'editar' | 'baja' | 'reactivar'; alicuota: Alicuota }

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para administrar las alícuotas de IVA.</p>
    </main>
  )
}

/**
 * Alícuotas de IVA de la organización (change 20c, tarea 7.3; spec `administracion-de-alicuotas`;
 * TR-02, CAT-01, CAT-05, ADR-061). Lista activas e inactivas (la misma consulta que usa el
 * formulario de productos); alta, cambio de nombre, baja y reactivación con `ADMIN_CONFIGURACION`
 * (ADR-027). El porcentaje no se edita una vez creada. Sin lógica de negocio: las reglas las valida
 * el servidor.
 */
export function AlicuotasScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <AlicuotasListado />
    </SiTienePermiso>
  )
}

function AlicuotasListado() {
  const consulta = useAlicuotas()
  const modificar = useModificarAlicuota()
  const [accion, setAccion] = useState<Accion | null>(null)
  const cerrar = () => setAccion(null)

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = consulta
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const alicuotas = consulta.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const columnas: ColumnaTabla<Alicuota>[] = [
    { clave: 'nombre', encabezado: 'Nombre', render: (a) => <span className="font-medium text-primary">{a.nombre}</span> },
    {
      clave: 'porcentaje',
      encabezado: 'Porcentaje',
      ayuda: 'alicuotas.valor',
      render: (a) => formatearPorcentaje(parsearImporteDesdeApi(a.valor)),
    },
    {
      clave: 'estado',
      encabezado: 'Estado',
      render: (a) => <Badge variante={a.activo ? 'positivo' : 'negativo'}>{a.activo ? 'Activo' : 'De baja'}</Badge>,
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      ayuda: 'alicuotas.baja',
      render: (a) => (
        <span className="flex items-center gap-2">
          <Boton variante="secundario" aria-label={`Editar ${a.nombre}`} onClick={() => setAccion({ tipo: 'editar', alicuota: a })}>
            Editar
          </Boton>
          {a.activo ? (
            <Boton variante="secundario" aria-label={`Dar de baja ${a.nombre}`} onClick={() => setAccion({ tipo: 'baja', alicuota: a })}>
              Dar de baja
            </Boton>
          ) : (
            <Boton variante="secundario" aria-label={`Reactivar ${a.nombre}`} onClick={() => setAccion({ tipo: 'reactivar', alicuota: a })}>
              Reactivar
            </Boton>
          )}
        </span>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} acciones={<Boton onClick={() => setAccion({ tipo: 'nueva' })}>Nueva alícuota</Boton>} />
      <p className="text-sm text-primary/70">
        Son los porcentajes de IVA que se asignan a los productos. Una alícuota dada de baja no se borra: las compras y ventas
        de antes conservan el porcentaje con que se hicieron.
      </p>
      {consulta.isPending && <p>Cargando…</p>}
      {consulta.isError && <Alert>No se pudieron obtener las alícuotas.</Alert>}
      {consulta.isSuccess && alicuotas.length === 0 && <p className="text-sm text-primary/70">Todavía no hay alícuotas.</p>}
      {consulta.isSuccess && alicuotas.length > 0 && (
        <Card>
          <Tabla filas={alicuotas} columnas={columnas} obtenerClave={(a) => a.id} etiqueta={TITULO} />
        </Card>
      )}
      {accion?.tipo === 'nueva' && <AlicuotaDialogo onCerrar={cerrar} />}
      {accion?.tipo === 'editar' && <AlicuotaDialogo key={accion.alicuota.id} alicuota={accion.alicuota} onCerrar={cerrar} />}
      {(accion?.tipo === 'baja' || accion?.tipo === 'reactivar') && (
        <CambioDeEstadoDeCatalogoDialogo
          key={accion.alicuota.id}
          id={accion.alicuota.id}
          titulo={`${accion.tipo === 'reactivar' ? 'Reactivar' : 'Dar de baja'} ${accion.alicuota.nombre}`}
          mensaje={
            accion.tipo === 'reactivar'
              ? `«${accion.alicuota.nombre}» vuelve a ofrecerse al crear o editar productos.`
              : `«${accion.alicuota.nombre}» deja de ofrecerse al crear o editar productos. No se borra: las compras y ventas de antes la conservan y la podés reactivar cuando quieras.`
          }
          reactivar={accion.tipo === 'reactivar'}
          describirError={describirErrorDeAlicuota}
          onConfirmar={(operationId) =>
            modificar.mutateAsync({
              alicuotaId: accion.alicuota.id,
              nombre: accion.alicuota.nombre,
              valor: accion.alicuota.valor,
              activo: accion.tipo === 'reactivar',
              operationId,
            })
          }
          onCerrar={cerrar}
        />
      )}
    </main>
  )
}

export default AlicuotasScreen
