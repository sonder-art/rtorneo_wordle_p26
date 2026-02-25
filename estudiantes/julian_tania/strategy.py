"""Strategy template — copy this directory to estudiantes/<your_team>/

Rename the class and the ``name`` property, then implement your logic
in the ``guess`` method.
"""

from __future__ import annotations
import numpy as np
import random
from collections import defaultdict
from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates


class MyStrategy(Strategy):
    """Nuestra estrategia será híbrida, basada en la Entropía (Numpy) y Score Esperado (W.5+W.6)."""

    @property
    def name(self) -> str:
        # Convention: "StrategyName_teamname"
        return "EntropyMaster_julian_tania"  # <-- CHANGE THIS

    def begin_game(self, config: GameConfig) -> None:
        """Called once at the start of each game.

        Available information in config:
          - config.word_length    (int)  — 4, 5, or 6
          - config.vocabulary     (tuple) — all valid words (secret is from here)
          - config.mode           (str)  — "uniform" or "frequency"
          - config.probabilities  (dict) — word -> probability (sums to 1)
          - config.max_guesses    (int)  — maximum guesses allowed (typically 6)
          - config.allow_non_words (bool) — True = you can guess ANY letter combo
        """
        self._vocab = list(config.vocabulary)
        self._config = config

        # Openers pre-computados: Las mejores aperturas para cada variante del juego (uniform o frecuency, longitud 4, 5 o 6)
        self._openers = {
            (4, "uniform"): "roia",
            (4, "frequency"): "cora",
            (5, "uniform"): "careo",
            (5, "frequency"): "careo",
            (6, "uniform"): "careto",
            (6, "frequency"): "cerito",
        }

    def guess(self, history: list[tuple[str, tuple[int, ...]]]) -> str:
        """Return the next guess.

        Parameters
        ----------
        history : list of (guess, feedback) tuples
            Each feedback is a tuple of ints:
              2 = green (correct letter, correct position)
              1 = yellow (correct letter, wrong position)
              0 = gray (letter not in word)

        Returns
        -------
        str
            A lowercase string of length config.word_length.
            Can be ANY letter combination (not restricted to vocabulary)
            for better information discovery.
        """
        # Filter candidates consistent with all feedback so far
        candidates = self._vocab
        for g, pat in history:
            candidates = filter_candidates(candidates, g, pat)

        if not candidates:
            return self._vocab[0]

        # -------------------------------------------------------
        # YOUR LOGIC HERE
        # Replace the line below with your strategy.
        # You have access to:
        #   - candidates: remaining valid words
        #   - self._config.probabilities: word -> probability
        #   - self._config.mode: "uniform" or "frequency"
        #   - self._config.word_length: 4, 5, or 6
        #   - feedback(secret, guess): compute feedback pattern
        #   - filter_candidates(words, guess, pattern): filter words
        # -------------------------------------------------------

        # Caso de un solo candidato restante por si acaso
        if len(candidates) == 1:
            return candidates[0]
        
        # Si es el turno 1: usamos el opener precalculado
        if not history:
            key = (self._config.word_length, self._config.mode)
            return self._openers.get(key, self._vocab[0])
        
        # Si estamos en el turno 5 o 6: usamos score esperado o máxima probabilidad
        # Apagamos la entropía
        if len(candidates) <= 10 or len(history) >= 4:
            # Ordenamos de mayor a menor probabilidad y disparamos a la primera
            candidates.sort(key=lambda w: self._config.probabilities.get(w, 0), reverse=True)
            return candidates[0]
        
        # Si estamos en los primeros turnos: usamos entropía
        guesses_to_test = candidates
        # Si hay más de 150 palabras por testear, tomamos un sample de 150 palabras para ahorrar tiempo de cálculo
        if len(candidates) > 150:
            guesses_to_test = random.sample(candidates, 150)
        
        best_guess = candidates[0]
        max_entropy = -1.0

        # Suma para normalizar probabilidades
        total_prob = sum(self._config.probabilities.get(c, 1.0) for c in candidates)
        if total_prob == 0: total_prob = 1.0

        # Calculamos la entropía de cada posible guess sobre los candidatos restantes
        for g in guesses_to_test:
            pattern_probs = defaultdict(float)
            
            # Simulación contra posibles respuestas
            for c in candidates:
                pat = feedback(c, g)
                prob_c = self._config.probabilities.get(c, 1.0) / total_prob
                pattern_probs[pat] += prob_c
            
            # Ecuación de Shannon con NumPy
            p_array = np.array(list(pattern_probs.values()))
            entropy = -np.sum(p_array * np.log2(p_array + 1e-9))
            
            if entropy > max_entropy:
                max_entropy = entropy
                best_guess = g

        return best_guess