# Frontend

React + TypeScript (`strict: true`) + Vite. Ver [`docs/02-arquitectura.md`](../docs/02-arquitectura.md)
§3.2 y §13 para el stack completo y la estructura de `src/`.

```bash
npm install
npm run dev               # desarrollo
npm run build             # build de producción
npm run typecheck         # tsc -b --noEmit
npm run lint              # ESLint
npm run test              # Vitest
npm run generate:api-types  # regenera src/api/schema.gen.ts desde el OpenAPI del backend
npm run check:api-types     # regenera y falla si queda un diff sin commitear (lo mismo que corre CI)
```

## Tipos del cliente API (`docs/02-arquitectura.md` §11)

`src/api/schema.gen.ts` se genera con `openapi-typescript` a partir del
esquema OpenAPI real del backend (`backend/openapi.json`, generado a su vez
por `backend/scripts/export_openapi.py` sin necesitar una base de datos ni
un servidor corriendo). Ambos archivos se versionan: correr
`npm run generate:api-types` después de cambiar cualquier endpoint y
commitear el resultado. El job de CI "3. Tipos del cliente API generados
desde el OpenAPI" corre `npm run check:api-types` y falla si el árbol de
trabajo queda con cambios sin commitear después de regenerar -- cierra el
hueco que el change 01b (`design.md` D3) había dejado documentado a
propósito.
