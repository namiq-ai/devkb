"""What the C# extractor knows about .NET's own types, which no repository declares (SPEC-DEVKB-CSHARP-3, F2).

Two facts per type, both from the public .NET API (System.*, Microsoft.Extensions.DependencyInjection.Abstractions):

- BASES: the base class and interfaces, by simple name and without generic arguments, so that an extension method on
  `TextReader` is found for a `StreamReader` receiver and one on `IEnumerable` for a `List<T>`.
- MEMBERS: the instance method names a receiver of that type already has. C# binds an instance method before any
  extension method, so `list.IndexOf(x)` on a `List<T>` is List's own, never an `IndexOf` extension of the repository.

Deliberately small: the types repositories call most. A type that is not here is treated as before (its exact name or
`I` + its name only). Wrong entries would cost precision, so each line is the documented API, nothing inferred.
"""
from __future__ import annotations

_ENUMERABLE = {"IEnumerable"}
_COLLECTION = {"ICollection", "IReadOnlyCollection"} | _ENUMERABLE
_LIST = {"IList", "IReadOnlyList"} | _COLLECTION
_DICT = {"IDictionary", "IReadOnlyDictionary"} | _COLLECTION

BASES: dict[str, set[str]] = {
    "object": set(),
    "string": {"IEnumerable", "IComparable", "IEquatable", "ICloneable", "IConvertible"},
    "String": {"string"},
    "List": _LIST,
    "Collection": _LIST,
    "ObservableCollection": {"Collection"} | _LIST,
    "ReadOnlyCollection": _LIST,
    "Array": _LIST,
    "ImmutableArray": _LIST,
    "ImmutableList": _LIST,
    "Dictionary": _DICT,
    "ConcurrentDictionary": _DICT,
    "SortedDictionary": _DICT,
    "ImmutableDictionary": _DICT,
    "HashSet": {"ISet", "IReadOnlySet"} | _COLLECTION,
    "SortedSet": {"ISet", "IReadOnlySet"} | _COLLECTION,
    "ISet": _COLLECTION,
    "Queue": _COLLECTION,
    "Stack": _COLLECTION,
    "ConcurrentQueue": _COLLECTION,
    "ConcurrentBag": _COLLECTION,
    "IList": _COLLECTION,
    "IReadOnlyList": {"IReadOnlyCollection"} | _ENUMERABLE,
    "ICollection": _ENUMERABLE,
    "IReadOnlyCollection": _ENUMERABLE,
    "IDictionary": _COLLECTION,
    "IReadOnlyDictionary": {"IReadOnlyCollection"} | _ENUMERABLE,
    "IQueryable": _ENUMERABLE,
    "IOrderedQueryable": {"IQueryable"} | _ENUMERABLE,
    "IOrderedEnumerable": _ENUMERABLE,
    "IGrouping": _ENUMERABLE,
    "ILookup": _ENUMERABLE,
    "IAsyncEnumerable": set(),
    "Stream": {"IDisposable", "IAsyncDisposable"},
    "FileStream": {"Stream", "IDisposable", "IAsyncDisposable"},
    "MemoryStream": {"Stream", "IDisposable", "IAsyncDisposable"},
    "BufferedStream": {"Stream", "IDisposable", "IAsyncDisposable"},
    "TextReader": {"IDisposable"},
    "StreamReader": {"TextReader", "IDisposable"},
    "StringReader": {"TextReader", "IDisposable"},
    "TextWriter": {"IDisposable", "IAsyncDisposable"},
    "StreamWriter": {"TextWriter", "IDisposable", "IAsyncDisposable"},
    "StringWriter": {"TextWriter", "IDisposable", "IAsyncDisposable"},
    "XmlReader": {"IDisposable"},
    "XmlWriter": {"IDisposable", "IAsyncDisposable"},
    "Expression": set(),
    "LambdaExpression": {"Expression"},
    "MemberExpression": {"Expression"},
    "MethodCallExpression": {"Expression"},
    "ParameterExpression": {"Expression"},
    "ConstantExpression": {"Expression"},
    "BinaryExpression": {"Expression"},
    "UnaryExpression": {"Expression"},
    "NewExpression": {"Expression"},
    "MemberInfo": {"ICustomAttributeProvider"},
    "Type": {"MemberInfo", "ICustomAttributeProvider", "IReflect"},
    "TypeInfo": {"Type", "MemberInfo", "ICustomAttributeProvider", "IReflect"},
    "MethodBase": {"MemberInfo", "ICustomAttributeProvider"},
    "MethodInfo": {"MethodBase", "MemberInfo", "ICustomAttributeProvider"},
    "ConstructorInfo": {"MethodBase", "MemberInfo", "ICustomAttributeProvider"},
    "PropertyInfo": {"MemberInfo", "ICustomAttributeProvider"},
    "FieldInfo": {"MemberInfo", "ICustomAttributeProvider"},
    "ParameterInfo": {"ICustomAttributeProvider"},
    "Assembly": {"ICustomAttributeProvider"},
    "Exception": {"ISerializable"},
    "ServiceCollection": {"IServiceCollection", "IList", "ICollection", "IEnumerable"},
    "IServiceCollection": {"IList", "ICollection", "IEnumerable"},
    "ClaimsPrincipal": {"IPrincipal"},
    "HttpClient": {"HttpMessageInvoker", "IDisposable"},
    "StringBuilder": {"ISerializable"},
    "CancellationTokenSource": {"IDisposable"},
    "Task": {"IAsyncResult", "IDisposable"},
    # Entity Framework Core, seen from the many repositories that use it (in EF Core itself these are its own types,
    # which take precedence over this table)
    "DbSet": {"IQueryable", "IEnumerable", "IAsyncEnumerable"},
    "DbContext": {"IDisposable", "IAsyncDisposable"},
}

