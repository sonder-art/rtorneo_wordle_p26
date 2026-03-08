from __future__ import annotations
import math
from collections import defaultdict, Counter
from strategy import Strategy, GameConfig
from wordle_env import feedback, filter_candidates


# -------------------------------------------------------------------- #
#  OPENERS PRE-CALCULADOS OFFLINE                                       #
#  Calculados minimizando score esperado (W.6) contra el vocabulario    #
#  completo de cada configuracion. Pre-calcular ahorra ~1-2 seg de      #
#  begin_game(), dejando todo el presupuesto de 5 seg para guess().     #
#                                                                       #
#  Script para recalcular si cambia el vocabulario:                     #
#                                                                       #
#    from wordle_env import feedback                                    #
#    from lexicon import load_lexicon                                   #
#    from collections import defaultdict                                #
#    import math                                                        #
#                                                                       #
#    for length in [4, 5, 6]:                                           #
#      for mode in ["uniform", "frequency"]:                            #
#        lex = load_lexicon(length=length, mode=mode)                   #
#        vocab = list(lex.vocabulary)                                   #
#        probs = lex.probabilities                                      #
#        total = sum(probs.get(w,1.0) for w in vocab)                   #
#        if total == 0: total = 1.0                                     #
#        # Evaluar top-500 por cobertura de letras                      #
#        from collections import Counter                                #
#        freq = Counter()                                               #
#        for w in vocab: freq.update(set(w))                            #
#        top = sorted(vocab, key=lambda p: sum(freq[c]                  #
#                     for c in set(p)), reverse=True)[:500]             #
#        mejor, mejor_s = vocab[0], float('inf')                        #
#        for palabra in top:                                            #
#            grupos = defaultdict(list)                                  #
#            for c in vocab:                                             #
#                pat = feedback(c, palabra)                              #
#                grupos[pat].append(c)                                   #
#            score = 0.0                                                 #
#            for g in grupos.values():                                   #
#                pw = sum(probs.get(c,1.0) for c in g) / total          #
#                ng = len(g)                                             #
#                if ng == 1: cost = 1.0                                  #
#                elif ng == 2: cost = 1.5                                #
#                else: cost = 1.0 + math.log2(ng)                       #
#                score += pw * cost                                      #
#            if score < mejor_s:                                         #
#                mejor_s, mejor = score, palabra                         #
#        print(f"({length}, '{mode}'): '{mejor}',  # S={mejor_s:.4f}")  #
# -------------------------------------------------------------------- #

OPENERS = {
    (4, "uniform"):   "sale",
    (4, "frequency"): "cora",
    (5, "uniform"):   "careo",
    (5, "frequency"): "careo",
    (6, "uniform"):   "careto",
    (6, "frequency"): "cerito",
}


