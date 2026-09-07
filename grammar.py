from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path


EPSILON = "ε"
EOF = "EOF"


def _common_prefix(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, ...]:
    prefix: list[str] = []
    for left, right in zip(first, second):
        if left != right:
            break
        prefix.append(left)
    return tuple(prefix)


@dataclass(frozen=True)
class Production:
    lhs: str
    rhs: tuple[str, ...]

    def __str__(self) -> str:
        symbols = " ".join(self.rhs) if self.rhs else EPSILON
        return f"{self.lhs} ::= {symbols}"


class Grammar:
    def __init__(self, productions: list[Production]):
        if not productions:
            raise ValueError("a gramática deve possuir ao menos uma produção")

        self.start_symbol = productions[0].lhs
        self.nonterminals = list(
            dict.fromkeys(production.lhs for production in productions)
        )
        self._by_lhs: dict[str, list[Production]] = {
            nonterminal: [] for nonterminal in self.nonterminals
        }
        for production in productions:
            self._by_lhs[production.lhs].append(production)

        self.first: dict[str, set[str]] = {}
        self.follow: dict[str, set[str]] = {}
        self.start: dict[Production, set[str]] = {}

    @property
    def productions(self) -> list[Production]:
        return [
            production
            for nonterminal in self.nonterminals
            for production in self._by_lhs[nonterminal]
        ]

    @property
    def terminals(self) -> set[str]:
        nonterminals = set(self.nonterminals)
        return {
            symbol
            for production in self.productions
            for symbol in production.rhs
            if symbol not in nonterminals
        }

    @classmethod
    def from_text(cls, text: str) -> Grammar:
        productions: list[Production] = []

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "::=" not in line:
                raise ValueError(f"linha {line_number}: esperado '::='")

            lhs, rhs = line.split("::=", 1)
            lhs = lhs.strip()
            if not lhs:
                raise ValueError(f"linha {line_number}: lado esquerdo vazio")

            for alternative in rhs.split("|"):
                alternative = alternative.strip()
                if not alternative:
                    raise ValueError(
                        f"linha {line_number}: alternativa vazia deve usar ε"
                    )
                symbols = tuple(alternative.split())
                if symbols == (EPSILON,):
                    symbols = ()
                elif EPSILON in symbols:
                    raise ValueError(
                        f"linha {line_number}: ε deve ser a alternativa completa"
                    )
                productions.append(Production(lhs, symbols))

        return cls(productions)

    @classmethod
    def from_file(cls, path: str | Path) -> Grammar:
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    def productions_for(self, nonterminal: str) -> list[Production]:
        return list(self._by_lhs[nonterminal])

    def _empty_sets_by_nonterminal(self) -> dict[str, set[str]]:
        return {nonterminal: set() for nonterminal in self.nonterminals}

    def _invalidate_sets(self) -> None:
        self.first = {}
        self.follow = {}
        self.start = {}

    def _insert_nonterminal_after(self, existing: str, new: str) -> None:
        position = self.nonterminals.index(existing) + 1
        self.nonterminals.insert(position, new)
        self._by_lhs[new] = []

    def _replace_productions(
        self,
        nonterminal: str,
        alternatives: list[tuple[str, ...]],
    ) -> None:
        self._by_lhs[nonterminal] = [
            Production(nonterminal, symbols) for symbols in alternatives
        ]
        self._invalidate_sets()

    def _fresh_nonterminal(self, base: str) -> str:
        candidate = base + "'"
        occupied = set(self.nonterminals) | self.terminals
        while candidate in occupied:
            candidate += "'"
        return candidate

    def first_of_sequence(self, symbols: tuple[str, ...]) -> set[str]:
        """Calcule FIRST para uma sequência de zero ou mais símbolos."""
        raise NotImplementedError("implemente FIRST de uma sequência")

    def build_first(self) -> None:
        """Preencha self.first por iteração até um ponto fixo."""
        raise NotImplementedError("implemente FIRST")

    def build_follow(self) -> None:
        """Preencha self.follow; FIRST deve ter sido calculado antes."""
        raise NotImplementedError("implemente FOLLOW")

    def build_start(self) -> None:
        """Associe a cada produção seu conjunto START."""
        raise NotImplementedError("implemente START")

    def build_sets(self) -> None:
        self.build_first()
        self.build_follow()
        self.build_start()

    # Função para eliminar recursão direta a esquerda
    def eliminate_direct_left_recursion(self, nonterminal: str) -> bool:
        productions = self.productions_for(nonterminal)
        rhs_recursive = []
        rhs_base = []
        
        for production in productions:
            if production.rhs and production.rhs[0] == nonterminal:
                rhs_recursive.append(production.rhs[1:])
            else:
                rhs_base.append(production.rhs)

        if not rhs_recursive: # Nao há recursao direta neste nao-terminal
            return False  
        
        # Calcula e registra o nome do auxiliar na gramática
        a_linha = self._fresh_nonterminal(nonterminal)
        self._insert_nonterminal_after(nonterminal, a_linha)
        
        a_productions = [beta + (a_linha,) for beta in rhs_base]

        a_linha_productions = [alpha + (a_linha,) for alpha in rhs_recursive]
        a_linha_productions.append(())

        self._replace_productions(nonterminal, a_productions)
        self._replace_productions(a_linha, a_linha_productions)

        return True
        
    def eliminate_all_direct_left_recursion(self) -> None:
        for nonterminal in list(self.nonterminals):
            self.eliminate_direct_left_recursion(nonterminal)

    def left_factor_once(self, nonterminal: str) -> bool:
        """Infraestrutura fornecida: fatore um prefixo comum."""
        productions = self.productions_for(nonterminal)
        best_prefix: tuple[str, ...] = ()

        for first, second in combinations(productions, 2):
            prefix = _common_prefix(first.rhs, second.rhs)
            if len(prefix) > len(best_prefix):
                best_prefix = prefix

        if not best_prefix:
            return False

        group = [
            production
            for production in productions
            if production.rhs[: len(best_prefix)] == best_prefix
        ]
        helper = self._fresh_nonterminal(nonterminal)
        self._insert_nonterminal_after(nonterminal, helper)

        alternatives: list[tuple[str, ...]] = []
        inserted = False
        for production in productions:
            if production in group:
                if not inserted:
                    alternatives.append(best_prefix + (helper,))
                    inserted = True
            else:
                alternatives.append(production.rhs)

        suffixes = list(
            dict.fromkeys(
                production.rhs[len(best_prefix) :]
                for production in group
            )
        )
        self._replace_productions(nonterminal, alternatives)
        self._replace_productions(helper, suffixes)
        return True

    def left_factor(self) -> bool:
        """Infraestrutura fornecida: repita a fatoração até estabilizar."""
        changed_any = False
        while True:
            for nonterminal in list(self.nonterminals):
                if self.left_factor_once(nonterminal):
                    changed_any = True
                    break
            else:
                return changed_any

    def ll1_conflicts(
        self,
    ) -> list[tuple[Production, Production, set[str]]]:
        """Infraestrutura fornecida: encontre STARTs sobrepostos."""
        if set(self.start) != set(self.productions):
            raise RuntimeError("calcule START antes de verificar LL(1)")

        conflicts: list[tuple[Production, Production, set[str]]] = []
        for nonterminal in self.nonterminals:
            for first, second in combinations(
                self.productions_for(nonterminal), 2
            ):
                overlap = self.start[first] & self.start[second]
                if overlap:
                    conflicts.append((first, second, overlap))
        return conflicts

    def is_ll1(self) -> bool:
        return not self.ll1_conflicts()

    @staticmethod
    def _format_set(values: set[str]) -> str:
        return "{ " + ", ".join(sorted(values)) + " }"

    def format_sets(self) -> str:
        lines = ["FIRST"]
        lines.extend(
            f"{nonterminal}: {self._format_set(self.first[nonterminal])}"
            for nonterminal in self.nonterminals
        )
        lines.append("")
        lines.append("FOLLOW")
        lines.extend(
            f"{nonterminal}: {self._format_set(self.follow[nonterminal])}"
            for nonterminal in self.nonterminals
        )
        lines.append("")
        lines.append("START")
        lines.extend(
            f"{production}: {self._format_set(self.start[production])}"
            for production in self.productions
        )
        return "\n".join(lines)

    def __str__(self) -> str:
        lines: list[str] = []
        for nonterminal in self.nonterminals:
            alternatives = " | ".join(
                " ".join(production.rhs) if production.rhs else EPSILON
                for production in self.productions_for(nonterminal)
            )
            lines.append(f"{nonterminal} ::= {alternatives}")
        return "\n".join(lines)
