import re
from enum import Enum
from pprint import pformat

from pysmt.exceptions import ConvertExpressionError
from pysmt.shortcuts import (
    GE,
    LE,
    LT,
    TRUE,
    And,
    Equals,
    Exists,
    Iff,
    Int,
    Not,
    NotEquals,
    Or,
    Plus,
    Symbol,
    Times,
    get_free_variables,
    is_unsat,
    qelim,
    simplify,
)
from pysmt.typing import INT

from app.utilities import error_exit


class NodeType(Enum):
    # two args
    Equal = 1
    NotEqual = 2
    LessEqual = 3
    LessThan = 4
    Times = 5
    Plus = 6
    # one arg
    Int = 7
    Symbol = 8
    # no arg
    TrueFormula = 9


class RawClause:
    """
    Represent a clause using our own AST. Does not go up to AND/OR level.
    """

    def __init__(self, node_type: NodeType, arg_one, arg_two):
        self.node_type = node_type
        self.arg_one = arg_one
        self.arg_two = arg_two

    def is_about_return_value(self) -> bool:
        str_repr = self.__str__()
        return "return" in str_repr and "return->" not in str_repr

    def __str__(self):
        if self.node_type == NodeType.Equal:
            return f"{str(self.arg_one)} = {str(self.arg_two)}"
        elif self.node_type == NodeType.NotEqual:
            return f"{str(self.arg_one)} != {str(self.arg_two)}"
        elif self.node_type == NodeType.LessEqual:
            return f"{str(self.arg_one)} <= {str(self.arg_two)}"
        elif self.node_type == NodeType.LessThan:
            return f"{str(self.arg_one)} < {str(self.arg_two)}"
        elif self.node_type == NodeType.Times:
            return f"{str(self.arg_one)} * {str(self.arg_two)}"
        elif self.node_type == NodeType.Plus:
            return f"{str(self.arg_one)} + {str(self.arg_two)}"
        elif self.node_type == NodeType.Int:
            return str(self.arg_one)
        elif self.node_type == NodeType.Symbol:
            return str(self.arg_one)
        elif self.node_type == NodeType.TrueFormula:
            return "True"
        else:
            # should not happen
            return ""

    def to_smt_formula(self):
        if self.node_type == NodeType.Equal:
            return Equals(self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula())
        elif self.node_type == NodeType.NotEqual:
            return NotEquals(
                self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula()
            )
        elif self.node_type == NodeType.LessEqual:
            return LE(self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula())
        elif self.node_type == NodeType.LessThan:
            return LT(self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula())
        elif self.node_type == NodeType.Times:
            return Times(self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula())
        elif self.node_type == NodeType.Plus:
            return Plus(self.arg_one.to_smt_formula(), self.arg_two.to_smt_formula())
        elif self.node_type == NodeType.Int:
            return Int(self.arg_one)
        elif self.node_type == NodeType.Symbol:
            return Symbol(self.arg_one, INT)
        elif self.node_type == NodeType.TrueFormula:
            return TRUE()
        else:
            error_exit(f"Unknown node type: {self.node_type}")

    @staticmethod
    def transform_clauses_with_restricted_var(raw_f_list):
        """
        Given a list of raw formulas, if there are clauses of the form p = a_ + 1,
        transform it to p != 0.
        """
        res_list = []
        for raw_f in raw_f_list:
            # p = a_ + 1
            if (
                raw_f.node_type == NodeType.Equal
                and raw_f.arg_one.node_type == NodeType.Symbol
                and RawClause.is_avar_plus_one(raw_f.arg_two)
            ):
                new_f = RawClause(
                    NodeType.NotEqual,
                    raw_f.arg_one,
                    RawClause(NodeType.Int, 0, None),
                )
                res_list.append(new_f)
            # a_ + 1 = p
            elif (
                raw_f.node_type == NodeType.Equal
                and raw_f.arg_two.node_type == NodeType.Symbol
                and RawClause.is_avar_plus_one(raw_f.arg_one)
            ):
                new_f = RawClause(
                    NodeType.NotEqual,
                    raw_f.arg_two,
                    RawClause(NodeType.Int, 0, None),
                )
                res_list.append(new_f)
            # not these two forms, just preserve them
            else:
                res_list.append(raw_f)

        return res_list

    @staticmethod
    def remove_redundant_pointer_clauses(raw_f_list: list["RawClause"]):
        """
        Given a list of raw formulas, remove redundancy introduced by pointers.
        Redundancy: (p != 0 and p >= 1) and (p != 0 and p = a_ + 1).
        When these pairs appear together, we only keep p != 0.
        """
        var_neq_zero: list[str] = []
        raw_f: RawClause

        # figure out the p for which p != 0
        for raw_f in raw_f_list:
            if raw_f.node_type == NodeType.NotEqual:
                if (
                    raw_f.arg_one.node_type == NodeType.Symbol
                    and raw_f.arg_two.node_type == NodeType.Int
                ):
                    if raw_f.arg_two.arg_one == 0:
                        var_neq_zero.append(raw_f.arg_one.arg_one)
                if (
                    raw_f.arg_two.node_type == NodeType.Symbol
                    and raw_f.arg_one.node_type == NodeType.Int
                ):
                    if raw_f.arg_one.arg_one == 0:
                        var_neq_zero.append(str(raw_f.arg_two.arg_one))

        # remove the clause of p >= 1 or p = a_ + 1, if any
        res_list = []
        for raw_f in raw_f_list:
            # 1 <= p, do not add to final result
            if (
                raw_f.node_type == NodeType.LessEqual
                and raw_f.arg_one.node_type == NodeType.Int
                and raw_f.arg_two.node_type == NodeType.Symbol
            ):
                if raw_f.arg_one.arg_one == 1 and raw_f.arg_two.arg_one in var_neq_zero:
                    continue
            # p = a_ + 1, do not add to final result
            if (
                raw_f.node_type == NodeType.Equal
                and raw_f.arg_one.node_type == NodeType.Symbol
                and raw_f.arg_one.arg_one in var_neq_zero
            ):
                # now check rhs
                rhs_f = raw_f.arg_two
                if RawClause.is_avar_plus_one(rhs_f):
                    continue
            # a_ + 1 = p, do not add to final result
            if (
                raw_f.node_type == NodeType.Equal
                and raw_f.arg_two.node_type == NodeType.Symbol
                and raw_f.arg_two.arg_one in var_neq_zero
            ):
                # now check lhs
                lhs_f = raw_f.arg_one
                if RawClause.is_avar_plus_one(lhs_f):
                    continue

            # not the cases that should be discard
            res_list.append(raw_f)

        return res_list

    @staticmethod
    def is_avar_plus_one(term):
        """
        Check if term is of the form a_ + 1.
        """
        a_var_pattern = "^a[0-9]+$"
        if term.node_type == NodeType.Plus:
            # a_ + 1
            if (
                term.arg_one.node_type == NodeType.Symbol
                and term.arg_two.node_type == NodeType.Int
            ):
                matched_a_var_pattern = re.search(a_var_pattern, term.arg_one.arg_one)
                if matched_a_var_pattern and term.arg_two.arg_one == 1:
                    return True
            # 1 + a_
            if (
                term.arg_two.node_type == NodeType.Symbol
                and term.arg_one.node_type == NodeType.Int
            ):
                matched_a_var_pattern = re.search(a_var_pattern, term.arg_two.arg_one)
                if matched_a_var_pattern and term.arg_one.arg_one == 1:
                    return True
        return False

    @staticmethod
    def build_linear_arith(arith_list: list[tuple[str, int]]):
        """
        Helper method to build raw formula of the form [2·x + 3/4·y + 12].
        """
        res_list = []
        for lvar, coefficient in arith_list:
            if not lvar:
                # lvar is "", which means term is constant, just need to check coefficient
                res_list.append(RawClause(NodeType.Int, coefficient, None))
            else:
                symbol = RawClause(NodeType.Symbol, lvar, None)
                int_co = RawClause(NodeType.Int, coefficient, None)
                if coefficient == 1:  # 1 * x, we can omit 1
                    res_list.append(symbol)
                else:
                    res_list.append(RawClause(NodeType.Times, int_co, symbol))
        if len(res_list) < 1:
            error_exit("Building linear arith, but there is no term!")
        elif len(res_list) == 1:
            return res_list[0]
        else:
            # now, we have multiple terms to add together
            # remove terms that are just a constant 0, since +0 does not do anything
            res_list = [
                term
                for term in res_list
                if not (term.node_type == NodeType.Int and term.arg_one == 0)
            ]
            res = res_list.pop(0)
            for term in res_list:
                res = RawClause(NodeType.Plus, res, term)
            return res

    @staticmethod
    def build_equality_to_var(lhs: str, rhs_list: list[tuple[str, int]]):
        """
        Build equality formula with lhs being a variable.
        """
        lhs_symbol = RawClause(NodeType.Symbol, lhs, None)
        rhs = RawClause.build_linear_arith(rhs_list)
        return RawClause(NodeType.Equal, lhs_symbol, rhs)

    @staticmethod
    def build_equality(lhs, rhs):
        """
        Build equality formula with lhs/rhs being int/list of (str, int).
        param lhs, rhs: int/list of (str, int).
        """
        if isinstance(lhs, int):
            lhs_s = RawClause(NodeType.Int, lhs, None)
        else:
            lhs_s = RawClause.build_linear_arith(lhs)
        if isinstance(rhs, int):
            rhs_s = RawClause(NodeType.Int, rhs, None)
        else:
            rhs_s = RawClause.build_linear_arith(rhs)
        return RawClause(NodeType.Equal, lhs_s, rhs_s)

    @staticmethod
    def build_inequality(typ, lhs, rhs):
        """
        :param typ: str, specifying type of inequality.
        :param lhs, rhs: int/list of (str, int).
        :returns: linear inequality formula in pysmt.
        """
        if isinstance(lhs, int):
            lhs_s = RawClause(NodeType.Int, lhs, None)
        else:
            lhs_s = RawClause.build_linear_arith(lhs)
        if isinstance(rhs, int):
            rhs_s = RawClause(NodeType.Int, rhs, None)
        else:
            rhs_s = RawClause.build_linear_arith(rhs)

        if typ == "LessEqual":
            return RawClause(NodeType.LessEqual, lhs_s, rhs_s)
        elif typ == "LessThan":
            return RawClause(NodeType.LessThan, lhs_s, rhs_s)
        elif typ == "NotEqual":
            return RawClause(NodeType.NotEqual, lhs_s, rhs_s)
        else:  # not supported typ = just return true formula and ignore
            return RawClause.get_true_formula()

    @staticmethod
    def get_true_formula():
        return RawClause(NodeType.TrueFormula, None, None)