_SEQ = {"GetEnumerator"}
_COLL = _SEQ | {"Add", "Clear", "Contains", "CopyTo", "Remove"}
_LISTM = _COLL | {"IndexOf", "Insert", "RemoveAt"}

MEMBERS: dict[str, set[str]] = {
    "object": {"Equals", "GetHashCode", "GetType", "ToString"},
    "string": {"Contains", "CompareTo", "CopyTo", "EndsWith", "Equals", "GetEnumerator", "IndexOf", "IndexOfAny",
               "Insert", "LastIndexOf", "LastIndexOfAny", "Normalize", "PadLeft", "PadRight", "Remove", "Replace",
               "Split", "StartsWith", "Substring", "ToCharArray", "ToLower", "ToLowerInvariant", "ToUpper",
               "ToUpperInvariant", "Trim", "TrimEnd", "TrimStart", "AsSpan", "AsMemory", "GetHashCode"},
    "List": _LISTM | {"AddRange", "AsReadOnly", "BinarySearch", "ConvertAll", "Exists", "Find", "FindAll",
                      "FindIndex", "FindLast", "FindLastIndex", "ForEach", "GetRange", "InsertRange",
                      "LastIndexOf", "RemoveAll", "RemoveRange", "Reverse", "Sort", "ToArray", "TrimExcess",
                      "TrueForAll", "EnsureCapacity"},
    "Collection": _LISTM,
    "ObservableCollection": _LISTM | {"Move"},
    "ReadOnlyCollection": {"Contains", "CopyTo", "GetEnumerator", "IndexOf"},
    "Array": {"Clone", "CopyTo", "GetEnumerator", "GetLength", "GetLowerBound", "GetUpperBound", "GetValue",
              "Initialize", "SetValue"},
    "ImmutableArray": {"Add", "AddRange", "Contains", "IndexOf", "Insert", "Remove", "RemoveAt", "Replace",
                       "SetItem", "Sort", "ToBuilder", "GetEnumerator", "AsSpan", "CopyTo"},
    "ImmutableList": {"Add", "AddRange", "Clear", "Contains", "Find", "FindAll", "IndexOf", "Insert", "Remove",
                      "RemoveAll", "RemoveAt", "Replace", "SetItem", "Sort", "ToBuilder", "GetEnumerator"},
    "Dictionary": _COLL | {"ContainsKey", "ContainsValue", "EnsureCapacity", "TryAdd", "TryGetValue",
                           "TrimExcess", "GetAlternateLookup"},
    "ConcurrentDictionary": _COLL | {"AddOrUpdate", "ContainsKey", "GetOrAdd", "TryAdd", "TryGetValue",
                                     "TryRemove", "TryUpdate", "ToArray"},
    "SortedDictionary": _COLL | {"ContainsKey", "ContainsValue", "TryGetValue"},
    "ImmutableDictionary": {"Add", "AddRange", "Clear", "ContainsKey", "ContainsValue", "Remove", "RemoveRange",
                            "SetItem", "SetItems", "TryGetValue", "ToBuilder", "GetEnumerator", "Contains"},
    "HashSet": _COLL | {"ExceptWith", "IntersectWith", "IsProperSubsetOf", "IsProperSupersetOf", "IsSubsetOf",
                        "IsSupersetOf", "Overlaps", "RemoveWhere", "SetEquals", "SymmetricExceptWith",
                        "TrimExcess", "TryGetValue", "UnionWith", "EnsureCapacity"},
    "SortedSet": _COLL | {"ExceptWith", "IntersectWith", "IsSubsetOf", "IsSupersetOf", "Overlaps",
                          "RemoveWhere", "Reverse", "SetEquals", "UnionWith", "GetViewBetween"},
    "ISet": _COLL | {"ExceptWith", "IntersectWith", "IsSubsetOf", "IsSupersetOf", "Overlaps", "SetEquals",
                     "SymmetricExceptWith", "UnionWith"},
    "Queue": _SEQ | {"Clear", "Contains", "CopyTo", "Dequeue", "Enqueue", "Peek", "ToArray", "TryDequeue",
                     "TryPeek", "TrimExcess"},
    "Stack": _SEQ | {"Clear", "Contains", "CopyTo", "Peek", "Pop", "Push", "ToArray", "TryPeek", "TryPop"},
    "ConcurrentQueue": _SEQ | {"Clear", "CopyTo", "Enqueue", "ToArray", "TryDequeue", "TryPeek"},
    "ConcurrentBag": _SEQ | {"Add", "Clear", "CopyTo", "ToArray", "TryPeek", "TryTake"},
    "IList": _LISTM,
    "IReadOnlyList": _SEQ,
    "ICollection": _COLL,
    "IReadOnlyCollection": _SEQ,
    "IDictionary": _COLL | {"ContainsKey", "TryGetValue"},
    "IReadOnlyDictionary": _SEQ | {"ContainsKey", "TryGetValue"},
    "IEnumerable": _SEQ,
    "IQueryable": _SEQ,
    "IAsyncEnumerable": {"GetAsyncEnumerator"},
    "Stream": {"BeginRead", "BeginWrite", "Close", "CopyTo", "CopyToAsync", "Dispose", "DisposeAsync", "EndRead",
               "EndWrite", "Flush", "FlushAsync", "Read", "ReadAsync", "ReadByte", "ReadExactly",
               "ReadExactlyAsync", "ReadAtLeast", "ReadAtLeastAsync", "Seek", "SetLength", "Write", "WriteAsync",
               "WriteByte"},
    "MemoryStream": {"GetBuffer", "ToArray", "TryGetBuffer", "WriteTo"},
    "FileStream": {"Lock", "Unlock"},
    "TextReader": {"Close", "Dispose", "Peek", "Read", "ReadAsync", "ReadBlock", "ReadBlockAsync", "ReadLine",
                   "ReadLineAsync", "ReadToEnd", "ReadToEndAsync"},
    "StreamReader": {"DiscardBufferedData"},
    "TextWriter": {"Close", "Dispose", "DisposeAsync", "Flush", "FlushAsync", "Write", "WriteAsync", "WriteLine",
                   "WriteLineAsync"},
    "StreamWriter": set(),
    "StringWriter": {"GetStringBuilder"},
    "XmlReader": {"GetAttribute", "IsStartElement", "MoveToAttribute", "MoveToContent", "MoveToElement",
                  "MoveToFirstAttribute", "MoveToNextAttribute", "Read", "ReadAsync", "ReadContentAsString",
                  "ReadElementContentAsString", "ReadElementContentAsInt", "ReadElementContentAsBoolean",
                  "ReadEndElement", "ReadInnerXml", "ReadOuterXml", "ReadStartElement", "ReadSubtree",
                  "ReadToDescendant", "ReadToFollowing", "ReadToNextSibling", "Skip", "SkipAsync", "Close",
                  "Dispose"},
    "Expression": {"Reduce", "ReduceAndCheck", "ReduceExtensions", "ToString"},
    "LambdaExpression": {"Compile"},
    "Type": {"GetConstructor", "GetConstructors", "GetCustomAttributes", "GetElementType", "GetEnumNames",
             "GetEnumValues", "GetEvent", "GetEvents", "GetField", "GetFields", "GetGenericArguments",
             "GetGenericTypeDefinition", "GetInterface", "GetInterfaces", "GetMember", "GetMembers", "GetMethod",
             "GetMethods", "GetNestedType", "GetNestedTypes", "GetProperties", "GetProperty", "IsAssignableFrom",
             "IsAssignableTo", "IsDefined", "IsEnumDefined", "IsInstanceOfType", "IsSubclassOf",
             "MakeArrayType", "MakeByRefType", "MakeGenericType", "MakePointerType", "GetTypeInfo",
             "GetDefaultMembers", "GetArrayRank", "IsEquivalentTo"},
    "MemberInfo": {"GetCustomAttributes", "GetCustomAttributesData", "IsDefined", "HasSameMetadataDefinitionAs"},
    "MethodBase": {"GetParameters", "Invoke", "GetMethodBody", "GetGenericArguments"},
    "MethodInfo": {"GetBaseDefinition", "GetGenericMethodDefinition", "MakeGenericMethod", "CreateDelegate"},
    "PropertyInfo": {"GetAccessors", "GetGetMethod", "GetSetMethod", "GetValue", "SetValue", "GetIndexParameters"},
    "FieldInfo": {"GetValue", "SetValue"},
    "Assembly": {"CreateInstance", "GetCustomAttributes", "GetExportedTypes", "GetManifestResourceNames",
                 "GetManifestResourceStream", "GetName", "GetType", "GetTypes", "GetReferencedAssemblies"},
    "Exception": {"GetBaseException", "GetObjectData"},
    "StringBuilder": {"Append", "AppendFormat", "AppendJoin", "AppendLine", "Clear", "CopyTo", "EnsureCapacity",
                      "Insert", "Remove", "Replace", "ToString", "GetChunks"},
    "HttpClient": {"CancelPendingRequests", "DeleteAsync", "GetAsync", "GetByteArrayAsync", "GetStreamAsync",
                   "GetStringAsync", "PatchAsync", "PostAsync", "PutAsync", "Send", "SendAsync"},
    "CancellationTokenSource": {"Cancel", "CancelAfter", "CancelAsync", "Dispose", "TryReset"},
    "Task": {"ConfigureAwait", "ContinueWith", "GetAwaiter", "RunSynchronously", "Start", "Wait", "WaitAsync",
             "Dispose"},
    "ValueTask": {"AsTask", "ConfigureAwait", "GetAwaiter", "Preserve"},
    "DbSet": {"Add", "AddAsync", "AddRange", "AddRangeAsync", "AsAsyncEnumerable", "AsQueryable", "Attach",
              "AttachRange", "Find", "FindAsync", "Remove", "RemoveRange", "Update", "UpdateRange", "GetEnumerator"},
    "DbContext": {"Add", "AddAsync", "AddRange", "AddRangeAsync", "Attach", "AttachRange", "Dispose", "DisposeAsync",
                  "Entry", "Find", "FindAsync", "Remove", "RemoveRange", "SaveChanges", "SaveChangesAsync", "Set",
                  "Update", "UpdateRange"},
    "ClaimsPrincipal": {"AddIdentities", "AddIdentity", "FindAll", "FindFirst", "HasClaim", "IsInRole", "Clone"},
    "Guid": {"CompareTo", "Equals", "ToByteArray", "ToString", "TryFormat", "TryWriteBytes"},
    "DateTime": {"Add", "AddDays", "AddHours", "AddMilliseconds", "AddMinutes", "AddMonths", "AddSeconds",
                 "AddTicks", "AddYears", "CompareTo", "Subtract", "ToLocalTime", "ToString", "ToUniversalTime"},
    "TimeSpan": {"Add", "CompareTo", "Duration", "Multiply", "Negate", "Subtract", "ToString"},
    "Span": {"Clear", "CopyTo", "Fill", "GetEnumerator", "Slice", "ToArray", "TryCopyTo"},
    "ReadOnlySpan": {"CopyTo", "GetEnumerator", "Slice", "ToArray", "TryCopyTo", "IndexOf", "Contains",
                     "StartsWith", "EndsWith", "Trim", "Split", "SequenceEqual"},
}


