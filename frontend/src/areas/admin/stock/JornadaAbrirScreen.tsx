import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { esquemaApertura, ubicacionesParaAbrir } from '../../../domain/stock/jornadas'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useAbrirJornada, useJornadaActual, useUbicaciones } from '../../../features/stock/hooks'
import { AVISO_REQUIERE_CONEXION, CLASE_CONTROL, CLASE_ENLACE, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Abrir jornada'

/**
 * Apertura de una jornada (change 15, tarea 14.2; RUT-01, RUT-03, INV-16; `design.md` D4, D16). Lo
 * ve quien tiene `ABRIR_JORNADA`. Ofrece solo las ubicaciones activas, con toma y libres; avisa que
 * requiere conexión (`ONLINE`, sin cola) y reintenta con el mismo `operation_id` mientras no cambia
 * la ubicación. Si otro la tomó antes, muestra el mensaje y se queda acá.
 */
export function JornadaAbrirScreen() {
  return (
    <SiTienePermiso
      permiso="ABRIR_JORNADA"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para abrir jornadas." />}
    >
      <Formulario />
    </SiTienePermiso>
  )
}

function Formulario() {
  const navigate = useNavigate()
  const ubicaciones = useUbicaciones(true)
  const actual = useJornadaActual(true)
  const abrir = useAbrirJornada()
  const [ubicacionId, setUbicacionId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const operationId = useOperationIdPorContenido({ ubicacion_id: ubicacionId })
  const opciones = ubicacionesParaAbrir(ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? [])

  async function enviar() {
    const validado = esquemaApertura.safeParse({ ubicacion_id: ubicacionId })
    if (!validado.success) {
      setError(validado.error.issues[0]?.message ?? 'Elegí la ubicación que vas a tomar.')
      return
    }
    setError(null)
    setEnviando(true)
    try {
      const jornada = await abrir.mutateAsync({ ubicacion_id: validado.data.ubicacion_id, operationId })
      navigate(`/admin/stock/jornadas/${jornada.id}`)
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'apertura'))
      // Otra jornada la tomó antes: se vuelve a leer qué ubicaciones quedan libres.
      if (falla instanceof ErrorDeStock && falla.codigo === 'UBICACION_TOMADA') void ubicaciones.refetch()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <Link to="/admin/stock/jornadas" className={CLASE_ENLACE}>
            Volver al listado
          </Link>
        }
      />
      {actual.data && (
        <p className="text-sm text-primary/70">
          Ya tenés una jornada en curso en {actual.data.ubicacion_nombre}.{' '}
          <Link to={`/admin/stock/jornadas/${actual.data.id}`} className="underline">
            Ver mi jornada
          </Link>
        </p>
      )}
      <Card>
        <form
          onSubmit={(evento) => {
            evento.preventDefault()
            void enviar()
          }}
          noValidate
          className="flex flex-col gap-4"
        >
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
          {ubicaciones.isError && <Alert>No se pudieron obtener las ubicaciones.</Alert>}
          <label className="flex flex-col gap-1 text-sm text-primary">
            Ubicación
            <select
              className={CLASE_CONTROL}
              value={ubicacionId}
              onChange={(evento) => setUbicacionId(evento.target.value)}
            >
              <option value="">Elegí la ubicación</option>
              {opciones.map((ubicacion) => (
                <option key={ubicacion.id} value={ubicacion.id}>
                  {ubicacion.nombre}
                </option>
              ))}
            </select>
          </label>
          {error && <Alert>{error}</Alert>}
          <div>
            <Boton type="submit" disabled={enviando || abrir.isPending}>
              Abrir jornada
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default JornadaAbrirScreen
