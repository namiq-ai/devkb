# Truth corrections for the C# value report

**Outcome.** The hand check below found that the compiler truth recorded calls only, not property reads; a second
look at the regenerated truth found that it merged same-named types of two assemblies (Polly and Polly.Core both
declare `Polly.CircuitBreaker.CircuitStateController<T>`). Both are fixed in `bench/roslyn_truth/Program.cs` (property
and indexer accesses are edges to the accessor; method groups are recorded as `delegates` and followed like dispatch;
ids carry the assembly) and the truth regenerated (`cs-truth` run 44015588074). `questions.json` now holds that truth.

What the regenerated truth says about the names traced by hand below: on EF Core, `AddEntry`, `BatchCommands`,
`CreateCommandBatches`, `PropagateResults`, `PropagateOutputParameters` are right (static); 24 others, `SaveChanges`
and the SQL generators among them, reach the target through `IReadOnlyModificationCommand.ColumnModifications`
(dispatch: neither right nor wrong, the truth's existing rule); `TryCreateDependentKeyValue` likewise; `IsModified` is
wrong. Only names the tool still cannot judge stay as `uncertain_by_hand` (listed at the end).

`score(..., compiler_only=True)` ignores `uncertain_by_hand`.

## EF Core `ModificationCommand.GetTableMapping` (pinned `8859f78f10`)

The compiler truth has 9 names and stops at four properties whose getters reach the target:
`ModificationCommand.ColumnModifications` (getter → `GenerateColumnModifications` → `GetTableMapping`) and
`IsOptionalSplitFragment`, `IsOptionalSplitFragmentRowAssumedAbsent`, `IsOptionalSplitFragmentPayloadAllNull`
(`ModificationCommand.cs` lines 101–130). `ModificationCommand` is the only production class implementing
`IReadOnlyModificationCommand`, so a read through the interface reaches it too.

Every name an agent listed that the compiler truth did not hold was traced with `bench/cs_reach_text.py` and each path
read in the source. Added as right (29):

```
AddEntry: Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
AddParameters: Update.ReaderModificationCommandBatch.AddParameters [ReaderModificationCommandBatch.cs:266] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AddSeedData: Migrations.Internal.MigrationsModelDiffer.AddSeedData [MigrationsModelDiffer.cs:1892] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AddUnchangedSharingEntries: Update.Internal.CommandBatchPreparer.AddUnchangedSharingEntries [CommandBatchPreparer.cs:334] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
AppendDeleteAndSelectOperation: Update.UpdateAndSelectSqlGenerator.AppendDeleteAndSelectOperation [UpdateAndSelectSqlGenerator.cs:149] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendDeleteReturningOperation: Update.UpdateSqlGenerator.AppendDeleteReturningOperation [UpdateSqlGenerator.cs:167] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendInsertAndSelectOperation: Update.UpdateAndSelectSqlGenerator.AppendInsertAndSelectOperation [UpdateAndSelectSqlGenerator.cs:57] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendInsertOperation: SqlServer.Update.Internal.SqlServerUpdateSqlGenerator.AppendInsertOperation [SqlServerUpdateSqlGenerator.cs:43] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendInsertReturningOperation: Update.UpdateSqlGenerator.AppendInsertReturningOperation [UpdateSqlGenerator.cs:73] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendStoredProcedureCall: SqlServer.Update.Internal.SqlServerUpdateSqlGenerator.AppendStoredProcedureCall [SqlServerUpdateSqlGenerator.cs:592] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendUpdateAndSelectOperation: Update.UpdateAndSelectSqlGenerator.AppendUpdateAndSelectOperation [UpdateAndSelectSqlGenerator.cs:103] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
AppendUpdateReturningOperation: Update.UpdateSqlGenerator.AppendUpdateReturningOperation [UpdateSqlGenerator.cs:117] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
BatchCommands: Update.Internal.CommandBatchPreparer.BatchCommands [CommandBatchPreparer.cs:63] -> Update.Internal.CommandBatchPreparer.CreateModificationCommands [CommandBatchPreparer.cs:221] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
Compare: Update.Internal.ModificationCommandComparer.Compare [ModificationCommandComparer.cs:20] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
CreateModificationCommands: Update.Internal.CommandBatchPreparer.CreateModificationCommands [CommandBatchPreparer.cs:221] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
PropagateOutputParameters: Update.ModificationCommand.PropagateOutputParameters [ModificationCommand.cs:1296] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
PropagateResults: Update.ModificationCommand.PropagateResults [ModificationCommand.cs:1236] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
Consume: Update.AffectedCountModificationCommandBatch.Consume [AffectedCountModificationCommandBatch.cs:34] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
ConsumeAsync: Update.AffectedCountModificationCommandBatch.ConsumeAsync [AffectedCountModificationCommandBatch.cs:153] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
CreateCurrentValueGetter: Update.Internal.ColumnAccessorsFactory.CreateCurrentValueGetter [ColumnAccessorsFactory.cs:39] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
CreateOriginalValueGetter: Update.Internal.ColumnAccessorsFactory.CreateOriginalValueGetter [ColumnAccessorsFactory.cs:81] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
DiffData: Migrations.Internal.MigrationsModelDiffer.DiffData [MigrationsModelDiffer.cs:2150] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
GetDataOperations: Migrations.Internal.MigrationsModelDiffer.GetDataOperations [MigrationsModelDiffer.cs:2343] -> Migrations.Internal.MigrationsModelDiffer.DiffData [MigrationsModelDiffer.cs:2150] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
IsValid: SqlServer.Update.Internal.SqlServerModificationCommandBatch.IsValid [SqlServerModificationCommandBatch.cs:72] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
ParameterCount: Update.AffectedCountModificationCommandBatch.ParameterCount [AffectedCountModificationCommandBatch.cs:479] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
ProcessEntry: Update.Internal.CommandBatchPreparer.CreateModificationCommands.ProcessEntry [CommandBatchPreparer.cs:279] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
RollbackLastCommand: Update.ReaderModificationCommandBatch.RollbackLastCommand [ReaderModificationCommandBatch.cs:134] -> Update.ModificationCommand.ColumnModifications [ModificationCommand.cs:134] -> Update.ModificationCommand.GenerateColumnModifications [ModificationCommand.cs:294] -> GetTableMapping
SaveChanges: Storage.RelationalDatabase.SaveChanges [RelationalDatabase.cs:53] -> Update.Internal.CommandBatchPreparer.BatchCommands [CommandBatchPreparer.cs:63] -> Update.Internal.CommandBatchPreparer.CreateModificationCommands [CommandBatchPreparer.cs:221] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
SaveChangesAsync: Storage.RelationalDatabase.SaveChangesAsync [RelationalDatabase.cs:74] -> Update.Internal.CommandBatchPreparer.BatchCommands [CommandBatchPreparer.cs:63] -> Update.Internal.CommandBatchPreparer.CreateModificationCommands [CommandBatchPreparer.cs:221] -> Update.ModificationCommand.AddEntry [ModificationCommand.cs:155] -> Update.ModificationCommand.IsOptionalSplitFragmentRowAssumedAbsent [ModificationCommand.cs:111] -> GetTableMapping
```

Checked by hand: `ModificationCommand.PropagateResults` (line 1236) reads `ColumnModifications` at line 1240;
`ModificationCommand.AddEntry` (lines 155–225) reads `IsOptionalSplitFragmentRowAssumedAbsent` at line 204;
`SqlServerUpdateSqlGenerator.AppendStoredProcedureCall` reads `command.ColumnModifications` at lines 627 and 651 (the
tracer's first hit was a comment on line 650; the reads hold).

Neither right nor wrong: `ModificationCommandComparer`, `UpdateSqlGenerator` (type names; a property shares each name,
so the method-name filter let them through). **Still wrong**: `IsModified` (the target's caller calls it: a callee),
and `CreateCommandBatches`, `TryCreateDependentKeyValue` (no path found; not proven either way, counted wrong).

## Polly `CircuitStateController.EnsureNotDisposed` (pinned)

`CircuitBreakerManualControl.CloseAsync`, `IsolateAsync` and `Initialize` invoke callbacks that
`CircuitBreakerResilienceStrategy` (lines 20–21) registers as method groups: `_controller.IsolateCircuitAsync`,
`_controller.CloseCircuitAsync`, both in the truth. They reach the target at run time, like interface dispatch, which
the compiler truth already scores as neither right nor wrong; these are scored the same way.

## Polly `ComponentDisposeHelper.ThrowDisposed` (pinned)

`DisposeHelper` is a property of `ResiliencePipeline` (the helper instance, `DisposeHelper.EnsureNotDisposed()`), not
a method: neither right nor wrong. `DisposeAsync`, `ForceDisposeAsync`, `TryDisposeSafeAsync` stay wrong (they do not
reach `ThrowDisposed`).

## Not corrected

FluentValidation: `ChildRules`, `SetValidator`, `SetDisplayName`, `RuleForEach` configure rules whose lambdas run
later; they do not reach `GetFromNonGenericContext` themselves and stay wrong.

## Still by hand (`uncertain_by_hand`)

| Question | Names | Why the tool cannot judge them |
|---|---|---|
| EF Core `GetTableMapping` | `ModificationCommandComparer`, `UpdateSqlGenerator` | type names a property shares, not methods |
| EF Core `GetTableMapping` | `IsValid` | `SqlServerModificationCommandBatch.IsValid` reads `ColumnModifications` through the interface (dispatch) but is in EFCore.SqlServer, which the truth job does not compile |
| Polly `EnsureNotDisposed` | `CloseAsync`, `IsolateAsync`, `Initialize` | they invoke the callbacks the strategy registers; `delegates` records who registers a method group, not who invokes the delegate field |
| Polly `ThrowDisposed` | `DisposeHelper` | a property, not a method |

## Known convention

A call or property read inside a lambda belongs to the member that creates the lambda (as in devkb's graph). On Polly
`EnsureNotDisposed` this puts the strategy constructor, `CreateStrategy` and `AddCircuitBreaker` in the truth
(`stateProvider?.Initialize(() => _controller.CircuitState)`), though the lambda runs later.