def ancestors(name: str) -> set[str]:
    """`name` and every .NET type it derives from or implements, as far as the table knows."""
    out, todo = {name}, [name]
    while todo:
        for b in BASES.get(todo.pop(), ()):
            if b not in out:
                out.add(b)
                todo.append(b)
    if name in BASES or name in MEMBERS:
        out.add("object")
    return out


# Types that implement their interfaces explicitly: `array.IndexOf(x)` does not compile through IList.IndexOf, so an
# interface's member names are not callable on them.
EXPLICIT = {"Array"}


def members(name: str) -> set[str] | None:
    """Instance method names a receiver of .NET type `name` has (its own and inherited), or None if unknown."""
    if name not in BASES and name not in MEMBERS:
        return None
    if name in EXPLICIT:
        return MEMBERS.get(name, set()) | MEMBERS["object"]
    return set().union(*(MEMBERS.get(t, set()) for t in ancestors(name))) | MEMBERS["object"]


def known(name: str) -> bool:
    return name in BASES or name in MEMBERS


# Implicit conversions between .NET types that are not inheritance: an argument of the key type may be passed where
# any of these is expected.
CONVERTS: dict[str, set[str]] = {
    "Array": {"Span", "ReadOnlySpan", "Memory", "ReadOnlyMemory", "ArraySegment"},
    "ArraySegment": {"Span", "ReadOnlySpan", "Memory", "ReadOnlyMemory"},
    "Span": {"ReadOnlySpan"},
    "Memory": {"ReadOnlyMemory"},
    "string": {"ReadOnlySpan", "ReadOnlyMemory"},
    "String": {"ReadOnlySpan", "ReadOnlyMemory"},
}

