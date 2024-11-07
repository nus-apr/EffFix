import hashlib
import json
import os
import shutil
from enum import Enum
from pprint import pformat

from app import definitions, emitter, utilities, values
from app.equivalence.smt import SmtFormula
from app.parsing.parse_report import PulseBug
from app.parsing.parse_summary import PulseDisjunctParser
from app.result import result


class RewardType(Enum):
    BIG = "big"
    SMALL = "small"
    NO = "no"


class DisjunctLabel:
    def __init__(self, text: str, start_line: int, end_line: int):
        # this is the label text
        self.text: str = text
        # use these two lines for comparison, instead of doing hash ...
        self.start_line: int = start_line
        self.end_line: int = end_line

    @staticmethod
    def turn_line_nums_into_hash(start_line: int, end_line: int) -> str:
        """
        Pre-condition: file on disk should be aligned with start_line and end_line meaning.
        """
        bug_file = os.path.join(values.CONF_DIR_SRC_BUILD, values.CONF_BUG_FILE)
        with open(bug_file) as f:
            bug_lines = f.readlines()
        hash_input = ""
        if start_line <= 0 or start_line > len(bug_lines):
            hash_input += str(start_line)
        else:
            bug_content = bug_lines[start_line - 1]
            bug_content = bug_content.strip().strip("\n").strip()
            hash_input += bug_content

        hash_input += " "
        if end_line <= 0 or end_line > len(bug_lines):
            hash_input += str(end_line)
        else:
            bug_content = bug_lines[end_line - 1]
            bug_content = bug_content.strip().strip("\n").strip()
            hash_input += bug_content

        hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        return hash

    def is_ok(self):
        return self.text == definitions.LABEL_OK

    def is_showing_pulse_bug(self, bug: PulseBug):
        """
        Checks whether this label is showing the `bug`.
        Handles compilcation where bug type in whole-program report and single-function
        disjuncts are different.
        """
        both_leak = (
            bug.type == definitions.BUG_TYPE_LEAK
            and self.text == definitions.LABEL_MEMORY_LEAK
        )
        both_npe = bug.type == definitions.BUG_TYPE_NULLPTR and (
            self.text == definitions.LABEL_INVALID_ACCESS
            or self.text == definitions.LABEL_ABORT
        )
        if not (both_leak or both_npe):
            return False
        same_start = self.start_line == bug.start_line
        same_end = self.end_line == bug.end_line
        return same_start and same_end

    def is_buggy_type(self):
        return (
            self.text == definitions.LABEL_MEMORY_LEAK
            or self.text == definitions.LABEL_ABORT
            or self.text == definitions.LABEL_LATENT_ABORT
        )

    def is_abort_type(self):
        return (
            self.text == definitions.LABEL_ABORT
            or self.text == definitions.LABEL_LATENT_ABORT
        )

    def __eq__(self, other):
        if not isinstance(other, DisjunctLabel):
            return False
        return (
            self.text == other.text
            and self.start_line == other.start_line
            and self.end_line == other.end_line
        )

    def __hash__(self):
        return hash((self.text, self.start_line, self.end_line))

    def __str__(self):
        res = (
            "<"
            + self.text
            + ", "
            + str(self.start_line)
            + ", "
            + str(self.end_line)
            + ">"
        )
        return res


