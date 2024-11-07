from collections import defaultdict
from pprint import pformat

from app.equivalence.smt import FormulaCollection, RawClause, SmtFormula


class ParsedHeapEdges:
    """
    Data structure used during parsing.
    Representing a set of parsed heap edges.
    """

    def __init__(self):
        # each entry represents a set of links coming out from one parent
        # parent => [ (child, link_name) ]
        # here, all names are logical var
        self.edges = dict()
        self.nodes = set()
        # (parent, link_name, child)
        self.edges_in_cycle: set[tuple[str, str, str]] = set()

    def add_edge(self, parent, child, link_name):
        """
        Internal method - should not be directly used.
        :param parent: logical var for parent.
        :param child: logical var for child.
        :param link_name: For field access edge, this is field name;
                          for dereference edge, this is the str "*".
        """
        edge_pair = (child, link_name)
        self.nodes.add(child)
        self.nodes.add(parent)
        if parent in self.edges:
            self.edges[parent].append(edge_pair)
        else:
            self.edges[parent] = [edge_pair]

    def add_dereference_edge(self, parent, child):
        self.add_edge(parent, child, "*")

    def add_field_edge(self, parent, child, link_name):
        self.add_edge(parent, child, link_name)

    def has_parent_node(self, parent):
        return parent in self.edges

    def get_children(self, parent):
        if parent not in self.edges:
            return []
        return self.edges[parent]

    def get_children_not_in_cycle_edges(self, parent):
        """
        Similar to get_children, but filters out children such that this parent->child
        edge has appeared in any cycle.
        """
        if parent not in self.edges:
            return []
        return [
            (child, link_name)
            for child, link_name in self.edges[parent]
            if (parent, link_name, child) not in self.edges_in_cycle
        ]

    def __detect_cycle_util(self, node, visited, rec_stack):
        visited[node] = True
        rec_stack[node] = True

        if node not in self.edges:
            # no edge from this node
            rec_stack[node] = False
            return []

        for child, _ in self.edges[node]:
            if not visited[child]:
                if self.__detect_cycle_util(child, visited, rec_stack):
                    return True
            elif rec_stack[child]:
                return True

        rec_stack[node] = False
        return False

    def has_cycle(self) -> bool:
        """
        Detect cycle in the heap graph.
        :return: True if cycle detected.
        """
        visited = defaultdict(bool)
        rec_stack = defaultdict(bool)

        for node in self.nodes:
            if not visited[node]:
                if self.__detect_cycle_util(node, visited, rec_stack):
                    return True
        return False

    def __get_all_cycles_dfs(self, start, end):
        fringe = [(start, [])]
        while fringe:
            node, path = fringe.pop()
            if path and node == end:
                yield path
                continue
            if node not in self.edges:
                # no edge starting from this node
                continue
            for child, _ in self.edges[node]:
                if child in path:
                    continue
                fringe.append((child, path + [child]))

    def get_all_cycles(self):
        """
        Get all cycles in the heap graph.
        Store all edges appeared in a cycle to self.edges_in_cycle
        """
        all_cycles = []
        for node in self.nodes:
            for path in self.__get_all_cycles_dfs(node, node):
                all_cycles.append([node] + path)

        edges_in_cycle = set()
        for cycle in all_cycles:
            # a cycle is in the form ['v30', 'v32', 'v23', 'v31', 'v30']
            for parent, child in zip(cycle, cycle[1:]):
                for child2, link_name in self.edges[parent]:
                    # lets get link name from this data structure
                    if child2 == child:
                        edges_in_cycle.add((parent, link_name, child))
                        break

        self.edges_in_cycle = edges_in_cycle

    def print(self):
        """
        Dereference: *
        Field access: -> (always -> since Infer assumes field access is from a pointer)
        """
        pass


