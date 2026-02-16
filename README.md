# Wordle Tournament — IA Primavera 2026 ITAM

Torneo de estrategias de Wordle en español.
Tu equipo implementa **una sola** estrategia que resuelve Wordle para palabras de **4, 5 y 6 letras** en modos **uniform** y **frequency**.
El framework descubre todas las estrategias, las corre en paralelo, y genera un leaderboard.

---

## TL;DR — Setup en 3 comandos

```bash
pip install -r requirements.txt
python3 run_all.py              # descarga datos + corre torneo de prueba
```

Eso es todo. Descarga los corpus (si no existen), corre las 6 rondas oficiales con 10 juegos por ronda, e imprime el leaderboard.

---

## Que tienes que hacer (estudiantes)

### 1. Copia el template

```bash
cp -r estudiantes/_template estudiantes/mi_equipo
```

### 2. Edita `estudiantes/mi_equipo/strategy.py`

```python
from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates


class MiEstrategia(Strategy):
    @property
    def name(self) -> str:
        return "MiEstrategia_mi_equipo"   # <-- nombre unico

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        # Filtra candidatos con el feedback acumulado
        candidates = self._vocab
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)
        # ----- TU LOGICA AQUI -----
        return candidates[0]
```

**Tu estrategia debe funcionar para 4, 5 y 6 letras, en modo uniform y frequency.**

### 3. Prueba localmente

```bash
# Prueba rapida (verbose = ves cada intento)
python3 experiment.py --strategy "MiEstrategia_mi_equipo" --num-games 10 --verbose

# Probar 6 letras, modo frequency
python3 experiment.py --strategy "MiEstrategia_mi_equipo" --length 6 --mode frequency --verbose

# Torneo local: tu estrategia vs los 3 benchmarks (Random, MaxProb, Entropy)
python3 tournament.py --team mi_equipo --official --num-games 10
```

### 4. Entrega: abre un PR

```bash
git add estudiantes/mi_equipo/strategy.py
git commit -m "add strategy mi_equipo"
git push   # abre PR en GitHub
```

---

## Que se evalua y que no

**Solo se ejecuta `estudiantes/<equipo>/strategy.py`** — ese es el unico archivo que el framework importa durante el torneo. Todo tu codigo de estrategia debe estar en ese archivo (una sola clase que hereda de `Strategy`).

Puedes tener otros archivos en tu directorio para desarrollo local:
- Notebooks de analisis y experimentacion
- Scripts auxiliares para explorar datos
- Tablas precomputadas, graficas, resultados locales
- Otros archivos `.py` con funciones de apoyo

Pero **nada de eso sera accesible durante la evaluacion**. El framework solo importa `strategy.py` y ejecuta tu clase. Si necesitas funciones auxiliares, defínelas dentro del mismo archivo.

**Precomputacion:** Puedes hacer calculos costosos en `begin_game(config)` (se llama al inicio de cada juego). El presupuesto de 5 segundos cubre `begin_game()` + todos los `guess()` del juego.

---

## Que informacion recibe tu estrategia

Al inicio de cada juego se llama `begin_game(config)` con un `GameConfig`:

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `config.word_length` | `int` | 4, 5, o 6 |
| `config.vocabulary` | `tuple[str,...]` | Todas las palabras validas (la secreta sale de aqui) |
| `config.mode` | `str` | `"uniform"` o `"frequency"` |
| `config.probabilities` | `dict[str,float]` | palabra -> probabilidad (suman 1) |
| `config.max_guesses` | `int` | Intentos maximos (normalmente 6) |
| `config.allow_non_words` | `bool` | `True` = puedes adivinar CUALQUIER combinacion de letras |

En cada turno se llama `guess(history)` donde `history` es una lista de `(intento, feedback)`:
- `2` = verde (letra correcta, posicion correcta)
- `1` = amarillo (letra correcta, posicion incorrecta)
- `0` = gris (letra no esta en la palabra)

**Puedes adivinar cualquier combinacion de letras**, no solo palabras del vocabulario. Esto permite guesses exploratorios para ganar mas informacion.

---

## Formato del torneo

**6 rondas:**

| Ronda | Longitud | Modo |
|-------|----------|------|
| 1 | 4 letras | uniform |
| 2 | 4 letras | frequency |
| 3 | 5 letras | uniform |
| 4 | 5 letras | frequency |
| 5 | 6 letras | uniform |
| 6 | 6 letras | frequency |