class SmtFormula:
    def __init__(self):
        pass

    @staticmethod
    def build_conjunction(formula_list):
        """
        :param formula_list: list of clauses in pysmt.
        :returns: A conjunction formula of the terms in pysmt.
        """
        conjunction = And(formula_list)
        conjunction = simplify(conjunction)
        return conjunction

    @staticmethod
    def build_disjunction(formula_list):
        """
        :param formula_list: list of clauses in pysmt.
        :returns: A disjunction formula of the terms in pysmt.
        """
        conjunction = Or(formula_list)
        conjunction = simplify(conjunction)
        return conjunction

    @staticmethod
    def check_equivalence(f_one, f_two):
        """
        Checks if two formulas are equivalent.
        :param f_one, f_two: terms in pysmt.
        :returns: True if equivalent; False otherwise.
        """
        return is_unsat(Not(Iff(f_one, f_two)), solver_name="cvc4")

    @staticmethod
    def check_implication(f_one, f_two):
        """
        Checks if f_one implies f_two.
        :param f_one, f_two: terms in pysmt.
        :returns: True if f_one implies f_two; False otherwise.
        """
        return is_unsat(And(f_one, Not(f_two)), solver_name="cvc4")

    @staticmethod
    def check_strictly_smaller(f_one, f_two):
        return SmtFormula.check_implication(
            f_one, f_two
        ) and not SmtFormula.check_implication(f_two, f_one)

    @staticmethod
    def get_true_formula():
        return TRUE()


