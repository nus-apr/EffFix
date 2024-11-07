/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/loc-after
 */

import cpp
import semmle.code.cpp.commons.Dependency
import semmle.code.cpp.Function
import semmle.code.cpp.controlflow.StackVariableReachability
import semmle.code.cpp.dataflow.TaintTracking

string target_function() { result = HOLDER_FUNC }

/* line where the target variable is initialized. */
int trace_start_line() { result = HOLDER_START_LINE }

int trace_end_line() { result = HOLDER_END_LINE }

predicate is_target_func(Function func) { func.getName() = target_function() }

predicate is_in_target_func(Stmt stmt) {
  exists(Function func |
    is_target_func(func) and
    stmt.getEnclosingFunction() = func
  )
}

predicate isStartStmt(Stmt stmt) {
  exists(Location loc |
    is_in_target_func(stmt) and
    loc = stmt.getLocation() and
    loc.getStartLine() = trace_start_line()
  )
}

predicate isEndStmt(Stmt stmt) {
  exists(Location loc |
    is_in_target_func(stmt) and
    loc = stmt.getLocation() and
    loc.getStartLine() = trace_end_line()
  )
}

Stmt ancestorOf(Stmt stmt) {
  result = stmt.getAPredecessor().getEnclosingStmt()
  or
  result = ancestorOf(stmt.getAPredecessor().getEnclosingStmt())
}

/** When the faulty point (last access) is a `default` case in switch,
 * Infer wrongly reports the location to be some other case labels. Thus, the statements under
 * the reported case would not be ancestors of the statements in the default case.
 */
predicate isSiblingStmtInSwitchCase(Stmt stmt_one, Stmt stmt_two) {
  stmt_one instanceof SwitchCase and
  exists(SwitchStmt switchStmt, SwitchCase someCase |
    stmt_one.(SwitchCase).getSwitchStmt() = switchStmt and
    someCase = switchStmt.getASwitchCase() and
    stmt_two = someCase.getAStmt()
  )
}

from Stmt start_stmt, Stmt end_stmt, Stmt target_stmt
where
  isStartStmt(start_stmt) and
  isEndStmt(end_stmt) and
  is_in_target_func(target_stmt) and
  start_stmt = ancestorOf(target_stmt) and
  (
    target_stmt = end_stmt or
    end_stmt = ancestorOf(target_stmt) or
    // end_stmt is a switch case label, we allow everything in that switch statement
    // to be returned
    isSiblingStmtInSwitchCase(end_stmt, target_stmt)
  )
select target_stmt, target_stmt.getLocation().getStartLine().toString()
