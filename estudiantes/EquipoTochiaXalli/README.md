# Estrategia Wordle — EquipoTochiaXalli

## Idea central

En lugar de maximizar entropia de Shannon (cuanta informacion gano por turno),
esta estrategia minimiza el **Score Esperado de Intentos** — es decir, elige
la palabra que hace terminar el juego en el **menor numero de turnos totales**.

La diferencia es sutil pero importante:
- Shannon pregunta: *que palabra me da mas informacion AHORA?*
- Score Esperado pregunta: *que palabra me hace terminar el juego mas rapido?*

Ambas son metricas validas de teoria de la informacion, pero optimizan cosas
distintas. Score Esperado es lo que describe la seccion W.6 del curso.

---

## Metrica principal: Score Esperado (W.6)

Para cada palabra candidata a guess, simulamos todos los posibles feedbacks
que podriamos recibir y calculamos cuantos intentos nos costaria resolver
el juego en promedio:

```
E[intentos] = suma p(patron) * costo(grupo)
```

Donde:
- `p(patron)` = probabilidad de recibir ese patron de feedback
- `costo(grupo)` = intentos estimados para resolver ese grupo

```
costo(grupo):
  1 candidato  -> 1.0   (lo resolvemos directo)
  2 candidatos -> 1.5   (50% lo acertamos, 50% necesitamos 1 mas)
  n candidatos -> 1 + log2(n)  (aproximacion logaritmica)
```

**Minimizar este valor = elegir el guess mas eficiente.**

---

## Componentes de la estrategia

### 1. Openers pre-calculados

La primera palabra se calcula offline minimizando el score esperado contra
todo el vocabulario. Esto ahorra tiempo de computo en begin_game() y
garantiza el mejor arranque posible.

Script para recalcularlos si cambia el vocabulario (incluido en el codigo).

| Longitud | Modo      | Opener   |
|----------|-----------|----------|
| 4 letras | uniform   | `sale`   |
| 4 letras | frequency | `cora`   |
| 5 letras | uniform   | `careo`  |
| 5 letras | frequency | `careo`  |
| 6 letras | uniform   | `careto` |
| 6 letras | frequency | `cerito` |

Si el torneo usa un vocabulario diferente, el codigo calcula el opener
dinamicamente como fallback.

### 2. Discriminador Minimax (emergencias)

Cuando quedan pocos turnos y muchos candidatos, activamos un discriminador
que busca en TODO el vocabulario la palabra que **minimiza el grupo mas
grande posible** (estrategia minimax).

Esto garantiza que en el peor caso siempre queden pocos candidatos
para el siguiente turno.

Se activa automaticamente cuando:
- Quedan 2 turnos y mas de 2 candidatos
- Quedan 3 turnos y mas de 4 candidatos
- Quedan 4 turnos y mas de 12 candidatos

### 3. Pool adaptativo de busqueda

Para vocabularios pequenos (4 letras, ~1853 palabras) evaluamos
TODO el vocabulario en cada turno.

Para vocabularios grandes usamos un presupuesto de ~500k llamadas
a feedback() por turno, priorizando palabras que cubren las letras
mas frecuentes en los candidatos actuales.

### 4. Cierre inteligente

Cuando los candidatos restantes caben en los turnos disponibles,
elegimos directamente el mas probable en lugar de seguir explorando.

---

## Resultados (pruebas locales, 30 juegos)

| Longitud | Modo      | Resueltos | Media |
|----------|-----------|-----------|-------|
| 4 letras | uniform   | 100%      | ~4.5  |
| 4 letras | frequency | 100%      | ~4.3  |
| 5 letras | uniform   | 100%      | ~3.8  |
| 5 letras | frequency | 100%      | ~3.7  |
| 6 letras | uniform   | 100%      | ~3.3  |
| 6 letras | frequency | 100%      | ~3.2  |

---

## Dependencias

Solo modulos de la libreria estandar de Python mas `numpy`.

---

## Equipo

**EquipoTochiaXalli** — Primavera 2026