class DisjunctSignature:
    def __init__(
        self,
        label: DisjunctLabel,
        allocated: set[set[str]] | frozenset[set[str]],
        deallocated: set[set[str]] | frozenset[set[str]],
        return_formula,
        formula,
    ):
        self.label = label
        self.allocated = frozenset(allocated)
        self.deallocated = frozenset(deallocated)
        # special formula constraining return value
        self.return_formula = return_formula
        # general formula not related to return value
        self.formula = formula

    def contains_pulse_bug(self, bug: PulseBug):
        """
        Check whether `bug` is contained on this disjunct.
        """
        return self.label.is_showing_pulse_bug(bug)

    def is_mergable_with(self, other):
        """
        Check if it's possbile to merge two DisjunctSignatures.
        Mergable if they have the same label, and the same allocated/deallocated sets, and same constraints for the return value.
        Here, two allocated sets have different aliasing (e.g. { {a,c}, {b} } and { {a}, {b} }) are considered to be different.

        NOTE: do not merge non-error disjuncts, as that prevent us from checking whether
              a bug is partially fixed (i.e. whether part of the error path becomes good)
        """
        error_label_texts = [definitions.LABEL_ABORT, definitions.LABEL_MEMORY_LEAK]

        if not isinstance(other, DisjunctSignature):
            return False
        if self.label != other.label:
            return False
        if self.allocated != other.allocated:
            return False
        if self.deallocated != other.deallocated:
            return False
        return_constraints_equiv = SmtFormula.check_equivalence(
            self.return_formula, other.return_formula
        )
        if not return_constraints_equiv:
            return False

        if self.label.text in error_label_texts:
            # for error disjuncts, they can be merged now
            return True
        else:
            # for normal disjuncts, we only merge if the formula is equivalent
            return SmtFormula.check_equivalence(self.formula, other.formula)

    def merge_with(self, other):
        assert self.is_mergable_with(other)
        merged_formula = SmtFormula.build_disjunction([self.formula, other.formula])
        return DisjunctSignature(
            self.label,
            self.allocated,
            self.deallocated,
            self.return_formula,
            merged_formula,
        )

    def is_equal(self, other):
        """
        Use this to check for equality manually, instead of putting DisjunctSignature's
        into set and make set maintains the equality.
        This is because we can use allocated sets comparison as a fast
        track, and only do formula checking less frequently.
        On the other hand, set uses hash-values, which cannot be computed
        in stages like this.
        """
        if not isinstance(other, DisjunctSignature):
            return False
        if not self.is_label_and_sets_and_return_formula_equal(other):
            return False
        # for formula equality, use smt solver
        return SmtFormula.check_equivalence(self.formula, other.formula)

    def is_label_and_sets_and_return_formula_equal(self, other):
        if not isinstance(other, DisjunctSignature):
            return False
        return (
            (self.label == other.label)
            and (self.allocated == other.allocated)
            and (self.deallocated == other.deallocated)
            and SmtFormula.check_equivalence(self.return_formula, other.return_formula)
        )

    def is_label_and_sets_equal(self, other):
        """
        Check if the label and allocated/deallocated sets are equal.
        """
        if not isinstance(other, DisjunctSignature):
            return False
        return (
            (self.label == other.label)
            and (self.allocated == other.allocated)
            and (self.deallocated == other.deallocated)
        )

    def is_label_equal(self, other):
        if not isinstance(other, DisjunctSignature):
            return False
        return self.label == other.label

    def is_label_text_start_and_sets_equal(self, other):
        """
        Check if the label text, start line, and allocated/deallocated sets are equal.
        """
        if not isinstance(other, DisjunctSignature):
            return False
        return (
            (self.label.text == other.label.text)
            and (self.label.start_line == other.label.start_line)
            and (self.allocated == other.allocated)
            and (self.deallocated == other.deallocated)
        )

    def is_sets_and_return_equal(self, other):
        if not isinstance(other, DisjunctSignature):
            return False
        return (
            self.allocated == other.allocated
            and self.deallocated == other.deallocated
            and SmtFormula.check_equivalence(self.return_formula, other.return_formula)
        )

    def is_label_text_start_equal(self, other):
        """
        Check if the label text and start line are equal.
        """
        if not isinstance(other, DisjunctSignature):
            return False
        return (self.label.text == other.label.text) and (
            self.label.start_line == other.label.start_line
        )

    def is_label_text_equal(self, other):
        """
        Check if the label texts are equal.
        """
        if not isinstance(other, DisjunctSignature):
            return False
        return self.label.text == other.label.text

    def __str__(self):
        ret = "DisjunctSignature: "
        ret += "label: " + str(self.label) + ", \n"
        ret += "\t\tallocated: " + pformat(self.allocated) + ", \n"
        ret += "\t\tdeallocated: " + pformat(self.deallocated) + ", \n"
        ret += "\t\treturn_formula: " + pformat(self.return_formula) + ", \n"
        ret += "\t\tformula: " + pformat(self.formula)
        return ret


