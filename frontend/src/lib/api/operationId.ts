import { v7 as uuidv7 } from 'uuid'

/**
 * Genera un identificador de operación (UUIDv7) para el encabezado
 * `Operation-Id` que el bus de comandos exige en toda escritura
 * (`openspec/changes/04-pipeline-comandos/design.md` D4, D7 -- tarea 13.1).
 *
 * UUIDv7 porque es ordenable por tiempo de creación, igual que las claves
 * primarias del backend (`backend/app/core/ids.py`, `CLAUDE.md` §4:
 * "Claves primarias: UUIDv7").
 */
export function generarOperationId(): string {
  return uuidv7()
}