# Types whose instances are awaited for a result: `await x` of `Task<T>` is a `T`.
AWAITABLE = {"Task", "ValueTask"}
# Types whose `foreach` element is their first generic argument.
SEQUENCES = {"IEnumerable", "IReadOnlyList", "IReadOnlyCollection", "IList", "ICollection", "List", "Collection",
             "ReadOnlyCollection", "HashSet", "ISet", "IQueryable", "IOrderedEnumerable", "ImmutableArray",
             "ImmutableList", "Queue", "Stack", "IAsyncEnumerable", "ObservableCollection", "SortedSet",
             "ConcurrentBag", "ConcurrentQueue", "DbSet", "IOrderedQueryable", "ICollection_"}
# Delegate types: a lambda is passed where one of these is expected.
DELEGATES = {"Func", "Action", "Expression", "Predicate", "Comparison", "Converter", "EventHandler", "Delegate",
             "MulticastDelegate"}
# Value types and sealed types a lambda, or a literal of another kind, never converts to.
PRIMITIVES = {"int", "long", "short", "byte", "sbyte", "uint", "ulong", "ushort", "float", "double", "decimal",
              "bool", "char", "string", "Guid", "DateTime", "DateTimeOffset", "TimeSpan", "CancellationToken",
              "Int32", "Int64", "Boolean", "String", "Double", "Decimal"}
