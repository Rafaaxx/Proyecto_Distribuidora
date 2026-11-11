/**
 * Calentamiento previo a la suite (change 28, D14): el primer acceso a un entorno recién levantado
 * es lento (el proxy emite sus certificados, el backend abre su pool y deriva su primera
 * contraseña) y hacía fallar por tiempo agotado a la primera prueba. Se hacen las primeras
 * peticiones acá, fuera de cualquier prueba.
 */
import { randomUUID } from 'node:crypto'

import { request, type FullConfig } from '@playwright/test'

import { CONTRASENA, ORGANIZACION } from '../datos/escenario'

export default async function calentar(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL
  const contexto = await request.newContext({ baseURL, ignoreHTTPSErrors: true })
  try {
    for (const ruta of ['/api/v1/salud', '/', '/admin/login', '/ruta']) {
      await contexto.get(ruta, { timeout: 60_000 })
    }
    await contexto.post('/api/v1/auth/login', {
      timeout: 60_000,
      data: {
        organizacion_slug: ORGANIZACION,
        usuario: 'admin',
        contrasena: CONTRASENA,
        dispositivo_id: randomUUID(),
        nombre_dispositivo: 'Calentamiento',
      },
    })
  } finally {
    await contexto.dispose()
  }
}
