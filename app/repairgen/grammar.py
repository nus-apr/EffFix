import random
from collections import defaultdict

from app import emitter, values
from app.equivalence.cluster import RewardType
from app.repairgen import patch_utils


class Production:
    """
    Represent RHS of a production rule.
    """

    def __init__(self, rule_str: str):
        self.rule: list[str] = rule_str.split()

    def get_symbol_list(self):
        return self.rule

    def __eq__(self, other):
        if not isinstance(other, Production):
            return False
        this_str = " ".join(self.rule)
        other_str = " ".join(other.rule)
        return this_str == other_str

    def __hash__(self):
        return hash(" ".join(self.rule))

    def __str__(self):
        ret = " ".join(self.rule)
        return ret


class ProductionList:
    """
    Represent a list of RHS productions of a symbol.
    """

    def __init__(self):
        # map from production to a map from recur_depth to probability
        # the two floats are (pe, ppie), where the final probability is the average of the two
        # invariant: sum of all probabilities at each recur_depth is 1
        self.productions: dict[Production, dict[int, tuple[float, float]]] = (
            defaultdict()
        )
        # map from production to the probability weights for pe and ppie
        # note that the weights are global, not per depth
        self.prod_weights: dict[Production, tuple[int, int]] = defaultdict(
            lambda: (1, 1)
        )
        # whether is relevant to path/effect
        self.relevant_to_path = True
        self.relevant_to_effect = True
        # For each production at each depth, kept a count of final sentences that
        # can be derived
        # If Production itself is a terminal, the count is 1 for all depths
        self.prod_cache: dict[Production, dict[int, int]] = defaultdict()
        self.num_prods = 0

    def add_new_production(
        self,
        prod: Production,
        relevant_to_path,
        relevant_to_effect,
    ):
        self.productions[prod] = defaultdict()
        self.prod_cache[prod] = defaultdict()
        self.num_prods += 1
        self.relevant_to_path = relevant_to_path
        self.relevant_to_effect = relevant_to_effect

    def init_baseline_probabilities(self, total_depth: int):
        """
        Populate this list of productions with initial probabilties, which is just
        equality distributed per rule.
        """
        equal_probability = 0.0
        if self.num_prods > 0:
            equal_probability = 1.0 / self.num_prods
        for prod in self.productions:
            for i in range(total_depth + 1):
                self.productions[prod][i] = (equal_probability, equal_probability)

    def update_probabilities_based_on_cache(self):
        """
        Assuming prod_cache is in place, use it to update probabilities.
        """
        # first, get the total number of sentences at each depth
        total_sentences_at_depth = defaultdict(int)
        for prod in self.prod_cache:
            for depth in self.prod_cache[prod]:
                raw_count = self.prod_cache[prod][depth]
                if raw_count != -1:  # exclude unmodified cells
                    total_sentences_at_depth[depth] += raw_count

        # then, update probabilities
        for prod in self.prod_cache:
            for depth in self.prod_cache[prod]:
                if total_sentences_at_depth[depth] == 0:
                    # at this depth, no sentences can be derived from any rule
                    # => just equally distribute them
                    p = 1.0 / self.num_prods
                    self.productions[prod][depth] = (p, p)
                else:
                    p = self.prod_cache[prod][depth] / total_sentences_at_depth[depth]
                    self.productions[prod][depth] = (p, p)

    def set_default_cache_value(self, total_depth: int):
        """
        For prod cache, set default size estimate to -1,
        to indicate a cell was not updated before.
        """
        for prod in self.prod_cache:
            for i in range(total_depth + 1):
                self.prod_cache[prod][i] = -1

    def query_prod_cache(self, prod: Production, depth: int) -> int:
        return self.prod_cache[prod][depth]

    def update_single_prod_cache(self, prod: Production, depth: int, new_count: int):
        """
        Update cache value for a single production, at depth.
        """
        self.prod_cache[prod][depth] = new_count

    def update_all_prod_cache_same_depth(self, depth: int, new_count: int):
        """
        Update cache value for all productions, at depth.
        """
        for prod in self.productions:
            self.prod_cache[prod][depth] = new_count

    def update_single_prod_cache_all_depth(self, prod: Production, new_count: int):
        """
        Update cache value for a single production, but at all depth.
        """
        for depth in self.prod_cache[prod]:
            self.prod_cache[prod][depth] = new_count

    def update_probabilities(
        self,
        prods_to_update: list[Production],
        pe_increment: RewardType,
        ppie_increment: RewardType,
    ):
        """
        Update probabilities directly.
        """
        big_increment_fraction_pe = values.ADJ_FACTOR_SMALL
        small_increment_fraction_pe = values.ADJ_FACTOR_SMALL

        big_increment_fraction_ppie = values.ADJ_FACTOR_BIG
        small_increment_fraction_ppie = values.ADJ_FACTOR_SMALL

        prods_to_update = [prod for prod in prods_to_update if prod in self.productions]
        prods_unchanged = [
            prod for prod in self.productions if prod not in prods_to_update
        ]

        old_values_for_to_update = [
            self.productions[prod][0] for prod in prods_to_update
        ]
        old_values_for_unchanged = [
            self.productions[prod][0] for prod in prods_unchanged
        ]

        old_pe_for_to_update = [pe for pe, _ in old_values_for_to_update]
        old_ppie_for_to_update = [ppie for _, ppie in old_values_for_to_update]
        old_pe_for_unchanged = [pe for pe, _ in old_values_for_unchanged]
        old_ppie_for_unchanged = [ppie for _, ppie in old_values_for_unchanged]

        # calculate new values for those that are to be updated (rewarded)
        new_pe_for_to_update = old_pe_for_to_update
        sum_old_pe_for_to_update = sum(old_pe_for_to_update)
        if self.relevant_to_effect:
            if pe_increment == RewardType.BIG:
                total_extra_to_distribute = (
                    1 - sum_old_pe_for_to_update
                ) * big_increment_fraction_pe
            elif pe_increment == RewardType.SMALL:
                total_extra_to_distribute = (
                    1 - sum_old_pe_for_to_update
                ) * small_increment_fraction_pe
            else:  # no
                total_extra_to_distribute = 0
            if sum_old_pe_for_to_update == 0:
                # avoid div-by-zero
                # since old sum is already zero, we dont need to distribute new
                # things proportional to their old values
                new_pe_for_to_update = [
                    pe + (1 / len(old_pe_for_to_update)) * total_extra_to_distribute
                    for pe in old_pe_for_to_update
                ]
            else:
                new_pe_for_to_update = [
                    pe + (pe / sum_old_pe_for_to_update) * total_extra_to_distribute
                    for pe in old_pe_for_to_update
                ]

        new_ppie_for_to_update = old_ppie_for_to_update
        sum_old_ppie_for_to_update = sum(old_ppie_for_to_update)
        if self.relevant_to_path:
            if ppie_increment == RewardType.BIG:
                total_extra_to_distribute = (
                    1 - sum_old_ppie_for_to_update
                ) * big_increment_fraction_ppie
            elif ppie_increment == RewardType.SMALL:
                total_extra_to_distribute = (
                    1 - sum_old_ppie_for_to_update
                ) * small_increment_fraction_ppie
            else:  # no
                total_extra_to_distribute = 0
            if sum_old_ppie_for_to_update == 0:
                # avoid div-by-zero
                # since old sum is already zero, we dont need to distribute new
                # things proportional to their old values
                new_ppie_for_to_update = [
                    ppie + (1 / len(old_ppie_for_to_update)) * total_extra_to_distribute
                    for ppie in old_ppie_for_to_update
                ]
            else:
                new_ppie_for_to_update = [
                    ppie
                    + (ppie / sum_old_ppie_for_to_update) * total_extra_to_distribute
                    for ppie in old_ppie_for_to_update
                ]

        # calculate new values for those that did not get a reward
        sum_old_pe_for_unchanged = sum(old_pe_for_unchanged)
        sum_new_pe_for_to_update = sum(new_pe_for_to_update)
        if sum_old_pe_for_unchanged == 0:
            # they were already zero; cant be decreased further
            new_pe_for_unchanged = old_pe_for_unchanged
        else:
            new_pe_for_unchanged = [
                (1 - sum_new_pe_for_to_update) * (pe / sum_old_pe_for_unchanged)
                for pe in old_pe_for_unchanged
            ]

        sum_old_ppie_for_unchanged = sum(old_ppie_for_unchanged)
        sum_new_ppie_for_to_update = sum(new_ppie_for_to_update)
        if sum_old_ppie_for_unchanged == 0:
            # they were already zero; cant be decreased further
            new_ppie_for_unchanged = old_ppie_for_unchanged
        else:
            new_ppie_for_unchanged = [
                (1 - sum_new_ppie_for_to_update) * (ppie / sum_old_ppie_for_unchanged)
                for ppie in old_ppie_for_unchanged
            ]

        # update the probabilities
        for i, prod in enumerate(prods_to_update):
            new_pe = new_pe_for_to_update[i]
            new_ppie = new_ppie_for_to_update[i]
            # debugging
            old_pe, old_ppie = self.productions[prod][0]
            emitter.information(
                "Prod probability update: "
                + str(prod)
                + " : "
                + "pe: "
                + format(old_pe, ".3f")
                + "=>"
                + format(new_pe, ".3f")
                + " ; "
                + "ppie: "
                + format(old_ppie, ".3f")
                + "=>"
                + format(new_ppie, ".3f")
            )
            for depth in self.productions[prod]:
                self.productions[prod][depth] = (new_pe, new_ppie)

        for i, prod in enumerate(prods_unchanged):
            new_pe = new_pe_for_unchanged[i]
            new_ppie = new_ppie_for_unchanged[i]
            # debugging
            old_pe, old_ppie = self.productions[prod][0]
            emitter.information(
                "Prod probability update: "
                + str(prod)
                + " : "
                + "pe: "
                + format(old_pe, ".3f")
                + "=>"
                + format(new_pe, ".3f")
                + " ; "
                + "ppie: "
                + format(old_ppie, ".3f")
                + "=>"
                + format(new_ppie, ".3f")
            )
            for depth in self.productions[prod]:
                self.productions[prod][depth] = (new_pe, new_ppie)

    def init_prod_weights(self):
        """
        For the product weights dict to have all entries, do the initialization here.
        """
        for prod in self.productions:
            self.prod_weights[prod] = (1, 1)

    def update_prod_weights(
        self, prods_to_update: list[Production], weight_incre_pe: int, weight_incre_ppie
    ):
        """
        Update the weights for the given productions.
        """
        for prod in prods_to_update:
            # note: use this to check, because self.prod_weights is not initialized
            if prod not in self.prod_weights:
                continue
            (weight_pe, weight_ppie) = self.prod_weights[prod]
            new_weight_pe = weight_pe
            new_weight_ppie = weight_ppie

            if self.relevant_to_effect:
                new_weight_pe = weight_pe + weight_incre_pe
            if self.relevant_to_path:
                new_weight_ppie = weight_ppie + weight_incre_ppie
            self.prod_weights[prod] = (new_weight_pe, new_weight_ppie)

    def update_probabilities_based_on_weights(self):
        """
        Assuming weights have been updated, use it to re-calibrate the probabilities.
        """
        all_weight_pairs = self.prod_weights.values()
        total_weight_pe = sum([pair[0] for pair in all_weight_pairs])
        total_weight_ppie = sum([pair[1] for pair in all_weight_pairs])

        for prod in self.prod_weights:
            (weight_pe, weight_ppie) = self.prod_weights[prod]
            p_pe = weight_pe / total_weight_pe
            p_ppie = weight_ppie / total_weight_ppie

            for depth in self.productions[prod]:
                self.productions[prod][depth] = (p_pe, p_ppie)

    def get_productions_only(self) -> list[Production]:
        return list(self.productions.keys())

    def get_shuffled_productions_only(
        self, at_depth: int, is_random: bool
    ) -> list[Production]:
        """
        Get the list of productions, but in order shuffled according to the probability
        at current depth.
        """
        prod_list = list(self.productions.keys())
        if not prod_list:
            return []
        random.shuffle(prod_list)
        if is_random:
            selected_index = random.randint(0, len(prod_list) - 1)
            return [prod_list[selected_index]]
        else:
            probability_pairs = [self.productions[prod][at_depth] for prod in prod_list]
            probability_products = [pe * ppie for (pe, ppie) in probability_pairs]
            total_probability = sum(probability_products)
            prefix_sums = [probability_products[0]]
            for i in range(1, len(probability_products) - 1):
                prefix_sums.append(prefix_sums[i - 1] + probability_products[i])
            prefix_sums.append(total_probability)

            random_value = random.uniform(0, total_probability)

            # get index of the first element in prefix sums greater than random value
            upper_bound = min(n for n in prefix_sums if n > random_value)
            selected_index = prefix_sums.index(upper_bound)
            selection = prod_list[selected_index]

            return [selection]

    def print_prod_cache(self):
        """
        For debugging.
        """
        s = "Production cache (size estimate):\n"
        for prod in self.prod_cache:
            s += str(prod) + ": "
            for depth in self.prod_cache[prod]:
                s += "<" + str(depth) + ","
                s += str(self.prod_cache[prod][depth]) + ">"
                s += " ; "
            s += "\n"
        print(s)

    def print_real_productions(self):
        """
        For debugging.
        """
        s = "Production list: \n"
        for prod in self.productions:
            s += str(prod) + ": "
            for depth in self.productions[prod]:
                s += "<" + str(depth) + ","
                s += str(self.productions[prod][depth]) + ">"
                s += " ; "
            s += "\n"
        print(s)

    def to_string_with_probabilities(self) -> list[tuple[str, float, float, float]]:
        res = []
        prod_list = list(self.productions.keys())
        probability_pairs = [self.productions[prod][0] for prod in prod_list]
        probability_products = [pe * ppie for (pe, ppie) in probability_pairs]
        total_probability = sum(probability_products)
        scaled_product_probabilities = [
            p / total_probability for p in probability_products
        ]
        pe_list = [pair[0] for pair in probability_pairs]
        ppie_list = [pair[1] for pair in probability_pairs]
        for idx, prod in enumerate(prod_list):
            prod_str = str(prod)
            pe = pe_list[idx]
            ppie = ppie_list[idx]
            scaled_product = scaled_product_probabilities[idx]
            res.append((prod_str, pe, ppie, scaled_product))
        return res


