import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { aFiltros, esquemaPeriodo, type DatosPeriodo } from '../../../domain/cuentas-corrientes/periodoSchema'
import {
  columnasDeMovimiento,
  etiquetaDeTipo,
  formatearMonto,
  textoDeSaldo,
  type CuentaTipo,
} from '../../../domain/cuentas-corrientes/presentacion'
import { rutaDeOperacionDeMovimiento } from '../../../domain/cuentas-corrientes/enlaces'
import type { CodigoPermiso } from '../../../domain/identidad/permisos'
import type { MovimientoDeCuenta } from '../../../features/cuentas-corrientes/api'
import type { FiltrosEstadoDeCuenta } from '../../../features/cuentas-corrientes/claves'
import { RecursoNoEncontradoCuentasCorrientesError } from '../../../features/cuentas-corrientes/errores'
import { useEstadoDeCuenta } from '../../../features/cuentas-corrientes/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { formatearFechaHoraEnZona } from '../../../lib/fecha'

const SIN_PERMISO_DE_LECTURA = 'No tenés permiso para ver esta cuenta corriente.'
const NO_EXISTE = 'La cuenta corriente pedida no existe.'
const MENSAJE_GENERICO = 'No se pudo obtener la cuenta corriente.'

/** Permiso de lectura de la cuenta (`design.md` D2): el mismo de la ficha. */
const PERMISO_DE_LECTURA: Record<CuentaTipo, CodigoPermiso> = {
  CLIENTE: 'GESTIONAR_CLIENTES',
  PROVEEDOR: 'GESTIONAR_PROVEEDORES',
}

const COLECCION: Record<CuentaTipo, string> = { CLIENTE: 'clientes', PROVEEDOR: 'proveedores' }

function mensajeDeError(error: unknown): string {
  if (error instanceof RecursoNoEncontradoCuentasCorrientesError) {
    return NO_EXISTE
  }
  return error instanceof Error && error.message ? error.message : MENSAJE_GENERICO
}

/** Sin permiso: mismo texto que la red de seguridad del 403, para que el
 * mensaje no revele por qué el usuario no ve la pantalla. */
function CuentaCorrienteSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Cuenta corriente" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_LECTURA}</p>
    </main>
  )
}

/**
 * Estado de cuenta de un cliente o de un proveedor (change 08, tarea 7.3;
 * `design.md` D2, D9, D13; spec `administracion-de-cuentas-corrientes`).
 * Rutas `/admin/clientes/:entidadId/cuenta-corriente` y
 * `/admin/proveedores/:entidadId/cuenta-corriente`.
 *
 * La pantalla se decide con el permiso de lectura de `['yo']` (`usePermisos()`
 * vía `<SiTienePermiso>`, ADR-027): sin él, el estado de cuenta no se monta y
 * no se pide nada. La acción "Registrar saldo inicial" exige además
 * `IMPORTAR_DATOS` (D1). Las fechas se muestran en la zona horaria de la
 * organización que informa la API (TR-04) y los importes son strings formateados
 * por el dominio, nunca `number`.
 */
export function CuentaCorrienteScreen({ cuentaTipo }: { cuentaTipo: CuentaTipo }) {
  const { entidadId } = useParams<{ entidadId: string }>()
  return (
    <SiTienePermiso permiso={PERMISO_DE_LECTURA[cuentaTipo]} fallback={<CuentaCorrienteSinPermiso />}>
      {entidadId ? <EstadoDeCuentaDeEntidad cuentaTipo={cuentaTipo} entidadId={entidadId} /> : null}
    </SiTienePermiso>
  )
}

