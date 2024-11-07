import os
import random
import shutil

from app import definitions, emitter, infer, utilities, values
from app.equivalence.cluster import Cluster, ClusterManager
from app.repairgen import patch_utils
from app.result import result


def get_locally_good_clusters(cluster_manager: ClusterManager):
    normal_clusters = cluster_manager.clusters

    return [cluster for cluster in normal_clusters if cluster.is_locally_good]


def get_representative_patch(list_patches):
    sorted_patches = sorted(list_patches, key=lambda x: x[1])
    _, smallest_patch_size = sorted_patches[0]
    filtered_patches = [x[0] for x in sorted_patches if x[1] == smallest_patch_size]

    # for equally-smallest ones, select one randomly
    patch_path = random.choice(filtered_patches)
    return patch_path


def validate_a_cluster(patches_in_cluster):
    """
    :return: True if validation passed; False otherwise.
    """
    utilities.global_timer.start(definitions.DURATION_PATCH_VAL)

    selected_smallest_patch_path = get_representative_patch(patches_in_cluster)

    emitter.information(
        "Validating a cluster with patch: " + selected_smallest_patch_path
    )

    patch_utils.apply_patch_file(selected_smallest_patch_path)
    report_json_path = infer.infer_validation_whole_program()
    patch_utils.restore_file_to_unpatched_state()

    # check whether the original bug is there
    target_bug, _ = infer.identify_target_bug_in_unpatched_prog(report_json_path)
    orig_bug_disappeared = target_bug is None
    # no_new_bugs = num_bugs < values.TOTAL_NUM_BUGS
    validation_passed = orig_bug_disappeared

    if validation_passed:
        emitter.information(
            "Bug is fixed by this cluster! Smallest patch: "
            + selected_smallest_patch_path
        )
        # actually copy the representative patch over
        shutil.copy2(selected_smallest_patch_path, values.DIR_FINAL_PATCHES)
    else:
        emitter.information("Bug is NOT fixed by this cluster.")

    utilities.global_timer.pause(definitions.DURATION_PATCH_VAL)
    return validation_passed


def validate(cluster_managers: list[ClusterManager]):
    emitter.title("Validating locally good clusters")

    assert values.TARGET_BUG is not None

    # write changed-file file; used for validation run of Infer
    with open(values.INFER_CHANGED_FILES, "w") as f:
        f.write(values.TARGET_BUG.file)

    emitter.sub_title("Checking which clusters are locally good")
    locally_good_clusters: list[Cluster] = []
    for cluster_manager in cluster_managers:
        good_clusters = get_locally_good_clusters(cluster_manager)
        locally_good_clusters.extend(good_clusters)

    num_locally_good_clusters = len(locally_good_clusters)
    emitter.information(f"Number of locally good clusters: {num_locally_good_clusters}")
    clusters_str = "["
    for cluster in locally_good_clusters:
        clusters_str += str(cluster) + ",\n"
    clusters_str += "]"
    emitter.information("Locally good clusters are: " + clusters_str)

    if not locally_good_clusters:
        emitter.warning("No locally good clusters found. Cannot validate.")
        return

    if not os.path.isdir(values.DIR_FINAL_PATCHES):
        os.makedirs(values.DIR_FINAL_PATCHES)

    if values.VALIDATE_GLOBAL:
        # (3) get one representative from each locally good cluster
        #     and run infer whole program analysis on it
        emitter.sub_title("Validating locally good clusters")
        globally_good_clusters = []
        for cluster in locally_good_clusters:
            result.add_locally_plausible_patches([x[0] for x in cluster.patches])
            is_globally_good = validate_a_cluster(cluster.patches)
            if is_globally_good:
                globally_good_clusters.append(cluster)
                result.add_globally_plausible_cluster_name(cluster.cluster_name)
                result.add_globally_plausible_patches([x[0] for x in cluster.patches])

        average_val_time = utilities.global_timer.print_total_and_average(
            definitions.DURATION_PATCH_VAL, num_locally_good_clusters
        )
        if average_val_time is not None:
            result.specify_avg_validation_time(average_val_time)

        num_globally_good_clusters = len(globally_good_clusters)
        emitter.information(
            f"Num locally good: {num_locally_good_clusters}; num globally good: {num_globally_good_clusters}"
        )

        # send final patch paths to result
        final_patches = os.listdir(values.DIR_FINAL_PATCHES)
        final_patches = [
            os.path.join(values.DIR_FINAL_PATCHES, x) for x in final_patches
        ]
        # one final patch per globally good cluster
        result.specify_globally_representative_patches(final_patches)

    else:
        result.specify_avg_validation_time(0.0)
        result.specify_globally_representative_patches([])
        for cluster in locally_good_clusters:
            cluster_patch_list = [x[0] for x in cluster.patches]
            rep_patch = get_representative_patch(cluster.patches)
            shutil.copy2(
                rep_patch,
                f"{values.DIR_FINAL_PATCHES}/rep_{cluster.cluster_name}.patch",
            )
            result.add_locally_plausible_patches(cluster_patch_list)
            for p_path in cluster_patch_list:
                shutil.copy2(p_path, values.DIR_FINAL_PATCHES)
