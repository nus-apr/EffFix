import json


class Result:
    """
    Make a class to organize results.
    """

    def __init__(self):
        # map from location to results at that location
        self.loc_resutls = dict()
        self.return_stmts = []
        self.label_names = []
        # this is for the overall number
        # there is also a similar entry in loc-result; that's for per loc infos
        self.locally_good_patches = []
        self.globally_good_clusters = []
        self.globally_good_patches = []
        self.globally_representative_patches = []
        self.patch_found_time = []
        self.average_validation_time = 0
        self.total_resets = 0
        self.stagnated_prod_rules = dict()
        self.used_prod_rules = dict()
        self.plausible_prod_rules = dict()

    def fix_locations(self, fix_locations: list[int]):
        for loc in fix_locations:
            self.loc_resutls[loc] = dict()

    def returns(self, returns: list[str]):
        self.return_stmts = returns

    def labels(self, labels: list[str]):
        self.label_names = labels

    def pointer_vars(self, loc, pointers: list[str]):
        self.loc_resutls[loc]["pointers"] = pointers

    def non_pointer_vars(self, loc, non_pointers: list[str]):
        self.loc_resutls[loc]["non_pointers"] = non_pointers

    def constants(self, loc, constants: list[str]):
        self.loc_resutls[loc]["constants"] = constants

    def num_clusters(self, loc, num: int):
        self.loc_resutls[loc]["num_clusters"] = num

    def num_total_patches(self, loc, num: int):
        self.loc_resutls[loc]["num_total_patches"] = num

    ##### local
    def locally_plausible_cluster_names(self, loc, cluster_names: list[str]):
        self.loc_resutls[loc]["locally_plausible_clusters"] = cluster_names

    def found_new_locally_plausible_patch(self, time_stamp: float):
        self.patch_found_time.append(time_stamp)

    def add_locally_plausible_patches(self, patches: list[str]):
        self.locally_good_patches.extend(patches)

    def add_globally_plausible_cluster_name(self, cluster_name: str):
        self.globally_good_clusters.append(cluster_name)

    def add_globally_plausible_patches(self, patches: list[str]):
        self.globally_good_patches.extend(patches)

    def specify_globally_representative_patches(self, patches: list[str]):
        self.globally_representative_patches = patches

    ##### Probability
    def new_probability_update(self, loc, time_stamp: float, grammar_state):
        if "grammar_states" not in self.loc_resutls[loc]:
            self.loc_resutls[loc]["grammar_states"] = []

        self.loc_resutls[loc]["grammar_states"].append(
            {"timestamp": time_stamp, "state": grammar_state}
        )

    def add_stagnated_prod_rule(self, optima_signature):
        if optima_signature not in self.stagnated_prod_rules:
            self.stagnated_prod_rules[optima_signature] = 0
        self.stagnated_prod_rules[optima_signature] += 1

    def add_used_prod_rule(self, rule_signature):
        if rule_signature not in self.used_prod_rules:
            self.used_prod_rules[rule_signature] = 0
        self.used_prod_rules[rule_signature] += 1

    def generate_prod_signature(self, prod_rules, non_terminals):
        # generate signature for current rule set
        non_leaf_rules = []
        for p in prod_rules:
            token_list = str(p).split(" ")
            if any(t in non_terminals for t in token_list):
                non_leaf_rules.append(str(p))
        prod_rule_signature = ",".join(non_leaf_rules)
        return prod_rule_signature

    def add_plausible_prod_rule(self, rule_signature):
        if rule_signature not in self.plausible_prod_rules:
            self.plausible_prod_rules[rule_signature] = 0
        self.plausible_prod_rules[rule_signature] += 1

    ##### Others
    def specify_avg_validation_time(self, t: float):
        self.average_validation_time = t

    def count_reset(self):
        self.total_resets += 1

    def to_json(self, output_file):
        # calculate some aggregated stats over the locations
        total_num_clusters = 0
        total_num_patches = 0
        total_num_pointers = 0
        total_num_non_pointers = 0
        total_num_constants = 0
        total_num_locally_good_clusters = 0

        for loc in self.loc_resutls:
            total_num_clusters += self.loc_resutls[loc]["num_clusters"]
            total_num_patches += self.loc_resutls[loc]["num_total_patches"]
            total_num_pointers += len(self.loc_resutls[loc]["pointers"])
            total_num_non_pointers += len(self.loc_resutls[loc]["non_pointers"])
            total_num_constants += len(self.loc_resutls[loc]["constants"])
            total_num_locally_good_clusters += len(
                self.loc_resutls[loc]["locally_plausible_clusters"]
            )

        average_num_pointers = total_num_pointers / len(self.loc_resutls)
        average_num_non_pointers = total_num_non_pointers / len(self.loc_resutls)
        average_num_constants = total_num_constants / len(self.loc_resutls)

        # build a json object containing all the fields
        json_obj = {
            "stats": {
                "num_fix_locations": len(self.loc_resutls.keys()),
                "return_stmts": self.return_stmts,
                "return_stmts_count": len(self.return_stmts),
                "labels": self.label_names,
                "labels_count": len(self.label_names),
                "avg_num_pointers": average_num_pointers,
                "avg_num_non_pointers": average_num_non_pointers,
                "avg_num_constants": average_num_constants,
                "total_num_patches": total_num_patches,
                "total_num_clusters": total_num_clusters,
                "num_patches_per_cluster": total_num_patches / total_num_clusters,
                "average_validation_time": format(self.average_validation_time, ".5f")
                + " s",
                "total_num_locally_plausible_clusters": total_num_locally_good_clusters,
                "total_num_locally_plausible_patches": len(self.locally_good_patches),
                "total_num_globally_plausible_clusters": len(
                    self.globally_good_clusters
                ),
                "total_num_globally_plausible_patches": len(self.globally_good_patches),
                "total_num_globally_representative_patches": len(
                    self.globally_representative_patches
                ),
                "globally_plausible_clusters": self.globally_good_clusters,
                "globally_representative_patches": self.globally_representative_patches,
                "total_stagnated_rules": len(self.stagnated_prod_rules),
                "total_prod_rules": len(self.used_prod_rules),
                "total_plausible_prod_rules": len(self.plausible_prod_rules),
                "total_resets": self.total_resets,
            },
            "plausible_patch_found_time": self.patch_found_time,
            "loc_results": self.loc_resutls,
            "stagnated_prod_rules": self.stagnated_prod_rules,
            "plausible_prod_rules": self.plausible_prod_rules,
            "used_prod_rules": self.used_prod_rules,
        }

        with open(output_file, "w") as f:
            json.dump(json_obj, f, indent=4)


result = Result()
