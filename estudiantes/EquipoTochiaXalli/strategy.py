from __future__ import annotations
import numpy as np
import random
from collections import defaultdict
from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates


class MyStrategy(Strategy):

    @property
    def name(self) -> str:
        return "EstrategiaEntropia_EquipoTochiaXalli"

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config

        # Openers mejorados — especialmente el de 4 letras uniform
        self._openers = {
            (4, "uniform"):   "sale",   # cubre s,a,l,e — letras muy comunes
            (4, "frequency"): "cora",
            (5, "uniform"):   "careo",
            (5, "frequency"): "careo",
            (6, "uniform"):   "careto",
            (6, "frequency"): "cerito",
        }

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:

        candidates = self._vocab
        for past_guess, pattern in history:
            candidates = filter_candidates(candidates, past_guess, pattern)

        if not candidates:
            return self._vocab[0]

        if len(candidates) == 1:
            return candidates[0]

        # Turno 1: opener fijo óptimo
        if not history:
            key = (self._config.word_length, self._config.mode)
            return self._openers.get(key, self._vocab[0])

        max_guesses = self._config.max_guesses
        turnos_jugados = len(history)
        guesses_left = max_guesses - turnos_jugados

        # Solo queda 1 turno → forzosamente el más probable
        if guesses_left <= 1:
            return self._mejor_por_probabilidad(candidates)

        # ============================================================
        # MODO EMERGENCIA: pocos turnos y muchos candidatos
        # Si quedan 2 turnos y más de 2 candidatos → DISCRIMINAR urgente
        # Si quedan 3 turnos y más de 3 candidatos → también discriminar
        # ============================================================
        if guesses_left == 2 and len(candidates) > 2:
            discriminador = self._buscar_discriminador(candidates, self._vocab)
            if discriminador:
                return discriminador

        if guesses_left == 3 and len(candidates) > 6:
            discriminador = self._buscar_discriminador(candidates, self._vocab)
            if discriminador:
                return discriminador

        # Candidatos caben en los turnos restantes con margen → adivinar directo
        if len(candidates) <= guesses_left - 1:
            return self._mejor_por_probabilidad(candidates)

        vocab_size = len(self._vocab)

        # ============================================================
        # Selección de palabras a evaluar
        # ============================================================
        if vocab_size <= 2000:
            # 4 letras: buscamos en TODO el vocabulario siempre
            palabras_a_evaluar = self._vocab

        elif len(candidates) <= 15:
            extra = random.sample(self._vocab, min(500, vocab_size))
            palabras_a_evaluar = list(set(candidates + extra))

        elif len(candidates) <= 100:
            extra = random.sample(self._vocab, min(400, vocab_size))
            palabras_a_evaluar = list(set(candidates + extra))

        else:
            muestra_cands = random.sample(candidates, min(150, len(candidates)))
            muestra_vocab = random.sample(self._vocab, min(150, vocab_size))
            palabras_a_evaluar = list(set(muestra_cands + muestra_vocab))

        mejor_guess = candidates[0]
        mejor_score = -1.0

        total_prob = sum(
            self._config.probabilities.get(c, 1.0) for c in candidates
        )
        if total_prob == 0:
            total_prob = 1.0

        for palabra in palabras_a_evaluar:
            distribucion = defaultdict(float)

            for c in candidates:
                patron = feedback(c, palabra)
                prob_c = self._config.probabilities.get(c, 1.0) / total_prob
                distribucion[patron] += prob_c

            probs_array = np.array(list(distribucion.values()))
            entropia = -np.sum(probs_array * np.log2(probs_array + 1e-9))

            bonus = 0.1 if palabra in candidates else 0.0
            score_final = entropia + bonus

            if score_final > mejor_score:
                mejor_score = score_final
                mejor_guess = palabra

        return mejor_guess

    def _buscar_discriminador(self, candidates, vocab):
        """
        Busca una palabra que separe los candidatos en grupos lo más
        pequeños posible. Ideal para situaciones de emergencia.
        """
        mejor = None
        mejor_max_grupo = len(candidates) + 1

        # Buscamos en todo el vocabulario para encontrar el mejor discriminador
        for palabra in vocab:
            grupos = defaultdict(int)
            for c in candidates:
                pat = feedback(c, palabra)
                grupos[pat] += 1

            # Queremos minimizar el grupo más grande (minimax)
            max_grupo = max(grupos.values())

            if max_grupo < mejor_max_grupo:
                mejor_max_grupo = max_grupo
                mejor = palabra

            # Si encontramos uno que separa todo perfectamente, usarlo ya
            if mejor_max_grupo == 1:
                break

        return mejor

    def _mejor_por_probabilidad(self, candidates):
        return max(
            candidates,
            key=lambda w: self._config.probabilities.get(w, 0.0)
        )