function EstadoDeCuentaDeEntidad({ cuentaTipo, entidadId }: { cuentaTipo: CuentaTipo; entidadId: string }) {
  const [filtros, setFiltros] = useState<FiltrosEstadoDeCuenta>({})
  const estado = useEstadoDeCuenta(cuentaTipo, entidadId, filtros)
  const rutaDeLaFicha = `/admin/${COLECCION[cuentaTipo]}/${entidadId}`

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DatosPeriodo>({
    resolver: zodResolver(esquemaPeriodo),
    defaultValues: { desde: '', hasta: '' },
  })

  const filtrar = handleSubmit((datos) => {
    setFiltros(aFiltros(datos))
  })

  const quitarFiltro = () => {
    reset({ desde: '', hasta: '' })
    setFiltros({})
  }

  const hayFiltro = filtros.desde !== undefined || filtros.hasta !== undefined
  // Un fallo al traer una página posterior deja la consulta en `success` (ya
  // hay datos que mostrar) con el error aparte; se lee acá, antes de que el
  // estrechamiento por `isSuccess` lo descarte.
  const errorAlCargarMas = estado.isFetchNextPageError ? mensajeDeError(estado.error) : null

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Cuenta corriente"
        acciones={
          <>
            {cuentaTipo === 'PROVEEDOR' && (
              <SiTienePermiso permiso="REGISTRAR_PAGO_PROVEEDOR">
                <Link
                  to={`/admin/pagos-proveedores/nuevo?proveedor=${entidadId}`}
                  className="text-sm text-primary/70 hover:text-primary hover:underline"
                >
                  Registrar pago
                </Link>
              </SiTienePermiso>
            )}
            {estado.isSuccess && (
              <SiTienePermiso permiso="IMPORTAR_DATOS">
                <Link
                  to={`${rutaDeLaFicha}/cuenta-corriente/saldo-inicial`}
                  className="text-sm text-primary/70 hover:text-primary hover:underline"
                >
                  Registrar saldo inicial
                </Link>
              </SiTienePermiso>
            )}
            <Link to={rutaDeLaFicha} className="text-sm text-primary/70 hover:text-primary hover:underline">
              Volver a la ficha
            </Link>
          </>
        }
      />

      <Card>
        <form onSubmit={filtrar} noValidate className="flex flex-wrap items-start gap-3">
          <Campo id="desde" etiqueta="Desde" error={errors.desde?.message}>
            <input
              id="desde"
              type="date"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('desde')}
            />
          </Campo>
          <Campo id="hasta" etiqueta="Hasta" error={errors.hasta?.message}>
            <input
              id="hasta"
              type="date"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('hasta')}
            />
          </Campo>
          <div className="flex items-end gap-2 self-end">
            <Boton type="submit">Filtrar</Boton>
            {hayFiltro && (
              <Boton type="button" variante="secundario" onClick={quitarFiltro}>
                Quitar filtro
              </Boton>
            )}
          </div>
        </form>
      </Card>

      {estado.isPending && <p>Cargando…</p>}
      {estado.isError && <Alert>{mensajeDeError(estado.error)}</Alert>}
      {estado.isSuccess && (
        <ContenidoDelEstado
          cuentaTipo={cuentaTipo}
          paginas={estado.data.pages}
          hayFiltro={hayFiltro}
          hayMas={estado.hasNextPage}
          cargandoMas={estado.isFetchingNextPage}
          errorAlCargarMas={errorAlCargarMas}
          onCargarMas={() => void estado.fetchNextPage()}
        />
      )}
    </main>
  )
}

interface PaginaDeEstado {
  saldo_anterior: string
  saldo_actual: string
  zona_horaria: string
  items: MovimientoDeCuenta[]
}

function ContenidoDelEstado({
  cuentaTipo,
  paginas,
  hayFiltro,
  hayMas,
  cargandoMas,
  errorAlCargarMas,
  onCargarMas,
}: {
  cuentaTipo: CuentaTipo
  paginas: PaginaDeEstado[]
  hayFiltro: boolean
  hayMas: boolean
  cargandoMas: boolean
  errorAlCargarMas: string | null
  onCargarMas: () => void
}) {
  const { tiene } = usePermisos()
  const primera = paginas[0]
  if (!primera) return null
  const zona = primera.zona_horaria
  const movimientos = paginas.flatMap((pagina) => pagina.items)

  // Solo la cuenta de un proveedor enlaza a la operación que originó el movimiento (change 12,
  // D7): a pagos y compras, y solo a quien tiene permiso de leerlos.
  const enlazaAOperaciones = cuentaTipo === 'PROVEEDOR'
  const tipoDelMovimiento = (m: MovimientoDeCuenta) => {
    const etiqueta = etiquetaDeTipo(m.tipo)
    const ruta = enlazaAOperaciones ? rutaDeOperacionDeMovimiento(m.tipo, m.origen_id, tiene) : null
    return ruta === null ? (
      etiqueta
    ) : (
      <Link to={ruta} className="text-primary hover:underline">
        {etiqueta}
      </Link>
    )
  }

  const columnas: ColumnaTabla<MovimientoDeCuenta>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (m) => formatearFechaHoraEnZona(m.occurred_at, zona) },
    { clave: 'tipo', encabezado: 'Tipo', render: tipoDelMovimiento },
    { clave: 'aumento', encabezado: 'Aumento', render: (m) => columnasDeMovimiento(m).aumento },
    { clave: 'reduccion', encabezado: 'Reducción', render: (m) => columnasDeMovimiento(m).reduccion },
    { clave: 'saldo', encabezado: 'Saldo acumulado', render: (m) => formatearMonto(m.saldo_acumulado) },
  ]

  return (
    <>
      <Card>
        <p className="text-sm font-medium text-primary">{textoDeSaldo(cuentaTipo, primera.saldo_actual)}</p>
        {hayFiltro && (
          <p className="mt-1 text-sm text-primary/70">Saldo anterior: {formatearMonto(primera.saldo_anterior)}</p>
        )}
      </Card>

      {movimientos.length === 0 ? (
        <p className="text-sm text-primary/70">No hay movimientos en este período.</p>
      ) : (
        <Card>
          <Tabla filas={movimientos} columnas={columnas} obtenerClave={(m) => m.id} />
        </Card>
      )}

      {errorAlCargarMas && <Alert>{errorAlCargarMas}</Alert>}
      {hayMas && (
        <div>
          <Boton type="button" variante="secundario" disabled={cargandoMas} onClick={onCargarMas}>
            Cargar más
          </Boton>
        </div>
      )}
    </>
  )
}

export default CuentaCorrienteScreen
