import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy, useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { clavesIdentidad } from '../../features/identidad/claves'
import { suscribirACambiosDeToken } from '../../lib/auth/tokenStore'
import { AdminInicio } from './AdminInicio'
import { AdminLayout } from './AdminLayout'
import { LoginScreen } from './auth/LoginScreen'
import { DispositivosScreen } from './dispositivos/DispositivosScreen'

// Carga diferida: el bundle de catálogo no se descarga hasta que alguien
// navega a `/admin/catalogo` (tarea 10.1, mismo criterio que `AppRoutes.tsx`
// entre `/ruta` y `/admin`).
const CatalogoArea = lazy(() => import('./catalogo/CatalogoArea'))
const ProveedoresArea = lazy(() => import('./proveedores/ProveedoresArea'))
const ClientesArea = lazy(() => import('./clientes/ClientesArea'))
const StockArea = lazy(() => import('./stock/StockArea'))
const ComprasArea = lazy(() => import('./compras/ComprasArea'))
const ImportacionArea = lazy(() => import('./importacion/ImportacionArea'))
const ConfiguracionArea = lazy(() => import('./configuracion/ConfiguracionArea'))

/**
 * `docs/02-arquitectura.md` §13.1: `/admin` usa TanStack Query contra la
 * API (a diferencia de `/ruta`, que solo lee de Dexie); el `QueryClient` se
 * crea acá para que solo exista mientras el área de administración está
 * montada (carga diferida, `AppRoutes.tsx`).
 *
 * Sin sesión restaurada todavía (ese flujo no lo pide ningún escenario de
 * este change): la raíz de `/admin` redirige siempre a `login`. Cambia
 * cuando exista una pantalla que dependa de sesión persistida entre
 * recargas.
 *
 * `inicio` es la ruta índice dentro del layout (tarea 7.6, **B3**): el login
 * lleva ahí y desde ahí se salta a la primera sección que el usuario pueda
 * usar, o se informa que no tiene ninguna.
 */
const queryClient = new QueryClient()

/**
 * Suscripción única a `tokenStore` (tarea 6.5, `design.md` D2-A): al
 * fijarse un token (login o renovación exitosa) invalida `['yo']` sin
 * cancelar un pedido en curso (`cancelRefetch: false`, así no se duplica
 * el `/yo` que justo disparó la renovación); al limpiarse (renovación
 * rechazada) reinicia `['yo']`. `tokenStore` no conoce React ni TanStack:
 * esta es la única función que traduce sus avisos a operaciones del
 * `QueryClient`.
 *
 * **Por qué `resetQueries` y no `removeQueries`** (tarea 11.2, cierra el
 * hallazgo de la 10.5). `removeQueries` saca la consulta de la caché y la
 * **destruye**, pero el observer de `usePermisos()` sigue suscrito a
 * ese objeto destruido y no vuelve a crear la consulta. Con un 401 de
 * `/yo` en vuelo, ese observer queda esperando un resultado que ya se
 * descartó, así que `/admin` se queda en blanco para siempre; con datos
 * viejos en caché, el menú sigue mostrando secciones que la sesión
 * terminada ya no habilita, y ninguno de los dos estados dispara el
 * aviso "Iniciar sesión" (**B1**), que solo existe en estado `error`.
 *
 * `resetQueries` deja el observer como estaba, tira el resultado anterior
 * (los permisos viejos salen del menú de una) y vuelve a ejecutar la
 * consulta: `obtenerYo()` falla rápido con 401, `usePermisos()` queda en
 * `error` y el encabezado ofrece "Iniciar sesión". Como además
 * `tokenStore` ya sabe que la sesión terminó, esa consulta no vuelve a
 * pedir nada al servidor.
 */
function useSuscripcionAYo() {
  useEffect(() => {
    const desuscribir = suscribirACambiosDeToken((token) => {
      if (token) {
        void queryClient.invalidateQueries({ queryKey: clavesIdentidad.yo() }, { cancelRefetch: false })
      } else {
        // `void`: `resetQueries` devuelve una promesa que no interesa
        // esperar (el aviso de `tokenStore` no es un punto de espera).
        void queryClient.resetQueries({ queryKey: clavesIdentidad.yo() })
      }
    })
    return desuscribir
  }, [])
}

export function AdminScreen() {
  useSuscripcionAYo()

  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/" element={<Navigate to="login" replace />} />
        <Route path="login" element={<LoginScreen />} />
        <Route element={<AdminLayout />}>
          <Route path="inicio" element={<AdminInicio />} />
          <Route path="dispositivos" element={<DispositivosScreen />} />
          <Route
            path="catalogo/*"
            element={
              <Suspense fallback={null}>
                <CatalogoArea />
              </Suspense>
            }
          />
          <Route
            path="proveedores/*"
            element={
              <Suspense fallback={null}>
                <ProveedoresArea />
              </Suspense>
            }
          />
          <Route
            path="compras/*"
            element={
              <Suspense fallback={null}>
                <ComprasArea />
              </Suspense>
            }
          />
          <Route
            path="clientes/*"
            element={
              <Suspense fallback={null}>
                <ClientesArea />
              </Suspense>
            }
          />
          <Route
            path="stock/*"
            element={
              <Suspense fallback={null}>
                <StockArea />
              </Suspense>
            }
          />
          <Route
            path="importacion/*"
            element={
              <Suspense fallback={null}>
                <ImportacionArea />
              </Suspense>
            }
          />
          <Route
            path="configuracion/*"
            element={
              <Suspense fallback={null}>
                <ConfiguracionArea />
              </Suspense>
            }
          />
        </Route>
      </Routes>
    </QueryClientProvider>
  )
}

export default AdminScreen