class PatchSignature:
    """
    A patch signature is a reduced set of DisjunctSignatures.
    "Reduced" means that the raw PathSignatures are merged.
    """

    def __init__(self):
        # a list of disjunct signatures
        self.signatures: list[DisjunctSignature] = []

    def contains_pulse_bug(self, bug: PulseBug):
        """
        Checks whether any disjuncts contains `bug`.
        """
        return any([sig.contains_pulse_bug(bug) for sig in self.signatures])

    def contains_new_bugs_than(self, other):
        """
        Checks whether this sig contains new bugs that are not in `other`.
        Essentially doing set difference on the two sets of labels.
        """
        if not isinstance(other, PatchSignature):
            return False
        this_labels = {sig.label for sig in self.signatures if not sig.label.is_ok()}
        other_labels = {sig.label for sig in other.signatures if not sig.label.is_ok()}
        diff_set = this_labels.difference(other_labels)
        return len(diff_set) > 0

    def pick_disjunct_sig_with_target_bug(
        self, target_bug: PulseBug
    ) -> DisjunctSignature | None:
        """
        Pick a disjunct signature that contains the target bug.
        """
        for sig in self.signatures:
            if sig.contains_pulse_bug(target_bug):
                return sig
        return None

    @staticmethod
    def remove_similar_buggy_disjuncts(
        orig_sig_list: list[DisjunctSignature],
        new_patched_sig_list: list[DisjunctSignature],
        target_bug: PulseBug,
    ) -> tuple[list[DisjunctSignature], list[DisjunctSignature]]:
        """
        When deciding on the pe ppie increment, we only use label text and start line to identify
        the buggy disjunct. However, in some cases, the program could have other bugs having
        the same text and start line.
        Instead of using some other hacks, we first remove those "similar" bugs from both patch sigs.
        """
        buggy_signature_idxes = []
        for idx, disjunct_sig in enumerate(orig_sig_list):
            if disjunct_sig.contains_pulse_bug(target_bug):
                buggy_signature_idxes.append(idx)

        assert len(buggy_signature_idxes) > 0
        buggy_disjunct_sig = orig_sig_list[buggy_signature_idxes[0]]

        # note that disjuncts in this list are NOT the original buggy disjunct we want to fix
        similar_bug_dis_sigs = [
            dis_sig
            for dis_sig in orig_sig_list
            if dis_sig.is_label_text_start_equal(buggy_disjunct_sig)
            and dis_sig.label.end_line != buggy_disjunct_sig.label.end_line
        ]

        # remove "similar" bugs from both patch sigs
        def f(sig: DisjunctSignature) -> bool:
            for dis_sig in similar_bug_dis_sigs:
                if sig.is_label_equal(dis_sig):
                    return False
            return True

        filtered_orig = list(filter(f, orig_sig_list))
        filtered_new = list(filter(f, new_patched_sig_list))
        return filtered_orig, filtered_new

    @staticmethod
    def should_big_or_small_increase_pe(
        orig_sig_list: list[DisjunctSignature],
        new_sig_list: list[DisjunctSignature],
        target_bug: PulseBug,
    ) -> tuple[bool, bool]:
        """
        Small increase pe: if original buggy disjuncts no long exist, and no new buggy disjuncts
                           are introduced.
        Big increase pe: on top of small increase pe, the functionality of "most" disjuncts should
                         not change. The functionality is approximated with allocated/deallocated
                         sets + return value. By "most", we mean all disjuncts in the original
                         program, other than those with "Abort"-like labels. When resolving "Abort"
                         disjuncts, it's inevitable to change its functionality, because the return
                         value has to be added if the abort goes away.

        :return: (bool, bool) => (should_big_increase_pe, should_small_increase_pe)
        """
        ### (1) check whehther we can small increase pe

        # get the buyggy disjunct, as well as the non-buggy disjuncts
        buggy_signature_idx = -1
        for idx, disjunct_sig in enumerate(orig_sig_list):
            if disjunct_sig.contains_pulse_bug(target_bug):
                buggy_signature_idx = idx
                break
        assert buggy_signature_idx != -1
        buggy_disjunct_sig = orig_sig_list[buggy_signature_idx]

        # frist check - must fix target bug
        fixed_target_bug = all(
            [
                not sig.is_label_text_start_equal(buggy_disjunct_sig)
                for sig in new_sig_list
            ]
        )
        if not fixed_target_bug:
            return False, False

        all_orig_bug_sigs = [sig for sig in orig_sig_list if sig.label.is_buggy_type()]

        # second check - must not introduce new bug
        introduce_new_bug = False
        for sig in new_sig_list:
            if not sig.label.is_buggy_type():
                continue
            # now we have a sig which is buggy in some way - they must be same as one of the original
            same_as_one_of_original = any(
                [
                    sig.is_label_text_start_equal(orig_sig)
                    for orig_sig in all_orig_bug_sigs
                ]
            )
            if not same_as_one_of_original:
                introduce_new_bug = True
                break

        if introduce_new_bug:
            return False, False

        ### (2) now we know should definitely small increase pe; check whether we should big increase pe

        # (2.1) old functionality should remain
        # NOTE: we only consider non-abort disjuncts here, because original abort
        #       disjuncts should have functionality (i.e. return value) being changed.
        orig_non_abort_disjunct_list = [
            sig for sig in orig_sig_list if not sig.label.is_abort_type()
        ]
        for this_dis_sig in orig_non_abort_disjunct_list:
            # check whether this disjunct has a corresponding new disjunct
            matched_with_any_new_dis = False
            for other_dis_sig in new_sig_list:
                # only consider sets and return value when doing matching,
                # since these represents effect and "functionality"
                this_match_with_other = this_dis_sig.is_sets_and_return_equal(
                    other_dis_sig
                )
                if this_match_with_other:
                    matched_with_any_new_dis = True
                    break
            if not matched_with_any_new_dis:
                # this disjunct has no corresponding new disjunct
                return False, True

        # (2.2) new functionality should not be introduced
        # NOTE: this direction is trickier. For NPE bugs, if the fix is correct, likely
        #       new functionality SHOULD be introduced becase an abort is resolved.
        #       Hence, if original disjuncts contain aborts, this check cannot be reliably
        #       carried out.
        if len(orig_non_abort_disjunct_list) != len(orig_sig_list):
            # original disjuncts contain aborts
            return True, True
        for this_dis_sig in new_sig_list:
            matched_with_any_orig_dis = False
            for other_dis_sig in orig_non_abort_disjunct_list:
                this_match_with_other = this_dis_sig.is_sets_and_return_equal(
                    other_dis_sig
                )
                if this_match_with_other:
                    matched_with_any_orig_dis = True
                    break
            if not matched_with_any_orig_dis:
                # this disjunct has no corresponding original disjunct
                return False, True

        # if we reach here, then no old functionality is removed, and no new functionality
        # is introduced
        return True, True

    @staticmethod
    def should_big_or_small_increase_ppie(
        orig_sig_list: list[DisjunctSignature],
        new_sig_list: list[DisjunctSignature],
        target_bug: PulseBug,
    ) -> tuple[bool, bool]:
        """
        :return: (bool, bool) => (should_big_increase_ppie, should_small_increase_ppie)
        """
        # get the buyggy disjunct, as well as the non-buggy disjuncts
        buggy_signature_idxes = []
        for idx, disjunct_sig in enumerate(orig_sig_list):
            if disjunct_sig.contains_pulse_bug(target_bug):
                buggy_signature_idxes.append(idx)

        assert len(buggy_signature_idxes) > 0

        ok_disjunct_sigs = [
            sig
            for idx, sig in enumerate(orig_sig_list)
            if idx not in buggy_signature_idxes
        ]
        # there can actually be more than one buggy disjuncts corresponding to the
        # same target bug; for simplicity we only use one of them now
        buggy_disjunct_sig = orig_sig_list[buggy_signature_idxes[0]]

        entire_state_changed_for_buggy_disjunct = True
        partial_state_changed_for_buggy_disjunct = False
        state_changed_for_ok_disjuncts = False

        # (1) check whether the original buggy disjunct has changed
        # the buggy disjunct has changed entirely, if no (label, set) in new signatures can match
        #     the buggy disjunct
        # the buggy disjunct has changed partially, if there is at least a (label, set) in new signatures
        #     that can match the buggy disjunct, but the formula implication only happens in
        #     one direction (the matched disjunct formula is strictly smaller)
        for this_dis_sig in new_sig_list:
            label_sets_match = this_dis_sig.is_label_text_start_and_sets_equal(
                buggy_disjunct_sig
            )
            if label_sets_match:
                # firstly, the criteria for "entirely changed" has failed
                entire_state_changed_for_buggy_disjunct = False
                # check whether the formula implication is one-directional
                this_disjunct_smaller_than_buggy = SmtFormula.check_strictly_smaller(
                    this_dis_sig.formula, buggy_disjunct_sig.formula
                )
                if this_disjunct_smaller_than_buggy:
                    partial_state_changed_for_buggy_disjunct = True

            # if we found the condition for both, dont waste time checking other disjuncts
            if (
                not entire_state_changed_for_buggy_disjunct
                and partial_state_changed_for_buggy_disjunct
            ):
                break

        for orig_ok_dis_sig in ok_disjunct_sigs:
            # (2) for original ok disjunct, check whether any of them has been changed
            # to check whether one original ok disjunct has changed, we first match its (label, set)
            # with the new signatures.
            # If there is no match, this original ok disjunct has been changed.
            # If there are some matches, but for all matches, the formulas are not equivalent, then
            #    this original ok disjunct has been changed.
            matched_new_disjunct_idxes = [
                idx
                for idx, this_dis_sig in enumerate(new_sig_list)
                if orig_ok_dis_sig.is_label_text_start_and_sets_equal(this_dis_sig)
            ]
            if not matched_new_disjunct_idxes:
                # this original ok disjunct does not match to anything => it has been changed
                state_changed_for_ok_disjuncts = True
                break
            # this original ok disjunct match to something, now check whether the formula is equivalent
            matched_new_dis_sigs = [
                new_sig_list[idx] for idx in matched_new_disjunct_idxes
            ]
            any_dis_with_equiv_formula = any(
                [
                    SmtFormula.check_equivalence(
                        matched_new_dis_sig.formula, orig_ok_dis_sig.formula
                    )
                    for matched_new_dis_sig in matched_new_dis_sigs
                ]
            )
            if not any_dis_with_equiv_formula:
                state_changed_for_ok_disjuncts = True
                break

        should_big_increase = entire_state_changed_for_buggy_disjunct and (
            not state_changed_for_ok_disjuncts
        )
        should_small_increase = partial_state_changed_for_buggy_disjunct and (
            not state_changed_for_ok_disjuncts
        )
        return should_big_increase, should_small_increase

    def add_new_disjunct_signature(self, disjunct_sig: DisjunctSignature):
        """
        Add a new disjunct signature, while trying to merge it to one of the existing disjunct signatures.
        """
        updated_signatures = []
        did_merge = False
        for sig in self.signatures:
            if disjunct_sig.is_mergable_with(sig):
                merged_sig = disjunct_sig.merge_with(sig)
                updated_signatures.append(merged_sig)
                did_merge = True
            else:
                # not mergable
                updated_signatures.append(sig)

        if not did_merge:
            # could not merge this new one to any of the exsiting ones
            updated_signatures.append(disjunct_sig)

        self.signatures = updated_signatures

    def is_equal(self, other):
        if not isinstance(other, PatchSignature):
            return False
        if len(self.signatures) != len(other.signatures):
            return False
        for s in self.signatures:
            # can't match s with any DisjunctSignature in other
            if not any([s.is_equal(o) for o in other.signatures]):
                return False
        return True

    def __str__(self):
        ret = "PatchSignature: [\n"
        sorted_sigs = sorted(self.signatures, key=lambda s: s.label.text)
        for s in sorted_sigs:
            ret += "\t" + str(s) + ",\n"
        ret += "]"
        return ret

    def __repr__(self):
        return self.__str__()


