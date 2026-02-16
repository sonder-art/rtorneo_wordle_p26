# Guia para Equipos

Guia paso a paso para configurar tu equipo y desarrollar una estrategia competitiva de Wordle.

## Paso 1: Configuracion Inicial

```bash
git clone <repo-url>
cd rtorneo_wordle_p26
pip install -r requirements.txt
python3 run_all.py --setup-only    # descarga las listas de palabras para 4, 5 y 6 letras
```

## Paso 2: Crea el Directorio de tu Equipo

```bash
cp -r estudiantes/_template estudiantes/nombre_de_tu_equipo
```

Estructura de tu directorio:
```
estudiantes/nombre_de_tu_equipo/
    strategy.py      # <-- UNICO ARCHIVO EVALUADO (todo tu codigo debe estar aqui)
    results/          # Se crea automaticamente para las salidas locales de experiment/tournament
    ...               # Agrega lo que necesites para desarrollo (notebooks, scripts, datos)
```

**Importante:** Solo se ejecuta `strategy.py` durante el torneo. El framework importa unicamente ese archivo. Puedes tener notebooks de analisis, scripts auxiliares, tablas precomputadas y otros archivos en tu directorio para experimentacion local, pero **nada de eso sera accesible durante la evaluacion**. Si necesitas funciones auxiliares, defínelas dentro del mismo `strategy.py`.

## Paso 3: Implementa tu Estrategia

Edita `estudiantes/nombre_de_tu_equipo/strategy.py`:

1. **Renombra** la clase y actualiza la propiedad `name`
2. **Implementa** tu logica en `guess()`
3. **Usa** `config` en `begin_game()` para acceder a la informacion del juego

Informacion clave disponible a traves de `GameConfig`:
- `config.word_length` — 4, 5 o 6
- `config.vocabulary` — todas las palabras validas (tupla)
- `config.mode` — "uniform" o "frequency"
- `config.probabilities` — diccionario palabra -> probabilidad (suma 1)
- `config.max_guesses` — intentos maximos (6)
- `config.allow_non_words` — True = puedes adivinar CUALQUIER combinacion de letras, no solo palabras del vocabulario

## Paso 4: Prueba tu Estrategia

### Experimento rapido
```bash
python3 experiment.py --strategy "TuNombre_equipo" --num-games 10 --verbose
```

### Prueba diferentes configuraciones
```bash
# Palabras de 4 letras, uniforme
python3 experiment.py --strategy "TuNombre_equipo" --length 4 --num-games 20 --verbose

# Palabras de 6 letras, frecuencia
python3 experiment.py --strategy "TuNombre_equipo" --length 6 --mode frequency --num-games 20 --verbose
```

### Torneo local (contra benchmarks)
```bash
# Comparacion rapida (6 rondas oficiales)
python3 tournament.py --team nombre_de_tu_equipo --official --num-games 10

# O usa run_all.py (descarga datos si es necesario tambien)
python3 run_all.py --team nombre_de_tu_equipo --num-games 20
```

Todos los resultados se guardan en `estudiantes/nombre_de_tu_equipo/results/` como JSON, CSV y PNG.

## Paso 5: Analiza los Resultados

### Salida en terminal
Los comandos de experiment y tournament imprimen estadisticas detalladas en la terminal.

### Archivos JSON
Los resultados se guardan como JSON estructurado en tu directorio de resultados:
```bash
cat estudiantes/nombre_de_tu_equipo/results/experiment_tunombre_equipo.json | python3 -m json.tool
```

### Dashboard
```bash
python3 run_all.py --num-games 50 --dashboard
# Abre http://localhost:8080
```

## Paso 6: Entrega

```bash
git add estudiantes/nombre_de_tu_equipo/strategy.py
git commit -m "add strategy nombre_de_tu_equipo"
git push origin main
# Abre un Pull Request en GitHub
```

Solo `strategy.py` es evaluado. Todo lo demas en tu directorio (notebooks, scripts, datos precomputados) es para tu propio desarrollo y no sera cargado durante el torneo.

## Consejos

- **Empieza simple.** La plantilla ya filtra candidatos por retroalimentacion. Construye sobre eso.
- **Monitorea tus tiempos.** Usa `--verbose` para ver detalles por intento. Mantente por debajo de 5 segundos en total por juego (el timeout es estricto e incluye `begin_game()` + todos los `guess()`).
- **Prueba todas las configuraciones.** Tu estrategia debe funcionar para palabras de 4, 5 y 6 letras en ambos modos.
- **Usa los benchmarks.** Random, MaxProb y Entropy son tus competidores base. Si superas a Entropy, vas muy bien.
- **Ejecuta simulaciones.** Puedes usar `feedback()` y `filter_candidates()` dentro de tu estrategia para simular resultados.
- **Piensa en terminos de teoria de la informacion.** Cada intento debe maximizar la informacion que obtienes sobre la palabra secreta.
- **Intentos con no-palabras.** Puedes adivinar cualquier combinacion de letras (ej. "aeiou") para maximizar informacion, aunque no sea una palabra real.
- **Precomputacion.** Puedes hacer calculos costosos en `begin_game(config)` (se llama al inicio de cada juego). Pero recuerda que los 5 segundos cubren todo: `begin_game()` + todos los `guess()`.

## Utilidades Disponibles

```python
from wordle_env import feedback, filter_candidates
from lexicon import load_lexicon

# Calcula la retroalimentacion para cualquier intento contra cualquier palabra secreta
fb = feedback("canto", "arcos")  # -> (1, 0, 1, 1, 0)

# Filtra candidatos consistentes con la retroalimentacion
remaining = filter_candidates(word_list, "arcos", (1, 0, 1, 1, 0))

# Carga la lista completa de palabras con probabilidades
lex = load_lexicon(word_length=5, mode="frequency")
```