class FormulaCollection:
    """
    Maintains both raw clauses and pysmt formulas.
    One collection is for one disjunct.
    """

    def __init__(self):
        # raw clause representation, items in list should be conjuncted
        self.path_clause_list: list[RawClause] = list()
        self.all_clause_list: list[RawClause] = list()
        # raw clause for the return value
        self.return_clause_list: list[RawClause] = list()
        # smt representation
        self.path_smt = None
        self.all_smt = None
        self.return_smt = None

    def add_to_conjunct_list_all(self, conjunct: list[RawClause]):
        self.all_clause_list.extend(conjunct)

    def add_to_conjunct_list_path(self, conjunct: list[RawClause]):
        self.path_clause_list.extend(conjunct)

    def separate_clause_for_return_value(self):
        """
        Separate the clauses in the collection that are related to
        the special return value.
        NOTE: just doing it for all_formula, since path formula is
              deprecated and no one is using it.
        """
        separated_list = list()
        orig_list = list()
        for clause in self.all_clause_list:
            if clause.is_about_return_value():
                separated_list.append(clause)
            else:
                orig_list.append(clause)

        self.all_clause_list = orig_list
        self.return_clause_list = separated_list

    def transform_clauses_with_restricted_var(self):
        """
        For the two lists of clauses, transform p = a_ + 1 to p != 0.
        """
        self.path_clause_list = RawClause.transform_clauses_with_restricted_var(
            self.path_clause_list
        )
        self.all_clause_list = RawClause.transform_clauses_with_restricted_var(
            self.all_clause_list
        )

    def remove_redundant_pointer_clauses(self):
        """
        For the two lists of clauses, remove redundant clauses due to pointers.
        """
        self.path_clause_list = RawClause.remove_redundant_pointer_clauses(
            self.path_clause_list
        )
        self.all_clause_list = RawClause.remove_redundant_pointer_clauses(
            self.all_clause_list
        )

    def build_smt_representation(self):
        """
        Given the clause list representation, populate the smt representation.
        """
        path_smt_conjuncts = []
        all_smt_conjuncts = []
        return_smt_conjuncts = []
        for clause in self.path_clause_list:
            smt = clause.to_smt_formula()
            path_smt_conjuncts.append(smt)
        for clause in self.all_clause_list:
            smt = clause.to_smt_formula()
            all_smt_conjuncts.append(smt)
        for clause in self.return_clause_list:
            smt = clause.to_smt_formula()
            return_smt_conjuncts.append(smt)

        self.path_smt = SmtFormula.build_conjunction(path_smt_conjuncts)
        self.all_smt = SmtFormula.build_conjunction(all_smt_conjuncts)
        self.return_smt = SmtFormula.build_conjunction(return_smt_conjuncts)

    def add_aliasing_info_to_smt(self, aliasing_info: list[set[str]]):
        """
        Add aliasing information to the smt representation.
        """
        self.path_smt = FormulaCollection.add_aliasing_info_to_one(
            self.path_smt, aliasing_info
        )
        self.all_smt = FormulaCollection.add_aliasing_info_to_one(
            self.all_smt, aliasing_info
        )
        self.return_smt = FormulaCollection.add_aliasing_info_to_one(
            self.return_smt, aliasing_info
        )

    def eliminate_avar_lvars_in_smt(self):
        """
        Eliminate logical variables in the smt representation.
        """
        self.path_smt = (
            FormulaCollection.eliminate_restricted_and_left_over_logical_vars(
                self.path_smt
            )
        )
        self.all_smt = (
            FormulaCollection.eliminate_restricted_and_left_over_logical_vars(
                self.all_smt
            )
        )
        self.return_smt = (
            FormulaCollection.eliminate_restricted_and_left_over_logical_vars(
                self.return_smt
            )
        )

    @staticmethod
    def add_aliasing_info_to_one(formula, aliasing_info):
        """
        Given a set of aliasing information, build equality constraints over pairs of them,
        and add such constraints to the given formula.
        """
        new_formula = formula
        symbols = get_free_variables(formula)
        symbol_names = [s.symbol_name() for s in symbols]
        for name in symbol_names:
            for aliased_set in aliasing_info:
                for aliased_name in aliased_set:
                    if name == aliased_name:
                        # we have a name, that falls into this set
                        aliased_list = list(aliased_set)
                        for a_one, a_two in zip(aliased_list[:-1], aliased_list[1:]):
                            new_equality = Equals(
                                Symbol(a_one, INT), Symbol(a_two, INT)
                            )
                            new_formula = And(new_formula, new_equality)
        return new_formula

    @staticmethod
    def eliminate_restricted_and_left_over_logical_vars(formula):
        """
        Pulse uses restrited vars to represent inequality using equality.
        The restricted vars by definition represent non-negative value,
        and their logical name starts with 'a'.
        Moreover, there are some leftover logical variable without mapping to program
        variable at this stage. This is either because the logical variable itself
        is not present in the program (e.g. constant or intermediate computation result),
        or we ignored parsing about its attribute before.

        This method eliminates restricted variables and leftover varaibles in the current formula,
        by doing quantifier elimination on them.

        :param formula: the input formula to be considered.
        :param lvar_to_pvar_set: mapping from logical variable to set of program variables.
        """
        new_formula = formula
        a_pattern = "^a[0-9]+$"
        v_pattern = "^v[0-9]+$"
        symbols = get_free_variables(formula)
        restricted_vars = []
        left_over_lvars = []
        for symbol in symbols:
            symbol_name = symbol.symbol_name()
            matched_a_pattern = re.search(a_pattern, symbol_name)
            matched_v_pattern = re.search(v_pattern, symbol_name)
            if matched_a_pattern:
                restricted_vars.append(symbol)
            if matched_v_pattern:
                left_over_lvars.append(symbol)

        # add constraints on restricted variables
        for restricted_var in restricted_vars:
            new_constraint = GE(restricted_var, Int(0))
            new_formula = And(new_formula, new_constraint)

        # Added all the extra conjuncts; now eliminate using quantifier elimination
        quatifiers = restricted_vars + left_over_lvars
        new_formula = Exists(quatifiers, new_formula)
        try:
            new_formula = qelim(new_formula)
        except ConvertExpressionError:
            # during qelim, pysmt needs to convert z3 expression back to its reprsentation
            # however, expressions containing % cannot be convert, and raise exception
            # We have no way to control what z3 outputs as results of qelim,
            # so too bad, have to just return some default value
            new_formula = SmtFormula.get_true_formula()

        return simplify(new_formula)

    def __str__(self):
        ret = "\nPath formula :\n\t"
        ret += pformat(self.path_smt) + "\n"
        ret += "All formula :\n\t"
        ret += pformat(self.all_smt)
        return ret