**Scoring (Borda Count — como se decide quien gana):**

En cada ronda se rankean las estrategias por **promedio de intentos** (menor = mejor):

1. Se ordenan las estrategias de menor a mayor promedio de intentos
2. El **1er lugar** gana N puntos (N = total de estrategias), el 2do gana N-1, etc.
3. **Empates**: si dos estrategias empatan, reciben el promedio de puntos de sus posiciones
4. Los puntos se **suman a traves de las 6 rondas** (o 6 x repeticiones)
5. **Gana quien tenga mas puntos totales**

Juegos no resueltos y timeouts cuentan como `max_guesses + 1` intentos.

Ejemplo con 4 estrategias y 6 rondas:

| Ronda | 1er (4pts) | 2do (3pts) | 3er (2pts) | 4to (1pt) |
|-------|-----------|-----------|-----------|----------|
| 4-uniform | Entropy | MiBot | MaxProb | Random |
| 4-frequency | MiBot | Entropy | MaxProb | Random |
| ... | ... | ... | ... | ... |
| **Total** | **Entropy: 22** | **MiBot: 20** | **MaxProb: 14** | **Random: 7** |

Al final del torneo se muestra el **leaderboard completo** con los **top 3 destacados** (oro, plata, bronce).

**Restricciones:**
- Maximo **6 intentos** por juego
- Timeout de **5 segundos por juego** (estricto — incluye `begin_game` + todos los `guess`)
- **1 core** de CPU por estrategia (forzado automaticamente)
- **2GB** de memoria maxima por estrategia
- Seed **aleatoria** (no la conoces de antemano)
- Estrategias se ejecutan en **lotes** para evitar sobrecarga del sistema

**Distribution shock:** En modo `frequency`, se aplica una perturbacion (white noise) a las probabilidades. Las probabilidades perturbadas se pasan via `GameConfig` — son visibles pero no predecibles.

---

## Reglas

1. **Un archivo**: `estudiantes/<equipo>/strategy.py`. Eso es tu entrega. Todo tu codigo debe estar ahi.
2. **Nombre unico**: `name` debe incluir el nombre del equipo (ej: `"MiEstrategia_mi_equipo"`).
3. **Sin dependencias extra**: Solo `numpy` + libreria estandar de Python.
4. **No ML/RL**: Usa agentes basados en metas o utilidad. Simulaciones si estan permitidas.
5. **5 segundos** maximo por juego (un secreto, hasta 6 intentos). El timeout es estricto.
6. **1 core** de CPU.
7. **No hagas trampa**: Solo recibes `history` de `(intento, feedback)`. No puedes acceder al secreto.

---

## Benchmarks incluidos

Tu estrategia compite contra estos 3 benchmarks:

| Estrategia | Que hace |
|-----------|----------|
| **Random** | Elige al azar entre candidatos restantes |
| **MaxProb** | Elige el candidato mas probable |
| **Entropy** | Maximiza la ganancia de informacion (entropia de Shannon) |

Si tu estrategia no le gana a Random, algo anda mal.

---

## Comandos

### Un solo comando (recomendado)

```bash
# Prueba rapida (descarga datos + torneo con 10 juegos/ronda)
python3 run_all.py

# Torneo mas serio (100 juegos/ronda)
python3 run_all.py --num-games 100

# Solo tu equipo vs benchmarks
python3 run_all.py --team mi_equipo --num-games 20

# Con dashboard (abre el navegador al terminar)
python3 run_all.py --num-games 50 --dashboard
```

### Evaluacion real (profesor)

```bash
# Torneo de evaluacion: todas las estrategias, 100 juegos/ronda, 3 repeticiones, 5% shock
python3 run_all.py --real

# Con dashboard
python3 run_all.py --real --dashboard

# Custom: mas juegos, seed fija
python3 run_all.py --real --num-games 200 --seed 42

# Via Docker (identico, en contenedor aislado)
docker compose up real-tournament
```

### Torneo (granular)

```bash
python3 tournament.py --official --num-games 100
python3 tournament.py --official --repetitions 5 --num-games 100
python3 tournament.py --official --shock 0.05 --num-games 100
python3 tournament.py --official --name "Torneo Final" --num-games 100
python3 tournament.py --team mi_equipo --official --num-games 50
```

### Experimento individual

