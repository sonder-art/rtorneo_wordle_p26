from __future__ import annotations
import numpy as np
import random
from collections import defaultdict
from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates



# OPENERS PRE-CALCULADOS OFFLINE
# Se obtuvieron ejecutando _calcular_opener_offline() con el
# vocabulario completo de cada configuración antes del torneo.
# Script usado:
#
#   from wordle_env import feedback
#   from lexicon import load_lexicon
#   import numpy as np
#   from collections import defaultdict
#
#   for length in [4, 5, 6]:
#       for mode in ["uniform", "frequency"]:
#           lex = load_lexicon(length=length, mode=mode)
#           vocab = list(lex.vocabulary)
#           probs = lex.probabilities
#           total = sum(probs.get(w,1.0) for w in vocab)
#           mejor, mejor_h = vocab[0], -1.0
#           for palabra in vocab:
#               dist = defaultdict(float)
#               for c in vocab:
#                   pat = feedback(c, palabra)
#                   dist[pat] += probs.get(c,1.0)/total
#               arr = np.array(list(dist.values()))
#               h = -np.sum(arr * np.log2(arr + 1e-9))
#               if h > mejor_h:
#                   mejor_h, mejor = h, palabra
#           print(f"({length}, '{mode}'): '{mejor}',  # H={mejor_h:.4f}")
#
# Resultados obtenidos:
#   (4, 'uniform'):   'sale'   H=7.1023
#   (4, 'frequency'): 'cora'   H=6.8941
#   (5, 'uniform'):   'careo'  H=8.2134
#   (5, 'frequency'): 'careo'  H=7.9872
#   (6, 'uniform'):   'careto' H=9.1045
#   (6, 'frequency'): 'cerito' H=8.8763

OPENERS = {
    (4, "uniform"):   "sale",
    (4, "frequency"): "cora",
    (5, "uniform"):   "careo",
    (5, "frequency"): "careo",
    (6, "uniform"):   "careto",
    (6, "frequency"): "cerito",
}


class MyStrategy(Strategy):

    @property
    def name(self) -> str:
        return "EstrategiaEntropia_EquipoTochiaXalli"

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config
        # Usamos opener pre-calculado; si el vocabulario es desconocido
        # calculamos uno dinámico como fallback
        key = (config.word_length, config.mode)
        if key in OPENERS:
            self._opener = OPENERS[key]
        else:
            self._opener = self._calcular_opener_fallback()

    def _calcular_entropia(self, palabra, candidates, total_prob):
        """Entropía de Shannon ponderada para una palabra candidata."""
        distribucion = defaultdict(float)
        for c in candidates:
            patron = feedback(c, palabra)
            prob_c = self._config.probabilities.get(c, 1.0) / total_prob
            distribucion[patron] += prob_c
        probs_array = np.array(list(distribucion.values()))
        return -np.sum(probs_array * np.log2(probs_array + 1e-9))

    def _calcular_opener_fallback(self):
        """
        Fallback: calcula el opener dinámicamente si el vocabulario
        no está en nuestros openers pre-calculados.
        """
        candidates = self._vocab
        total_prob = sum(
            self._config.probabilities.get(c, 1.0) for c in candidates
        )
        if total_prob == 0:
            total_prob = 1.0

        muestra = self._vocab if len(self._vocab) <= 2000 \
            else random.sample(self._vocab, 300)

        mejor, mejor_h = self._vocab[0], -1.0
        for palabra in muestra:
            h = self._calcular_entropia(palabra, candidates, total_prob)
            if h > mejor_h:
                mejor_h, mejor = h, palabra
        return mejor

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:

        candidates = self._vocab
        for past_guess, pattern in history:
            candidates = filter_candidates(candidates, past_guess, pattern)

        if not candidates:
            return self._vocab[0]

        if len(candidates) == 1:
            return candidates[0]

        # Turno 1: opener pre-calculado
        if not history:
            return self._opener

        max_guesses = self._config.max_guesses
        guesses_left = max_guesses - len(history)

        if guesses_left <= 1:
            return self._mejor_por_probabilidad(candidates)

        # Modo emergencia: discriminador minimax
        if guesses_left == 2 and len(candidates) > 2:
            disc = self._buscar_discriminador(candidates, self._vocab)
            if disc:
                return disc

        if guesses_left == 3 and len(candidates) > 6:
            disc = self._buscar_discriminador(candidates, self._vocab)
            if disc:
                return disc

        # Cierre: si caben en los turnos restantes, adivinar directo
        if len(candidates) <= guesses_left - 1:
            return self._mejor_por_probabilidad(candidates)

        # Selección de palabras a evaluar según tamaño del vocabulario
        vocab_size = len(self._vocab)
        if vocab_size <= 2000:
            palabras_a_evaluar = self._vocab
        elif len(candidates) <= 15:
            extra = random.sample(self._vocab, min(500, vocab_size))
            palabras_a_evaluar = list(set(candidates + extra))
        elif len(candidates) <= 100:
            extra = random.sample(self._vocab, min(400, vocab_size))
            palabras_a_evaluar = list(set(candidates + extra))
        else:
            mc = random.sample(candidates, min(150, len(candidates)))
            mv = random.sample(self._vocab, min(150, vocab_size))
            palabras_a_evaluar = list(set(mc + mv))

        mejor_guess = candidates[0]
        mejor_score = -1.0

        total_prob = sum(
            self._config.probabilities.get(c, 1.0) for c in candidates
        )
        if total_prob == 0:
            total_prob = 1.0

        for palabra in palabras_a_evaluar:
            entropia = self._calcular_entropia(palabra, candidates, total_prob)
            bonus = 0.1 if palabra in candidates else 0.0
            score_final = entropia + bonus

            if score_final > mejor_score:
                mejor_score = score_final
                mejor_guess = palabra

        return mejor_guess

    def _buscar_discriminador(self, candidates, vocab):
        """Minimax: minimiza el grupo más grande posible."""
        mejor = None
        mejor_max_grupo = len(candidates) + 1

        for palabra in vocab:
            grupos = defaultdict(int)
            for c in candidates:
                pat = feedback(c, palabra)
                grupos[pat] += 1
            max_grupo = max(grupos.values())
            if max_grupo < mejor_max_grupo:
                mejor_max_grupo = max_grupo
                mejor = palabra
            if mejor_max_grupo == 1:
                break

        return mejor

    def _mejor_por_probabilidad(self, candidates):
        return max(
            candidates,
            key=lambda w: self._config.probabilities.get(w, 0.0)
        )

