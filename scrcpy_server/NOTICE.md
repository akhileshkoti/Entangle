# Vendored scrcpy-server

- Source: https://github.com/Genymobile/scrcpy
- Release tag: v4.1
- Asset: `scrcpy-server-v4.1` (Apache License 2.0, see `LICENSE`)
- Retrieved: 2026-08-20
- SHA-256: deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae (matches upstream `SHA256SUMS.txt`)

Used unmodified as the on-device capture/control server, launched via
`adb shell ... app_process ... com.genymobile.scrcpy.Server 4.1 ...` — the same
technique scrcpy's own PC client uses. Not redistributed further; vendored here
solely so this project's PC-side code has a pinned, known-good server binary to
push to the device each session.

Client-server version strings must match exactly (`4.1`), or the server refuses
to start.