```bash
python3 experiment.py --strategy "Random" --num-games 20 --verbose
python3 experiment.py --strategy "Entropy" --length 6 --mode frequency --num-games 50 --verbose
python3 experiment.py --strategy "MiEstrategia_mi_equipo" --team mi_equipo --num-games 10 --verbose
```

### Solo descargar datos

```bash
python3 download_words.py --all-lengths
python3 run_all.py --setup-only
```

---

## Utilidades para tu estrategia

```python
from wordle_env import feedback, filter_candidates
from lexicon import load_lexicon

# Simular feedback entre dos palabras
pat = feedback("canto", "arcos")  # -> (1, 0, 1, 1, 0)
# 2=verde, 1=amarillo, 0=gris

# Filtrar candidatos por feedback
remaining = filter_candidates(word_list, "arcos", (1, 0, 1, 1, 0))

# Cargar lexico con probabilidades
lex = load_lexicon(word_length=5, mode="frequency")
lex.words   # -> ['abaco', 'abajo', ...]
lex.probs   # -> {'abaco': 0.00012, ...}
```

Usa `feedback()` y `filter_candidates()` — estan optimizadas y son las mismas que usa el motor del juego.

---

## Dashboard

```bash
# Lanzar dashboard (abre http://localhost:8080)
python3 run_all.py --dashboard-only

# Torneo + dashboard al terminar
python3 run_all.py --num-games 50 --dashboard

# Via Docker
docker compose up dashboard
```

El dashboard incluye:
- **Panel de control** para lanzar y detener torneos desde el navegador
- **Presets** (Rapido, Oficial, Real) que rellenan el formulario — lanzas cuando quieras
- **Nombre opcional** para cada torneo
- **Historial de torneos** — cada ejecucion se guarda automaticamente; dropdown para cargar resultados anteriores
- **Leaderboard** con medallas para el top 3, explicacion del sistema de puntuacion
- **Detalle por ronda**, distribucion de intentos, y comparacion entre estrategias
- **Barra de progreso** en tiempo real durante la ejecucion

---

## Docker (todo en contenedor)

```bash
docker compose up download            # descargar corpus
docker compose up tournament           # torneo oficial (100 juegos/ronda)
docker compose up real-tournament      # evaluacion real (100 juegos, 3 reps, shock)
docker compose up dashboard            # dashboard en http://localhost:8080

# Experimento
STRATEGY=Entropy LENGTH=6 MODE=frequency NUM_GAMES=50 docker compose up experiment

# Tu equipo
TEAM=mi_equipo docker compose up team-tournament
```

---

## Estructura del repositorio

```
rtorneo_wordle_p26/
├── run_all.py            # Un comando para todo (setup + torneo + dashboard)
├── strategy.py           # Clase base (Strategy) + GameConfig
├── wordle_env.py         # Motor del juego (feedback, filtrado)
├── lexicon.py            # Carga de palabras + modos uniform/frequency
├── tournament.py         # Torneo paralelo (oficial y custom)
├── experiment.py         # Pruebas individuales con output detallado
├── download_words.py     # Descarga corpus desde OpenSLR
├── strategies/           # Benchmarks: Random, MaxProb, Entropy
├── estudiantes/          # <-- AQUI VA TU ESTRATEGIA
│   ├── _template/        #     Template para copiar
│   └── <tu-equipo>/
│       └── strategy.py   #     Tu estrategia (UNICO archivo evaluado)
├── data/                 # Listas de palabras (mini + full)
├── results/              # Salidas del torneo
│   ├── runs/             #     Historial: results/runs/<timestamp>/
│   └── latest.json       #     Ultimo torneo (para el dashboard)
├── dashboard/            # Dashboard web (HTML + JS + Chart.js)
├── docs/                 # Documentacion adicional (reglas, guia)
├── Dockerfile
├── docker-compose.yaml
└── requirements.txt
```

---

## Outputs

| Archivo | Que es |
|---------|--------|
| `results/runs/<timestamp>/tournament_results.json` | Datos completos del torneo (para dashboard) |
| `results/latest.json` | Copia del ultimo torneo ejecutado |
| `results/tournament_official.csv` | CSV: strategy, secret, num_guesses, solved |
| `results/tournament_official.png` | Histogramas de distribucion de intentos |
| `estudiantes/<equipo>/results/` | Resultados locales de tu equipo |
