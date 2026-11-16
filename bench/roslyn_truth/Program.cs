// Compiler truth for the C# benchmarks: every method, constructor, accessor and local function the compiler sees in
// a repository, and every call between them as Roslyn's semantic model binds it.
//
//   dotnet run -- REPO_ROOT OUT.json PROJECT.csproj...
//
// Output (the shape of the C/C++ libclang truth): {"defs": {id: [file, line_start, line_end, "Type.Method"]},
// "edges": [[caller_id, callee_id]], "dispatch": [[implementation_id, base_or_interface_id]], "errors": {project: n},
// "failures": [...], "resolved": n, "unresolved": n}. Only calls whose target is defined in the repository are edges;
// a call inside a lambda belongs to the member that contains the lambda (as in devkb). Static binding: a call through
// an interface or virtual method is an edge to that declaration; `dispatch` lists who implements or overrides what.
using System.Text.Json;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.MSBuild;

MSBuildLocator.RegisterDefaults();
return await Truth.Run(args);

static class Truth
{
    public static async Task<int> Run(string[] args)
    {
        var root = Path.GetFullPath(args[0]).TrimEnd('/') + "/";
        var outPath = args[1];
        var failures = new List<string>();
        using var ws = MSBuildWorkspace.Create(new Dictionary<string, string>
            { ["Configuration"] = "Debug", ["RunAnalyzers"] = "false", ["TreatWarningsAsErrors"] = "false" });
        ws.RegisterWorkspaceFailedHandler(e => { if (failures.Count < 300) failures.Add(e.Diagnostic.Message); });
        foreach (var p in args.Skip(2))
        {
            var full = Path.GetFullPath(Path.Combine(root, p));
            if (ws.CurrentSolution.Projects.Any(x => string.Equals(x.FilePath, full, StringComparison.OrdinalIgnoreCase)))
                continue;
            try { await ws.OpenProjectAsync(full); }
            catch (Exception ex) { failures.Add($"{p}: {ex.Message}"); }
        }

        var defs = new Dictionary<string, object[]>();
        var edges = new HashSet<(string, string)>();
        var dispatch = new HashSet<(string, string)>();
        var errors = new Dictionary<string, int>();
        var done = new HashSet<string>();                  // file + defining symbol set: multi-targeting repeats files
        long resolved = 0, unresolved = 0;
        foreach (var project in ws.CurrentSolution.Projects)
        {
            var comp = await project.GetCompilationAsync();
            if (comp is null) continue;
            errors[project.Name] = comp.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error);
            foreach (var tree in comp.SyntaxTrees)
            {
                var path = tree.FilePath;
                if (string.IsNullOrEmpty(path) || !path.StartsWith(root)) continue;
                var rel = Path.GetRelativePath(root, path).Replace('\\', '/');
                if (rel.Contains("/obj/") || rel.StartsWith("obj/") || rel.Contains("/bin/")) continue;
                if (!done.Add(rel + "|" + project.AssemblyName)) continue;
                var model = comp.GetSemanticModel(tree);
                foreach (var node in (await tree.GetRootAsync()).DescendantNodes())
                {
                    if (node is BaseMethodDeclarationSyntax or LocalFunctionStatementSyntax or AccessorDeclarationSyntax
                        or PropertyDeclarationSyntax or IndexerDeclarationSyntax)
                    {
                        foreach (var sym in Declared(model, node))
                        {
                            var span = tree.GetLineSpan(node.Span);
                            defs[Id(sym)] = new object[] { rel, span.StartLinePosition.Line + 1,
                                                           span.EndLinePosition.Line + 1, Qn(sym) };
                            if (sym.OverriddenMethod is { } ov && ov.Locations.Any(l => l.IsInSource))
                                dispatch.Add((Id(sym), Id(ov.OriginalDefinition)));
                            foreach (var iface in sym.ContainingType?.AllInterfaces ?? Enumerable.Empty<INamedTypeSymbol>())
                                foreach (var im in iface.GetMembers().OfType<IMethodSymbol>())
                                    if (SymbolEqualityComparer.Default.Equals(
                                            sym.ContainingType!.FindImplementationForInterfaceMember(im), sym)
                                        && im.Locations.Any(l => l.IsInSource))
                                        dispatch.Add((Id(sym), Id(im.OriginalDefinition)));
                        }
                    }
                    if (node is not (InvocationExpressionSyntax or BaseObjectCreationExpressionSyntax
                        or ConstructorInitializerSyntax)) continue;
                    var info = model.GetSymbolInfo(node);
                    var callee = (info.Symbol ?? (info.CandidateSymbols.Length == 1 ? info.CandidateSymbols[0] : null))
                        as IMethodSymbol;
                    if (callee is null) { unresolved++; continue; }
                    resolved++;
                    callee = (callee.ReducedFrom ?? callee).OriginalDefinition;
                    if (!callee.Locations.Any(l => l.IsInSource)) continue;          // defined outside the repository
                    var caller = Enclosing(node, model);
                    if (caller is not null) edges.Add((Id(caller), Id(callee)));
                }
            }
        }
        var json = new Dictionary<string, object>
        {
            ["defs"] = defs,
            ["edges"] = edges.Select(e => new[] { e.Item1, e.Item2 }).ToList(),
            ["dispatch"] = dispatch.Select(e => new[] { e.Item1, e.Item2 }).ToList(),
            ["errors"] = errors, ["failures"] = failures, ["resolved"] = resolved, ["unresolved"] = unresolved,
            ["projects"] = ws.CurrentSolution.Projects.Select(p => p.Name).ToList(),
        };
        await File.WriteAllTextAsync(outPath, JsonSerializer.Serialize(json));
        Console.WriteLine($"projects {ws.CurrentSolution.Projects.Count()} defs {defs.Count} edges {edges.Count} " +
                          $"dispatch {dispatch.Count} resolved {resolved} unresolved {unresolved} " +
                          $"compile errors {errors.Values.Sum()} workspace failures {failures.Count}");
        return 0;
    }

    static IEnumerable<IMethodSymbol> Declared(SemanticModel model, SyntaxNode node)
    {
        var s = model.GetDeclaredSymbol(node);
        if (s is IMethodSymbol m) { yield return m; yield break; }
        // an expression-bodied property or indexer (`int X => ...;`) has no accessor syntax: its getter is the method
        if (s is IPropertySymbol p && node is BasePropertyDeclarationSyntax bp && bp.AccessorList is null && p.GetMethod is { } g)
            yield return g;
    }

    static IMethodSymbol? Enclosing(SyntaxNode node, SemanticModel model)
    {
        for (var n = node.Parent; n is not null; n = n.Parent)
        {
            switch (n)
            {
                case LocalFunctionStatementSyntax or BaseMethodDeclarationSyntax or AccessorDeclarationSyntax:
                    return model.GetDeclaredSymbol(n) as IMethodSymbol;
                case PropertyDeclarationSyntax or IndexerDeclarationSyntax:
                    return Declared(model, n).FirstOrDefault();
                case TypeDeclarationSyntax:
                    return null;                            // a field or property initializer: no enclosing method
            }
        }
        return null;
    }

    static string Id(IMethodSymbol m)
    {
        var id = m.OriginalDefinition.GetDocumentationCommentId();
        if (!string.IsNullOrEmpty(id) && m.MethodKind != MethodKind.LocalFunction) return id;
        var loc = m.Locations.FirstOrDefault(l => l.IsInSource);
        return m.ToDisplayString() + "@" + (loc is null ? "" : loc.SourceTree!.FilePath + ":" + loc.SourceSpan.Start);
    }

    static string Qn(IMethodSymbol m)
    {
        if (m.MethodKind == MethodKind.LocalFunction && m.ContainingSymbol is IMethodSymbol outer)
            return Qn(outer) + "." + m.Name;
        var name = m.MethodKind switch
        {
            MethodKind.Constructor or MethodKind.StaticConstructor => "ctor",
            MethodKind.PropertyGet or MethodKind.PropertySet => (m.AssociatedSymbol?.Name ?? m.Name),
            _ => m.Name,
        };
        return (m.ContainingType?.Name ?? "") + "." + name;
    }
}
