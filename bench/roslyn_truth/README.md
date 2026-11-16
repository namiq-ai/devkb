# Compiler truth for C#

`Program.cs` opens a repository's projects with Roslyn's MSBuildWorkspace (after `dotnet restore`) and writes every
method, constructor, accessor and local function, and every call between them as the compiler binds it. It is the
C# counterpart of the libclang truth used for C and C++ (`bench/exercises/cpp/truth_clang.py`). No .NET SDK is needed
locally: `.github/workflows/cs-truth.yml` runs it on GitHub's runners for the five C# dogfood repositories and uploads
one JSON per repository as an artifact.
