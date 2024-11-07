/**
 * @kind problem
 * @problem.severity warning
 * @id cpp/patch-ingredients
 */

import cpp
import semmle.code.cpp.commons.Dependency
import semmle.code.cpp.Function
import semmle.code.cpp.controlflow.StackVariableReachability
import semmle.code.cpp.dataflow.TaintTracking


// HOLDER_FILE should only contain the base name
string target_file() { result = HOLDER_FILE }

string target_function() { result = HOLDER_FUNC }

/* line where the target variable is initialized. */
int taint_src_line() { result = HOLDER_START_LINE }

/* line where the fix location is. */
int fix_line() { result = HOLDER_FIX_LINE }

predicate is_target_file(File file) {
  file.getBaseName() = target_file()
}

predicate is_target_func(Function func) {
  func.getName() = target_function() and
  is_target_file(func.getFile())
}

predicate isTaintSrcLocation(Location loc) {
  exists(Function func |
    is_target_func(func) and
    loc.getFile() = func.getFile() and
    loc.getStartLine() = taint_src_line()
  )
}

predicate isFixLocation(Location loc) {
  exists(Function func |
    is_target_func(func) and
    loc.getFile() = func.getFile() and
    loc.getStartLine() = fix_line()
  )
}

predicate isFixLocationStmt(Stmt stmt) {
  exists(Location loc |
    isFixLocation(loc) and
    loc = stmt.getLocation()
  )
}

Stmt ancestorOf(Stmt stmt) {
  result = stmt.getAPredecessor().getEnclosingStmt()
  or
  result = ancestorOf(stmt.getAPredecessor().getEnclosingStmt())
}

predicate ancestorOfFixLoc(Stmt stmt) {
  exists(Stmt fixLocStmt |
    isFixLocationStmt(fixLocStmt) and
    stmt = ancestorOf(fixLocStmt)
  )
}

predicate isAccessInTargetFunction(VariableAccess node) {
    exists(Function func |
        is_target_func(func) and
        node.getEnclosingFunction() = func
    )
}

predicate isDeclarationSource(Expr expr) {
  // expr is a variable access, whose target is the declaraction on taint src line
  exists(LocalVariable var |
    is_target_func(var.getFunction()) and
    isTaintSrcLocation(var.getDefinitionLocation()) and
    var = expr.(VariableAccess).getTarget()
  )
}

predicate isExprSource(Expr expr) {
  // expr is the lhs of an assignment statement, which is on the taint src line
  exists(Stmt stmt |
    isTaintSrcLocation(expr.getLocation()) and
    stmt = expr.getEnclosingStmt() and
    ancestorOfFixLoc(stmt) and
    // node is lhs of assign statement
    expr = ((stmt.(ExprStmt)).getExpr()).(AssignExpr).getLValue()
  )
}


predicate isExprSink(Expr node) {
    isAccessInTargetFunction(node.(VariableAccess)) and
    // isPredessesorOfFixLoc(node.getBasicBlock())
    ( ancestorOfFixLoc(node.getEnclosingStmt()) or
    isFixLocationStmt(node.getEnclosingStmt()) )
}

class TaintTrackingConfiguration extends TaintTracking::Configuration {
  TaintTrackingConfiguration() { this = "TaintTrackingConfiguration" }

  override predicate isSource(DataFlow::Node node) {
    isExprSource(node.asExpr()) or isDeclarationSource(node.asExpr())
  }

  override predicate isSink(DataFlow::Node node) { isExprSink(node.asExpr()) }

  override predicate isAdditionalTaintStep(DataFlow::Node node1, DataFlow::Node node2) {
    exists(VariableAccess va1, VariableAccess va2, Stmt stmt1, Stmt stmt2 |
      va1 = node1.asExpr() and
      va2 = node2.asExpr() and
      va1.getEnclosingFunction() = va2.getEnclosingFunction() and
      stmt1 = va1.getEnclosingStmt() and
      stmt2 = va2.getEnclosingStmt() and
      (
        // (1) referring to the same variable
        va1.getTarget() = va2.getTarget()
        // (2) they appear in the same statement, but this statement should not be
        //     the taint src. (Since LHS of taint src is where the taint starts, and
        //     we dont want the RHS there.)
        or (
          (stmt1 = stmt2) and not isTaintSrcLocation(stmt1.getLocation())
        )
      )
    )
  }
}


string expandPointerFieldAccess(PointerFieldAccess fa) {
  if not (fa.getQualifier() instanceof PointerFieldAccess) then
    result = fa.getQualifier().toString() + "->" + fa.toString()
  else
    result = expandPointerFieldAccess(fa.getQualifier()) + "->" + fa.toString()
}

string expandPointerOrDotFieldAccess(VariableAccess fa) {
  if fa.getQualifier() instanceof PointerFieldAccess or fa.getQualifier() instanceof DotFieldAccess then
    // can still expand
    if fa instanceof PointerFieldAccess then
      result = expandPointerOrDotFieldAccess(fa.getQualifier()) + "->" + fa.toString()
    else // fa instance of DotFieldAccess
      result = expandPointerOrDotFieldAccess(fa.getQualifier()) + "." + fa.toString()
  else
  if fa instanceof PointerFieldAccess then
    result = fa.getQualifier().toString() + "->" + fa.toString()
  else // fa instance of DotFieldAccess
    result = fa.getQualifier().toString() + "." + fa.toString()
}

string getStringFromAccess(VariableAccess va) {
  if va instanceof PointerFieldAccess or va instanceof DotFieldAccess
  then result = expandPointerOrDotFieldAccess(va)
  else result = va.toString()
}

predicate is_va_arith_type(VariableAccess va) {
  va.getUnspecifiedType() instanceof ArithmeticType
}

predicate is_va_pointer_type(VariableAccess va) {
  va.getUnspecifiedType() instanceof PointerType
}

predicate is_va_pointer_or_arith_type(VariableAccess va) {
  is_va_arith_type(va) or is_va_pointer_type(va)
}

string getFinalOutput(VariableAccess va) {
  if is_va_pointer_type(va)
  then result = "pointer(" + getStringFromAccess(va) + ")"
  else result = "non-pointer(" + getStringFromAccess(va) + ")"
}

from TaintTrackingConfiguration config, Expr src, Expr sink, string s
where
  config.hasFlow(DataFlow::exprNode(src), DataFlow::exprNode(sink)) and
  is_va_pointer_or_arith_type(sink.(VariableAccess)) and
  s = getFinalOutput(sink.(VariableAccess))
select sink, s