class CFG:
    def __init__(self):
        self.sym_to_prods: dict[str, ProductionList] = defaultdict(ProductionList)
        self.terminals: list[str] = []  # TODO: this may not be needed
        self.non_terminals: list[str] = []
        self.starting_nonterminal: str | None = None

        # TODO: is this really useful?
        # cache the result for each [non-terminal][recur_depth] pair
        self.symbol_cache: dict[str, dict[int, str]] = dict()

    def add_prod_list(
        self, lhs: str, rhs: str, relevant_to_path=True, relevant_to_effect=True
    ):
        """
        Add production to the grammar. 'rhs' can be several productions separated by '|'.
        Each production is a sequence of symbols separated by whitespace.
        Usage:
            grammar.add_prod('NT', 'VP PP')
            grammar.add_prod('Digit', '1|2|3|4')
        """
        prods = rhs.split("|")
        for prod_str in prods:
            self.add_prod(
                lhs,
                prod_str,
                relevant_to_path=relevant_to_path,
                relevant_to_effect=relevant_to_effect,
            )

    def add_prod(
        self,
        lhs: str,
        rhs: str,
        relevant_to_path=True,
        relevant_to_effect=True,
    ):
        """
        Add a single production rule, where `rhs` is just one production.
        """
        self.non_terminals.append(lhs)
        prod = Production(rhs)
        self.sym_to_prods[lhs].add_new_production(
            prod, relevant_to_path, relevant_to_effect
        )

    def specify_terminals(self, symbols):
        self.terminals.extend(symbols)

    def specify_terminal(self, symbol):
        self.terminals.append(symbol)

    def specify_nonterminal(self, symbol):
        self.non_terminals.append(symbol)

    def specify_starting_nonterminal(self, symbol):
        self.starting_nonterminal = symbol

    def finalize_grammar(self, depth: int):
        """
        Call this after adding production rules and terminals.
        """
        for prod_list in self.sym_to_prods.values():
            prod_list.init_baseline_probabilities(depth)
            prod_list.init_prod_weights()
            prod_list.set_default_cache_value(depth)

    def find_terminals_in_symbol_prods(
        self, symbol: str, at_depth: int, is_random: bool
    ) -> tuple[str, Production] | None:
        """
        Given a symbol SYM, find all sentences that can be constructed without
        unrolling any more non-terminals (in SYM's productions).
        :return: a tuple of (generated string, used production).
                 The production with highest probability is preferred.
        """
        prod_list: ProductionList = self.sym_to_prods[symbol]

        for production in prod_list.get_shuffled_productions_only(at_depth, is_random):
            # productions are already iterated with a rank - the first one should be returned
            curr_str = ""
            this_prod_has_nonterminal = False
            for sym in production.get_symbol_list():
                if self.is_nonterminal(sym):
                    this_prod_has_nonterminal = True
                    break
                else:
                    curr_str += sym + " "
            if not this_prod_has_nonterminal:
                return (curr_str, production)

        return None

    def gen_random_helper(
        self,
        symbol: str,
        recur_depth: int,
        remaining_prods_this_lvl: list[Production],
        black_list: list[Production],
        is_random: bool,
    ) -> tuple[str | None, list[Production]]:
        """
        Generate a random sentence from the grammar, starting with the give symbol.
        :recur_depth: coins left when we are in the `remaining_prods_this_lvl`.
        :return: (str, List[Production]) - the generated sentence, and the list of productions used
        """
        # catch corner case, where a non-terminal does not have any productions when initialized
        # This can happen when there is no identifier or pointers as patch ingredients
        if not remaining_prods_this_lvl:
            return None, []

        if recur_depth == 0:
            # do not have budget anymore - try to find a terminal
            found_terminal = self.find_terminals_in_symbol_prods(
                symbol, recur_depth, is_random
            )
            if found_terminal is None:
                # reach this symbol with 0 depth, but no sentences can be constructed
                return None, []

            string, prod = found_terminal
            # got some sentence
            return string, [prod]

        curr_prod = remaining_prods_this_lvl[0]
        black_list.append(curr_prod)
        sentence_res = ""
        prod_list_res = [curr_prod]

        for sym in curr_prod.get_symbol_list():
            if self.is_nonterminal(sym):
                sym_prod_list: ProductionList = self.sym_to_prods[sym]
                # go to next (deeper) level
                shuffled_prods = sym_prod_list.get_shuffled_productions_only(
                    recur_depth - 1, is_random
                )
                # remove all black listed productions
                for prod in black_list:
                    if prod in shuffled_prods:
                        shuffled_prods.remove(prod)

                # random.shuffle(sym_prods)
                subsentence, used_prods = self.gen_random_helper(
                    sym, recur_depth - 1, shuffled_prods, black_list.copy(), is_random
                )
                while subsentence is None and len(shuffled_prods) > 1:
                    # walking this subtree with this production failed
                    shuffled_prods = shuffled_prods[1:]
                    subsentence, used_prods = self.gen_random_helper(
                        sym,
                        recur_depth - 1,
                        shuffled_prods,
                        black_list.copy(),
                        is_random,
                    )

                if subsentence is None:
                    # tried all productions with this sym at this depth, but none worked
                    return None, []
                else:
                    sentence_res += subsentence
                    prod_list_res = prod_list_res + used_prods
            else:  # terminal symbol
                sentence_res += sym + " "

        return sentence_res, prod_list_res

    def gen_random(
        self, recur_depth: int, is_random: bool
    ) -> tuple[str | None, list[Production]]:
        assert self.starting_nonterminal is not None

        starting_prod_list: ProductionList = self.sym_to_prods[
            self.starting_nonterminal
        ]
        shuffled_starting_prods = starting_prod_list.get_shuffled_productions_only(
            recur_depth - 1, is_random
        )
        return self.gen_random_helper(
            self.starting_nonterminal,
            recur_depth - 1,
            shuffled_starting_prods,
            [],
            is_random,
        )

    def estimate_size(self, symbol, recur_depth):
        """
        NOTE: this function is currently not accurate.
        Estimate the size (i.e. number of sentences) that can be generated from each
        production for the symbol.
        While estimating for each production, return count for the symbol
        (which is the sum of each production).
        """
        # Cache for the base cases have been pre-filled.

        prod_list: ProductionList = self.sym_to_prods[symbol]
        overall_count = 0

        for prod in prod_list.get_productions_only():
            # for each rhs production, estimate the size, update cache,
            # and sum the numbers together as the result for lhs
            # use one coin to go from lhs to rhs
            depth_left = recur_depth - 1
            # first try to query cache for this one
            cached_res = prod_list.query_prod_cache(prod, depth_left)
            if cached_res != -1:
                # updated before
                overall_count += cached_res
                continue

            # this prod-depth was not cached
            prod_res_count = 0
            for sym in prod.get_symbol_list():
                if self.is_terminal(sym):
                    prod_res_count = patch_utils.concat_one_to_all_estimate_size(
                        prod_res_count
                    )
                elif self.is_nonterminal(sym):
                    child_res_count = self.estimate_size(sym, depth_left)
                    if child_res_count > 0:
                        prod_res_count = patch_utils.concat_two_lists_estimate_size(
                            prod_res_count, child_res_count
                        )
                    else:
                        # no count for this child symbol
                        #  => this prod cannot become a sentence, with current depth_left
                        prod_res_count = 0
                        break
            # finished processing one Production => cache this result
            prod_list.update_single_prod_cache(prod, depth_left, prod_res_count)
            overall_count += prod_res_count

        return overall_count

    def fill_prod_cache_for_base_cases(self):
        """
        If a Production is just one terminal symbol, its cache should be 1 for all depths.
        Else, its cache for depth 0 should be 0.
        """
        for symbol in self.sym_to_prods:
            prod_list: ProductionList = self.sym_to_prods[symbol]
            for prod in prod_list.get_productions_only():
                sym_list = prod.get_symbol_list()
                if len(sym_list) == 1 and self.is_terminal(sym_list[0]):
                    # Found it. Update cache for all depths
                    prod_list.update_single_prod_cache_all_depth(prod, 1)
                else:
                    prod_list.update_single_prod_cache(prod, 0, 0)

    def print_all_prod_cache(self):
        for symbol in self.sym_to_prods:
            prod_list: ProductionList = self.sym_to_prods[symbol]
            print(f"Symbol {symbol} =>")
            prod_list.print_prod_cache()

    def print_all_real_prod(self):
        for symbol in self.sym_to_prods:
            prod_list: ProductionList = self.sym_to_prods[symbol]
            print(f"Symbol {symbol} =>")
            prod_list.print_real_productions()

    def update_probabilities_based_on_size(self):
        """
        With estimated sizes, update probabilities in the real production lists.
        """
        for prod_list in self.sym_to_prods.values():
            prod_list.update_probabilities_based_on_cache()

    def cache_results(self, symbol, recur_depth, result):
        if symbol not in self.symbol_cache:
            self.symbol_cache[symbol] = dict()
        self.symbol_cache[symbol][recur_depth] = result

    def is_nonterminal(self, symbol):
        return symbol in self.non_terminals

    def is_terminal(self, symbol):
        return symbol not in self.non_terminals

    def reset_probabilities(self, depth):
        for prod_list in self.sym_to_prods.values():
            prod_list.init_baseline_probabilities(depth)
            prod_list.init_prod_weights()
            prod_list.set_default_cache_value(depth)

        # return a state of the current grammar (w. probabilities updated)
        grammar_state = self.get_grammar_state()
        return grammar_state

    def update_probabilities(
        self,
        prods_to_update: list[Production],
        pe_increment: RewardType,
        ppie_increment: RewardType,
    ):
        """
        For each production in prods, update its probabilities.
        """
        for prod_list in self.sym_to_prods.values():
            prod_list_prods = prod_list.get_productions_only()
            common_prods = [prod for prod in prod_list_prods if prod in prods_to_update]
            if not common_prods:
                continue
            # has common ones; this prod list should be updated
            prod_list.update_probabilities(common_prods, pe_increment, ppie_increment)

        # return a state of the current grammar (w. probabilities updated)
        grammar_state = self.get_grammar_state()
        return grammar_state

    def get_grammar_state(self):
        """
        Get the current grammar state.
        Result is a list of (rule, pe, ppie, avg) tuples,
        where rule is a string representation.
        """
        grammar_state = []
        for symbol in self.sym_to_prods:
            prod_list: ProductionList = self.sym_to_prods[symbol]
            prefix = symbol + " -> "
            prods_with_prob = prod_list.to_string_with_probabilities()
            rules_with_prob = [
                {
                    "rule": prefix + prod_str,
                    "pe": pe,
                    "ppie": ppie,
                    "scaled_product": scaled_product,
                }
                for prod_str, pe, ppie, scaled_product in prods_with_prob
            ]
            grammar_state.extend(rules_with_prob)
        return grammar_state

    def update_prod_weights(
        self,
        prods_to_update: list[Production],
        weight_incre_pe: int,
        weight_incre_ppie: int,
    ):
        """
        For each production in prods, update its weights.
        """
        for prod_list in self.sym_to_prods.values():
            prod_list_prods = prod_list.get_productions_only()
            common_prods = [prod for prod in prod_list_prods if prod in prods_to_update]
            if not common_prods:
                continue
            # has common ones; the common ones should be updated
            prod_list.update_prod_weights(
                common_prods, weight_incre_pe, weight_incre_ppie
            )

    def update_probabilities_based_on_weights(self):
        for prod_list in self.sym_to_prods.values():
            prod_list.update_probabilities_based_on_weights()