class MyStrategy(Strategy):
    """
    Estrategia basada en Minimizacion de Score Esperado (W.6).
    E[intentos] = suma p(patron) * costo(grupo_resultante).

    Mejoras clave:
    - Openers pre-calculados (ahorra tiempo para los guess)
    - Busqueda en TODO el vocabulario cuando el presupuesto lo permite
    - Discriminador minimax para situaciones criticas
    """

    @property
    def name(self) -> str:
        return "Estrategia_EquipoTochiaXalli"

    def begin_game(self, config: GameConfig) -> None:
        self._vocab = list(config.vocabulary)
        self._config = config
        self._word_len = config.word_length

        # Opener pre-calculado (o fallback dinamico)
        key = (config.word_length, config.mode)
        if key in OPENERS and OPENERS[key] in config.vocabulary:
            self._opener = OPENERS[key]
        else:
            self._opener = self._calcular_opener_fallback()

        # Frecuencia global de letras (para ranking de pools)
        self._freq = Counter()
        for w in self._vocab:
            self._freq.update(set(w))

    #  SCORE ESPERADO (W.6)                                               

    def _score_esperado(self, palabra, candidates):
        """
        Numero esperado de intentos adicionales si adivinamos `palabra`.

        E[costo] = suma p(patron) * costo(grupo)

        costo(grupo):
          |grupo| == 1 -> 1.0
          |grupo| == 2 -> 1.5
          |grupo| >= 3 -> 1 + log2(|grupo|)

        MINIMIZAR = mejor.
        """
        if not candidates:
            return float('inf')

        probs = self._config.probabilities
        total = sum(probs.get(c, 1.0) for c in candidates)
        if total == 0:
            total = 1.0

        grupos = defaultdict(list)
        for c in candidates:
            pat = feedback(c, palabra)
            grupos[pat].append(c)

        score = 0.0
        for grupo in grupos.values():
            prob_patron = sum(probs.get(c, 1.0) for c in grupo) / total

            ng = len(grupo)
            if ng == 1:
                costo = 1.0
            elif ng == 2:
                costo = 1.5
            else:
                costo = 1.0 + math.log2(ng)

            score += prob_patron * costo

        return score

    #  OPENER FALLBACK                                                    

    def _calcular_opener_fallback(self):
        """Calcula opener si el vocab no esta en la tabla."""
        freq = self._freq if hasattr(self, '_freq') else Counter()
        if not freq:
            for w in self._vocab:
                freq.update(set(w))

        def cobertura(p):
            return sum(freq[c] for c in set(p))

        candidatas = sorted(self._vocab, key=cobertura, reverse=True)[:400]

        mejor = candidatas[0]
        mejor_score = float('inf')

        for palabra in candidatas:
            s = self._score_esperado(palabra, self._vocab)
            if s < mejor_score:
                mejor_score = s
                mejor = palabra

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
        n = len(candidates)

        # Ultimo turno: apostar por el mas probable
        if guesses_left <= 1:
            return self._mejor_candidato(candidates)

        # Pocos candidatos que caben en turnos restantes
        if n <= guesses_left - 1:
            return self._mejor_candidato(candidates)

        # ---- EMERGENCIAS: discriminador minimax ----
        # Busca la palabra (de TODO el vocab) que minimiza el grupo
        # mas grande. Garantiza que el peor caso sea manejable.

        if guesses_left <= 2 and n > 2:
            disc = self._discriminador(candidates)
            if disc:
                return disc

        if guesses_left == 3 and n > 4:
            disc = self._discriminador(candidates)
            if disc:
                return disc

        if guesses_left == 4 and n > 12:
            disc = self._discriminador(candidates)
            if disc:
                return disc

        # ---- CASO GENERAL: minimizar score esperado ----
        pool = self._construir_pool(candidates)

        cand_set = set(candidates)
        mejor = candidates[0]
        mejor_score = float('inf')

        for palabra in pool:
            s = self._score_esperado(palabra, candidates)
            # Bonus si la palabra puede ser la respuesta correcta
            if palabra in cand_set:
                s -= 0.05
            if s < mejor_score:
                mejor_score = s
                mejor = palabra

        return mejor


    def _construir_pool(self, candidates):
        """
        Decide cuantas palabras evaluar segun el presupuesto de tiempo.
        Para vocabularios chicos (<=2000, como 4 letras), evalua TODO.
        Para vocabularios grandes, usa top-K por cobertura.
        """
        n = len(candidates)
        v = len(self._vocab)

        # Si el vocabulario es chico, evaluar TODO — este es el cambio
        # clave que hace la diferencia vs. pools fijos
        if v <= 2000:
            return self._vocab

        # Vocabulario grande: presupuesto adaptativo
        # Cada palabra cuesta n llamadas a feedback()
        # Presupuesto conservador: ~500k llamadas
        budget = 500_000
        max_pool = budget // max(n, 1)

        if max_pool >= v:
            return self._vocab

        # Frecuencia de letras en candidatos actuales
        freq_actual = Counter()
        for w in candidates:
            freq_actual.update(set(w))

        def cobertura(p):
            return sum(freq_actual[c] for c in set(p))

        k = min(max_pool, v)
        extra = sorted(self._vocab, key=cobertura, reverse=True)[:k]
        return list(set(candidates) | set(extra))



    def _discriminador(self, candidates):
        """
        Busca en TODO el vocabulario la palabra que minimiza el
        grupo mas grande (peor caso). Desempata por mas grupos
        distintos, luego prefiere candidatos.
        """
        mejor = None
        mejor_distintos = 0
        mejor_max_grupo = len(candidates) + 1
        cand_set = set(candidates)

        for palabra in self._vocab:
            grupos = defaultdict(int)
            for c in candidates:
                pat = feedback(c, palabra)
                grupos[pat] += 1

            distintos = len(grupos)
            max_grupo = max(grupos.values())

            # Priorizar: mas grupos distintos, luego menor max grupo,
            # luego preferir candidatos como tiebreaker
            if (distintos > mejor_distintos or
                (distintos == mejor_distintos and
                 max_grupo < mejor_max_grupo) or
                (distintos == mejor_distintos and
                 max_grupo == mejor_max_grupo and
                 palabra in cand_set)):
                mejor_distintos = distintos
                mejor_max_grupo = max_grupo
                mejor = palabra

            if mejor_max_grupo == 1:
                break

        return mejor


    def _mejor_candidato(self, candidates):
        """Devuelve el candidato con mayor probabilidad."""
        return max(
            candidates,
            key=lambda w: self._config.probabilities.get(w, 0.0)
        )