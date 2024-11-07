"""
Main repair loop.
"""

import signal
import time

from app import codeql, definitions, emitter, infer, utilities, values
from app.equivalence.cluster import Cluster, ClusterManager
from app.repairgen import patch_utils
from app.repairgen.generator import Generator
from app.result import result

# use this to record the entire search space size
# TODO: this calculation is inaccurate, so should be ignored for now
total_search_space_size = 0


def gen_patch_and_classify(
    fix_loc_line: int,
    fix_loc_end_line: int,
    generator: Generator,
    cluster_manager: ClusterManager,
) -> int:
    """
    Generate one patch and classify it into a cluster.
    :return: 0 if successful, 1 if failed
    """
    # restore a copy from the backupfile
    patch_utils.restore_file_to_unpatched_state()

    # (1) generate a patch candidate
    utilities.global_timer.start(definitions.DURATION_PATCH_GEN)

    # gen_random can stuck forever due to some reason.
    # Abort if it takes more than 60s to generate one string
    signal.alarm(30)
    try:
        is_random = not values.LEARN_PROBABILITIES
        patch_instruction, used_prods = generator.gen_random(is_random)
    except Exception as e:
        emitter.information(
            f"Stuck on one grammar generation. end repair loop for one location. Exception: {e}"
        )
        utilities.global_timer.pause(definitions.DURATION_PATCH_GEN)
        if values.LEARN_PROBABILITIES and values.IS_RESET_PROB:
            emitter.error("exhaustion detected, resetting probabilities")
            result.count_reset()
            grammar_state = generator.grammar.reset_probabilities(
                values.GENERATOR_MAX_DEPTH
            )
            time_elapsed = utilities.global_timer.get_elapsed_from_overall_start()
            result.new_probability_update(fix_loc_line, time_elapsed, grammar_state)
        return 1
    finally:
        signal.alarm(0)

    utilities.global_timer.pause(definitions.DURATION_PATCH_GEN)

    if patch_instruction is None:
        return 1

    patch_file_path = patch_utils.weave_patch_instruction(
        patch_instruction, fix_loc_line, fix_loc_end_line
    )

    # (2) get the summary of new patch, and put it to suitable cluster
    utilities.global_timer.start(definitions.DURATION_FOOTPRINT_GEN)
    infer_summary_file = infer.infer_target_function()
    utilities.global_timer.pause(definitions.DURATION_FOOTPRINT_GEN)

    utilities.global_timer.start(definitions.DURATION_PATCH_CLUSTER)
    if infer_summary_file is None:
        # summary file was not produced - assume the patch could not be compiled
        cluster_manager.add_new_noncompilable_patch(patch_file_path)
    else:
        # exceptions happened in pysmt are tricky to debug;
        # assume the patch is bad if such exceptions are triggered
        try:
            cluster: Cluster = cluster_manager.add_new_patch(
                patch_file_path, len(used_prods), infer_summary_file
            )

            emitter.information(f"Adding to Cluster {cluster.cluster_name}")

            # code to detect if we are stuck in a local optima
            is_stagnated = False
            prod_rule_signature = result.generate_prod_signature(
                used_prods, generator.grammar.non_terminals
            )
            result.add_used_prod_rule(prod_rule_signature)
            if prod_rule_signature not in values.USED_PROD_RULES:
                values.USED_PROD_RULES[prod_rule_signature] = 0
            if prod_rule_signature not in values.PLAUSIBLE_PROD_RULES:
                values.PLAUSIBLE_PROD_RULES[prod_rule_signature] = 0
            values.USED_PROD_RULES[prod_rule_signature] += 1

            if cluster.is_locally_good:
                result.add_plausible_prod_rule(prod_rule_signature)
                values.PLAUSIBLE_PROD_RULES[prod_rule_signature] += 1

            count_used = values.USED_PROD_RULES[prod_rule_signature]
            count_plausible = values.PLAUSIBLE_PROD_RULES[prod_rule_signature]

            if (count_used % values.MAX_GENERATE_THRESHOLD == 0) or (
                count_plausible > 0
                and count_plausible % values.MAX_PLAUSIBLE_THRESHOLD == 0
            ):
                is_stagnated = True

            if is_stagnated and values.IS_RESET_PROB and values.LEARN_PROBABILITIES:
                emitter.error("stagnation detected, resetting probabilities")
                values.STAGNATED_PROD_RULES.append(prod_rule_signature)
                emitter.highlight(f"Grammar: :{prod_rule_signature}")
                emitter.highlight(f"plausible count: {count_plausible}")
                emitter.highlight(f"cumulative repetition: {count_used}")
                result.add_stagnated_prod_rule(prod_rule_signature)
                result.count_reset()

                grammar_state = generator.grammar.reset_probabilities(
                    values.GENERATOR_MAX_DEPTH
                )
                time_elapsed = utilities.global_timer.get_elapsed_from_overall_start()
                result.new_probability_update(fix_loc_line, time_elapsed, grammar_state)

            if not is_stagnated and values.LEARN_PROBABILITIES:
                # skip updating if its an already known local optima
                if prod_rule_signature not in values.STAGNATED_PROD_RULES:
                    emitter.highlight(f"Grammar: :{prod_rule_signature}")
                    emitter.highlight(f"plausible count: {count_plausible}")
                    emitter.highlight(f"cumulative repetition: {count_used}")
                    emitter.information(f"Cluster pe increment: {cluster.pe_increment}")
                    emitter.information(
                        f"Cluster ppie increment: {cluster.ppie_increment}"
                    )
                    utilities.global_timer.start(definitions.DURATION_PROB_UPDATE)
                    grammar_state = generator.grammar.update_probabilities(
                        used_prods, cluster.pe_increment, cluster.ppie_increment
                    )
                    time_elapsed = (
                        utilities.global_timer.get_elapsed_from_overall_start()
                    )
                    result.new_probability_update(
                        fix_loc_line, time_elapsed, grammar_state
                    )
                    utilities.global_timer.pause(definitions.DURATION_PROB_UPDATE)

        except Exception:
            cluster_manager.add_new_noncompilable_patch(patch_file_path)

    utilities.global_timer.pause(definitions.DURATION_PATCH_CLUSTER)
    return 0


