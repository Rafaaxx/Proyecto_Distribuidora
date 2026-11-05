## ADDED Requirements

### Requirement: Las pantallas de la rendición explican el conteo y la entrega

`/admin` DEBE tener las claves de ayuda `stock.entregaDelDia` (junto a la entrega en el detalle de la jornada), `stock.rendicion` (en «Rendir» y en la pantalla de conteo), `stock.esperado` y `stock.diferenciaRendicion` (en las columnas del conteo y del resumen), `stock.resumenJornada` (en el resumen) y `stock.remanente` (en el diálogo de cierre), y el área de ruta `ruta.terminarDia` (en «Terminar el día»); y las revisadas `stock.tomaActual` y `ruta.sincronizar`, con los textos aprobados, sin ejemplos, citando sus reglas. Todo ID citado DEBE existir en `01-dominio.md` o en `docs/adr/` (`design.md` D12).

#### Scenario: Ayuda del conteo
- **WHEN** la Supervisora abre la ayuda de la rendición, del esperado o de la diferencia
- **THEN** ve el texto aprobado, sin ejemplo
- **Regla:** RUT-06; RUT-07; ADR-051

#### Scenario: Ayuda de «Terminar el día»
- **WHEN** el vendedor abre la ayuda de «Terminar el día», también sin señal
- **THEN** lee que después no puede vender, anular ni cobrar en esa jornada y que lo pendiente se envía primero
- **Regla:** RUT-05

#### Scenario: Textos revisados
- **WHEN** se abre la ayuda de la toma actual o de «Sincronizar»
- **THEN** el texto nombra la rendición o la entrega del día
- **Regla:** STK-09; SYN-03

#### Scenario: Clave o ID inexistente
- **WHEN** una pantalla usa una clave que no existe o un texto cita un ID que no está en `docs/`
- **THEN** la prueba de claves de ayuda falla
- **Regla:** ADR-051
