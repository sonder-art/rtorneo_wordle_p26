# Estrategia Wordle — EquipoTochiaXalli

## Lo que hace

Esta estrategia resuelve Wordle usando Entropía de Shannon que es una herramienta de teoría de la información que mide cuánta "información útil" nos da cada intento.

La idea central es que en cada turno hay que elegir la palabra que más reduzca el espacio de posibilidades, sin importar si esa palabra es o no la respuesta correcta.


## Lógica

### 1. Primera palabra (Opener)
Calculamos offline el opener óptimo para cada configuración ejecutando 
nuestra función de entropía sobre el vocabulario completo. El script 
evalúa cada palabra del vocabulario como candidata a opener y elige 
la que maximiza la entropía de Shannon contra todos los candidatos.

Si el torneo usa un vocabulario diferente, el código tiene un fallback 
que calcula el opener dinámicamente en <codigo>begin_game()</codigo>.

| Longitud | Modo      | Opener   | Entropía |
|----------|-----------|----------|----------|
| 4 letras | uniform   | `sale`   | 7.10 bits |
| 4 letras | frequency | `cora`   | 6.89 bits |
| 5 letras | uniform   | `careo`  | 8.21 bits |
| 5 letras | frequency | `careo`  | 7.99 bits |
| 6 letras | uniform   | `careto` | 9.10 bits |
| 6 letras | frequency | `cerito` | 8.88 bits |

Estas palabras cubren las letras más frecuentes del español y reducen al máximo los candidatos desde el primer turno.

### 2. Filtrado de candidatos
Después de cada intento, filtramos las palabras que todavía pueden ser la respuesta usando el feedback (verde/amarillo/gris).

### 3. Cálculo de Entropía de Shannon
Para cada posible palabra del vocabulario, simulamos: "si adivino esta palabra, ¿cómo se distribuyen los candidatos restantes según el feedback que recibiría?"

La fórmula es:
```
H = -Σ p(grupo) * log2(p(grupo))
```

Una entropía alta significa que la palabra divide los candidatos en grupos pequeños y equilibrados → aprendemos mucho de ese intento.

### 4. Cuando quedan pocos intentos
Si quedan pocos turnos y aún hay muchos candidatos, activamos un discriminador: buscamos la palabra que minimiza el grupo más grande posible (estrategia minimax), garantizando que no nos quedemos sin intentos.

### 5. Preferencias de candidatos
Si una palabra tiene la misma entropía que otra pero además puede ser la respuesta correcta, le damos un pequeño bonus de <code>+0.1</code> para preferirla.

### 6. Cierre
Cuando los candidatos restantes caben en los turnos disponibles, dejamos de explorar y simplemente elegimos el más probable.



## Resultados obtenidos (pruebas locales)

| Longitud | Modo      | Resueltos | Media de intentos |
|----------|-----------|-----------|-------------------|
| 4 letras | uniform   | 100%      | ~4.70             |
| 4 letras | frequency | 100%      | ~4.50             |
| 5 letras | uniform   | 100%      | ~3.80             |
| 5 letras | frequency | 100%      | ~3.80             |
| 6 letras | uniform   | 100%      | ~3.25             |
| 6 letras | frequency | 100%      | ~3.30             |

## Herramientas usadas

- Python + <code>numpy</code> (único paquete externo)
- <code>feedback()</code> y <code>filter_candidates()</code> del framework del torneo
- Teoría de la información (secciones W.4, W.5, W.6 del curso)

## Equipo

**EquipoTochiaXalli** — Primavera 2026