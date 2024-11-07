/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/labels
 */


import cpp

string target_function() { result = HOLDER_FUNC }

predicate is_target_function(Function func) {
    func.getName() = target_function()
}

predicate is_label_in_func(LabelStmt ls, Function func) {
    ls.getEnclosingFunction() = func and
    ls.isNamed()
}

string print_ls(LabelStmt ls) {
    result = ls.getName()
}

from Function target_func, LabelStmt ls
where is_target_function(target_func) and
    is_label_in_func(ls, target_func)
select ls, print_ls(ls)
