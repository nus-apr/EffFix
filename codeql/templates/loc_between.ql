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

/* line where the bug happens */
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

from Stmt start_stmt, Stmt end_stmt, Stmt target_stmt
where
  isStartStmt(start_stmt) and
  isEndStmt(end_stmt) and
  is_in_target_func(target_stmt) and
  start_stmt = ancestorOf(target_stmt) and
  (
    target_stmt = end_stmt or
    target_stmt = ancestorOf(end_stmt)
  )
select target_stmt, target_stmt.getLocation().getStartLine().toString()
