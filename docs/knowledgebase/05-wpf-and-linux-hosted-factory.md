# Building Windows apps (WPF) with a Linux-hosted factory

## Q: If the factory is hosted on Linux, can we only build/develop/test Linux-focused applications? We cannot implement a WPF .NET application using the factory?

No, being hosted on Linux doesn't limit what the agents can *write*. It limits what they can *build, run and test* on that same machine. For a WPF app, part of the work fits and part doesn't.

**What works on Linux for a WPF / .NET app:**
- **Writing the code:** agents can write C#, XAML, ViewModels and tests regardless of the host OS.
- **Building:** the .NET SDK for Linux can compile WPF projects (`net8.0-windows`) if the project sets `<EnableWindowsTargeting>true</EnableWindowsTargeting>`. You get a build check, but the app can't be started there.
- **Unit tests for non-UI logic:** if ViewModels, services and domain code live in plain `net8.0` class libraries with no WPF references, their xUnit/NUnit tests run fine on Linux. Clean MVVM makes most of the app testable this way.

**What doesn't work on Linux:**
- **Running the app or testing the UI:** WPF needs Windows' graphics stack. Nothing renders, and UI automation (FlaUI, WinAppDriver, Appium) can't run there.
- **Windows-only APIs:** registry, COM, Windows services and similar behaviour can't be exercised.

**How to close the gap:**
1. **Windows CI:** a GitHub Actions job on `windows-latest` runs the full build, the UI tests, and packaging (MSIX or installer). The factory's judge merges only when the required GitHub checks are green. So if that Windows job is a required check, Windows behaviour is part of the merge gate even though the agents work on Linux.
2. **A Windows test machine or VM** for manual or automated UI runs outside the factory.

**On this machine specifically:** the factory runs in WSL on a Windows box, and WSL can start Windows programs (`dotnet.exe`, `/mnt/c/...`). In principle an agent could run real Windows builds and tests from WSL. I haven't checked that, and it would likely clash with the factory's sandbox and worker guard, which are designed to keep agents inside their Linux environment. I'd treat it as an experiment, not a setup to rely on.

**Bottom line:** yes, you can build a WPF app with the factory: code, Linux build check, and logic tests by the agents, with Windows-only verification moved to Windows CI. If the app is mostly UI with little separable logic, much of the checking falls outside what the agents can verify themselves.
