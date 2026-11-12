import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import type { paths } from '../../../src/api/schema.gen'

const RUTA_SCHEMA = path.resolve(__dirname, '../../../src/api/schema.gen.ts')

/**
 * `docs/02-arquitectura.md` §11: "El OpenAPI generado por FastAPI es el
 * contrato. El front genera sus tipos con openapi-typescript en cada
 * cambio; CI verifica que los tipos generados estén actualizados." Tarea
 * 13.1 -- cierra el hueco documentado en `design.md` D3 del change 01b.
 *
 * `import type` se borra en tiempo de ejecución (esbuild/TypeScript la
 * elide), así que no basta para forzar un rojo real si el archivo no
 * existe: la prueba de contenido con `node:fs` es la que efectivamente
 * falla antes de generar el archivo y pasa después. Los literales tipados
 * de abajo son además el contrato que `npm run typecheck` exige que
 * compile.
 */
describe('tipos generados desde el OpenAPI del backend (tarea 13.1)', () => {
  it('genera src/api/schema.gen.ts con las rutas de autenticación e identidad', () => {
    expect(existsSync(RUTA_SCHEMA)).toBe(true)
    const contenido = readFileSync(RUTA_SCHEMA, 'utf-8')
    expect(contenido).toContain('/api/v1/auth/login')
    expect(contenido).toContain('/api/v1/identidad/dispositivos')
  })

  it('declara el contrato de POST /api/v1/auth/login', () => {
    type CuerpoLogin =
      paths['/api/v1/auth/login']['post']['requestBody']['content']['application/json']

    const cuerpo: CuerpoLogin = {
      organizacion_slug: 'demo',
      usuario: 'vendedor1',
      contrasena: 'correcta',
      dispositivo_id: '00000000-0000-0000-0000-000000000000',
      nombre_dispositivo: 'Teléfono de ruta',
    }

    expect(cuerpo.usuario).toBe('vendedor1')
  })

  it('declara el contrato de GET /api/v1/identidad/dispositivos', () => {
    type Dispositivo = NonNullable<
      paths['/api/v1/identidad/dispositivos']['get']['responses']['200']['content']['application/json']
    >[number]

    const dispositivo: Dispositivo = {
      id: '00000000-0000-0000-0000-000000000000',
      nombre: 'Teléfono de ruta',
      prefijo: 'V01',
      estado: 'ACTIVO',
      ultimo_correlativo: 0,
      revocado_en: null,
    }

    expect(dispositivo.estado).toBe('ACTIVO')
  })
})