def repair(
    fix_loc_line: int,
    return_stmts: list[str],
    labels: list[str],
    time_budget: float,
):
    global total_search_space_size

    assert values.TARGET_BUG is not None

    time_start = time.perf_counter()

    emitter.title(f"Repairing Program at location: {fix_loc_line}")

    # (3) Compute various things for patch ingredients
    emitter.sub_title(f"Loc {fix_loc_line}: Getting patch ingredients at fix location")

    utilities.global_timer.start(definitions.DURATION_CODEQL_STMT_BOUNDARY)
    emitter.information(
        f"Loc {fix_loc_line}: [Codeql] Running statement boundary query"
    )
    codeql.run_stmt_boundary_query(values.TARGET_BUG.file, fix_loc_line)
    fix_loc_end_line = codeql.parse_stmt_boudary_query_result()
    emitter.highlight("Statement at fix location ends at line " + str(fix_loc_end_line))
    utilities.global_timer.stop(definitions.DURATION_CODEQL_STMT_BOUNDARY)

    utilities.global_timer.start(definitions.DURATION_CODEQL_EXTRACT_VAR)
    emitter.information(
        f"Loc {fix_loc_line}: [Codeql] Running patch ingredient (variable) query"
    )
    codeql.run_extract_var_query(
        values.TARGET_BUG.file,
        values.TARGET_BUG.procedure,
        values.TARGET_BUG.start_line,
        fix_loc_line,
    )
    pointer_vars, non_pointer_vars = codeql.parse_extract_var_query_result()
    emitter.highlight(f"Loc {fix_loc_line}: Pointer variables: " + str(pointer_vars))
    emitter.highlight(
        f"Loc {fix_loc_line}: Non-pointer variables: " + str(non_pointer_vars)
    )
    result.pointer_vars(fix_loc_line, pointer_vars)
    result.non_pointer_vars(fix_loc_line, non_pointer_vars)
    utilities.global_timer.stop(definitions.DURATION_CODEQL_EXTRACT_VAR)

    utilities.global_timer.start(definitions.DURATION_CODEQL_CONSTS)
    emitter.information(
        f"Loc {fix_loc_line}: [Codeql] Running patch ingredient (constants) query"
    )
    codeql.run_consts_query(
        values.TARGET_BUG.file, values.TARGET_BUG.procedure, fix_loc_line
    )
    consts = codeql.parse_consts_query_result()
    emitter.highlight(f"Loc {fix_loc_line}: Constants: " + str(consts))
    result.constants(fix_loc_line, consts)
    utilities.global_timer.stop(definitions.DURATION_CODEQL_CONSTS)

    ################ start doing real repair ##################

    emitter.sub_title(
        f"Loc {fix_loc_line}: Initializing Patch Generator and Cluster Manager"
    )
    generator = Generator(
        pointer_vars,
        non_pointer_vars,
        return_stmts,
        labels,
        consts,
        values.GENERATOR_MAX_DEPTH,
    )
    generator.build_grammar()
    search_space_size = generator.estimate_size()

    cluster_manager = ClusterManager(values.DIR_ALL_PATCHES, "L" + str(fix_loc_line))

    emitter.sub_title(f"Loc {fix_loc_line}: Entering the main repair loop")

    emitter.information(
        f"Loc {fix_loc_line}: Total search space size: {search_space_size}"
    )

    total_search_space_size += search_space_size

    if time.perf_counter() - time_start >= time_budget:
        utilities.error_exit(
            "Time budget for this location exceeded before entering the main repair loop. Try increasing the time limit."
        )

    # send the initial grammar state to result
    grammar_state = generator.grammar.get_grammar_state()
    time_elapsed = utilities.global_timer.get_elapsed_from_overall_start()
    result.new_probability_update(fix_loc_line, time_elapsed, grammar_state)

    while True:
        if time.perf_counter() - time_start >= time_budget:
            emitter.information(
                f"Loc {fix_loc_line}: Ending repair loop since time budget is exceeded"
            )
            break
        if cluster_manager.get_total_num_patches() == search_space_size:
            emitter.information(
                f"Loc {fix_loc_line}: Ending repair loop since search space is exhausted"
            )
            break
        ret = gen_patch_and_classify(
            fix_loc_line, fix_loc_end_line, generator, cluster_manager
        )
        if ret != 0:
            emitter.warning("did not generate a new patch")

    emitter.sub_title(f"Loc {fix_loc_line}: Repair loop finished")

    result.num_clusters(fix_loc_line, cluster_manager.get_num_clusters())
    result.num_total_patches(fix_loc_line, cluster_manager.get_total_num_patches())
    good_cluster_names = [
        c.cluster_name for c in cluster_manager.clusters if c.is_locally_good
    ]
    result.locally_plausible_cluster_names(fix_loc_line, good_cluster_names)

    return cluster_manager