NUMERIC = {"int", "long", "short", "byte", "sbyte", "uint", "ulong", "ushort", "float", "double", "decimal",
           "Int32", "Int64", "Double", "Decimal", "nint", "nuint"}


# ── LINQ and fluent builders (round 3, found on Jellyfin: `people.Where(i => i.IsType(...))` left `i` untyped) ──
# A LINQ call on a sequence whose element type is known: the lambda's parameter is an element, and the result is:
LINQ_SAME = {"Where", "OrderBy", "OrderByDescending", "ThenBy", "ThenByDescending", "Skip", "Take", "SkipWhile",
             "TakeWhile", "Distinct", "DistinctBy", "Reverse", "AsEnumerable", "Concat", "Union", "UnionBy",
             "Except", "ExceptBy", "Intersect", "IntersectBy", "SkipLast", "TakeLast", "OfType_"}   # a sequence
LINQ_ELEMENT = {"First", "FirstOrDefault", "Single", "SingleOrDefault", "Last", "LastOrDefault", "ElementAt",
                "ElementAtOrDefault", "MinBy", "MaxBy", "Find", "FindLast"}                          # an element
LINQ_TO = {"ToList": "List", "ToArray": "Array", "ToHashSet": "HashSet", "ToImmutableArray": "ImmutableArray",
           "ToImmutableList": "ImmutableList", "FindAll": "List"}                                    # a collection