class ParsedVariableMap:
    """
    Data structure used during parsing.
    Represent mappings from program var to logical var, and vice versa.
    """

    def __init__(self):
        # map from all pvar to lvar
        self.pvar_to_lvar: dict[str, str] = dict()
        # map from lvar to all pvar, where value is a set of pvar
        self.lvar_to_pvar_set: dict[str, set[str]] = dict()
        # map from lvar to pvar, where all the lvars are root variables (has corresponding stack var)
        self.root_lvar_to_pvar: dict[str, str] = dict()

    def add_root_pvar(self, pvar: str, lvar: str):
        real_pvar_name = "&(" + pvar + ")"
        self.pvar_to_lvar[real_pvar_name] = lvar
        self.root_lvar_to_pvar[lvar] = real_pvar_name

    def expand_along_heap_edges(self, heap_edges: ParsedHeapEdges):
        """
        Pre-condition: the root variables pvar-to-lvar and lvar-to-pvar are populated.
        This method expands the mapping along the given set of heap edges.
        :param heap_edges: ParsedHeapEdges.
        """
        frontier_lvar_to_pvar = self.root_lvar_to_pvar
        while frontier_lvar_to_pvar:  # not empty
            new_frontier = {}
            for lvar in frontier_lvar_to_pvar:
                if not heap_edges.has_parent_node(lvar):
                    continue
                # only consider children that are not in cycle
                children = heap_edges.get_children_not_in_cycle_edges(lvar)
                if not children:
                    continue
                # now really have children to expand to
                parent_name = frontier_lvar_to_pvar[lvar]
                for child, link_name in children:
                    if link_name == "*":  # Dereference:
                        if parent_name.startswith("&(") and parent_name[-1] == ")":
                            # whole expr is wrapped by &(), dereference is just removing it
                            new_name = parent_name[2:-1]
                        else:
                            new_name = "*(" + parent_name + ")"
                    else:  # FieldAccess
                        new_name = "&(" + parent_name + "->" + link_name + ")"
                    # add this edge
                    self.pvar_to_lvar[new_name] = child
                    new_frontier[child] = new_name
            frontier_lvar_to_pvar = new_frontier

    def construct_lvar_to_pvar_set(self):
        """
        With pvar-to-lvar mapping set, construct mapping for the other direction.
        Will construct a map with entry type (lvar => {pvar1, pvar2, ...}).
        """
        if self.lvar_to_pvar_set:  # computed before, skip
            return self.lvar_to_pvar_set

        map_ltop: dict[str, set[str]] = dict()

        for pvar in self.pvar_to_lvar:
            lvar = self.pvar_to_lvar[pvar]
            if lvar not in map_ltop:
                map_ltop[lvar] = {pvar}
            else:
                map_ltop[lvar].add(pvar)

        for lvar in map_ltop:
            map_ltop[lvar] = set(sorted(map_ltop[lvar], reverse=True))

        self.lvar_to_pvar_set = map_ltop
        return self.lvar_to_pvar_set

    def get_aliasing_info(self) -> list[set[str]]:
        """
        Return the list of sets of program variables that are aliased.
        """
        return list(self.lvar_to_pvar_set.values())

    def get_first_pvar_for_lvar(self, lvar):
        """
        For a logical variable, return its corresponding program variable name.
        When multiple pvars are possbile, pick the first one after sorting.
        """
        if lvar not in self.lvar_to_pvar_set:
            return ""
        pvar_set = self.lvar_to_pvar_set[lvar]
        pvar_list = sorted(list(pvar_set), reverse=True)
        if not pvar_list:
            return ""
        else:
            return pvar_list[0]

    def __str__(self):
        return pformat(self.lvar_to_pvar_set)