def print_repair_stats(cluster_managers: list[ClusterManager]):
    num_total_patches = 0
    num_total_clusters = 0

    for cluster_manager in cluster_managers:
        num_total_patches += cluster_manager.get_total_num_patches()
        num_total_clusters += cluster_manager.get_num_clusters()

    # time stats
    utilities.global_timer.print_total_and_average(
        definitions.DURATION_PATCH_GEN, num_total_patches
    )

    if values.LEARN_PROBABILITIES:
        utilities.global_timer.print_total_and_average(
            definitions.DURATION_PROB_UPDATE, num_total_patches
        )

    utilities.global_timer.print_total_and_average(
        definitions.DURATION_PATCH_SIGN_GEN, num_total_patches
    )

    utilities.global_timer.print_total_and_average(
        definitions.DURATION_FOOTPRINT_GEN, num_total_patches
    )

    utilities.global_timer.print_total_and_average(
        definitions.DURATION_PATCH_CLUSTER, num_total_patches
    )

    # patch stats
    average_patches_per_cluster = num_total_patches / num_total_clusters

    emitter.information(f"Number of prod-rule-combos: {len(values.USED_PROD_RULES)}")
    p_count = 0
    for p in values.PLAUSIBLE_PROD_RULES:
        if values.PLAUSIBLE_PROD_RULES[p] > 0:
            p_count += 1
    emitter.information(f"Number of plausible prod-rule-combos: {p_count}")
    emitter.information(f"Number of clusters: {num_total_clusters}")
    emitter.information(f"Number of clustered patches: {num_total_patches}")
    emitter.information(
        "Average number of patches per cluster:"
        + format(average_patches_per_cluster, ".3f")
    )
    index = 0
    for prod_combo in values.PLAUSIBLE_PROD_RULES:
        index = index + 1
        emitter.information(
            f"plausible-prod-combo-{index}: {values.PLAUSIBLE_PROD_RULES[prod_combo]}"
        )

    index = 0
    for prod_combo in values.USED_PROD_RULES:
        index = index + 1
        emitter.information(f"prod-combo-{index}: {values.USED_PROD_RULES[prod_combo]}")
