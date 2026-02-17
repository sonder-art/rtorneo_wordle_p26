# Reglas del Torneo

## Mecanica del Juego

Wordle es un juego de adivinanza de palabras. En cada juego:
1. Se elige una palabra secreta del vocabulario.
2. La estrategia realiza hasta 6 intentos.
3. Despues de cada intento, se proporciona retroalimentacion:
   - **2 (verde):** letra correcta en la posicion correcta.
   - **1 (amarillo):** letra correcta en la posicion incorrecta.
   - **0 (gris):** la letra no esta en la palabra (o ya fue consumida).
4. Un juego se considera "resuelto" si la estrategia adivina la palabra secreta en 6 intentos o menos.

El algoritmo de retroalimentacion utiliza un enfoque de dos pasadas: primero se asignan los verdes, luego los amarillos, respetando los conteos de frecuencia de cada letra.

## Formato del Torneo

**6 rondas canonicas:** palabras de {4, 5, 6} letras x modos {uniform, frequency}. El torneo oficial usa el corpus completo (~2k-6k palabras reales por longitud, filtradas por diccionario Hunspell). El corpus mini (~50 palabras) esta disponible con `--corpus mini` para debug/testing rapido.

**Puntuacion:** En cada ronda, las estrategias se clasifican por el promedio de intentos (menor es mejor). El 1er lugar obtiene N puntos (N = total de estrategias), el 2do obtiene N-1, etc. Los empates reciben el promedio de puntos. Los puntos se suman a lo largo de las 6 rondas.

**Repeticiones:** El torneo puede ejecutarse con multiples repeticiones (cada una con una semilla aleatoria diferente) para mayor robustez estadistica. Los puntos se acumulan a traves de todas las repeticiones.

## Restricciones de Recursos

| Recurso | Limite |
|---------|--------|
| Tiempo por juego | 5 segundos (estricto) |
| Nucleos de CPU | 1 por estrategia |
| Memoria | 2 GB por estrategia |
| Dependencias | numpy + biblioteca estandar unicamente |
| Intentos maximos | 6 por juego |

El timeout de 5 segundos es **estricto** y se aplica con `signal.SIGALRM`. El presupuesto de 5 segundos cubre `begin_game()` + todos los `guess()` del juego. Si una estrategia excede el limite, el juego se registra como fallido (no resuelto, max_guesses + 1 intentos).

## Requisitos de la Estrategia

1. **Un solo archivo:** `estudiantes/<nombre_equipo>/strategy.py` — este es el **unico** archivo que el framework importa durante el torneo.
2. **Clase:** Debe ser subclase de `Strategy` de `strategy.py`.
3. **Nombre:** La propiedad `name` debe ser unica entre todos los equipos (convencion: `"NombreEstrategia_nombreequipo"`).
4. **Generalidad:** Debe funcionar para todas las longitudes de palabra (4, 5, 6) y ambos modos (uniform, frequency).
5. **Interfaz:** Usa unicamente `begin_game(config: GameConfig)` y `guess(history)`.
6. **Todo en un archivo:** Si necesitas funciones auxiliares, defínelas dentro de `strategy.py`. Otros archivos en tu directorio no seran accesibles durante la evaluacion.

Puedes tener otros archivos en tu directorio (notebooks, scripts, datos precomputados) para desarrollo local, pero **nada de eso sera cargado ni accesible** durante el torneo.

## Enfoques Prohibidos

- **No aprendizaje automatico** (redes neuronales, optimizacion basada en gradientes, modelos aprendidos)
- **No aprendizaje por refuerzo** (Q-learning, policy gradient, etc.)
- **Permitido:** Agentes basados en metas, agentes basados en utilidad, algoritmos de busqueda, simulaciones, metodos de teoria de la informacion, puntuacion heuristica, tablas precalculadas

La intencion es que las estrategias utilicen razonamiento algoritmico y teoria de la informacion, no parametros aprendidos.

## Perturbacion de Distribucion

En el modo `frequency` durante los torneos oficiales, se aplica una pequena perturbacion aleatoria (ruido blanco, tipicamente del 5%) a la distribucion de probabilidad. Esto:
- Prueba la robustez ante pequenos cambios en la distribucion
- Evita que las estrategias memoricen valores exactos de probabilidad
- Es transparente: las probabilidades perturbadas se pasan a la estrategia a traves de `GameConfig.probabilities`

La magnitud y la semilla de la perturbacion no se conocen de antemano.

## Criterios de Descalificacion

Una estrategia puede ser descalificada si:
- Falla consistentemente (excepciones no manejadas)
- Excede el limite de tiempo en la mayoria de los juegos
- Usa dependencias externas mas alla de numpy
- Intenta acceder a la palabra secreta durante el juego
- Utiliza tecnicas de ML/RL
- Modifica el estado del sistema o archivos fuera del directorio de su equipo

## Juego Limpio

- La semilla aleatoria para cada ronda del torneo se genera en tiempo de ejecucion y no se comparte con los equipos.
- Todas las estrategias reciben el mismo vocabulario, probabilidades y configuracion de juego.
- Las estrategias se ejecutan en procesos aislados (sin comunicacion entre estrategias).
