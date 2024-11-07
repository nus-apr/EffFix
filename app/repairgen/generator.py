from app.repairgen.grammar import CFG, Production


class Generator:
    def __init__(
        self, pointer_list, identifier_list, return_stmts, labels, consts, depth
    ):
        self.pointer_list = pointer_list
        self.identifier_list = identifier_list
        self.constant_list = consts
        self.return_stmts = return_stmts
        self.labels = labels
        # keep track of what has been generated
        self.generated_instrs = set()
        # max allowed depth for unrolling the grammar
        self.depth = depth

    def gather_exit_stmts(self):
        """
        From the list of returns and labels, construct all "exit" stmts.
        :return: list of exit stmts, list of symbols involved (which should be terminals)
        """
        exits = []
        symbols = []
        exits.extend(self.return_stmts)
        for label in self.labels:
            exits.append("goto " + label + ";")
            symbols.append(label.strip("\n"))
        for return_stmt in self.return_stmts:
            tokens = return_stmt.strip("\n").split()
            symbols.extend(tokens)
        symbols = list(set(symbols))
        return exits, symbols

    def build_grammar(self):
        """
        This is where grammar is defined.
        """
        g = CFG()

        g.add_prod("POINTER_CONST", "NULL")
        g.specify_terminal("NULL")

        for pointer in self.pointer_list:
            g.add_prod("POINTER", pointer)
            # those that are to be used in conditionals
            g.add_prod("COND_POINTER", pointer)
            g.specify_terminal(pointer)

        for identifier in self.identifier_list:
            g.add_prod("ID", identifier, relevant_to_effect=False)
            g.specify_terminal(identifier)

        for constant in self.constant_list:
            g.add_prod("CONST", constant, relevant_to_effect=False)
            g.specify_terminal(constant)

        # specify exit stmts and symbols involved in them
        exit_stmts, new_symbols = self.gather_exit_stmts()
        for stmt in exit_stmts:
            g.add_prod("EXIT_STMT", stmt)
        g.specify_terminals(new_symbols)

        # it's possbile that these 4 are never added as lhs;
        # manually specify them to be safe
        g.specify_nonterminal("POINTER")
        g.specify_nonterminal("ID")
        g.specify_nonterminal("CONST")
        g.specify_nonterminal("EXIT_STMT")

        g.add_prod_list("ARITH_OP", "+ | - | * | /", relevant_to_effect=False)
        g.add_prod_list(
            "REL_OP", "< | <= | == | != | > | >= ", relevant_to_effect=False
        )
        g.add_prod_list("POINTER_OP", "== | !=", relevant_to_effect=False)

        g.add_prod("POINTER_EXPR", "POINTER")
        g.add_prod("POINTER_EXPR", "POINTER_CONST")

        g.add_prod("ARITH_EXPR", "ID")
        g.add_prod("ARITH_EXPR", "ID ARITH_OP ID")

        g.add_prod("BOOL_EXPR", "BOOL_EXPR_S || BOOL_EXPR_S", relevant_to_effect=False)
        g.add_prod("BOOL_EXPR", "BOOL_EXPR_S && BOOL_EXPR_S", relevant_to_effect=False)
        g.add_prod("BOOL_EXPR", "! ( BOOL_EXPR_S )", relevant_to_effect=False)
        g.add_prod("BOOL_EXPR", "BOOL_EXPR_S", relevant_to_effect=False)
        g.add_prod(
            "BOOL_EXPR_S", "ARITH_EXPR REL_OP ARITH_EXPR", relevant_to_effect=False
        )
        g.add_prod("BOOL_EXPR_S", "ARITH_EXPR REL_OP CONST", relevant_to_effect=False)
        g.add_prod(
            "BOOL_EXPR_S",
            "COND_POINTER POINTER_OP COND_POINTER",
            relevant_to_effect=False,
        )
        g.add_prod(
            "BOOL_EXPR_S",
            "COND_POINTER POINTER_OP POINTER_CONST",
            relevant_to_effect=False,
        )

        g.add_prod("HEAP", "POINTER = POINTER_EXPR ;")
        g.add_prod("HEAP", "POINTER = malloc ( sizeof ( * POINTER ) ) ;")
        g.add_prod("HEAP", "free ( POINTER ) ;")

        g.add_prod("CMD", "HEAP")
        g.add_prod("CMD", "ID = ARITH_EXPR ;")
        g.add_prod("CMD", "return POINTER_EXPR ;")
        g.add_prod("CMD", "EXIT_STMT")
        g.add_prod("CMD", "if ( BOOL_EXPR ) { CMD }")
        g.add_prod("CMD", "CMD CMD")

        g.add_prod("POS", "FRONT", relevant_to_effect=False)
        g.add_prod("POS", "BACK", relevant_to_effect=False)

        g.add_prod("PATCH", "INSERT POS CMD")

        g.specify_terminals(["+", "-", "*", "/", "<", "<=", "==", "!=", ">", ">="])
        g.specify_terminals(["(", ")", "{", "}", "*", "||", "&&", "!", "=", ";"])
        g.specify_terminals(["1", "0"])  # use this instead of true/false
        g.specify_terminals(["return", "while", "if"])
        g.specify_terminals(["malloc", "sizeof", "free"])
        g.specify_terminals(["INSERT", "COND", "FRONT", "BACK"])

        g.specify_starting_nonterminal("PATCH")

        g.finalize_grammar(self.depth)

        self.grammar = g

    def gen_random(self, is_random) -> tuple[str | None, list[Production]]:
        """
        Generate a random sentence based on current grammar and grammar state.
        Make sure no duplicates are produced from one generator.
        """
        patch_instruction, used_prods = self.grammar.gen_random(self.depth, is_random)
        while patch_instruction in self.generated_instrs:
            patch_instruction, used_prods = self.grammar.gen_random(
                self.depth, is_random
            )
        self.generated_instrs.add(patch_instruction)
        return patch_instruction, used_prods

    def estimate_size(self):
        starting_sym = self.grammar.starting_nonterminal
        self.grammar.fill_prod_cache_for_base_cases()
        size = self.grammar.estimate_size(starting_sym, self.depth)
        return size