class PulseDisjunctParser:
    def __init__(self, disjunct_json):
        self.disjunct_json = disjunct_json
        # internal data structure of parser
        self.parsed_heap_edges = ParsedHeapEdges()
        self.parsed_variable_map = ParsedVariableMap()
        self.allocated_lvars = set()
        self.deallocated_lvars = set()
        # final outputs of parser
        self.heap_graph = None
        self.formulas = FormulaCollection()
        self.allocated_sets = set()  # set of set
        self.deallocated_sets = set()  # set of set

    def __parse_label(self, label_json):
        """
        Helper method to parse a label.
        """
        text = label_json[0]
        line_info = label_json[1]
        start_line = int(line_info[0])
        end_line = int(line_info[1])
        return (text, start_line, end_line)

    def parse_disjunct_trace_only(self):
        """
        Another main entry to the parser.
        This entry just parse the traced line number to save time.
        Mainly used for fix localization.
        """
        label_text, start_line, end_line = self.__parse_label(self.disjunct_json[0])
        content = self.disjunct_json[1]
        if content is not None:
            trace = content["full_trace"]
        else:
            # can't do much if not recorded
            trace = []
        return (label_text, start_line, end_line, trace)

    def parse_disjunct(self):
        """
        Main entry to the parser.
        One disjunct should ultimately contain a list of formulas and a heap graph.
        """
        label_text, start_line, end_line = self.__parse_label(self.disjunct_json[0])
        content = self.disjunct_json[1]

        default_res = (
            label_text,
            start_line,
            end_line,
            self.allocated_sets,
            self.deallocated_sets,
            SmtFormula.get_true_formula(),
            SmtFormula.get_true_formula(),
        )

        if content is None:
            # special case for label ErrorException, which has no content
            return default_res

        post = content["post"]
        formula = content["path_condition"]

        res = self.parse_disjunct_state(post)
        if res == -1:
            # bad state encoutered when parsing
            return default_res

        self.parse_disjunct_formula(formula)

        return (
            label_text,
            start_line,
            end_line,
            self.allocated_sets,
            self.deallocated_sets,
            self.formulas.all_smt,
            self.formulas.return_smt,
        )

    def parse_disjunct_state(self, state) -> int:
        """
        Parse state json into heap_edges, variable_map, and finally, heap_graph.
        :param state: json of either a pre or a post.
        :return: -1 if error; 0 if ok.s
        """
        heap = state["heap"]
        stack = state["stack"]
        attrs = state["attrs"]

        # (1) populate parsed_heap_edges
        for heap_entry in heap:
            self.parse_state_heap_entry(heap_entry)

        # (1.5) Check for cycles, and remember all edges appeared in a cycle;
        # these are skipped when we expand along heap edges, to avoid infinite loop
        self.parsed_heap_edges.get_all_cycles()

        # (2) parse top-level (stack) pvar-to-lvar mapping
        for stack_entry in stack:
            self.parse_state_stack_entry(stack_entry)

        # (3) parse attrs for more top-level (stack) pvar-to-lvar mapping
        #     Also parse the allocation/free attributes
        for attr_entry in attrs:
            self.parse_state_attr_entry(attr_entry)

        # (4) further populate mappings for internal variables, along heap edges
        self.parsed_variable_map.expand_along_heap_edges(self.parsed_heap_edges)
        self.parsed_variable_map.construct_lvar_to_pvar_set()

        # (5) using the variable mappings, convert allocation/deallocation
        #     sets from lvar to pvars
        self.allocated_sets = PulseDisjunctParser.build_to_aliased_set(
            self.allocated_lvars, self.parsed_variable_map
        )
        self.deallocated_sets = PulseDisjunctParser.build_to_aliased_set(
            self.deallocated_lvars, self.parsed_variable_map
        )

        # (6) build final heap graph with heap edges and variable map
        return 0

    @staticmethod
    def build_to_aliased_set(
        lvars: set[str], variable_map: ParsedVariableMap
    ) -> set[set[str]]:
        """
        Expand each lvar to a set of pvars, where all pvars in this set are aliased.
        """
        res = set()
        for lvar in lvars:
            if lvar not in variable_map.lvar_to_pvar_set:
                # for some reason, this lvar's mapping information is missing
                # in the summary post file
                continue
            curr_res = list()
            for pvar in variable_map.lvar_to_pvar_set[lvar]:
                curr_res.append(pvar)
            res.add(frozenset(curr_res))
        return res

    def parse_state_heap_entry(self, heap_entry):
        """
        Populate self.parsed_heap_edges with one more entry.
        :param heap_entry: An entry of heap in json.
        """
        lvar = heap_entry[0]
        content_list = heap_entry[1]

        for content in content_list:
            content_type = content[0][0]
            if content_type == "Dereference":
                inner_lvar = content[1][0]
                self.parsed_heap_edges.add_dereference_edge(lvar, inner_lvar)
            elif content_type == "FieldAccess":
                inner_lvar = content[1][0]
                field_name = content[0][1]["field_name"]
                self.parsed_heap_edges.add_field_edge(lvar, inner_lvar, field_name)

    def parse_state_stack_entry(self, stack_entry):
        """
        Populate self.parsed_variable_map with one root-level stack entry.
        :param stack_entry: An entry of stack in json.
        """
        meta_info = stack_entry[0]
        logical_var = stack_entry[1]
        if "ProgramVar" not in meta_info:
            return  # TODO: ignore for now

        pvar = meta_info[1]["plain"]
        lvar = logical_var[0]

        self.parsed_variable_map.add_root_pvar(pvar, lvar)

    def parse_state_attr_entry(self, attr_entry):
        lvar = attr_entry[0]
        attributes = attr_entry[1]
        has_been_allocated = False
        has_been_freed = False
        # these are the attributes for one lvar
        for attribute in attributes:
            if attribute[0] == "AddressOfStackVariable":
                # this is for building variable map
                stack_var_meta = attribute[1]
                if stack_var_meta[0] == "ProgramVar":
                    pvar = stack_var_meta[1]["plain"]
                    self.parsed_variable_map.add_root_pvar(pvar, lvar)
            elif attribute[0] == "Allocated":
                has_been_allocated = True
            elif attribute[0] == "Invalid":
                invalid_info = attribute[1:]
                if len(invalid_info) >= 1 and len(invalid_info[0]) >= 1:
                    invalid_reason = invalid_info[0][0]
                    if invalid_reason == "CFree":
                        has_been_freed = True
        if has_been_allocated and not has_been_freed:
            self.allocated_lvars.add(lvar)
        if has_been_freed:
            self.deallocated_lvars.add(lvar)

    def parse_disjunct_formula(self, formula):
        # (1) both is the conjunction of the other two
        both = formula["both"]
        linear_eqs = both["linear_eqs"]
        atoms = both["atoms"]  # mainly for inequalities

        self.parse_both_atoms(atoms)
        self.parse_both_linear_eqs(linear_eqs)

        # (2) pruned is the real path condition assumed to be true
        pruned = formula["pruned"]
        self.parse_pruned_atoms(pruned)

        # done parsing.
        # (3) transform clause with restricted variables to a form without them
        self.formulas.transform_clauses_with_restricted_var()

        # (4) remove redundant clauses due to pointers
        # TODO: check again whether this is necessary
        self.formulas.remove_redundant_pointer_clauses()

        # (5) move clauses related to return value into a separate list
        self.formulas.separate_clause_for_return_value()

        # (6) from the clause list representation, get smt representation
        self.formulas.build_smt_representation()

        # (6) Add aliasing info into the smt representation
        pvar_aliased_sets = self.parsed_variable_map.get_aliasing_info()
        self.formulas.add_aliasing_info_to_smt(pvar_aliased_sets)

        # (7) eliminate a-vars and leftover lvars
        self.formulas.eliminate_avar_lvars_in_smt()

    def parse_both_linear_eqs(self, linear_eqs):
        """
        Linear equation format: variable=linear_arith.
        """
        clause_list = []

        for eq in linear_eqs:
            lhs_lvar = eq[0]
            lhs_pvar_repr = self.get_pvar_representation(lhs_lvar)
            # parsing the rhs side
            rhs_linear_arith = eq[1]
            rhs_linear_arith_list = self.parse_formula_linear_arith(rhs_linear_arith)
            if not rhs_linear_arith_list:
                # empty list, means something wrong during parsing => just discard
                continue

            clause_eq = RawClause.build_equality_to_var(
                lhs_pvar_repr, rhs_linear_arith_list
            )
            clause_list.append(clause_eq)

        self.formulas.add_to_conjunct_list_all(clause_list)

    def parse_pruned_atoms(self, atoms):
        """
        This method parse all four types of atoms from the 'pruned' formula.
        Pulse Type: Typ of Term.t * Term.t
        """
        clause_list = []
        for atom in atoms:
            atom_type = atom[0]
            atom_lhs = atom[1]
            atom_rhs = atom[2]
            lhs_typ, lhs_content = self.parse_formula_term(atom_lhs)
            rhs_typ, rhs_content = self.parse_formula_term(atom_rhs)
            if not lhs_typ or not rhs_typ:
                # this kind of term (hence atom) is not supported
                continue
            if not lhs_content or rhs_content:
                # empty list, this means something wrong in parsing and we just want to discard
                continue
            if atom_type == "Equal":
                clause_eq = RawClause.build_equality(lhs_content, rhs_content)
                clause_list.append(clause_eq)
            else:
                clause_ieq = RawClause.build_inequality(
                    atom_type, lhs_content, rhs_content
                )
                clause_list.append(clause_ieq)

        self.formulas.add_to_conjunct_list_path(clause_list)

    def parse_both_atoms(self, atoms):
        """
        There are only four types of atoms:
            - LessEqual
            - LessThan
            - Equal (ignored, assume to be covered by linear eqs)
            - NotEqual
        This method parse them into inequalities.
        Pulse Type: Typ of Term.t * Term.t
        """
        clause_list = []

        for atom in atoms:
            atom_type = atom[0]
            atom_lhs = atom[1]
            atom_rhs = atom[2]
            if atom_type == "Equal":
                # assume Equal are already covered in linear_eqs and skip
                continue
            lhs_typ, lhs_content = self.parse_formula_term(atom_lhs)
            rhs_typ, rhs_content = self.parse_formula_term(atom_rhs)
            if not lhs_typ or not rhs_typ:
                # this kind of term (hence atom) not supported
                continue
            if not lhs_content or rhs_content:
                # empty list, this means something wrong in parsing and we just want to discard
                continue
            # here lhs_content and rhs_content can be int or arith_list
            #  => we deal with this in clause building.
            clause_ieq = RawClause.build_inequality(atom_type, lhs_content, rhs_content)
            clause_list.append(clause_ieq)

        self.formulas.add_to_conjunct_list_all(clause_list)

    def parse_formula_term(self, term):
        """
        Helper method to parse a term, which appears in a few places. Pulse Type: Term.t
        :param: json term. This has a lot of types - we only consider a few.
        :returns: (typ, content). If typ is "Const", content is int;
                                  if typ is "Linear", content is list of linear arith.
        """
        term_type = term[0]
        if term_type == "Const":
            term_content = term[1]
            const_val = self.parse_rational(term_content)
            return term_type, const_val
        elif term_type == "Linear":
            term_content = term[1]
            linear_arith_list = self.parse_formula_linear_arith(term_content)
            return term_type, linear_arith_list
        else:  # other types of terms, ignore
            return None, None

    def parse_formula_linear_arith(self, linear_arith) -> list[tuple[str, int]]:
        """
        Helper method to parse a linear arith component, which appears in a few places. Pulse Type: LinArith.t
        :param linear_arith: json representing [2·x + 3/4·y + 12].
        :returns: list of (pvar_repr, coefficient), representing the linear arith.
                  if entry is ("", coefficient), the entry is just a const.
        """
        res = []
        var_part = linear_arith[0]
        const_part = linear_arith[1]
        # first deal with the var part
        for var_component in var_part:
            # each one is a variable with coefficient
            comp_lvar = var_component[0]
            comp_coefficient = var_component[1]
            comp_pvar_repr = self.get_pvar_representation(comp_lvar)
            coefficient = self.parse_rational(comp_coefficient)
            res.append((comp_pvar_repr, coefficient))
        # now left with the const part
        res.append(("", self.parse_rational(const_part)))
        return res

    def parse_rational(self, rational_json) -> int:
        num = int(rational_json["num"])
        den = int(rational_json["den"])
        if den == 0:
            return 0
        # TODO: float is not captured
        return num // den

    def get_pvar_representation(self, lvar):
        """
        :param pvar: str of logical variable.
        :returns: The str repr of lvar.
            If mapping found, this is the first mapped program variable.
            If mapping not found, this is the str logical variable itself.
        """
        pvar_repr = self.parsed_variable_map.get_first_pvar_for_lvar(lvar)
        if not pvar_repr:
            # use lvar first, may be simplifiable later
            return lvar
        else:
            return pvar_repr