class Cluster:
    def __init__(self, cluster_name: str, sig: PatchSignature, all_patches_dir: str):
        self.cluster_name: str = cluster_name
        self.sig: PatchSignature = sig
        # (patch_file_path, patch_size)
        self.patches: list[tuple[str, int]] = []
        # keep track whether this cluster is locally good
        self.is_locally_good: bool = False
        # keep track of how probabilities should be updated for patches in this cluster
        self.pe_increment: RewardType = RewardType.NO
        self.ppie_increment: RewardType = RewardType.NO
        # place to store all the patch files
        self.cluster_dir = os.path.join(all_patches_dir, cluster_name)
        os.makedirs(self.cluster_dir)

    def add_patch(self, patch_file_path: str, patch_size: int):
        """
        Assume patch_file_path is arbitrary. We will move it to the cluster dir.
        """
        shutil.move(patch_file_path, self.cluster_dir)
        new_file_path = os.path.join(
            self.cluster_dir, os.path.basename(patch_file_path)
        )
        self.patches.append((new_file_path, patch_size))

    def compute_rewards_and_local_goodness(self):
        assert values.TARGET_BUG is not None
        assert values.TARGET_BUG_SIG is not None

        this_sig_list: list[DisjunctSignature] = self.sig.signatures
        target_sig_list: list[DisjunctSignature] = values.TARGET_BUG_SIG.signatures

        target_sig_list, this_sig_list = PatchSignature.remove_similar_buggy_disjuncts(
            target_sig_list, this_sig_list, values.TARGET_BUG
        )

        big_pe, small_pe = PatchSignature.should_big_or_small_increase_pe(
            target_sig_list, this_sig_list, values.TARGET_BUG
        )
        if big_pe:
            self.pe_increment = RewardType.BIG
        elif small_pe:
            self.pe_increment = RewardType.SMALL

        big_ppie, small_ppie = PatchSignature.should_big_or_small_increase_ppie(
            target_sig_list, this_sig_list, values.TARGET_BUG
        )
        if big_ppie:
            self.ppie_increment = RewardType.BIG
        elif small_ppie:
            self.ppie_increment = RewardType.SMALL

        emitter.information(f"pe_increment: {self.pe_increment}")
        emitter.information(f"ppie_increment: {self.ppie_increment}")

        if self.pe_increment != RewardType.NO and self.ppie_increment == RewardType.BIG:
            self.is_locally_good = True

    def get_num_patches(self):
        return len(self.patches)

    def __str__(self):
        ret = self.cluster_name + " : "
        if self.is_locally_good:
            ret += "GOOD, "
        else:
            ret += "BAD, "
        ret += f"pe_incre: {self.pe_increment}" + ", "
        ret += f"ppie_incre: {self.ppie_increment}" + ", "
        ret += str(self.sig) + " =>\n[\n"
        for path, size in self.patches:
            if self.is_locally_good:
                ret += "\tPlausible Patch: " + path + " (size:" + str(size) + "),\n"
            else:
                ret += "\t" + path + " (size:" + str(size) + "),\n"
        ret += "]\n"
        return ret