LINQ_LAMBDA = LINQ_SAME | LINQ_ELEMENT | {"Select", "SelectMany", "Any", "All", "Count", "LongCount", "Sum", "Min",
                                          "Max", "Average", "GroupBy", "ToDictionary", "ToLookup", "ForEach",
                                          "FindIndex", "FindLastIndex", "Exists", "RemoveAll", "TrueForAll",
                                          "FindAll", "Aggregate_", "Zip_", "Join_", "CountBy", "AggregateBy_"}
# Outside types whose builder methods return the receiver itself (`services.AddSingleton<T>().AddX()`).
FLUENT_SELF = {"IServiceCollection", "ServiceCollection", "StringBuilder", "IHostBuilder", "IWebHostBuilder",
               "ILoggingBuilder", "IConfigurationBuilder", "ConfigurationBuilder", "IHealthChecksBuilder",
               "IMvcBuilder", "IHttpClientBuilder"}

# Microsoft.Extensions.* types repositories call everywhere: their own method names bind there, never to ours.
BASES.update({
    "ILogger": set(), "ILoggerFactory": {"IDisposable"}, "LoggerFactory": {"ILoggerFactory", "IDisposable"},
    "IServiceProvider": set(), "IServiceScope": {"IDisposable"}, "IServiceScopeFactory": set(),
    "IConfiguration": set(), "IConfigurationSection": {"IConfiguration"}, "IConfigurationRoot": {"IConfiguration"},
    "IHost": {"IDisposable"}, "IHostBuilder": set(), "ILoggingBuilder": set(),
})
MEMBERS.update({
    "ILogger": {"Log", "IsEnabled", "BeginScope"},
    "ILoggerFactory": {"CreateLogger", "AddProvider", "Dispose"},
    "IServiceProvider": {"GetService"},
    "IServiceScope": {"Dispose"},
    "IServiceScopeFactory": {"CreateScope"},
    "IConfiguration": {"GetSection", "GetChildren", "GetReloadToken"},
    "IHost": {"StartAsync", "StopAsync", "Dispose"},
    "IHostBuilder": {"Build", "ConfigureAppConfiguration", "ConfigureContainer", "ConfigureHostConfiguration",
                     "ConfigureServices", "UseServiceProviderFactory"},
})
# Extension methods .NET itself defines on those types, by the names repositories also use for their own methods.
DOTNET_EXTENSIONS = {"CreateLogger", "GetRequiredService", "GetService", "GetServices", "CreateScope",
                     "LogInformation", "LogWarning", "LogError", "LogDebug", "LogTrace", "LogCritical",
                     "GetValue", "GetConnectionString", "AddSingleton", "AddScoped", "AddTransient", "AddLogging",
                     "AddOptions", "Configure", "AddHttpClient"}