class ClusterManager:
    def __init__(self, patch_dir: str, cluster_name_prefix: str):
        # this is where patch clusters should be stored
        self.patch_dir = patch_dir
        if not os.path.isdir(self.patch_dir):
            os.makedirs(self.patch_dir)
        # clusters have names; to differentiate different manager, their
        # name prefix is determined by manager
        self.cluster_name_prefix = cluster_name_prefix
        # since we dont want to maintain hashvalues for Signatures,
        # instead of using a dict, we use a list of tuples
        # [ ..., (PatchSignature, [patch_file_paths]), ... ]
        self.clusters: list[Cluster] = []
        # a special cluster for non-compilable patches( List[str] )
        self.noncompilable_cluster = []

    @staticmethod
    def get_patch_sig_from_summary(infer_summary_file_path: str) -> PatchSignature:
        """
        Helper method.
        """
        with open(infer_summary_file_path) as f:
            infer_summary_json = json.load(f)

        patch_signature = PatchSignature()

        for disjunct_json in infer_summary_json:
            parser = PulseDisjunctParser(disjunct_json)
            (
                label_text,
                label_start_line,
                label_end_line,
                allocated,
                deallocated,
                formula,
                return_formula,
            ) = parser.parse_disjunct()
            label = DisjunctLabel(label_text, label_start_line, label_end_line)
            disjunct_signature = DisjunctSignature(
                label, allocated, deallocated, return_formula, formula
            )
            patch_signature.add_new_disjunct_signature(disjunct_signature)

        return patch_signature

    def add_new_noncompilable_patch(self, patch_file_path):
        noncomp_dir = os.path.join(self.patch_dir, "non-compilable")
        if not os.path.isdir(noncomp_dir):
            os.makedirs(noncomp_dir)
        shutil.move(patch_file_path, noncomp_dir)
        new_file_path = os.path.join(noncomp_dir, os.path.basename(patch_file_path))
        self.noncompilable_cluster.append(new_file_path)

    def add_new_patch(
        self, patch_file_path: str, patch_size: int, infer_summary_file_path: str
    ) -> Cluster:
        """
        Add a new patch to one of the clusters, based on the content of infer summary.
        :return: The cluster where this new patch is added to.
        """
        utilities.global_timer.start(definitions.DURATION_PATCH_SIGN_GEN)
        patch_signature = ClusterManager.get_patch_sig_from_summary(
            infer_summary_file_path
        )
        utilities.global_timer.pause(definitions.DURATION_PATCH_SIGN_GEN)
        # put patch signature into one of the clusters
        matched_cluster_idx = -1
        for idx, cluster in enumerate(self.clusters):
            if cluster.sig.is_equal(patch_signature):
                matched_cluster_idx = idx
                break

        final_cluster = None
        if matched_cluster_idx == -1:
            # not matched to any existing cluster
            new_cluster_id = len(self.clusters)
            new_cluster_name = (
                "cluster-" + self.cluster_name_prefix + "-" + str(new_cluster_id)
            )
            new_cluster = Cluster(new_cluster_name, patch_signature, self.patch_dir)
            emitter.information(f"Created new cluster {new_cluster_name}")
            emitter.information("Cluster signature: " + str(patch_signature))
            new_cluster.add_patch(patch_file_path, patch_size)
            # when creating a new cluster, compute how probability should be updated
            new_cluster.compute_rewards_and_local_goodness()
            # done; add this cluster to our collection
            self.clusters.append(new_cluster)
            final_cluster = new_cluster
        else:
            # matched - add this patch path to the existing cluster
            self.clusters[matched_cluster_idx].add_patch(patch_file_path, patch_size)
            final_cluster = self.clusters[matched_cluster_idx]

        is_patch_locally_good = final_cluster.is_locally_good
        if is_patch_locally_good:
            time_elapsed = utilities.global_timer.get_elapsed_from_overall_start()
            emitter.information(
                "Found a locally good patch after "
                + format(time_elapsed, ".3f")
                + "s from starting tool"
            )
            result.found_new_locally_plausible_patch(time_elapsed)

        return final_cluster

    def get_total_num_patches(self):
        count = 0
        for cluster in self.clusters:
            count += cluster.get_num_patches()
        count += len(self.noncompilable_cluster)
        return count

    def get_num_clusters(self):
        res = len(self.clusters)
        if self.noncompilable_cluster:
            res = res + 1
        return res

    def get_average_num_patches_per_cluster(self) -> float:
        num_patches = self.get_total_num_patches()
        num_clusters = self.get_num_clusters()
        return num_patches / num_clusters

    def __str__(self):
        ret = "\nNormal clusters: [\n"
        for cluster in self.clusters:
            ret += str(cluster)
        ret += "]\n\n"

        ret += "Non-compilable cluster: [\n"
        for path in self.noncompilable_cluster:
            ret += "\t" + path + ",\n"
        ret += "]\n"
        return ret
