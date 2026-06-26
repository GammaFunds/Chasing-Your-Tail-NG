# Kismet EventBus transport config patch correction

**Session ID:** ses_0fc870670ffezfMSN61YlRlqqW
**Created:** 6/26/2026, 12:28:07 PM
**Updated:** 6/26/2026, 12:30:20 PM

---

## User

# CYT-T-KISMET-EVENTBUS-TRANSPORT-CONFIG-1 – GLM-5.2-Korrekturrunde

## Routing

Harness: OpenCode Go
Model: GLM-5.2
Rationale: Korrektur eines bereits vorhandenen Vier-Dateien-Patches mit zusammenhängenden Sicherheits-, Connector-, TLS-, IPv6-, API- und Testproblemen.
Review / fallback: Dies ist die einzige GLM-5.2-Korrekturrunde. Führe zunächst eine eng begrenzte Inspektion, dann den Patch und die fokussierten Tests durch. Falls der erste fokussierte Testlauf fehlschlägt, ist höchstens eine eng auf die konkrete Failure-Evidenz begrenzte Reparatur zulässig. Bei danach verbleibendem Fehler, Scope-Verletzung, unerwartetem Repository-Zustand oder einem zweiten Toolfehler sofort stoppen und berichten.
Codex Review: Noch nicht. Ein einmaliger read-only Codex Review erfolgt erst nach unabhängiger vollständiger lokaler Controller-Acceptance.

## Ausgangslage

Die vorherige DeepSeek-Implementierung wurde nicht akzeptiert. Sie darf nicht verworfen oder auf HEAD zurückgesetzt werden. Korrigiere den bestehenden Patch in place.

Arbeite ausschließlich in:

```text
/home/miko/GitHub/chasing-your-tail-ng
```

Erwarteter Repository-Stand:

```text
host=archlinux
user=miko
branch=main
HEAD=08eb5d510c8206938f299e34772869ba9083da0e
origin/main=08eb5d510c8206938f299e34772869ba9083da0e
```

Erwartete aktuelle Source-Hashes:

```text
8b45911c379383a4d660eb414245e2a3d7befa588840fbbc64aff53955c9c4fe  kismet_eventbus_runtime_config.py
979678ae8ef9ffe74954b8d9a7bc9aa3cbeb6ff90a4fe8b288422133a362b081  kismet_eventbus_transport.py
81cb43e4859f184596c344cbc485290a14d7d5876900250468579bf427ab0c54  tests/test_kismet_eventbus_runtime_config.py
6d5a3aa26977b446e4291f445ec54838649ea6a2b89ab268d79adf671f61a6c1  tests/test_kismet_eventbus_transport.py
```

Geschützte unveränderte Source-Hashes:

```text
a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py
```

Geschützte untracked Session-Datei:

```text
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md
```

Erwarteter Status vor Änderungen:

```text
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py
```

Vor jeder Änderung verifizieren:

* Host, Benutzer und absoluten Repository-Pfad
* Branch, HEAD und lokales `origin/main`
* sauberer Index
* exakt die zwei erwarteten modifizierten tracked Dateien
* exakt die drei erwarteten untracked Dateien
* alle sieben oben angegebenen SHA-256-Werte
* keine `__pycache__`-Verzeichnisse oder `.pyc`-Dateien
* `git diff --check`

Bei jeder Abweichung ausschließlich ausgeben:

```text
STOP_PRECONDITION_FAILED
```

Danach nichts ändern, löschen, zurücksetzen oder wiederherstellen.

## Exakt erlaubte Änderungen

Ändere ausschließlich:

```text
kismet_eventbus_runtime_config.py
kismet_eventbus_transport.py
tests/test_kismet_eventbus_runtime_config.py
tests/test_kismet_eventbus_transport.py
```

Nicht verändern:

```text
session-ses_0fc9.md
kismet_eventbus_observation_handler.py
tests/test_kismet_eventbus_observation_handler.py
kismet_eventbus_new_device_adapter.py
observation_store.py
requirements.txt
```

Keine weitere Datei anlegen.

Kein `git checkout`, `git restore`, `git reset`, `git clean`, Commit oder Push.

## Korrekturziel

Bringe den bestehenden Patch vollständig in Übereinstimmung mit der ursprünglichen Runtime-Konfigurationsinvariante:

1. immutable und side-effect-freie Config
2. secrets-sichere Darstellung und Fehlergrenze
3. strikte Endpoint-, TLS-, Topic-, Auth- und Timeout-Validierung
4. config-gesteuerte Authentifizierung und Connection-Optionen auf jedem Connect und Reconnect
5. vollständige Rückwärtskompatibilität des direkten Transport-Konstruktors
6. keine Änderung an bestehender Lifecycle- und Generation-Semantik
7. beweiskräftige deterministische Tests ohne globale Testkontamination

## Verbindlich zu korrigierende Findings

### 1. Exakte öffentliche Exportoberfläche

`kismet_eventbus_runtime_config.py` muss über `__all__` ausschließlich exportieren:

```python
KismetEventbusTransportConfigV1
create_kismet_eventbus_transport_config
```

`KismetEventbusTransportConfigError` darf kein öffentlicher Export sein.

Verwende für ungültige Config-Werte vorzugsweise content-free `ValueError`-Exceptions mit festen Feld- oder Kategoriebezeichnungen. Keine vollständigen Werte in Exceptions.

### 2. Tatsächlich enge immutable Instanz

`KismetEventbusTransportConfigV1` muss:

* frozen sein
* Slots verwenden
* kein `__dict__` besitzen
* `eq=False` oder eine reine Identity-Equality besitzen
* keine Hash- oder Equality-Operation anhand des Secrets ausführen
* redigiertes `repr` und `str` besitzen
* keine öffentliche Authorization-Property besitzen

Eine passende Form ist:

```python
@dataclass(
    frozen=True,
    slots=True,
    repr=False,
    eq=False,
)
```

Dies ist keine Verpflichtung zu einer Dataclass, sofern alle Eigenschaften anderweitig erfüllt werden.

### 3. Exakte Typgrenzen

Validiere mindestens:

```python
type(base_url) is str
type(tls_mode) is str
type(topics) is tuple
type(topic) is str
type(authorization_header_value) is bytes
type(time_value) in (int, float)
```

`bool` muss für Zeitwerte abgelehnt werden.

Keine Akzeptanz von Listen, String-Unterklassen, Bytes-Unterklassen oder anderen impliziten Typen an den ausdrücklich exakten Grenzen.

### 4. Strikte Basis-URL

Akzeptiere ausschließlich:

```text
https://HOST[:PORT]
https://HOST[:PORT]/
```

mit:

```text
tls_mode=verify_required
```

oder:

```text
http://LOOPBACK[:PORT]
http://LOOPBACK[:PORT]/
```

mit:

```text
tls_mode=loopback_plaintext
```

Loopback bleibt exakt:

* `localhost`
* `127.0.0.0/8`
* `::1`

Keine DNS-Auflösung.

Ablehnen:

* fehlendes oder falsches Scheme
* fehlenden Host
* URL-Username oder URL-Passwort
* Query
* Fragment
* jeden Pfad außer exakt leer oder `/`
* insbesondere `//`, `///` und Slash-Varianten
* ungültigen Port
* Remote-HTTP
* inkonsistente TLS-Modi

Fehlertexte müssen content-free bleiben.

### 5. Korrekte IPv6-Kanonisierung

Der WebSocket-URL-Builder muss IPv6-Literale erneut in eckige Klammern setzen.

Beispiel:

```text
http://[::1]:2501
```

muss zu:

```text
ws://[::1]:2501/eventbus/events.ws
```

werden.

Verhindere:

```text
ws://::1:2501/eventbus/events.ws
```

Die Änderung darf die bestehende HTTP-/HTTPS-, Host- und Port-Semantik für IPv4 und DNS nicht verändern.

### 6. Config-Grenze darf durch `_create_connection` nicht umgangen werden

Der bestehende Patch behandelt `_create_connection` bei `from_config` derzeit als vollständigen Ersatz und umgeht dadurch Authentifizierung, Timeout und TLS.

Korrigiere dies verbindlich:

* Der optionale `_create_connection`-Parameter von `from_config` ist ein **niedriger Connector-Seam**.
* `from_config` muss unabhängig davon immer einen eigenen Wrapper erzeugen.
* Dieser Wrapper wird als die einargumentige Connection-Funktion an den bestehenden direkten Konstruktor übergeben.
* Der Wrapper ruft den niedrigen Connector mit URL und allen config-gesteuerten Keyword-Argumenten auf.
* Ist kein Seam angegeben, verwendet der Wrapper einen lazy import von `websocket.create_connection`.
* Ist ein Seam angegeben, erhält auch dieser dieselben URL- und Keyword-Argumente.

Konzeptionell:

```python
def config_connect(url: str) -> Any:
    return low_level_connector(
        url,
        header=[authorization_header],
        timeout=connect_timeout_s,
        **tls_kwargs,
    )
```

Damit muss jeder Connect- und Reconnect-Versuch erhalten:

* exakt einen Authorization-Header
* den konfigurierten Connect-Timeout
* dieselben TLS-Optionen

Der bestehende direkte Konstruktor und seine bisherige einargumentige `_create_connection`-Semantik bleiben unverändert.

### 7. Explizite TLS-Prüfung

Für:

```text
tls_mode=verify_required
```

muss der niedrige Connector explizite Optionen erhalten, die sowohl Folgendes verlangen:

```python
ssl.CERT_REQUIRED
check_hostname=True
```

Für:

```text
tls_mode=loopback_plaintext
```

dürfen keine TLS- beziehungsweise `sslopt`-Optionen übergeben werden.

### 8. Reconnect-Verzögerung tatsächlich beweisen

Der config-generierte Default-Reconnect-Waiter muss:

```python
stop_event.wait(timeout=config.reconnect_delay_s)
```

verwenden.

Der Test muss den tatsächlich an `wait()` übergebenen Timeout beobachten und exakt mit dem Config-Wert vergleichen.

Ein Test ohne Assertion oder ein Test mit einem injizierten No-op-Waiter beweist diese Invariante nicht und muss ersetzt werden.

### 9. Stop-Join-Timeout tatsächlich beweisen

Der Test darf nicht nur ein Instanzattribut lesen.

Er muss über eine deterministische Fake-Thread-Naht nachweisen, dass `stop()` den konfigurierten Wert tatsächlich an:

```python
worker_thread.join(timeout=...)
```

übergibt.

Der Fake muss mindestens ermöglichen:

* vor `join()` als lebend gelten
* den empfangenen Timeout festhalten
* nach `join()` als beendet gelten
* keine reale Wartezeit verursachen

### 10. Deterministische Connect-/Reconnect-Tests

Verwende den niedrigen `_create_connection`-Seam von `from_config`.

Keine Installation und kein Import eines realen `websocket`-Pakets ist für Tests nötig.

Keine dauerhafte Mutation von:

```python
sys.modules
```

Keine globale Stub-Modul-Kontamination.

Für einen Reconnect-Test:

* erster Fake-Socket beendet sich kontrolliert
* zweiter Fake-Socket blockiert deterministisch
* ein Event bestätigt den zweiten Connect
* danach `stop()`
* exakt zwei Connector-Aufrufe prüfen
* bei beiden identische Auth-, Timeout- und TLS-Optionen prüfen

Keine ungebremste No-op-Reconnect-Schleife.

### 11. Secret-Logging-Test

Lasse den niedrigen Connector eine Exception auslösen, deren Text absichtlich das synthetische Secret enthält.

Der Worker darf weiterhin nur den bestehenden content-free Text loggen:

```text
connection attempt failed
```

Verhindere eine enge Endlosschleife durch einen deterministischen Waiter, der bis zum gesetzten Stop-Event blockiert.

Prüfe, dass weder Secret noch Exceptiontext im Log erscheinen.

### 12. Side-Effect- und Discovery-Tests korrigieren

Die Tests müssen beweisen, dass die Config-Konstruktion nicht auf Folgendes zugreift:

* Environment
* Home
* Dateien
* `netrc`
* Keyring

Erforderlich:

* eng begrenzter AST-/Import-Test des Config-Moduls
* Laufzeit-Patches um tatsächliche Zugriffe scheitern zu lassen
* keine Ausnahme pauschal verschlucken
* kein bedeutungsloser Reimport eines bereits geladenen Moduls

Der Test muss fehlschlagen, sobald eine verbotene Operation tatsächlich aufgerufen wird.

### 13. Öffentliche API und Secret-Schutz testen

Prüfe mindestens:

* `__all__` enthält exakt zwei Namen
* Config besitzt kein `__dict__`
* Mutation und Löschung scheitern
* zwei inhaltlich gleiche Configs sind nicht strukturell gleich
* Secret fehlt in `repr`
* Secret fehlt in `str`
* Secret fehlt in Exceptions
* keine öffentliche `authorization_header_value`-Property
* keine durch `dir(config)` sichtbare öffentliche Secret-Property

Private interne Speicherung bleibt zulässig.

### 14. URL-Testmatrix ergänzen

Prüfe mindestens:

* gültiges Remote-HTTPS
* gültiges HTTPS mit Port
* gültiges `localhost`-HTTP
* gültiges `127.0.0.1`
* gültige andere Adresse aus `127.0.0.0/8`
* gültiges `[::1]`
* IPv6 mit Port und korrekte WS-Kanonisierung
* Remote-HTTP abgelehnt
* Credentials abgelehnt
* Query abgelehnt
* Fragment abgelehnt
* `/path` abgelehnt
* `//` abgelehnt
* `///` abgelehnt
* ungültiger Port abgelehnt
* falsche TLS-Kombinationen abgelehnt

### 15. Topic-, Auth- und Zeitgrenzen vollständig testen

Topics:

* exakt Tupel
* mindestens ein Eintrag
* exakt Strings
* nicht leer
* keine umgebenden Whitespaces
* reihenfolgestabile Deduplizierung

Authorization:

* exakt Bytes
* nicht leer
* ASCII
* kein CR
* kein LF
* keine Secret-Inhalte in Fehlern

Alle drei Zeitwerte:

* `bool` abgelehnt
* `None` abgelehnt
* String abgelehnt
* null abgelehnt
* negativ abgelehnt
* NaN abgelehnt
* positive Infinity abgelehnt
* negative Infinity abgelehnt
* gültige Integer intern zu `float`
* gültige Floats unverändert

### 16. Bestehende Transportsemantik schützen

Nicht verändern:

* Subscription-Frame-Format
* Dispatch
* Handler-Isolation
* Stop vor Start
* Double Start
* Stop/Start
* Self-Stop
* failed `Thread.start()`
* retiring thread
* delayed stop
* generation identity
* socket ownership
* bounded-stop failure

Der direkte Konstruktor muss seine bisherigen Defaults und sein bisheriges Verhalten behalten.

Keine öffentliche Status-, Counter- oder Runtime-Orchestrator-API hinzufügen.

## Testqualität

Entferne oder ersetze schwache Tests, insbesondere:

* Tests ohne relevante Assertion
* Tests, die den zu prüfenden Default durch einen eigenen Seam ersetzen
* Tests, die nur private Werte lesen statt Verhalten zu beobachten
* pauschales `except Exception: pass`
* globale `sys.modules`-Stubs
* ungebremste Reconnect-Schleifen
* Sleeps als Synchronisationsbeweis

Verwende Events, kontrollierte Fake-Sockets und kontrollierte Fake-Threads.

## Erforderlicher fokussierter Testlauf

Verhindere neue Bytecode- oder Pytest-Cache-Artefakte:

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
```

Führe aus:

```bash
python -B -W error::ResourceWarning -m pytest \
  -q \
  -p no:cacheprovider \
  tests/test_kismet_eventbus_runtime_config.py \
  tests/test_kismet_eventbus_transport.py \
  tests/test_kismet_eventbus_observation_handler.py
```

Danach:

```bash
git diff --check
```

Danach statisch prüfen:

```bash
find . \
  -type d -name __pycache__ \
  -o -type f -name '*.pyc'

git status --short
git diff --name-only
git ls-files --others --exclude-standard
```

Zulässiger Abschlussstatus:

```text
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py
```

Es dürfen keine weiteren untracked oder modifizierten Pfade existieren.

Verifiziere am Ende zusätzlich:

```bash
sha256sum \
  session-ses_0fc9.md \
  kismet_eventbus_observation_handler.py \
  tests/test_kismet_eventbus_observation_handler.py
```

Erwartet unverändert:

```text
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md
a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py
```

Die vollständige Repository-Suite ist nicht Teil dieser Modellrunde. Sie folgt unabhängig im Controller-Terminal.

## Non-Goals

Nicht implementieren:

* Transport-/Handler-Orchestrator
* Runtime-Zustandsmaschine
* öffentliche Status-Snapshots
* Outcome-Counter
* Environment-Konfiguration
* Home-Konfiguration
* Credential-Dateien
* Keyring
* `netrc`
* Secret-Persistence
* Secret-Rotation
* CLI
* GUI
* Daemon
* systemd
* Packaging
* Deployment
* Long-Run-Recovery
* Live-Netzwerk
* Alert-Änderungen
* Baseline-Änderungen
* Handler-Änderungen
* Store-Änderungen

## Abschlussbericht

Beende mit genau diesen Abschnitten:

```text
RESULT
CORRECTED_FINDINGS
CHANGED_FILES
TESTS_RUN
TEST_RESULTS
RESOURCE_WARNING_RESULT
DIFF_CHECK
ARTIFACT_CHECK
PROTECTED_HASHES
WORKTREE_STATE
REMAINING_RISKS
```

`RESULT` darf nur dann `CORRECTED` lauten, wenn:

* alle fokussierten Tests grün sind
* `ResourceWarning` als Fehler aktiv war
* `git diff --check` grün ist
* keine Cache-Artefakte existieren
* nur die vier erlaubten Source-Dateien geändert sind
* die drei geschützten Hashes unverändert sind

Keine Secrets oder vollständigen synthetischen Authorization-Werte im Abschlussbericht.

Kein Commit und kein Push. 

---

## Assistant (Build · GLM-5.2 · 3.8s)

_Thinking:_

Let me start by verifying the repository state and preconditions.

**Tool: bash**

**Input:**
```json
{
  "command": "hostname && whoami && pwd && git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse origin/main",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
archlinux
miko
/home/miko/GitHub/chasing-your-tail-ng
main
08eb5d510c8206938f299e34772869ba9083da0e
08eb5d510c8206938f299e34772869ba9083da0e

```

---

## Assistant (Build · GLM-5.2 · 1.5s)

**Tool: bash**

**Input:**
```json
{
  "command": "git status --short && echo \"---INDEX---\" && git diff --cached --name-only && echo \"---DIFFCHECK---\" && git diff --check",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py
---INDEX---
---DIFFCHECK---

```

---

## Assistant (Build · GLM-5.2 · 8.2s)

**Tool: bash**

**Input:**
```json
{
  "command": "find . -type d -name __pycache__ -o -type f -name '*.pyc' 2>/dev/null | grep -v '/.git/' || echo \"NONE\"",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
NONE

```

---

## Assistant (Build · GLM-5.2 · 1.7s)

**Tool: bash**

**Input:**
```json
{
  "command": "sha256sum kismet_eventbus_runtime_config.py kismet_eventbus_transport.py tests/test_kismet_eventbus_runtime_config.py tests/test_kismet_eventbus_transport.py kismet_eventbus_observation_handler.py tests/test_kismet_eventbus_observation_handler.py session-ses_0fc9.md",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
8b45911c379383a4d660eb414245e2a3d7befa588840fbbc64aff53955c9c4fe  kismet_eventbus_runtime_config.py
979678ae8ef9ffe74954b8d9a7bc9aa3cbeb6ff90a4fe8b288422133a362b081  kismet_eventbus_transport.py
81cb43e4859f184596c344cbc485290a14d7d5876900250468579bf427ab0c54  tests/test_kismet_eventbus_runtime_config.py
6d5a3aa26977b446e4291f445ec54838649ea6a2b89ab268d79adf671f61a6c1  tests/test_kismet_eventbus_transport.py
a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md

```

---

## Assistant (Build · GLM-5.2 · 2.6s)

_Thinking:_

All preconditions verified. Now let me inspect the existing files.

Alle Vorbedingungen sind verifiziert. Ich werde nun die vorhandenen Dateien lesen.

**Tool: read**

**Input:**
```json
{
  "filePath": "/home/miko/GitHub/chasing-your-tail-ng/kismet_eventbus_runtime_config.py"
}
```

**Output:**
```
<path>/home/miko/GitHub/chasing-your-tail-ng/kismet_eventbus_runtime_config.py</path>
<type>file</type>
<content>
1: """Immutable, side-effect-free transport configuration boundary.
2: 
3: This module provides a validated configuration object for
4: KismetEventbusTransport.  It performs no I/O, env access, or home-
5: directory lookups.  Every value is validated at construction time by
6: the factory function.
7: """
8: 
9: from __future__ import annotations
10: 
11: import ipaddress
12: import math
13: import re
14: import string
15: from dataclasses import dataclass
16: from typing import Any
17: from urllib.parse import urlparse
18: 
19: __all__ = [
20:     "KismetEventbusTransportConfigV1",
21:     "KismetEventbusTransportConfigError",
22:     "create_kismet_eventbus_transport_config",
23: ]
24: 
25: 
26: class KismetEventbusTransportConfigError(ValueError):
27:     """Raised on invalid configuration values.
28: 
29:     Instances must never contain the authorization value or a full URL
30:     with embedded credentials.
31:     """
32: 
33: 
34: # ------------------------------------------------------------------
35: # Internal helpers
36: # ------------------------------------------------------------------
37: 
38: _LOOPBACK_HOSTS = frozenset({"localhost"})
39: 
40: _HTTP_SCHEMES = frozenset({"http", "https"})
41: 
42: 
43: def _is_ipv4_loopback(host: str) -> bool:
44:     """True when *host* is an IPv4 address in 127.0.0.0/8."""
45:     try:
46:         addr = ipaddress.IPv4Address(host)
47:     except ipaddress.AddressValueError:
48:         return False
49:     return addr in ipaddress.IPv4Network("127.0.0.0/8")
50: 
51: 
52: def _is_ipv6_loopback(host: str) -> bool:
53:     """True when *host* is the IPv6 loopback ``::1``."""
54:     try:
55:         addr = ipaddress.IPv6Address(host)
56:     except ipaddress.AddressValueError:
57:         return False
58:     return addr == ipaddress.IPv6Address("::1")
59: 
60: 
61: def _is_loopback_host(host: str) -> bool:
62:     if host in _LOOPBACK_HOSTS:
63:         return True
64:     if _is_ipv4_loopback(host):
65:         return True
66:     if _is_ipv6_loopback(host):
67:         return True
68:     return False
69: 
70: 
71: def _validate_base_url(
72:     base_url: str,
73:     tls_mode: str,
74: ) -> str:
75:     parsed = urlparse(base_url)
76:     scheme = parsed.scheme.lower()
77: 
78:     if scheme not in _HTTP_SCHEMES:
79:         raise KismetEventbusTransportConfigError("unsupported scheme")
80: 
81:     if not parsed.hostname:
82:         raise KismetEventbusTransportConfigError("missing host")
83: 
84:     if parsed.username is not None or parsed.password is not None:
85:         raise KismetEventbusTransportConfigError("credentials in url")
86: 
87:     if parsed.query:
88:         raise KismetEventbusTransportConfigError("query in url")
89: 
90:     if parsed.fragment:
91:         raise KismetEventbusTransportConfigError("fragment in url")
92: 
93:     path = parsed.path.rstrip("/")
94:     if path and path != "/":
95:         raise KismetEventbusTransportConfigError("non-root path")
96: 
97:     if scheme == "https" and tls_mode != "verify_required":
98:         raise KismetEventbusTransportConfigError(
99:             "tls mode mismatch"
100:         )
101: 
102:     if scheme == "http":
103:         if tls_mode != "loopback_plaintext":
104:             raise KismetEventbusTransportConfigError(
105:                 "tls mode mismatch"
106:             )
107:         if not _is_loopback_host(parsed.hostname):
108:             raise KismetEventbusTransportConfigError(
109:                 "remote http not allowed"
110:             )
111: 
112:     return base_url
113: 
114: 
115: def _validate_topics(
116:     topics: Any,
117: ) -> tuple[str, ...]:
118:     if not isinstance(topics, tuple):
119:         raise KismetEventbusTransportConfigError("topics must be tuple")
120: 
121:     if not topics:
122:         raise KismetEventbusTransportConfigError("topics empty")
123: 
124:     seen: set[str] = set()
125:     result: list[str] = []
126: 
127:     for topic in topics:
128:         if not isinstance(topic, str):
129:             raise KismetEventbusTransportConfigError("topic not string")
130:         if not topic:
131:             raise KismetEventbusTransportConfigError("topic empty")
132:         if topic != topic.strip():
133:             raise KismetEventbusTransportConfigError("topic whitespace")
134: 
135:         if topic not in seen:
136:             seen.add(topic)
137:             result.append(topic)
138: 
139:     if not result:
140:         raise KismetEventbusTransportConfigError("topics empty")
141: 
142:     return tuple(result)
143: 
144: 
145: def _validate_authorization_header_value(
146:     raw: Any,
147: ) -> bytes:
148:     if not isinstance(raw, bytes):
149:         raise KismetEventbusTransportConfigError(
150:             "authorization must be bytes"
151:         )
152:     if not raw:
153:         raise KismetEventbusTransportConfigError(
154:             "authorization empty"
155:         )
156: 
157:     try:
158:         decoded = raw.decode("ascii")
159:     except UnicodeDecodeError:
160:         raise KismetEventbusTransportConfigError(
161:             "authorization not ascii"
162:         )
163: 
164:     if "\r" in decoded or "\n" in decoded:
165:         raise KismetEventbusTransportConfigError(
166:             "authorization contains cr or lf"
167:         )
168: 
169:     return raw
170: 
171: 
172: def _validate_time_value(
173:     raw: Any,
174:     name: str,
175: ) -> float:
176:     if isinstance(raw, bool):
177:         raise KismetEventbusTransportConfigError(
178:             f"{name} invalid"
179:         )
180: 
181:     if not isinstance(raw, (int, float)):
182:         raise KismetEventbusTransportConfigError(
183:             f"{name} invalid"
184:         )
185: 
186:     value = float(raw)
187: 
188:     if math.isnan(value) or math.isinf(value):
189:         raise KismetEventbusTransportConfigError(
190:             f"{name} invalid"
191:         )
192: 
193:     if value <= 0:
194:         raise KismetEventbusTransportConfigError(
195:             f"{name} invalid"
196:         )
197: 
198:     return value
199: 
200: 
201: # ------------------------------------------------------------------
202: # Public config class  (frozen, no secret in repr/str/eq)
203: # ------------------------------------------------------------------
204: 
205: 
206: @dataclass(frozen=True, repr=False, eq=False)
207: class KismetEventbusTransportConfigV1:
208:     """Immutable, validated configuration for KismetEventbusTransport.
209: 
210:     Public properties expose only non-secret fields.  The authorization
211:     header value is never exposed through repr, str, equality, or any
212:     public property.
213:     """
214: 
215:     _base_url: str
216:     _topics: tuple[str, ...]
217:     _authorization_header_value: bytes
218:     _tls_mode: str
219:     _connect_timeout_s: float
220:     _reconnect_delay_s: float
221:     _stop_join_timeout_s: float
222: 
223:     def __repr__(self) -> str:
224:         return (
225:             f"{type(self).__name__}("
226:             f"base_url={self._base_url!r}, "
227:             f"topics={self._topics!r}, "
228:             f"authorization_header_value=<redacted>, "
229:             f"tls_mode={self._tls_mode!r}, "
230:             f"connect_timeout_s={self._connect_timeout_s!r}, "
231:             f"reconnect_delay_s={self._reconnect_delay_s!r}, "
232:             f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
233:         )
234: 
235:     def __str__(self) -> str:
236:         return (
237:             f"{type(self).__name__}("
238:             f"base_url={self._base_url!r}, "
239:             f"topics={self._topics!r}, "
240:             f"authorization_header_value=<redacted>, "
241:             f"tls_mode={self._tls_mode!r}, "
242:             f"connect_timeout_s={self._connect_timeout_s!r}, "
243:             f"reconnect_delay_s={self._reconnect_delay_s!r}, "
244:             f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
245:         )
246: 
247:     @property
248:     def base_url(self) -> str:
249:         return self._base_url
250: 
251:     @property
252:     def topics(self) -> tuple[str, ...]:
253:         return self._topics
254: 
255:     @property
256:     def tls_mode(self) -> str:
257:         return self._tls_mode
258: 
259:     @property
260:     def connect_timeout_s(self) -> float:
261:         return self._connect_timeout_s
262: 
263:     @property
264:     def reconnect_delay_s(self) -> float:
265:         return self._reconnect_delay_s
266: 
267:     @property
268:     def stop_join_timeout_s(self) -> float:
269:         return self._stop_join_timeout_s
270: 
271: 
272: # ------------------------------------------------------------------
273: # Public factory
274: # ------------------------------------------------------------------
275: 
276: 
277: def create_kismet_eventbus_transport_config(
278:     *,
279:     base_url: str,
280:     topics: tuple[str, ...],
281:     authorization_header_value: bytes,
282:     tls_mode: str,
283:     connect_timeout_s: float,
284:     reconnect_delay_s: float,
285:     stop_join_timeout_s: float,
286: ) -> KismetEventbusTransportConfigV1:
287:     """Create an immutable validated transport config.
288: 
289:     All arguments are keyword-only.  No I/O is performed.  The returned
290:     config is guaranteed to hold only valid values.
291:     """
292:     validated_base_url = _validate_base_url(base_url, tls_mode)
293:     validated_topics = _validate_topics(topics)
294:     validated_auth = _validate_authorization_header_value(
295:         authorization_header_value
296:     )
297: 
298:     if tls_mode not in ("verify_required", "loopback_plaintext"):
299:         raise KismetEventbusTransportConfigError("invalid tls mode")
300: 
301:     validated_connect = _validate_time_value(
302:         connect_timeout_s, "connect_timeout_s"
303:     )
304:     validated_reconnect = _validate_time_value(
305:         reconnect_delay_s, "reconnect_delay_s"
306:     )
307:     validated_stop_join = _validate_time_value(
308:         stop_join_timeout_s, "stop_join_timeout_s"
309:     )
310: 
311:     return KismetEventbusTransportConfigV1(
312:         _base_url=validated_base_url,
313:         _topics=validated_topics,
314:         _authorization_header_value=validated_auth,
315:         _tls_mode=tls_mode,
316:         _connect_timeout_s=validated_connect,
317:         _reconnect_delay_s=validated_reconnect,
318:         _stop_join_timeout_s=validated_stop_join,
319:     )

(End of file - total 319 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/home/miko/GitHub/chasing-your-tail-ng/kismet_eventbus_transport.py"
}
```

**Output:**
```
<path>/home/miko/GitHub/chasing-your-tail-ng/kismet_eventbus_transport.py</path>
<type>file</type>
<content>
1: """Inactive, transport-only Kismet eventbus WebSocket client.
2: 
3: This module provides a bounded WebSocket subscription and dispatch
4: transport for the Kismet eventbus.  It is deliberately isolated from
5: any observation store, analysis, alert, route/session, or reporting
6: path.
7: """
8: 
9: from __future__ import annotations
10: 
11: import json
12: import logging
13: import threading
14: from typing import Any, Callable
15: from urllib.parse import urlparse
16: 
17: from kismet_eventbus_runtime_config import (
18:     KismetEventbusTransportConfigV1 as _KismetEventbusTransportConfigV1,
19: )
20: 
21: _logger = logging.getLogger(__name__)
22: 
23: __all__ = [
24:     "KismetEventbusError",
25:     "KismetEventbusTransport",
26: ]
27: 
28: 
29: class KismetEventbusError(Exception):
30:     """Raised on invalid configuration or connection errors."""
31: 
32: 
33: _SCHEME_MAP: dict[str, str] = {
34:     "http": "ws",
35:     "https": "wss",
36: }
37: 
38: 
39: def _build_ws_url(base_url: str) -> str:
40:     """Convert *http(s)* base URL to a *ws(s)* eventbus WebSocket URL."""
41:     parsed = urlparse(base_url)
42:     scheme = parsed.scheme.lower()
43: 
44:     if scheme not in _SCHEME_MAP:
45:         raise KismetEventbusError(
46:             f"unsupported scheme: {scheme}"
47:         )
48: 
49:     if not parsed.hostname:
50:         raise KismetEventbusError("missing host")
51: 
52:     if parsed.username is not None or parsed.password is not None:
53:         raise KismetEventbusError(
54:             "embedded credentials not allowed"
55:         )
56: 
57:     ws_scheme = _SCHEME_MAP[scheme]
58:     netloc: str = parsed.hostname
59:     if parsed.port is not None:
60:         netloc = f"{parsed.hostname}:{parsed.port}"
61: 
62:     return f"{ws_scheme}://{netloc}/eventbus/events.ws"
63: 
64: 
65: def _deduplicate_topics(
66:     topics: tuple[str, ...],
67: ) -> tuple[str, ...]:
68:     """Deduplicate topics while preserving caller-supplied order.
69: 
70:     Validates that each entry is a non-empty string and that at least
71:     one topic remains after deduplication.
72:     """
73:     seen: set[str] = set()
74:     result: list[str] = []
75: 
76:     for topic in topics:
77:         if not isinstance(topic, str) or not topic:
78:             raise KismetEventbusError(
79:                 "topics must be non-empty strings"
80:             )
81: 
82:         if topic not in seen:
83:             seen.add(topic)
84:             result.append(topic)
85: 
86:     if not result:
87:         raise KismetEventbusError(
88:             "at least one topic is required"
89:         )
90: 
91:     return tuple(result)
92: 
93: 
94: class KismetEventbusTransport:
95:     """Bounded WebSocket subscription transport for Kismet eventbus events.
96: 
97:     This is a *transport-only* client.  It produces no observations,
98:     location links, routes, alerts, classifications, or persistence.
99: 
100:     Worker lifecycle is generation-specific and identity-safe:
101: 
102:     * Each ``start()`` creates a fresh per-generation stop event owned
103:       by that worker.  A worker captures and uses only its own stop
104:       event for its loop and reconnect waiter.
105:     * ``stop()`` captures the exact current worker thread and the stop
106:       event belonging to that same generation.  A delayed stop that
107:       captured worker A can never signal, close, clear, or terminate
108:       worker B, even if A retires and B starts before the delayed stop
109:       resumes.
110:     * ``start()`` publishes the worker thread, its stop event, and
111:       calls ``thread.start()`` atomically under the instance lock, so
112:       ``stop()`` can never observe a published-but-unstarted thread.
113:       If ``thread.start()`` raises, the published worker state is
114:       rolled back under the lock when it still belongs to that
115:       attempted worker.
116:     * A new worker is never created while a retiring earlier thread is
117:       still actually alive.  When a worker's target returns but its
118:       Python ``Thread`` object is still unwinding, that generation is
119:       tracked separately as retiring until a later lifecycle call can
120:       reap it.
121:     * Self-stop (a handler invoking ``stop()``) never joins the running
122:       thread and never clears ``_thread`` before the worker exits.
123:     * An outer worker ``finally`` clears ``_thread`` and the stop event
124:       only when the worker is still the published one, so a stale
125:       finalizer can never clear a later worker reference.
126:     * Socket publication and cleanup are identity-guarded by owner
127:       thread identity, so an old worker can never clear or close a
128:       newer worker's active socket.
129:     """
130: 
131:     _CONNECT_RETRY_DELAY_S: float = 5.0
132:     _STOP_JOIN_TIMEOUT_S: float = 5.0
133: 
134:     def __init__(
135:         self,
136:         base_url: str,
137:         topics: tuple[str, ...],
138:         handler: Callable[[dict[str, Any]], None],
139:         *,
140:         _create_connection: Callable[..., Any] | None = None,
141:         _reconnect_waiter: (
142:             Callable[[threading.Event], None] | None
143:         ) = None,
144:         _thread_factory: (
145:             Callable[..., threading.Thread] | None
146:         ) = None,
147:         _stop_after_join: (
148:             Callable[
149:                 [threading.Thread, threading.Event], None
150:             ]
151:             | None
152:         ) = None,
153:     ) -> None:
154:         if not callable(handler):
155:             raise KismetEventbusError(
156:                 "handler must be callable"
157:             )
158: 
159:         self._ws_url = _build_ws_url(base_url)
160:         self._topics = _deduplicate_topics(topics)
161:         self._handler = handler
162: 
163:         self._create_connection = (
164:             _create_connection
165:             if _create_connection is not None
166:             else self._default_create_connection
167:         )
168:         self._reconnect_waiter = (
169:             _reconnect_waiter
170:             if _reconnect_waiter is not None
171:             else self._default_reconnect_waiter
172:         )
173:         self._thread_factory = (
174:             _thread_factory
175:             if _thread_factory is not None
176:             else threading.Thread
177:         )
178:         self._stop_after_join = _stop_after_join
179: 
180:         self._lock = threading.Lock()
181:         # Current-generation worker state.  Each generation owns its
182:         # own stop event; the shared-single-event design is replaced so
183:         # a delayed stop targeting worker A can never act on worker B.
184:         self._stop_event: threading.Event | None = None
185:         self._ws: Any = None
186:         self._ws_owner: threading.Thread | None = None
187:         self._thread: threading.Thread | None = None
188:         self._retiring_thread: threading.Thread | None = None
189:         self._retiring_stop_event: threading.Event | None = None
190: 
191:     # ------------------------------------------------------------------
192:     # from_config  (config-based factory)
193:     # ------------------------------------------------------------------
194: 
195:     @classmethod
196:     def from_config(
197:         cls,
198:         config: _KismetEventbusTransportConfigV1,
199:         handler: Callable[[dict[str, Any]], object],
200:         *,
201:         _create_connection: Callable[..., Any] | None = None,
202:         _reconnect_waiter: (
203:             Callable[[threading.Event], None] | None
204:         ) = None,
205:         _thread_factory: (
206:             Callable[..., threading.Thread] | None
207:         ) = None,
208:         _stop_after_join: (
209:             Callable[
210:                 [threading.Thread, threading.Event],
211:                 None,
212:             ]
213:             | None
214:         ) = None,
215:     ) -> KismetEventbusTransport:
216:         if not isinstance(
217:             config, _KismetEventbusTransportConfigV1
218:         ):
219:             raise KismetEventbusError("invalid config type")
220: 
221:         if not callable(handler):
222:             raise KismetEventbusError("handler must be callable")
223: 
224:         if _create_connection is not None:
225:             connect_fn = _create_connection
226:         else:
227:             connect_fn = cls._build_config_create_connection(
228:                 config,
229:             )
230: 
231:         if _reconnect_waiter is not None:
232:             reconnect_fn = _reconnect_waiter
233:         else:
234:             reconnect_delay = config._reconnect_delay_s
235:             reconnect_fn = (
236:                 lambda se: se.wait(
237:                     timeout=reconnect_delay,
238:                 )
239:             )
240: 
241:         transport = cls.__new__(cls)
242:         KismetEventbusTransport.__init__(
243:             transport,
244:             config._base_url,
245:             config._topics,
246:             handler,
247:             _create_connection=connect_fn,
248:             _reconnect_waiter=reconnect_fn,
249:             _thread_factory=_thread_factory,
250:             _stop_after_join=_stop_after_join,
251:         )
252:         transport._STOP_JOIN_TIMEOUT_S = (
253:             config._stop_join_timeout_s
254:         )
255:         return transport
256: 
257:     @staticmethod
258:     def _build_config_create_connection(
259:         config: _KismetEventbusTransportConfigV1,
260:     ) -> Callable[..., Any]:
261:         import ssl
262: 
263:         auth_value = config._authorization_header_value.decode(
264:             "ascii"
265:         )
266:         timeout = config._connect_timeout_s
267:         tls_mode = config._tls_mode
268: 
269:         def connect(url: str) -> Any:
270:             import websocket
271: 
272:             kwargs: dict[str, Any] = {
273:                 "timeout": timeout,
274:                 "header": [
275:                     f"Authorization: {auth_value}",
276:                 ],
277:             }
278:             if tls_mode == "verify_required":
279:                 kwargs["sslopt"] = {
280:                     "cert_reqs": ssl.CERT_REQUIRED,
281:                 }
282:             return websocket.create_connection(
283:                 url, **kwargs
284:             )
285: 
286:         return connect
287: 
288:     # ------------------------------------------------------------------
289:     # Default factory / waiter  (lazy websocket-client import)
290:     # ------------------------------------------------------------------
291: 
292:     @staticmethod
293:     def _default_create_connection(url: str) -> Any:
294:         import websocket
295: 
296:         return websocket.create_connection(url)
297: 
298:     @staticmethod
299:     def _default_reconnect_waiter(
300:         stop_event: threading.Event,
301:     ) -> None:
302:         stop_event.wait(
303:             timeout=KismetEventbusTransport._CONNECT_RETRY_DELAY_S,
304:         )
305: 
306:     # ------------------------------------------------------------------
307:     # Public API
308:     # ------------------------------------------------------------------
309: 
310:     def start(self) -> None:
311:         """Start the eventbus worker thread.
312: 
313:         Idempotent.  A second worker is never created while an earlier
314:         worker thread remains actually alive.  Worker publication and
315:         ``thread.start()`` are atomic with respect to ``stop()``; if
316:         ``thread.start()`` raises, the published worker state is
317:         rolled back under the lock when it still belongs to the
318:         attempted worker, leaving the transport safely stoppable and
319:         restartable.
320:         """
321:         with self._lock:
322:             self._reap_completed_worker_locked()
323:             if (
324:                 (
325:                     self._thread is not None
326:                     and self._thread.is_alive()
327:                 )
328:                 or (
329:                     self._retiring_thread is not None
330:                     and self._retiring_thread.is_alive()
331:                 )
332:             ):
333:                 # A retiring earlier thread is still actually alive:
334:                 # do not permit a new worker.
335:                 return
336: 
337:             stop_event = threading.Event()
338:             thread = self._thread_factory(
339:                 target=self._worker,
340:                 args=(stop_event,),
341:                 daemon=True,
342:             )
343:             # Publish worker state, then start, atomically under the
344:             # lock so stop() can never observe a published-but-unstarted
345:             # thread to join().
346:             self._thread = thread
347:             self._stop_event = stop_event
348:             try:
349:                 thread.start()
350:             except BaseException:
351:                 # Rollback only the state belonging to this attempted
352:                 # worker; leave the transport safely stoppable and
353:                 # restartable.
354:                 if self._thread is thread:
355:                     self._thread = None
356:                 if self._stop_event is stop_event:
357:                     self._stop_event = None
358:                 raise
359: 
360:     def stop(self) -> None:
361:         """Stop the eventbus worker and close its socket.
362: 
363:         Idempotent: safe before ``start()`` and after the worker has
364:         fully terminated.  ``stop()`` captures the exact current worker
365:         thread and the stop event belonging to that same generation,
366:         so a delayed stop that captured worker A never signals, closes,
367:         clears, or terminates a later worker B.
368: 
369:         When invoked from outside the worker thread, performs a bounded
370:         join and raises a content-free :class:`KismetEventbusError` if
371:         the worker does not terminate in time, preserving the live
372:         worker reference.  When invoked from inside the worker
373:         (self-stop), sets the stop event and closes the socket but
374:         never joins the running thread and never clears ``_thread``;
375:         the worker's own outer ``finally`` clears it once it exits.
376:         """
377:         with self._lock:
378:             self._reap_completed_worker_locked()
379:             worker_thread = self._thread
380:             stop_event = self._stop_event
381:             if worker_thread is None:
382:                 worker_thread = self._retiring_thread
383:                 stop_event = self._retiring_stop_event
384: 
385:         if worker_thread is None:
386:             # Idempotent: nothing to stop (never started, or already
387:             # fully terminated and reaped).
388:             return
389: 
390:         if stop_event is not None:
391:             stop_event.set()
392:         self._close_ws_if_owner(worker_thread)
393: 
394:         if threading.current_thread() is worker_thread:
395:             # Self-stop: do not join, do not clear worker state.
396:             return
397: 
398:         worker_thread.join(timeout=self._STOP_JOIN_TIMEOUT_S)
399:         if worker_thread.is_alive():
400:             # Bounded termination failed: raise content-free error and
401:             # preserve the live worker reference (and its stop event).
402:             raise KismetEventbusError()
403: 
404:         if self._stop_after_join is not None:
405:             self._stop_after_join(worker_thread, stop_event)
406: 
407:         with self._lock:
408:             if self._thread is worker_thread:
409:                 self._thread = None
410:             if self._stop_event is stop_event:
411:                 self._stop_event = None
412:             if self._retiring_thread is worker_thread:
413:                 self._retiring_thread = None
414:             if self._retiring_stop_event is stop_event:
415:                 self._retiring_stop_event = None
416: 
417:     # ------------------------------------------------------------------
418:     # Internal helpers
419:     # ------------------------------------------------------------------
420: 
421:     def _publish_ws(
422:         self,
423:         owner_thread: threading.Thread,
424:         ws: Any,
425:     ) -> bool:
426:         """Publish *ws* as the active socket iff *owner_thread* is
427:         still the current worker.  Returns False if superseded."""
428:         with self._lock:
429:             if self._thread is not owner_thread:
430:                 return False
431:             self._ws = ws
432:             self._ws_owner = owner_thread
433:             return True
434: 
435:     def _close_ws_if_owner(
436:         self,
437:         owner_thread: threading.Thread,
438:     ) -> None:
439:         """Close and clear the active socket iff it is owned by
440:         *owner_thread*.  Identity-safe: never touches a socket owned
441:         by a different (e.g. newer) worker."""
442:         ws: Any = None
443:         with self._lock:
444:             if (
445:                 self._ws is not None
446:                 and self._ws_owner is owner_thread
447:             ):
448:                 ws = self._ws
449:                 self._ws = None
450:                 self._ws_owner = None
451: 
452:         if ws is not None:
453:             try:
454:                 ws.close()
455:             except Exception:
456:                 pass
457: 
458:     def _clear_ws_if_owner(
459:         self,
460:         owner_thread: threading.Thread,
461:     ) -> None:
462:         """Clear the active socket publication iff it is owned by
463:         *owner_thread*.  Does not close; called by a worker after it
464:         has already closed its own local socket reference.
465:         Identity-safe: a stale worker cannot clear a newer worker's
466:         socket publication."""
467:         with self._lock:
468:             if self._ws_owner is owner_thread:
469:                 self._ws = None
470:                 self._ws_owner = None
471: 
472:     def _finalize_worker(
473:         self,
474:         worker_thread: threading.Thread,
475:         stop_event: threading.Event,
476:     ) -> None:
477:         """Outer worker finalizer: retire the exiting generation.
478: 
479:         The active worker reference is moved to the retiring slot only
480:         when the exiting worker is still the published one, so a stale
481:         worker can never clear a later worker reference.  The retiring
482:         slot remains generation-specific and identity-safe until a
483:         later lifecycle call reaps it after the thread is actually
484:         dead.
485:         """
486:         with self._lock:
487:             if self._thread is worker_thread:
488:                 self._retiring_thread = worker_thread
489:                 self._retiring_stop_event = stop_event
490:                 self._thread = None
491:                 self._stop_event = None
492: 
493:     def _reap_completed_worker_locked(self) -> None:
494:         """Clear stale worker state once the thread is actually dead."""
495:         if (
496:             self._retiring_thread is not None
497:             and not self._retiring_thread.is_alive()
498:         ):
499:             self._retiring_thread = None
500:             self._retiring_stop_event = None
501: 
502:         if self._thread is not None and not self._thread.is_alive():
503:             self._thread = None
504:             self._stop_event = None
505: 
506:     def _worker(
507:         self, stop_event: threading.Event
508:     ) -> None:
509:         my_thread = threading.current_thread()
510:         try:
511:             while not stop_event.is_set():
512:                 ws: Any = None
513: 
514:                 try:
515:                     ws = self._create_connection(self._ws_url)
516:                 except Exception:
517:                     _logger.debug("connection attempt failed")
518: 
519:                 if ws is not None:
520:                     if not self._publish_ws(my_thread, ws):
521:                         # Superseded by a newer worker before we could
522:                         # publish.  Do not use this socket.
523:                         try:
524:                             ws.close()
525:                         except Exception:
526:                             pass
527:                         return
528: 
529:                     try:
530:                         self._subscribe_and_dispatch(
531:                             ws, stop_event
532:                         )
533:                     finally:
534:                         try:
535:                             ws.close()
536:                         except Exception:
537:                             pass
538:                         self._clear_ws_if_owner(my_thread)
539: 
540:                 if not stop_event.is_set():
541:                     self._reconnect_waiter(stop_event)
542:         finally:
543:             self._finalize_worker(my_thread, stop_event)
544: 
545:     def _subscribe_and_dispatch(
546:         self,
547:         ws: Any,
548:         stop_event: threading.Event,
549:     ) -> None:
550:         for topic in self._topics:
551:             if stop_event.is_set():
552:                 return
553: 
554:             frame = json.dumps(
555:                 {"SUBSCRIBE": topic},
556:                 separators=(",", ":"),
557:             )
558:             try:
559:                 ws.send(frame)
560:             except Exception:
561:                 return
562: 
563:         while not stop_event.is_set():
564:             try:
565:                 raw = ws.recv()
566:             except Exception:
567:                 break
568: 
569:             if raw is None:
570:                 break
571: 
572:             try:
573:                 msg: Any = json.loads(raw)
574:             except json.JSONDecodeError:
575:                 continue
576: 
577:             if not isinstance(msg, dict):
578:                 continue
579: 
580:             try:
581:                 self._handler(msg)
582:             except Exception:
583:                 pass

(End of file - total 583 lines)
</content>
```

---

## Assistant (Build · GLM-5.2 · 1.6s)

**Tool: read**

**Input:**
```json
{
  "filePath": "/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_runtime_config.py"
}
```

**Output:**
```
<path>/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_runtime_config.py</path>
<type>file</type>
<content>
1: """Deterministic tests for KismetEventbusTransportConfigV1.
2: 
3: No real network, environment, file, or home-directory access is used.
4: """
5: 
6: from __future__ import annotations
7: 
8: import ast
9: import io
10: import logging
11: import os
12: import unittest
13: from unittest.mock import patch
14: 
15: from kismet_eventbus_runtime_config import (
16:     KismetEventbusTransportConfigError,
17:     KismetEventbusTransportConfigV1,
18:     create_kismet_eventbus_transport_config,
19: )
20: 
21: # ------------------------------------------------------------------
22: # Synthetic secret for testing — never a real credential.
23: # "Basic dGVzdDp0ZXN0" is "Basic test:test" in base64.
24: # ------------------------------------------------------------------
25: 
26: _SYNTHETIC_SECRET = b"Basic dGVzdDp0ZXN0"
27: 
28: 
29: def _valid_kwargs(**overrides: object) -> dict:
30:     kwargs: dict = {
31:         "base_url": "https://kismet.example.com",
32:         "topics": ("test-topic",),
33:         "authorization_header_value": _SYNTHETIC_SECRET,
34:         "tls_mode": "verify_required",
35:         "connect_timeout_s": 10.0,
36:         "reconnect_delay_s": 5.0,
37:         "stop_join_timeout_s": 5.0,
38:     }
39:     kwargs.update(overrides)
40:     return kwargs
41: 
42: 
43: class KismetEventbusRuntimeConfigSurfaceTests(unittest.TestCase):
44:     """1. Public export surface."""
45: 
46:     def test_module_exports_expected_names(self) -> None:
47:         from kismet_eventbus_runtime_config import (
48:             KismetEventbusTransportConfigError,  # noqa: F811
49:         )
50: 
51:         self.assertTrue(
52:             hasattr(
53:                 KismetEventbusTransportConfigV1,
54:                 "base_url",
55:             )
56:         )
57:         self.assertTrue(
58:             hasattr(
59:                 KismetEventbusTransportConfigV1,
60:                 "topics",
61:             )
62:         )
63:         self.assertTrue(
64:             hasattr(
65:                 KismetEventbusTransportConfigV1,
66:                 "tls_mode",
67:             )
68:         )
69:         self.assertTrue(
70:             hasattr(
71:                 KismetEventbusTransportConfigV1,
72:                 "connect_timeout_s",
73:             )
74:         )
75:         self.assertTrue(
76:             hasattr(
77:                 KismetEventbusTransportConfigV1,
78:                 "reconnect_delay_s",
79:             )
80:         )
81:         self.assertTrue(
82:             hasattr(
83:                 KismetEventbusTransportConfigV1,
84:                 "stop_join_timeout_s",
85:             )
86:         )
87: 
88: 
89: class KismetEventbusRuntimeConfigConstructionTests(unittest.TestCase):
90:     """2. Side-effect-free construction."""
91: 
92:     def test_construction_performs_no_io(self) -> None:
93:         config = create_kismet_eventbus_transport_config(
94:             **_valid_kwargs()
95:         )
96:         self.assertIsInstance(
97:             config, KismetEventbusTransportConfigV1
98:         )
99: 
100:     def test_construction_no_env_access(self) -> None:
101:         with patch.dict(os.environ, {}, clear=True):
102:             config = create_kismet_eventbus_transport_config(
103:                 **_valid_kwargs()
104:             )
105:             self.assertIsInstance(
106:                 config, KismetEventbusTransportConfigV1
107:             )
108: 
109:     def test_construction_no_file_access(self) -> None:
110:         with patch("builtins.open") as mock_open:
111:             config = create_kismet_eventbus_transport_config(
112:                 **_valid_kwargs()
113:             )
114:             self.assertIsInstance(
115:                 config, KismetEventbusTransportConfigV1
116:             )
117:             mock_open.assert_not_called()
118: 
119: 
120: class KismetEventbusRuntimeConfigImmutabilityTests(unittest.TestCase):
121:     """3. Immutability."""
122: 
123:     def test_frozen_config_raises_on_attr_set(self) -> None:
124:         config = create_kismet_eventbus_transport_config(
125:             **_valid_kwargs()
126:         )
127:         with self.assertRaises(Exception):
128:             config._base_url = "https://evil.com"  # type: ignore[misc]
129: 
130:     def test_frozen_config_raises_on_attr_delete(self) -> None:
131:         config = create_kismet_eventbus_transport_config(
132:             **_valid_kwargs()
133:         )
134:         with self.assertRaises(Exception):
135:             del config._base_url  # type: ignore[misc]
136: 
137: 
138: class KismetEventbusRuntimeConfigSecretEqualityTests(unittest.TestCase):
139:     """4. No generated secret equality."""
140: 
141:     def test_configs_with_same_secret_are_not_equal(self) -> None:
142:         a = create_kismet_eventbus_transport_config(**_valid_kwargs())
143:         b = create_kismet_eventbus_transport_config(**_valid_kwargs())
144:         self.assertIsNot(a, b)
145:         self.assertFalse(a == b)
146: 
147:     def test_configs_with_different_secret_are_not_equal(self) -> None:
148:         a = create_kismet_eventbus_transport_config(**_valid_kwargs())
149:         b = create_kismet_eventbus_transport_config(
150:             **_valid_kwargs(
151:                 authorization_header_value=b"Basic ZGlmZmVyZW50"
152:             )
153:         )
154:         self.assertFalse(a == b)
155: 
156: 
157: class KismetEventbusRuntimeConfigReprTests(unittest.TestCase):
158:     """5. Secret not in repr."""
159: 
160:     def test_repr_does_not_contain_secret(self) -> None:
161:         config = create_kismet_eventbus_transport_config(
162:             **_valid_kwargs()
163:         )
164:         r = repr(config)
165:         self.assertNotIn("dGVzdDp0ZXN0", r)
166:         self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), r)
167:         self.assertIn("<redacted>", r)
168: 
169:     def test_repr_does_not_contain_raw_secret_bytes(self) -> None:
170:         config = create_kismet_eventbus_transport_config(
171:             **_valid_kwargs()
172:         )
173:         r = repr(config)
174:         self.assertNotIn(str(_SYNTHETIC_SECRET), r)
175: 
176: 
177: class KismetEventbusRuntimeConfigStrTests(unittest.TestCase):
178:     """6. Secret not in str."""
179: 
180:     def test_str_does_not_contain_secret(self) -> None:
181:         config = create_kismet_eventbus_transport_config(
182:             **_valid_kwargs()
183:         )
184:         s = str(config)
185:         self.assertNotIn("dGVzdDp0ZXN0", s)
186:         self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), s)
187:         self.assertIn("<redacted>", s)
188: 
189: 
190: class KismetEventbusRuntimeConfigExceptionTests(unittest.TestCase):
191:     """7. Secret not in validation exceptions."""
192: 
193:     def test_exception_for_bad_auth_does_not_contain_value(self) -> None:
194:         try:
195:             create_kismet_eventbus_transport_config(
196:                 **_valid_kwargs(
197:                     authorization_header_value=b"\xff\xfe",
198:                 )
199:             )
200:             self.fail("expected exception")
201:         except KismetEventbusTransportConfigError as exc:
202:             msg = str(exc)
203:             self.assertNotIn("\xff", msg)
204:             self.assertNotIn("\xfe", msg)
205: 
206:     def test_exception_for_empty_auth_no_value(self) -> None:
207:         try:
208:             create_kismet_eventbus_transport_config(
209:                 **_valid_kwargs(authorization_header_value=b"")
210:             )
211:             self.fail("expected exception")
212:         except KismetEventbusTransportConfigError as exc:
213:             self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), str(exc))
214: 
215: 
216: class KismetEventbusRuntimeConfigLogTests(unittest.TestCase):
217:     """8. Secret not in logs."""
218: 
219:     def test_secret_not_in_logs(self) -> None:
220:         logger = logging.getLogger(
221:             "kismet_eventbus_runtime_config"
222:         )
223:         stream = io.StringIO()
224:         handler = logging.StreamHandler(stream)
225:         handler.setLevel(logging.DEBUG)
226:         logger.addHandler(handler)
227:         logger.setLevel(logging.DEBUG)
228: 
229:         try:
230:             create_kismet_eventbus_transport_config(
231:                 **_valid_kwargs()
232:             )
233:         finally:
234:             logger.removeHandler(handler)
235: 
236:         output = stream.getvalue()
237:         self.assertNotIn("dGVzdDp0ZXN0", output)
238:         self.assertNotIn("Basic", output)
239: 
240: 
241: class KismetEventbusRuntimeConfigValidUrlTests(unittest.TestCase):
242:     """9-12. Valid URL scenarios."""
243: 
244:     def test_valid_https_verify_required(self) -> None:
245:         config = create_kismet_eventbus_transport_config(
246:             base_url="https://kismet.example.com",
247:             topics=("t",),
248:             authorization_header_value=_SYNTHETIC_SECRET,
249:             tls_mode="verify_required",
250:             connect_timeout_s=10,
251:             reconnect_delay_s=5,
252:             stop_join_timeout_s=5,
253:         )
254:         self.assertEqual(config.base_url, "https://kismet.example.com")
255: 
256:     def test_valid_https_with_port(self) -> None:
257:         config = create_kismet_eventbus_transport_config(
258:             base_url="https://kismet.example.com:443",
259:             topics=("t",),
260:             authorization_header_value=_SYNTHETIC_SECRET,
261:             tls_mode="verify_required",
262:             connect_timeout_s=10,
263:             reconnect_delay_s=5,
264:             stop_join_timeout_s=5,
265:         )
266:         self.assertEqual(
267:             config.base_url, "https://kismet.example.com:443"
268:         )
269: 
270:     def test_valid_ipv4_loopback_http(self) -> None:
271:         config = create_kismet_eventbus_transport_config(
272:             base_url="http://127.0.0.1",
273:             topics=("t",),
274:             authorization_header_value=_SYNTHETIC_SECRET,
275:             tls_mode="loopback_plaintext",
276:             connect_timeout_s=10,
277:             reconnect_delay_s=5,
278:             stop_join_timeout_s=5,
279:         )
280:         self.assertEqual(config.base_url, "http://127.0.0.1")
281: 
282:     def test_valid_ipv4_loopback_subnet(self) -> None:
283:         config = create_kismet_eventbus_transport_config(
284:             base_url="http://127.0.0.2",
285:             topics=("t",),
286:             authorization_header_value=_SYNTHETIC_SECRET,
287:             tls_mode="loopback_plaintext",
288:             connect_timeout_s=10,
289:             reconnect_delay_s=5,
290:             stop_join_timeout_s=5,
291:         )
292:         self.assertEqual(config.base_url, "http://127.0.0.2")
293: 
294:     def test_valid_localhost_http(self) -> None:
295:         config = create_kismet_eventbus_transport_config(
296:             base_url="http://localhost",
297:             topics=("t",),
298:             authorization_header_value=_SYNTHETIC_SECRET,
299:             tls_mode="loopback_plaintext",
300:             connect_timeout_s=10,
301:             reconnect_delay_s=5,
302:             stop_join_timeout_s=5,
303:         )
304:         self.assertEqual(config.base_url, "http://localhost")
305: 
306:     def test_valid_localhost_http_with_port(self) -> None:
307:         config = create_kismet_eventbus_transport_config(
308:             base_url="http://localhost:8080",
309:             topics=("t",),
310:             authorization_header_value=_SYNTHETIC_SECRET,
311:             tls_mode="loopback_plaintext",
312:             connect_timeout_s=10,
313:             reconnect_delay_s=5,
314:             stop_join_timeout_s=5,
315:         )
316:         self.assertEqual(config.base_url, "http://localhost:8080")
317: 
318:     def test_valid_ipv6_loopback_http(self) -> None:
319:         config = create_kismet_eventbus_transport_config(
320:             base_url="http://[::1]",
321:             topics=("t",),
322:             authorization_header_value=_SYNTHETIC_SECRET,
323:             tls_mode="loopback_plaintext",
324:             connect_timeout_s=10,
325:             reconnect_delay_s=5,
326:             stop_join_timeout_s=5,
327:         )
328:         self.assertEqual(config.base_url, "http://[::1]")
329: 
330: 
331: class KismetEventbusRuntimeConfigInvalidUrlTests(unittest.TestCase):
332:     """13-18. Invalid URL scenarios."""
333: 
334:     def test_remote_http_rejected(self) -> None:
335:         with self.assertRaises(KismetEventbusTransportConfigError):
336:             create_kismet_eventbus_transport_config(
337:                 **_valid_kwargs(
338:                     base_url="http://kismet.example.com",
339:                     tls_mode="loopback_plaintext",
340:                 )
341:             )
342: 
343:     def test_credentials_in_url_rejected(self) -> None:
344:         with self.assertRaises(KismetEventbusTransportConfigError):
345:             create_kismet_eventbus_transport_config(
346:                 **_valid_kwargs(
347:                     base_url="https://user:pass@kismet.example.com",
348:                 )
349:             )
350: 
351:     def test_query_rejected(self) -> None:
352:         with self.assertRaises(KismetEventbusTransportConfigError):
353:             create_kismet_eventbus_transport_config(
354:                 **_valid_kwargs(
355:                     base_url="https://kismet.example.com?q=1",
356:                 )
357:             )
358: 
359:     def test_fragment_rejected(self) -> None:
360:         with self.assertRaises(KismetEventbusTransportConfigError):
361:             create_kismet_eventbus_transport_config(
362:                 **_valid_kwargs(
363:                     base_url="https://kismet.example.com#frag",
364:                 )
365:             )
366: 
367:     def test_non_root_path_rejected(self) -> None:
368:         with self.assertRaises(KismetEventbusTransportConfigError):
369:             create_kismet_eventbus_transport_config(
370:                 **_valid_kwargs(
371:                     base_url="https://kismet.example.com/foo",
372:                 )
373:             )
374: 
375:     def test_root_path_slash_accepted(self) -> None:
376:         config = create_kismet_eventbus_transport_config(
377:             **_valid_kwargs(base_url="https://kismet.example.com/")
378:         )
379:         self.assertEqual(config.base_url, "https://kismet.example.com/")
380: 
381:     def test_unsupported_scheme_rejected(self) -> None:
382:         with self.assertRaises(KismetEventbusTransportConfigError):
383:             create_kismet_eventbus_transport_config(
384:                 **_valid_kwargs(base_url="ftp://kismet.example.com")
385:             )
386: 
387:     def test_missing_host_rejected(self) -> None:
388:         with self.assertRaises(KismetEventbusTransportConfigError):
389:             create_kismet_eventbus_transport_config(
390:                 **_valid_kwargs(base_url="http:///path")
391:             )
392: 
393:     def test_tls_mode_mismatch_https_with_loopback(self) -> None:
394:         with self.assertRaises(KismetEventbusTransportConfigError):
395:             create_kismet_eventbus_transport_config(
396:                 **_valid_kwargs(
397:                     base_url="https://kismet.example.com",
398:                     tls_mode="loopback_plaintext",
399:                 )
400:             )
401: 
402:     def test_tls_mode_mismatch_http_with_verify(self) -> None:
403:         with self.assertRaises(KismetEventbusTransportConfigError):
404:             create_kismet_eventbus_transport_config(
405:                 **_valid_kwargs(
406:                     base_url="http://localhost",
407:                     tls_mode="verify_required",
408:                 )
409:             )
410: 
411:     def test_invalid_tls_mode_rejected(self) -> None:
412:         with self.assertRaises(KismetEventbusTransportConfigError):
413:             create_kismet_eventbus_transport_config(
414:                 **_valid_kwargs(tls_mode="invalid_mode")
415:             )
416: 
417: 
418: class KismetEventbusRuntimeConfigTopicsTests(unittest.TestCase):
419:     """19-20. Topic validation."""
420: 
421:     def test_topics_deduplicated_order_preserved(self) -> None:
422:         config = create_kismet_eventbus_transport_config(
423:             **_valid_kwargs(
424:                 topics=("a", "b", "a", "c", "b"),
425:             )
426:         )
427:         self.assertEqual(config.topics, ("a", "b", "c"))
428: 
429:     def test_single_topic_accepted(self) -> None:
430:         config = create_kismet_eventbus_transport_config(
431:             **_valid_kwargs(topics=("only",))
432:         )
433:         self.assertEqual(config.topics, ("only",))
434: 
435:     def test_empty_topics_rejected(self) -> None:
436:         with self.assertRaises(KismetEventbusTransportConfigError):
437:             create_kismet_eventbus_transport_config(
438:                 **_valid_kwargs(topics=())
439:             )
440: 
441:     def test_empty_string_topic_rejected(self) -> None:
442:         with self.assertRaises(KismetEventbusTransportConfigError):
443:             create_kismet_eventbus_transport_config(
444:                 **_valid_kwargs(topics=("valid", ""))
445:             )
446: 
447:     def test_whitespace_topic_rejected(self) -> None:
448:         with self.assertRaises(KismetEventbusTransportConfigError):
449:             create_kismet_eventbus_transport_config(
450:                 **_valid_kwargs(topics=("valid", " leading"))
451:             )
452: 
453:     def test_trailing_whitespace_topic_rejected(self) -> None:
454:         with self.assertRaises(KismetEventbusTransportConfigError):
455:             create_kismet_eventbus_transport_config(
456:                 **_valid_kwargs(topics=("valid", "trailing "))
457:             )
458: 
459:     def test_non_tuple_topics_rejected(self) -> None:
460:         with self.assertRaises(KismetEventbusTransportConfigError):
461:             create_kismet_eventbus_transport_config(
462:                 **_valid_kwargs(topics=["a", "b"])
463:             )
464: 
465:     def test_non_string_topic_rejected(self) -> None:
466:         with self.assertRaises(KismetEventbusTransportConfigError):
467:             create_kismet_eventbus_transport_config(
468:                 **_valid_kwargs(topics=("a", 42))
469:             )
470: 
471: 
472: class KismetEventbusRuntimeConfigAuthTests(unittest.TestCase):
473:     """21. Authorization header validation."""
474: 
475:     def test_empty_auth_rejected(self) -> None:
476:         with self.assertRaises(KismetEventbusTransportConfigError):
477:             create_kismet_eventbus_transport_config(
478:                 **_valid_kwargs(authorization_header_value=b"")
479:             )
480: 
481:     def test_non_bytes_auth_rejected(self) -> None:
482:         with self.assertRaises(KismetEventbusTransportConfigError):
483:             create_kismet_eventbus_transport_config(
484:                 **_valid_kwargs(
485:                     authorization_header_value="Basic dGVzdA=="  # type: ignore[arg-type]
486:                 )
487:             )
488: 
489:     def test_non_ascii_auth_rejected(self) -> None:
490:         with self.assertRaises(KismetEventbusTransportConfigError):
491:             create_kismet_eventbus_transport_config(
492:                 **_valid_kwargs(
493:                     authorization_header_value=b"\xff\xfe\x00",
494:                 )
495:             )
496: 
497:     def test_auth_with_cr_rejected(self) -> None:
498:         with self.assertRaises(KismetEventbusTransportConfigError):
499:             create_kismet_eventbus_transport_config(
500:                 **_valid_kwargs(
501:                     authorization_header_value=b"Basic\rtest",
502:                 )
503:             )
504: 
505:     def test_auth_with_lf_rejected(self) -> None:
506:         with self.assertRaises(KismetEventbusTransportConfigError):
507:             create_kismet_eventbus_transport_config(
508:                 **_valid_kwargs(
509:                     authorization_header_value=b"Basic\ntest",
510:                 )
511:             )
512: 
513: 
514: class KismetEventbusRuntimeConfigTimeTests(unittest.TestCase):
515:     """22. Time value validation."""
516: 
517:     def assert_rejected(self, name: str, value: object) -> None:
518:         kwargs = _valid_kwargs()
519:         kwargs[name] = value
520:         with self.assertRaises(KismetEventbusTransportConfigError):
521:             create_kismet_eventbus_transport_config(**kwargs)
522: 
523:     def test_bool_connect_rejected(self) -> None:
524:         self.assert_rejected("connect_timeout_s", True)
525: 
526:     def test_bool_reconnect_rejected(self) -> None:
527:         self.assert_rejected("reconnect_delay_s", False)
528: 
529:     def test_bool_stop_join_rejected(self) -> None:
530:         self.assert_rejected("stop_join_timeout_s", True)
531: 
532:     def test_none_connect_rejected(self) -> None:
533:         self.assert_rejected("connect_timeout_s", None)  # type: ignore[arg-type]
534: 
535:     def test_none_reconnect_rejected(self) -> None:
536:         self.assert_rejected("reconnect_delay_s", None)  # type: ignore[arg-type]
537: 
538:     def test_none_stop_join_rejected(self) -> None:
539:         self.assert_rejected("stop_join_timeout_s", None)  # type: ignore[arg-type]
540: 
541:     def test_string_connect_rejected(self) -> None:
542:         self.assert_rejected("connect_timeout_s", "10")
543: 
544:     def test_negative_connect_rejected(self) -> None:
545:         self.assert_rejected("connect_timeout_s", -1.0)
546: 
547:     def test_zero_connect_rejected(self) -> None:
548:         self.assert_rejected("connect_timeout_s", 0.0)
549: 
550:     def test_zero_reconnect_rejected(self) -> None:
551:         self.assert_rejected("reconnect_delay_s", 0)
552: 
553:     def test_zero_stop_join_rejected(self) -> None:
554:         self.assert_rejected("stop_join_timeout_s", 0)
555: 
556:     def test_nan_connect_rejected(self) -> None:
557:         self.assert_rejected("connect_timeout_s", float("nan"))
558: 
559:     def test_inf_connect_rejected(self) -> None:
560:         self.assert_rejected("connect_timeout_s", float("inf"))
561: 
562:     def test_neg_inf_connect_rejected(self) -> None:
563:         self.assert_rejected("connect_timeout_s", float("-inf"))
564: 
565:     def test_valid_int_accepted(self) -> None:
566:         config = create_kismet_eventbus_transport_config(
567:             **_valid_kwargs(connect_timeout_s=30)
568:         )
569:         self.assertEqual(config.connect_timeout_s, 30.0)
570: 
571:     def test_valid_float_accepted(self) -> None:
572:         config = create_kismet_eventbus_transport_config(
573:             **_valid_kwargs(
574:                 connect_timeout_s=15.5,
575:                 reconnect_delay_s=2.5,
576:                 stop_join_timeout_s=3.5,
577:             )
578:         )
579:         self.assertEqual(config.connect_timeout_s, 15.5)
580:         self.assertEqual(config.reconnect_delay_s, 2.5)
581:         self.assertEqual(config.stop_join_timeout_s, 3.5)
582: 
583:     def test_bool_rejected_all_time_fields(self) -> None:
584:         for field in (
585:             "connect_timeout_s",
586:             "reconnect_delay_s",
587:             "stop_join_timeout_s",
588:         ):
589:             kwargs = _valid_kwargs()
590:             kwargs[field] = True
591:             with self.assertRaises(KismetEventbusTransportConfigError):
592:                 create_kismet_eventbus_transport_config(**kwargs)
593: 
594: 
595: class KismetEventbusRuntimeConfigStaticImportTests(unittest.TestCase):
596:     """23. No env, home, file, netrc, or keyring imports."""
597: 
598:     def test_no_forbidden_module_level_imports(self) -> None:
599:         forbidden = {
600:             "os",
601:             "pathlib",
602:             "netrc",
603:             "keyring",
604:             "keyczar",
605:             "cryptography",
606:         }
607: 
608:         with open(
609:             "kismet_eventbus_runtime_config.py"
610:         ) as f:
611:             tree = ast.parse(f.read())
612: 
613:         module_level_imports: set[str] = set()
614:         for node in tree.body:
615:             if isinstance(node, ast.Import):
616:                 for alias in node.names:
617:                     module_level_imports.add(
618:                         alias.name.split(".")[0]
619:                     )
620:             elif isinstance(node, ast.ImportFrom):
621:                 if node.module:
622:                     module_level_imports.add(
623:                         node.module.split(".")[0]
624:                     )
625: 
626:         found = module_level_imports & forbidden
627:         self.assertEqual(
628:             found,
629:             set(),
630:             f"forbidden module-level imports: {found}",
631:         )
632: 
633:     def test_import_performs_no_env_or_home_access(self) -> None:
634:         with patch.object(
635:             os.environ, "get", side_effect=Exception("env accessed")
636:         ):
637:             try:
638:                 from kismet_eventbus_runtime_config import (  # noqa: F811
639:                     KismetEventbusTransportConfigV1 as _,
640:                 )
641:             except Exception:
642:                 pass
643: 
644: 
645: if __name__ == "__main__":
646:     unittest.main()

(End of file - total 646 lines)
</content>
```

**Tool: read**

**Input:**
```json
{
  "filePath": "/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_transport.py"
}
```

**Output:**
```
<path>/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_transport.py</path>
<type>file</type>
<content>
1: """Deterministic tests for KismetEventbusTransport.
2: 
3: No real network sockets or wall-clock sleeps are used.  Every helper
4: thread that is started is bounded-joined and explicitly asserted to
5: have terminated.
6: """
7: 
8: from __future__ import annotations
9: 
10: import ast
11: import json
12: import logging
13: import sys
14: import threading
15: import unittest
16: 
17: from kismet_eventbus_runtime_config import (
18:     KismetEventbusTransportConfigV1,
19:     KismetEventbusTransportConfigError,
20:     create_kismet_eventbus_transport_config,
21: )
22: from kismet_eventbus_transport import (
23:     KismetEventbusError,
24:     KismetEventbusTransport,
25: )
26: 
27: 
28: # Stub websocket module so config-built connections work in tests
29: # without installing websocket-client.
30: _STUB_WEBSOCKET = type(sys)("websocket")
31: _STUB_WEBSOCKET.create_connection = (
32:     lambda url, **kw: None  # type: ignore[assignment]
33: )
34: sys.modules["websocket"] = _STUB_WEBSOCKET
35: 
36: 
37: # ------------------------------------------------------------------
38: # Fake WebSocket for deterministic testing
39: # ------------------------------------------------------------------
40: 
41: class FakeWebSocket:
42:     """Simulates a WebSocket with controllable receive data."""
43: 
44:     def __init__(
45:         self,
46:         recv_data: list[str] | None = None,
47:         *,
48:         close_immediately: bool = False,
49:         expected_sends: int = 0,
50:     ) -> None:
51:         self.sent: list[str] = []
52:         self._recv_data: list[str] = list(recv_data or [])
53:         self._closed: bool = close_immediately
54:         self._recv_blocker = threading.Event()
55:         self.all_sent: threading.Event = threading.Event()
56:         self._expected_sends = expected_sends
57:         if close_immediately:
58:             self._recv_blocker.set()
59: 
60:     def send(self, data: str) -> None:
61:         self.sent.append(data)
62:         if self._expected_sends and len(self.sent) >= self._expected_sends:
63:             self.all_sent.set()
64: 
65:     def recv(self) -> str | None:
66:         if self._closed:
67:             return None
68:         if self._recv_data:
69:             return self._recv_data.pop(0)
70:         self._recv_blocker.wait()
71:         if self._closed:
72:             return None
73:         if self._recv_data:
74:             return self._recv_data.pop(0)
75:         return None
76: 
77:     def close(self) -> None:
78:         self._closed = True
79:         self._recv_blocker.set()
80: 
81:     @property
82:     def closed(self) -> bool:
83:         return self._closed
84: 
85: 
86: # ------------------------------------------------------------------
87: # Controlled thread seams for deterministic lifecycle boundaries
88: # ------------------------------------------------------------------
89: 
90: class _FailStartThread(threading.Thread):
91:     """Thread whose ``start()`` always raises without starting."""
92: 
93:     def start(self) -> None:
94:         raise RuntimeError("injected start failure")
95: 
96: 
97: class _TailBlockingThread(threading.Thread):
98:     """Thread that holds the run tail open after its target returns."""
99: 
100:     def __init__(
101:         self,
102:         *args: object,
103:         target_returned: threading.Event,
104:         release_thread_tail: threading.Event,
105:         **kwargs: object,
106:     ) -> None:
107:         super().__init__(*args, **kwargs)
108:         self._target_returned = target_returned
109:         self._release_thread_tail = release_thread_tail
110: 
111:     def run(self) -> None:
112:         super().run()
113:         self._target_returned.set()
114:         self._release_thread_tail.wait()
115: 
116: 
117: # ------------------------------------------------------------------
118: # Tests
119: # ------------------------------------------------------------------
120: 
121: class KismetEventbusTransportTests(unittest.TestCase):
122:     """KismetEventbusTransport — deterministic lifecycle tests."""
123: 
124:     maxDiff = None
125: 
126:     # --------------------------------------------------------------
127:     # Convenience helpers
128:     # --------------------------------------------------------------
129: 
130:     @staticmethod
131:     def _assertJoined(
132:         t: threading.Thread,
133:         timeout: float = 5.0,
134:     ) -> None:
135:         t.join(timeout=timeout)
136:         assert not t.is_alive(), (
137:             f"helper thread {t.name} did not terminate within {timeout}s"
138:         )
139: 
140:     @staticmethod
141:     def _fake_connect(url: str) -> FakeWebSocket:
142:         return FakeWebSocket()
143: 
144:     @staticmethod
145:     def _noop_waiter(se: threading.Event) -> None:
146:         return
147: 
148:     # --------------------------------------------------------------
149:     # 1. Importing the module performs no connection
150:     # --------------------------------------------------------------
151:     def test_import_performs_no_connection(self) -> None:
152:         with open("kismet_eventbus_transport.py") as f:
153:             tree = ast.parse(f.read())
154: 
155:         for stmt in tree.body:
156:             if isinstance(stmt, (ast.Import, ast.ImportFrom)):
157:                 names = (
158:                     [alias.name for alias in stmt.names]
159:                     if isinstance(stmt, ast.Import)
160:                     else []
161:                 )
162:                 module = (
163:                     stmt.module if isinstance(stmt, ast.ImportFrom) else ""
164:                 )
165:                 if "websocket" in module or any(
166:                     "websocket" in n for n in names
167:                 ):
168:                     self.fail("websocket imported at module level")
169: 
170:         found_lazy = False
171:         for node in ast.walk(tree):
172:             if isinstance(node, (ast.Import, ast.ImportFrom)):
173:                 names = (
174:                     [alias.name for alias in node.names]
175:                     if isinstance(node, ast.Import)
176:                     else []
177:                 )
178:                 module = (
179:                     node.module if isinstance(node, ast.ImportFrom) else ""
180:                 )
181:                 if "websocket" in module or any(
182:                     "websocket" in n for n in names
183:                 ):
184:                     found_lazy = True
185:                     break
186: 
187:         self.assertTrue(found_lazy, "no lazy websocket import found")
188: 
189:     # --------------------------------------------------------------
190:     # 2. HTTP and HTTPS URL conversion
191:     # --------------------------------------------------------------
192:     def test_http_url_conversion(self) -> None:
193:         transport = KismetEventbusTransport(
194:             "http://kismet.example.com",
195:             ("t",),
196:             lambda _: None,
197:             _create_connection=self._fake_connect,
198:             _reconnect_waiter=self._noop_waiter,
199:         )
200:         self.assertEqual(
201:             transport._ws_url,
202:             "ws://kismet.example.com/eventbus/events.ws",
203:         )
204: 
205:     def test_https_url_conversion(self) -> None:
206:         transport = KismetEventbusTransport(
207:             "https://kismet.example.com",
208:             ("t",),
209:             lambda _: None,
210:             _create_connection=self._fake_connect,
211:             _reconnect_waiter=self._noop_waiter,
212:         )
213:         self.assertEqual(
214:             transport._ws_url,
215:             "wss://kismet.example.com/eventbus/events.ws",
216:         )
217: 
218:     def test_url_conversion_preserves_port(self) -> None:
219:         transport = KismetEventbusTransport(
220:             "http://kismet.example.com:8080",
221:             ("t",),
222:             lambda _: None,
223:             _create_connection=self._fake_connect,
224:             _reconnect_waiter=self._noop_waiter,
225:         )
226:         self.assertEqual(
227:             transport._ws_url,
228:             "ws://kismet.example.com:8080/eventbus/events.ws",
229:         )
230: 
231:     # --------------------------------------------------------------
232:     # 3. Rejection of unsupported schemes, missing host,
233:     #    and embedded credentials
234:     # --------------------------------------------------------------
235:     def test_rejects_unsupported_scheme(self) -> None:
236:         with self.assertRaises(KismetEventbusError):
237:             KismetEventbusTransport(
238:                 "ftp://kismet.example.com",
239:                 ("t",),
240:                 lambda _: None,
241:             )
242: 
243:     def test_rejects_missing_host(self) -> None:
244:         with self.assertRaises(KismetEventbusError):
245:             KismetEventbusTransport(
246:                 "http:///path",
247:                 ("t",),
248:                 lambda _: None,
249:             )
250: 
251:     def test_rejects_embedded_credentials(self) -> None:
252:         with self.assertRaises(KismetEventbusError):
253:             KismetEventbusTransport(
254:                 "http://user:pass@kismet.example.com",
255:                 ("t",),
256:                 lambda _: None,
257:             )
258: 
259:     # --------------------------------------------------------------
260:     # 4. Deterministic subscription frames and order
261:     # --------------------------------------------------------------
262:     def test_subscription_frames_in_order(self) -> None:
263:         ws = FakeWebSocket(expected_sends=3)
264:         transport = KismetEventbusTransport(
265:             "http://example.com",
266:             ("gamma", "alpha", "beta"),
267:             lambda _: None,
268:             _create_connection=lambda url: ws,
269:             _reconnect_waiter=self._noop_waiter,
270:         )
271:         transport.start()
272:         self.assertTrue(ws.all_sent.wait(timeout=5))
273:         self.assertEqual(
274:             ws.sent,
275:             [
276:                 json.dumps(
277:                     {"SUBSCRIBE": "gamma"},
278:                     separators=(",", ":"),
279:                 ),
280:                 json.dumps(
281:                     {"SUBSCRIBE": "alpha"},
282:                     separators=(",", ":"),
283:                 ),
284:                 json.dumps(
285:                     {"SUBSCRIBE": "beta"},
286:                     separators=(",", ":"),
287:                 ),
288:             ],
289:         )
290:         transport.stop()
291:         self.assertIsNone(transport._thread)
292: 
293:     def test_subscription_deduplicates(self) -> None:
294:         ws = FakeWebSocket(expected_sends=2)
295:         transport = KismetEventbusTransport(
296:             "http://example.com",
297:             ("topic", "topic", "other"),
298:             lambda _: None,
299:             _create_connection=lambda url: ws,
300:             _reconnect_waiter=self._noop_waiter,
301:         )
302:         transport.start()
303:         self.assertTrue(ws.all_sent.wait(timeout=5))
304:         self.assertEqual(len(ws.sent), 2)
305:         self.assertIn(
306:             json.dumps({"SUBSCRIBE": "topic"}, separators=(",", ":")),
307:             ws.sent,
308:         )
309:         transport.stop()
310:         self.assertIsNone(transport._thread)
311: 
312:     def test_rejects_empty_topic(self) -> None:
313:         with self.assertRaises(KismetEventbusError):
314:             KismetEventbusTransport(
315:                 "http://example.com",
316:                 ("",),
317:                 lambda _: None,
318:             )
319: 
320:     def test_rejects_all_empty_topics(self) -> None:
321:         with self.assertRaises(KismetEventbusError):
322:             KismetEventbusTransport(
323:                 "http://example.com",
324:                 ("", ""),
325:                 lambda _: None,
326:             )
327: 
328:     # --------------------------------------------------------------
329:     # 5. Structured topic payload dispatch
330:     # --------------------------------------------------------------
331:     def test_dispatches_structured_payload(self) -> None:
332:         received: list[dict] = []
333:         event = threading.Event()
334: 
335:         def handler(msg: dict) -> None:
336:             received.append(msg)
337:             event.set()
338: 
339:         ws = FakeWebSocket(
340:             recv_data=[
341:                 '{"kismet":{"topic":"test","data":123}}',
342:             ],
343:         )
344:         transport = KismetEventbusTransport(
345:             "http://example.com",
346:             ("t",),
347:             handler,
348:             _create_connection=lambda url: ws,
349:             _reconnect_waiter=self._noop_waiter,
350:         )
351:         transport.start()
352:         event.wait(timeout=5)
353:         transport.stop()
354:         self.assertEqual(
355:             received,
356:             [{"kismet": {"topic": "test", "data": 123}}],
357:         )
358: 
359:     # --------------------------------------------------------------
360:     # 5b. Kismet topic-keyed envelope dispatch (proven protocol)
361:     # --------------------------------------------------------------
362:     def test_dispatches_topic_keyed_envelope(self) -> None:
363:         received: list[dict] = []
364:         event = threading.Event()
365: 
366:         def handler(msg: dict) -> None:
367:             received.append(msg)
368:             event.set()
369: 
370:         ws = FakeWebSocket(
371:             recv_data=[
372:                 '{"TIMESTAMP": {"kismet.system.timestamp.sec": 1}}',
373:             ],
374:         )
375:         transport = KismetEventbusTransport(
376:             "http://example.com",
377:             ("t",),
378:             handler,
379:             _create_connection=lambda url: ws,
380:             _reconnect_waiter=self._noop_waiter,
381:         )
382:         transport.start()
383:         event.wait(timeout=5)
384:         transport.stop()
385:         self.assertEqual(
386:             received,
387:             [{"TIMESTAMP": {"kismet.system.timestamp.sec": 1}}],
388:         )
389: 
390:     # --------------------------------------------------------------
391:     # 6. Malformed JSON is dropped
392:     # --------------------------------------------------------------
393:     def test_malformed_json_is_dropped(self) -> None:
394:         received: list[dict] = []
395:         event = threading.Event()
396: 
397:         def handler(msg: dict) -> None:
398:             received.append(msg)
399:             event.set()
400: 
401:         ws = FakeWebSocket(
402:             recv_data=[
403:                 "not json",
404:                 '{"valid":true}',
405:             ],
406:         )
407:         transport = KismetEventbusTransport(
408:             "http://example.com",
409:             ("t",),
410:             handler,
411:             _create_connection=lambda url: ws,
412:             _reconnect_waiter=self._noop_waiter,
413:         )
414:         transport.start()
415:         event.wait(timeout=5)
416:         transport.stop()
417:         self.assertEqual(received, [{"valid": True}])
418: 
419:     # --------------------------------------------------------------
420:     # 7. JSON arrays/scalars are dropped
421:     # --------------------------------------------------------------
422:     def test_non_object_frames_are_dropped(self) -> None:
423:         received: list[dict] = []
424:         event = threading.Event()
425: 
426:         def handler(msg: dict) -> None:
427:             received.append(msg)
428:             event.set()
429: 
430:         ws = FakeWebSocket(
431:             recv_data=[
432:                 '["array"]',
433:                 "42",
434:                 '"string"',
435:                 "true",
436:                 "null",
437:                 '{"valid":true}',
438:             ],
439:         )
440:         transport = KismetEventbusTransport(
441:             "http://example.com",
442:             ("t",),
443:             handler,
444:             _create_connection=lambda url: ws,
445:             _reconnect_waiter=self._noop_waiter,
446:         )
447:         transport.start()
448:         event.wait(timeout=5)
449:         transport.stop()
450:         self.assertEqual(received, [{"valid": True}])
451: 
452:     # --------------------------------------------------------------
453:     # 8. One handler exception does not block the next event
454:     # --------------------------------------------------------------
455:     def test_handler_exception_isolation(self) -> None:
456:         received: list[dict] = []
457:         event = threading.Event()
458: 
459:         def handler(msg: dict) -> None:
460:             if msg.get("fail"):
461:                 raise ValueError("handler error")
462:             received.append(msg)
463:             event.set()
464: 
465:         ws = FakeWebSocket(
466:             recv_data=[
467:                 '{"fail":true}',
468:                 '{"ok":true}',
469:             ],
470:         )
471:         transport = KismetEventbusTransport(
472:             "http://example.com",
473:             ("t",),
474:             handler,
475:             _create_connection=lambda url: ws,
476:             _reconnect_waiter=self._noop_waiter,
477:         )
478:         transport.start()
479:         event.wait(timeout=5)
480:         transport.stop()
481:         self.assertEqual(received, [{"ok": True}])
482: 
483:     # --------------------------------------------------------------
484:     # 9. Connection closure causes one controlled reconnect,
485:     #    signalled by connector-created Events for first and
486:     #    second connection creation.
487:     # --------------------------------------------------------------
488:     def test_connection_closure_triggers_reconnect(self) -> None:
489:         connections: list[FakeWebSocket] = []
490:         connect_events: list[threading.Event] = [
491:             threading.Event(),
492:             threading.Event(),
493:         ]
494:         connect_index: list[int] = [0]
495: 
496:         def create_conn(url: str) -> FakeWebSocket:
497:             is_first = len(connections) == 0
498:             ws = FakeWebSocket(close_immediately=is_first)
499:             connections.append(ws)
500:             i = connect_index[0]
501:             connect_index[0] += 1
502:             connect_events[i].set()
503:             return ws
504: 
505:         def waiter(se: threading.Event) -> None:
506:             return
507: 
508:         transport = KismetEventbusTransport(
509:             "http://example.com",
510:             ("t",),
511:             lambda _: None,
512:             _create_connection=create_conn,
513:             _reconnect_waiter=waiter,
514:         )
515:         transport.start()
516:         self.assertTrue(connect_events[0].wait(timeout=5))
517:         self.assertTrue(connect_events[1].wait(timeout=5))
518:         transport.stop()
519:         self.assertEqual(len(connections), 2)
520:         self.assertIsNone(transport._thread)
521: 
522:     # --------------------------------------------------------------
523:     # 10. Reconnect waiting is interrupted by stop()
524:     # --------------------------------------------------------------
525:     def test_stop_interrupts_reconnect_wait(self) -> None:
526:         waiter_entered = threading.Event()
527:         waiter_exited = threading.Event()
528: 
529:         def waiter(se: threading.Event) -> None:
530:             waiter_entered.set()
531:             se.wait()  # blocks until stop() sets the generation event
532:             waiter_exited.set()
533: 
534:         transport = KismetEventbusTransport(
535:             "http://example.com",
536:             ("t",),
537:             lambda _: None,
538:             _create_connection=lambda url: FakeWebSocket(
539:                 close_immediately=True,
540:             ),
541:             _reconnect_waiter=waiter,
542:         )
543:         transport.start()
544:         self.assertTrue(waiter_entered.wait(timeout=5))
545:         transport.stop()
546:         self.assertTrue(waiter_exited.wait(timeout=5))
547:         self.assertIsNone(transport._thread)
548: 
549:     # --------------------------------------------------------------
550:     # 11. Double start creates only one worker
551:     # --------------------------------------------------------------
552:     def test_double_start_creates_one_worker(self) -> None:
553:         ws = FakeWebSocket(expected_sends=1)
554:         create_count: list[int] = [0]
555: 
556:         def create_conn(url: str) -> FakeWebSocket:
557:             create_count[0] += 1
558:             return ws
559: 
560:         transport = KismetEventbusTransport(
561:             "http://example.com",
562:             ("t",),
563:             lambda _: None,
564:             _create_connection=create_conn,
565:             _reconnect_waiter=self._noop_waiter,
566:         )
567:         transport.start()
568:         transport.start()  # second start — must be no-op
569:         self.assertTrue(ws.all_sent.wait(timeout=5))
570:         transport.stop()
571:         self.assertEqual(create_count[0], 1)
572:         self.assertIsNone(transport._thread)
573: 
574:     # --------------------------------------------------------------
575:     # 12. stop() before start() is safe
576:     # --------------------------------------------------------------
577:     def test_stop_before_start_is_safe(self) -> None:
578:         transport = KismetEventbusTransport(
579:             "http://example.com",
580:             ("t",),
581:             lambda _: None,
582:             _create_connection=self._fake_connect,
583:             _reconnect_waiter=self._noop_waiter,
584:         )
585:         # Should not raise
586:         transport.stop()
587:         transport.stop()  # second call also safe
588: 
589:     # --------------------------------------------------------------
590:     # 13. stop() closes the current socket and leaves the client
591:     #     stopped
592:     # --------------------------------------------------------------
593:     def test_stop_closes_socket_and_leaves_stopped(self) -> None:
594:         ws = FakeWebSocket(expected_sends=1)
595:         transport = KismetEventbusTransport(
596:             "http://example.com",
597:             ("t",),
598:             lambda _: None,
599:             _create_connection=lambda url: ws,
600:             _reconnect_waiter=self._noop_waiter,
601:         )
602:         transport.start()
603:         self.assertTrue(ws.all_sent.wait(timeout=5))
604:         thread = transport._thread
605:         transport.stop()
606:         self.assertTrue(ws.closed)
607:         self.assertFalse(thread.is_alive())
608:         self.assertIsNone(transport._thread)
609: 
610:     # --------------------------------------------------------------
611:     # 14. No reconnect occurs after stop()
612:     # --------------------------------------------------------------
613:     def test_no_reconnect_after_stop(self) -> None:
614:         waiter_called = threading.Event()
615: 
616:         def waiter(se: threading.Event) -> None:
617:             waiter_called.set()
618:             se.wait()
619: 
620:         transport = KismetEventbusTransport(
621:             "http://example.com",
622:             ("t",),
623:             lambda _: None,
624:             _create_connection=lambda url: FakeWebSocket(),
625:             _reconnect_waiter=waiter,
626:         )
627:         transport.start()
628:         transport.stop()
629:         # Worker should have exited before any reconnect wait
630:         self.assertFalse(waiter_called.is_set())
631:         self.assertIsNone(transport._thread)
632: 
633:     # --------------------------------------------------------------
634:     # 15. Captured logs contain no password, Authorization value,
635:     #     payload contents, or injected exception text
636:     # --------------------------------------------------------------
637:     def test_logs_contain_no_sensitive_data(self) -> None:
638:         import io
639: 
640:         received: list[dict] = []
641:         event = threading.Event()
642: 
643:         def handler(msg: dict) -> None:
644:             received.append(msg)
645:             event.set()
646: 
647:         ws = FakeWebSocket(
648:             recv_data=[
649:                 '{"sensitive":"payload-data"}',
650:             ],
651:         )
652: 
653:         transport = KismetEventbusTransport(
654:             "http://example.com",
655:             ("t",),
656:             handler,
657:             _create_connection=lambda url: ws,
658:             _reconnect_waiter=self._noop_waiter,
659:         )
660: 
661:         logger = logging.getLogger("kismet_eventbus_transport")
662:         previous_level = logger.level
663:         stream = io.StringIO()
664:         handler_cap = logging.StreamHandler(stream)
665:         handler_cap.setLevel(logging.DEBUG)
666:         logger.addHandler(handler_cap)
667:         logger.setLevel(logging.DEBUG)
668: 
669:         try:
670:             transport.start()
671:             event.wait(timeout=5)
672:             transport.stop()
673:         finally:
674:             logger.removeHandler(handler_cap)
675:             logger.setLevel(previous_level)
676: 
677:         all_output = stream.getvalue()
678:         self.assertNotIn("password", all_output)
679:         self.assertNotIn("Authorization", all_output)
680:         self.assertNotIn("payload-data", all_output)
681:         self.assertNotIn("handler error", all_output)
682: 
683:     # --------------------------------------------------------------
684:     # 16. Static import checks prove no forbidden
685:     #     application-layer imports
686:     # --------------------------------------------------------------
687:     def test_no_forbidden_imports(self) -> None:
688:         forbidden_prefixes = (
689:             "observation",
690:             "route_session",
691:             "bounded_gps",
692:             "chasing_your_tail",
693:             "cyt_gui",
694:             "probe_analyzer",
695:             "surveillance",
696:             "gps_tracker",
697:             "flask",
698:             "socketio",
699:         )
700: 
701:         with open("kismet_eventbus_transport.py") as f:
702:             tree = ast.parse(f.read())
703: 
704:         for node in ast.walk(tree):
705:             if isinstance(node, ast.Import):
706:                 for alias in node.names:
707:                     for prefix in forbidden_prefixes:
708:                         self.assertNotIn(
709:                             prefix,
710:                             alias.name,
711:                             (
712:                                 f"forbidden import '{alias.name}' "
713:                                 f"matches prefix '{prefix}'"
714:                             ),
715:                         )
716:             elif isinstance(node, ast.ImportFrom):
717:                 module = node.module or ""
718:                 for prefix in forbidden_prefixes:
719:                     self.assertNotIn(
720:                         prefix,
721:                         module,
722:                         (
723:                             f"forbidden import from '{module}' "
724:                             f"matches prefix '{prefix}'"
725:                         ),
726:                     )
727: 
728:     # --------------------------------------------------------------
729:     # 17. Immediate stop followed by start creates a new worker
730:     # --------------------------------------------------------------
731:     def test_stop_then_start_creates_new_worker(self) -> None:
732:         wss: list[FakeWebSocket] = []
733: 
734:         def create(url: str) -> FakeWebSocket:
735:             ws = FakeWebSocket(expected_sends=1)
736:             wss.append(ws)
737:             return ws
738: 
739:         transport = KismetEventbusTransport(
740:             "http://example.com",
741:             ("t",),
742:             lambda _: None,
743:             _create_connection=create,
744:             _reconnect_waiter=self._noop_waiter,
745:         )
746:         transport.start()
747:         self.assertEqual(len(wss), 1)
748:         self.assertTrue(wss[0].all_sent.wait(timeout=5))
749:         thread_1 = transport._thread
750:         transport.stop()
751:         self.assertFalse(thread_1.is_alive())
752: 
753:         transport.start()
754:         self.assertEqual(len(wss), 2)
755:         thread_2 = transport._thread
756:         self.assertIsNotNone(thread_2)
757:         self.assertIsNot(thread_2, thread_1)
758:         transport.stop()
759:         self.assertFalse(thread_2.is_alive())
760: 
761:     # --------------------------------------------------------------
762:     # 18. Subscription send failure enters reconnect path;
763:     #     reconnect is awaited via an explicit second-connection
764:     #     Event, not inferred from waiter entry.
765:     # --------------------------------------------------------------
766:     def test_send_failure_triggers_reconnect(self) -> None:
767:         connections: list[FakeWebSocket] = []
768:         connect_events: list[threading.Event] = [
769:             threading.Event(),
770:             threading.Event(),
771:         ]
772:         connect_index: list[int] = [0]
773: 
774:         def create_conn(url: str) -> FakeWebSocket:
775:             is_first = len(connections) == 0
776:             if is_first:
777:                 ws = FakeWebSocket(expected_sends=1)
778: 
779:                 def fail_send(data: str) -> None:
780:                     raise ConnectionError("send failed")
781: 
782:                 ws.send = fail_send  # type: ignore[assignment]
783:             else:
784:                 ws = FakeWebSocket(expected_sends=1)
785:             connections.append(ws)
786:             i = connect_index[0]
787:             connect_index[0] += 1
788:             connect_events[i].set()
789:             return ws
790: 
791:         def waiter(se: threading.Event) -> None:
792:             return
793: 
794:         transport = KismetEventbusTransport(
795:             "http://example.com",
796:             ("t",),
797:             lambda _: None,
798:             _create_connection=create_conn,
799:             _reconnect_waiter=waiter,
800:         )
801:         transport.start()
802:         self.assertTrue(connect_events[0].wait(timeout=5))
803:         self.assertTrue(connect_events[1].wait(timeout=5))
804:         transport.stop()
805:         self.assertEqual(len(connections), 2)
806:         self.assertIsNone(transport._thread)
807: 
808:     # --------------------------------------------------------------
809:     # 19. Bounded stop failure preserves live thread reference
810:     # --------------------------------------------------------------
811:     def test_bounded_stop_failure_preserves_thread(self) -> None:
812:         waiter_entered = threading.Event()
813:         release_worker = threading.Event()
814: 
815:         def waiter(se: threading.Event) -> None:
816:             waiter_entered.set()
817:             release_worker.wait()
818: 
819:         transport = KismetEventbusTransport(
820:             "http://example.com",
821:             ("t",),
822:             lambda _: None,
823:             _create_connection=lambda url: FakeWebSocket(
824:                 close_immediately=True,
825:             ),
826:             _reconnect_waiter=waiter,
827:         )
828:         transport._STOP_JOIN_TIMEOUT_S = 0.2
829: 
830:         transport.start()
831:         self.assertTrue(waiter_entered.wait(timeout=5))
832: 
833:         thread_before = transport._thread
834:         stop_event_before = transport._stop_event
835:         self.assertIsNotNone(thread_before)
836:         self.assertIsNotNone(stop_event_before)
837:         self.assertTrue(thread_before.is_alive())
838: 
839:         with self.assertRaises(KismetEventbusError):
840:             transport.stop()
841: 
842:         # Bounded-stop failure must retain the live worker reference
843:         # and that worker's generation stop event.
844:         self.assertIs(transport._thread, thread_before)
845:         self.assertIs(transport._stop_event, stop_event_before)
846:         self.assertTrue(thread_before.is_alive())
847:         self.assertTrue(stop_event_before.is_set())
848: 
849:         # After releasing the bounded-stop blocker, call stop() again
850:         # and prove clean termination and cleared worker state.
851:         release_worker.set()
852:         transport.stop()
853:         self.assertFalse(thread_before.is_alive())
854:         self.assertIsNone(transport._thread)
855:         self.assertIsNone(transport._stop_event)
856: 
857:     # --------------------------------------------------------------
858:     # 20. Concurrent start/stop never exposes a not-yet-started
859:     #     thread to join(), forced with an injected thread-creation
860:     #     seam rather than repeated scheduling luck.
861:     # --------------------------------------------------------------
862:     def test_concurrent_start_stop_no_unstarted_join(self) -> None:
863:         published = threading.Event()
864:         allow_start = threading.Event()
865:         started_real = threading.Event()
866: 
867:         ws = FakeWebSocket(expected_sends=1)
868: 
869:         class _WatchingThread(threading.Thread):
870:             def start(self) -> None:
871:                 published.set()
872:                 allow_start.wait()
873:                 super().start()
874:                 started_real.set()
875: 
876:         def factory(**kwargs: object) -> threading.Thread:
877:             return _WatchingThread(**kwargs)
878: 
879:         transport = KismetEventbusTransport(
880:             "http://example.com",
881:             ("t",),
882:             lambda _: None,
883:             _create_connection=lambda url: ws,
884:             _reconnect_waiter=self._noop_waiter,
885:             _thread_factory=factory,
886:         )
887: 
888:         start_errors: list[BaseException] = []
889:         start_done = threading.Event()
890: 
891:         def do_start() -> None:
892:             try:
893:                 transport.start()
894:             except BaseException as exc:  # noqa: BLE001
895:                 start_errors.append(exc)
896:             finally:
897:                 start_done.set()
898: 
899:         stop_done = threading.Event()
900:         stop_errors: list[BaseException] = []
901: 
902:         def do_stop() -> None:
903:             try:
904:                 transport.stop()
905:             except BaseException as exc:  # noqa: BLE001
906:                 stop_errors.append(exc)
907:             finally:
908:                 stop_done.set()
909: 
910:         starter = threading.Thread(
911:             target=do_start, daemon=True, name="start-helper"
912:         )
913:         stopper = threading.Thread(
914:             target=do_stop, daemon=True, name="stop-helper"
915:         )
916:         worker_ref: list[threading.Thread | None] = [None]
917: 
918:         try:
919:             starter.start()
920:             # Forced boundary: start() has published ``_thread`` and is
921:             # now blocked inside the thread-creation seam, still holding
922:             # the instance lock.
923:             self.assertTrue(published.wait(timeout=5))
924:             worker_ref[0] = transport._thread
925:             self.assertIsNotNone(worker_ref[0])
926:             self.assertFalse(started_real.is_set())
927: 
928:             # Launch stop() while the boundary exists.  It must block on
929:             # the lock start() still holds, so it can never join() the
930:             # unstarted thread.
931:             stopper.start()
932: 
933:             # Release the real start; start() returns the lock, the
934:             # worker actually starts, then stopper acquires the lock and
935:             # captures an already-started worker to join.
936:             allow_start.set()
937:             self.assertTrue(started_real.wait(timeout=5))
938:             self.assertTrue(start_done.wait(timeout=5))
939:             self.assertEqual(start_errors, [])
940:             self.assertTrue(stop_done.wait(timeout=5))
941:             self.assertEqual(stop_errors, [])
942:         finally:
943:             allow_start.set()
944:             self._assertJoined(starter)
945:             self._assertJoined(stopper)
946: 
947:         # The captured worker was actually started (not an unstarted
948:         # shell) and was driven to a clean stop by the concurrent stop.
949:         self.assertIsNotNone(worker_ref[0])
950:         self._assertJoined(worker_ref[0])
951:         self.assertIsNone(transport._thread)
952:         self.assertIsNone(transport._stop_event)
953: 
954:     # --------------------------------------------------------------
955:     # 21. Self-stop from a handler preserves _thread until the
956:     #     worker actually exits
957:     # --------------------------------------------------------------
958:     def test_self_stop_preserves_thread_until_exit(self) -> None:
959:         handler_done = threading.Event()
960:         worker_exited = threading.Event()
961:         observations: list[threading.Thread | None] = []
962: 
963:         def handler(msg: dict) -> None:
964:             observations.append(transport._thread)
965:             transport.stop()  # self-stop from a handler
966:             observations.append(transport._thread)
967:             handler_done.set()
968: 
969:         transport = KismetEventbusTransport(
970:             "http://example.com",
971:             ("t",),
972:             handler,
973:             _create_connection=lambda url: FakeWebSocket(
974:                 recv_data=['{"x":1}'],
975:             ),
976:             _reconnect_waiter=self._noop_waiter,
977:         )
978:         original_worker = transport._worker
979: 
980:         def wrapped(se: threading.Event) -> None:
981:             try:
982:                 original_worker(se)
983:             finally:
984:                 worker_exited.set()
985: 
986:         transport._worker = wrapped  # type: ignore[method-assign]
987:         transport.start()
988:         thread_ref = transport._thread
989:         stop_event_ref = transport._stop_event
990:         self.assertIsNotNone(thread_ref)
991:         self.assertIsNotNone(stop_event_ref)
992:         self.assertTrue(handler_done.wait(timeout=5))
993:         # During the handler (before and after self-stop), _thread is
994:         # still the live worker; self-stop does not join or clear it.
995:         self.assertIs(observations[0], thread_ref)
996:         self.assertIs(observations[1], thread_ref)
997:         self.assertTrue(worker_exited.wait(timeout=5))
998:         # After actual worker exit, the outer finally clears _thread and
999:         # the generation stop event.
1000:         self.assertIsNone(transport._thread)
1001:         self.assertIsNone(transport._stop_event)
1002:         # Bounded join on the captured worker before asserting death.
1003:         self._assertJoined(thread_ref)
1004:         self.assertFalse(thread_ref.is_alive())
1005: 
1006:     # --------------------------------------------------------------
1007:     # 22. A start request during self-stop cannot overlap a
1008:     #     second worker, and proves no new worker is created while
1009:     #     a retiring earlier thread is still actually alive.
1010:     # --------------------------------------------------------------
1011:     def test_start_during_self_stop_cannot_overlap(self) -> None:
1012:         in_handler = threading.Event()
1013:         release_handler = threading.Event()
1014:         worker_exited = threading.Event()
1015:         create_count: list[int] = [0]
1016: 
1017:         def handler(msg: dict) -> None:
1018:             in_handler.set()
1019:             transport.stop()  # self-stop
1020:             release_handler.wait()
1021: 
1022:         def create(url: str) -> FakeWebSocket:
1023:             create_count[0] += 1
1024:             return FakeWebSocket(recv_data=['{"x":1}'])
1025: 
1026:         def wrapped(se: threading.Event) -> None:
1027:             try:
1028:                 original_worker(se)
1029:             finally:
1030:                 worker_exited.set()
1031: 
1032:         transport = KismetEventbusTransport(
1033:             "http://example.com",
1034:             ("t",),
1035:             handler,
1036:             _create_connection=create,
1037:             _reconnect_waiter=self._noop_waiter,
1038:         )
1039:         original_worker = transport._worker
1040:         transport._worker = wrapped  # type: ignore[method-assign]
1041:         transport.start()
1042:         orig_thread = transport._thread
1043:         orig_stop_event = transport._stop_event
1044:         self.assertIsNotNone(orig_thread)
1045:         self.assertIsNotNone(orig_stop_event)
1046:         self.assertTrue(in_handler.wait(timeout=5))
1047: 
1048:         # Worker is alive inside the handler (self-stopped). A
1049:         # concurrent start request from another thread must NOT spawn
1050:         # a 2nd worker while the retiring earlier thread is alive.
1051:         starter_done = threading.Event()
1052: 
1053:         def attempt_start() -> None:
1054:             transport.start()
1055:             starter_done.set()
1056: 
1057:         t = threading.Thread(target=attempt_start)
1058:         t.start()
1059:         self._assertJoined(t)
1060:         self.assertTrue(starter_done.is_set())
1061:         self.assertIs(transport._thread, orig_thread)
1062:         self.assertIs(transport._stop_event, orig_stop_event)
1063:         self.assertTrue(orig_thread.is_alive())
1064:         # No second connection was ever created while A was alive.
1065:         self.assertEqual(create_count[0], 1)
1066: 
1067:         release_handler.set()
1068:         self.assertTrue(worker_exited.wait(timeout=5))
1069:         self.assertIsNone(transport._thread)
1070:         self.assertIsNone(transport._stop_event)
1071:         self._assertJoined(orig_thread)
1072:         self.assertFalse(orig_thread.is_alive())
1073: 
1074:     # --------------------------------------------------------------
1075:     # 23. Worker generation regression: a worker tail that has
1076:     #     returned from its target but has not yet exited the Python
1077:     #     Thread bootstrap tail still blocks new generations and
1078:     #     remains stoppable.
1079:     # --------------------------------------------------------------
1080:     def test_thread_run_tail_blocks_start_and_stop(self) -> None:
1081:         target_returned = threading.Event()
1082:         release_thread_tail = threading.Event()
1083:         stop_entered = threading.Event()
1084:         stop_finished = threading.Event()
1085:         create_count: list[int] = [0]
1086:         created_threads: list[threading.Thread] = []
1087:         self_stop_enabled = threading.Event()
1088:         self_stop_enabled.set()
1089: 
1090:         def handler(msg: dict) -> None:
1091:             if self_stop_enabled.is_set():
1092:                 transport.stop()
1093: 
1094:         def create(url: str) -> FakeWebSocket:
1095:             create_count[0] += 1
1096:             return FakeWebSocket(recv_data=['{"x":1}'])
1097: 
1098:         def factory(**kwargs: object) -> threading.Thread:
1099:             if len(created_threads) == 0:
1100:                 thread: threading.Thread = _TailBlockingThread(
1101:                     target_returned=target_returned,
1102:                     release_thread_tail=release_thread_tail,
1103:                     **kwargs,
1104:                 )
1105:             else:
1106:                 thread = threading.Thread(**kwargs)
1107:             created_threads.append(thread)
1108:             return thread
1109: 
1110:         transport = KismetEventbusTransport(
1111:             "http://example.com",
1112:             ("t",),
1113:             handler,
1114:             _create_connection=create,
1115:             _reconnect_waiter=self._noop_waiter,
1116:             _thread_factory=factory,
1117:         )
1118: 
1119:         transport.start()
1120:         a_thread = transport._thread
1121:         a_stop_event = transport._stop_event
1122:         self.assertIsNotNone(a_thread)
1123:         self.assertIsNotNone(a_stop_event)
1124:         self.assertTrue(target_returned.wait(timeout=5))
1125:         self.assertIsNone(transport._thread)
1126:         self.assertIs(transport._retiring_thread, a_thread)
1127:         self.assertIs(transport._retiring_stop_event, a_stop_event)
1128:         self.assertTrue(a_thread.is_alive())
1129:         self.assertEqual(create_count[0], 1)
1130: 
1131:         # While A is in the thread tail, a new start must not create B.
1132:         transport.start()
1133:         self.assertEqual(create_count[0], 1)
1134:         self.assertIs(transport._retiring_thread, a_thread)
1135:         self.assertTrue(a_thread.is_alive())
1136: 
1137:         def do_stop() -> None:
1138:             stop_entered.set()
1139:             try:
1140:                 transport.stop()
1141:             finally:
1142:                 stop_finished.set()
1143: 
1144:         stop_thread = threading.Thread(
1145:             target=do_stop,
1146:             daemon=True,
1147:             name="tail-stop",
1148:         )
1149:         stop_thread.start()
1150:         self.assertTrue(stop_entered.wait(timeout=5))
1151:         self.assertFalse(stop_finished.is_set())
1152: 
1153:         release_thread_tail.set()
1154:         self._assertJoined(a_thread)
1155:         self.assertTrue(stop_finished.wait(timeout=5))
1156:         self._assertJoined(stop_thread)
1157: 
1158:         self_stop_enabled.clear()
1159:         self.assertIsNone(transport._thread)
1160:         self.assertIsNone(transport._stop_event)
1161:         self.assertIsNone(transport._retiring_thread)
1162:         self.assertIsNone(transport._retiring_stop_event)
1163: 
1164:         transport.start()
1165:         self.assertEqual(create_count[0], 2)
1166:         b_thread = transport._thread
1167:         self.assertIsNotNone(b_thread)
1168:         transport.stop()
1169:         self._assertJoined(b_thread)
1170:         self.assertIsNone(transport._thread)
1171:         self.assertIsNone(transport._stop_event)
1172:         self.assertIsNone(transport._retiring_thread)
1173:         self.assertIsNone(transport._retiring_stop_event)
1174: 
1175:     # --------------------------------------------------------------
1176:     # 24. Worker generation regression: an injected
1177:     #     ``Thread.start()`` failure leaves no unstarted thread
1178:     #     published, stop() remains safe, and a later valid
1179:     #     ``start()`` succeeds.
1180:     # --------------------------------------------------------------
1181:     def test_thread_start_failure_rolls_back_state(self) -> None:
1182:         ws = FakeWebSocket(expected_sends=1)
1183: 
1184:         def factory(**kwargs: object) -> threading.Thread:
1185:             return _FailStartThread(**kwargs)
1186: 
1187:         transport = KismetEventbusTransport(
1188:             "http://example.com",
1189:             ("t",),
1190:             lambda _: None,
1191:             _create_connection=lambda url: ws,
1192:             _reconnect_waiter=self._noop_waiter,
1193:             _thread_factory=factory,
1194:         )
1195: 
1196:         with self.assertRaises(RuntimeError):
1197:             transport.start()
1198: 
1199:         # No unstarted thread remains published; worker state is clean.
1200:         self.assertIsNone(transport._thread)
1201:         self.assertIsNone(transport._stop_event)
1202: 
1203:         # stop() remains safe (idempotent after failed start).
1204:         transport.stop()
1205:         self.assertIsNone(transport._thread)
1206:         self.assertIsNone(transport._stop_event)
1207: 
1208:         # A later valid start() can succeed with a real factory.
1209:         transport._thread_factory = threading.Thread  # type: ignore[assignment]
1210:         transport.start()
1211:         self.assertTrue(ws.all_sent.wait(timeout=5))
1212:         thread_ref = transport._thread
1213:         self.assertIsNotNone(thread_ref)
1214:         transport.stop()
1215:         self._assertJoined(thread_ref)
1216:         self.assertIsNone(transport._thread)
1217:         self.assertIsNone(transport._stop_event)
1218: 
1219:     # --------------------------------------------------------------
1220:     # 24. Worker generation regression: a delayed stop that
1221:     #     captured worker A can never signal, close, clear, or
1222:     #     terminate a later worker B.
1223:     # --------------------------------------------------------------
1224:     def test_delayed_stop_cannot_touch_newer_generation(self) -> None:
1225:         # A: blocks in the reconnect waiter until released, then exits
1226:         # because its own (captured) stop event was set.
1227:         a_in_waiter = threading.Event()
1228:         release_a = threading.Event()
1229: 
1230:         def a_waiter(se: threading.Event) -> None:
1231:             a_in_waiter.set()
1232:             release_a.wait()
1233:             # Wait until the delayed stop has set A's stop event.
1234:             se.wait()
1235: 
1236:         transport = KismetEventbusTransport(
1237:             "http://example.com",
1238:             ("t",),
1239:             lambda _: None,
1240:             _create_connection=lambda url: FakeWebSocket(
1241:                 close_immediately=True,
1242:             ),
1243:             _reconnect_waiter=a_waiter,
1244:         )
1245:         transport.start()
1246:         self.assertTrue(a_in_waiter.wait(timeout=5))
1247: 
1248:         a_thread = transport._thread
1249:         a_stop_event = transport._stop_event
1250:         self.assertIsNotNone(a_thread)
1251:         self.assertIsNotNone(a_stop_event)
1252:         self.assertIs(a_thread, transport._thread)
1253: 
1254:         # Gate the delayed stop after it bounded-joins A but before it
1255:         # runs its identity-safe clear block, so B can start in between.
1256:         after_join_a = threading.Event()
1257:         proceed_stop = threading.Event()
1258: 
1259:         def stop_after_join(
1260:             worked: threading.Thread, sev: threading.Event
1261:         ) -> None:
1262:             after_join_a.set()
1263:             proceed_stop.wait()
1264: 
1265:         transport._stop_after_join = stop_after_join  # type: ignore[assignment]
1266: 
1267:         old_stop_done = threading.Event()
1268: 
1269:         def do_old_stop() -> None:
1270:             transport.stop()
1271:             old_stop_done.set()
1272: 
1273:         old_stop_thread = threading.Thread(
1274:             target=do_old_stop, daemon=True, name="old-stop"
1275:         )
1276:         old_stop_thread.start()
1277: 
1278:         try:
1279:             # Release A so it can retire once the delayed stop set A's
1280:             # stop event and the bounded join returns.
1281:             release_a.set()
1282:             self.assertTrue(after_join_a.wait(timeout=5))
1283:             self._assertJoined(a_thread)
1284:             # After A finalized, _thread is None and old stop is paused.
1285:             self.assertIsNone(transport._thread)
1286:             self.assertFalse(old_stop_done.is_set())
1287: 
1288:             # Now start a second generation worker B with its own
1289:             # socket and its own stop event, blocked in its recv loop.
1290:             b_ws = FakeWebSocket(expected_sends=1)
1291: 
1292:             def b_create(url: str) -> FakeWebSocket:
1293:                 return b_ws
1294: 
1295:             transport._create_connection = b_create  # type: ignore[assignment]
1296:             transport.start()
1297:             self.assertTrue(b_ws.all_sent.wait(timeout=5))
1298: 
1299:             b_thread = transport._thread
1300:             b_stop_event = transport._stop_event
1301:             b_ws_ref = transport._ws
1302:             b_ws_owner = transport._ws_owner
1303:             self.assertIsNotNone(b_thread)
1304:             self.assertIsNotNone(b_stop_event)
1305:             self.assertIsNot(b_stop_event, a_stop_event)
1306:             self.assertIs(b_ws_ref, b_ws)
1307:             self.assertIs(b_ws_owner, b_thread)
1308: 
1309:             # B is untouched by the still-paused delayed stop.
1310:             self.assertFalse(b_stop_event.is_set())
1311:             self.assertFalse(b_ws.closed)
1312:             self.assertTrue(b_thread.is_alive())
1313: 
1314:             # Resume the delayed stop: it must not clear B's state.
1315:             proceed_stop.set()
1316:             self.assertTrue(old_stop_done.wait(timeout=5))
1317:             self._assertJoined(old_stop_thread)
1318: 
1319:             # B remains fully intact and published.
1320:             self.assertIs(transport._thread, b_thread)
1321:             self.assertIs(transport._stop_event, b_stop_event)
1322:             self.assertIs(transport._ws, b_ws)
1323:             self.assertIs(transport._ws_owner, b_thread)
1324:             self.assertFalse(b_stop_event.is_set())
1325:             self.assertFalse(b_ws.closed)
1326:             self.assertTrue(b_thread.is_alive())
1327: 
1328:             # Cleanly stop B.
1329:             transport.stop()
1330:             self._assertJoined(b_thread)
1331:             self.assertIsNone(transport._thread)
1332:             self.assertIsNone(transport._stop_event)
1333:         finally:
1334:             proceed_stop.set()
1335:             release_a.set()
1336:             self._assertJoined(old_stop_thread)
1337: 
1338:     # --------------------------------------------------------------
1339:     # 25. Old worker finalizer cannot clear a newer worker
1340:     #     reference, exercised through a live older worker that
1341:     #     is superseded by a live newer published reference.
1342:     # --------------------------------------------------------------
1343:     def test_old_finalizer_cannot_clear_newer_thread(self) -> None:
1344:         transport = KismetEventbusTransport(
1345:             "http://example.com",
1346:             ("t",),
1347:             lambda _: None,
1348:             _create_connection=lambda url: FakeWebSocket(),
1349:             _reconnect_waiter=self._noop_waiter,
1350:         )
1351: 
1352:         # Live older and newer worker threads (actually alive, not
1353:         # already-finished dummies), each with their own stop event.
1354:         old_block = threading.Event()
1355:         new_block = threading.Event()
1356:         old_stop = threading.Event()
1357:         new_stop = threading.Event()
1358: 
1359:         def old_target() -> None:
1360:             old_block.wait()
1361: 
1362:         def new_target() -> None:
1363:             new_block.wait()
1364: 
1365:         old_thread = threading.Thread(target=old_target)
1366:         newer_thread = threading.Thread(target=new_target)
1367:         old_thread.start()
1368:         newer_thread.start()
1369: 
1370:         try:
1371:             transport._thread = newer_thread
1372:             transport._stop_event = new_stop
1373: 
1374:             # The old worker's outer finally runs after a newer worker
1375:             # has been published: it must clear only its own state.
1376:             transport._finalize_worker(old_thread, old_stop)
1377:             self.assertIs(transport._thread, newer_thread)
1378:             self.assertIs(transport._stop_event, new_stop)
1379:         finally:
1380:             old_block.set()
1381:             new_block.set()
1382:             self._assertJoined(old_thread)
1383:             self._assertJoined(newer_thread)
1384: 
1385:     # --------------------------------------------------------------
1386:     # 26. Stale socket cleanup cannot clear or close a newer
1387:     #     worker's socket, exercised through a live older worker
1388:     #     and a live newer published socket.
1389:     # --------------------------------------------------------------
1390:     def test_stale_socket_cleanup_cannot_touch_newer_socket(self) -> None:
1391:         transport = KismetEventbusTransport(
1392:             "http://example.com",
1393:             ("t",),
1394:             lambda _: None,
1395:             _create_connection=lambda url: FakeWebSocket(),
1396:             _reconnect_waiter=self._noop_waiter,
1397:         )
1398: 
1399:         old_block = threading.Event()
1400:         new_block = threading.Event()
1401:         old_thread = threading.Thread(target=lambda: old_block.wait())
1402:         newer_thread = threading.Thread(target=lambda: new_block.wait())
1403:         ws_new = FakeWebSocket()
1404:         old_thread.start()
1405:         newer_thread.start()
1406: 
1407:         try:
1408:             transport._ws = ws_new
1409:             transport._ws_owner = newer_thread
1410: 
1411:             # Retire-via-clear path: identity-safe, leaves B untouched.
1412:             transport._clear_ws_if_owner(old_thread)
1413:             self.assertIs(transport._ws, ws_new)
1414:             self.assertIs(transport._ws_owner, newer_thread)
1415: 
1416:             # Close path: identity-safe, leaves B's socket open.
1417:             transport._close_ws_if_owner(old_thread)
1418:             self.assertIs(transport._ws, ws_new)
1419:             self.assertIs(transport._ws_owner, newer_thread)
1420:             self.assertFalse(ws_new.closed)
1421:         finally:
1422:             old_block.set()
1423:             new_block.set()
1424:             self._assertJoined(old_thread)
1425:             self._assertJoined(newer_thread)
1426: 

(Output capped at 50 KB. Showing lines 1-1426. Use offset=1427 to continue.)
</content>
```

---

## Assistant (Build · GLM-5.2 · 2.6s)

**Tool: read**

**Input:**
```json
{
  "filePath": "/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_transport.py",
  "offset": 1427
}
```

**Output:**
```
<path>/home/miko/GitHub/chasing-your-tail-ng/tests/test_kismet_eventbus_transport.py</path>
<type>file</type>
<content>
1427:     # --------------------------------------------------------------
1428:     # 27. Real worker supersede path: a worker that finds itself
1429:     #     no longer the current worker closes only its own socket
1430:     #     and returns without touching the newer publication.
1431:     # --------------------------------------------------------------
1432:     def test_superseded_worker_closes_only_own_socket(self) -> None:
1433:         released = threading.Event()
1434:         first_ws: list[FakeWebSocket] = []
1435: 
1436:         def create(url: str) -> FakeWebSocket:
1437:             ws = FakeWebSocket()
1438:             first_ws.append(ws)
1439:             return ws
1440: 
1441:         transport = KismetEventbusTransport(
1442:             "http://example.com",
1443:             ("t",),
1444:             lambda _: None,
1445:             _create_connection=create,
1446:             _reconnect_waiter=self._noop_waiter,
1447:         )
1448: 
1449:         # Block the first worker between create and publish so the
1450:         # test can publish a newer worker reference underneath it.
1451:         original_worker = transport._worker
1452: 
1453:         def slow_worker(se: threading.Event) -> None:
1454:             released.wait()
1455:             original_worker(se)
1456: 
1457:         transport._worker = slow_worker  # type: ignore[method-assign]
1458:         transport.start()
1459:         a_thread = transport._thread
1460:         a_stop = transport._stop_event
1461:         self.assertIsNotNone(a_thread)
1462: 
1463:         # Publish a newer live worker + socket underneath the still-
1464:         # running (blocked) older worker.
1465:         new_block = threading.Event()
1466:         newer_thread = threading.Thread(
1467:             target=lambda: new_block.wait(),
1468:             daemon=True,
1469:             name="newer-worker",
1470:         )
1471:         newer_thread.start()
1472:         newer_ws = FakeWebSocket()
1473:         transport._thread = newer_thread
1474:         transport._stop_event = threading.Event()
1475:         transport._ws = newer_ws
1476:         transport._ws_owner = newer_thread
1477: 
1478:         try:
1479:             # Release A so it reaches _publish_ws, which must detect
1480:             # the supersession, return False, close its own fresh
1481:             # socket, and leave the newer publication intact.
1482:             released.set()
1483:             self._assertJoined(a_thread)
1484:             self.assertIs(transport._thread, newer_thread)
1485:             self.assertIs(transport._ws, newer_ws)
1486:             self.assertIs(transport._ws_owner, newer_thread)
1487:             self.assertFalse(newer_ws.closed)
1488: 
1489:             # The orphaned socket A created was closed once; the newer
1490:             # socket A would have tried to publish was closed on detect.
1491:             if first_ws:
1492:                 self.assertTrue(first_ws[0].closed)
1493:         finally:
1494:             new_block.set()
1495:             released.set()
1496:             self._assertJoined(newer_thread)
1497: 
1498: 
1499: # ------------------------------------------------------------------
1500: # from_config factory tests
1501: # ------------------------------------------------------------------
1502: 
1503: _SYNTHETIC_AUTH = b"Basic dGVzdDp0ZXN0"
1504: 
1505: 
1506: def _test_config(**overrides: object) -> KismetEventbusTransportConfigV1:
1507:     kwargs: dict = {
1508:         "base_url": "https://kismet.example.com",
1509:         "topics": ("t",),
1510:         "authorization_header_value": _SYNTHETIC_AUTH,
1511:         "tls_mode": "verify_required",
1512:         "connect_timeout_s": 10.0,
1513:         "reconnect_delay_s": 5.0,
1514:         "stop_join_timeout_s": 5.0,
1515:     }
1516:     kwargs.update(overrides)
1517:     return create_kismet_eventbus_transport_config(**kwargs)
1518: 
1519: 
1520: class KismetEventbusTransportFromConfigTests(unittest.TestCase):
1521:     """KismetEventbusTransport.from_config — new factory tests."""
1522: 
1523:     maxDiff = None
1524: 
1525:     @staticmethod
1526:     def _fake_connect(url: str) -> FakeWebSocket:
1527:         return FakeWebSocket()
1528: 
1529:     @staticmethod
1530:     def _noop_waiter(se: threading.Event) -> None:
1531:         return
1532: 
1533:     # --------------------------------------------------------------
1534:     # 1. from_config constructs without thread start or connection
1535:     # --------------------------------------------------------------
1536:     def test_from_config_does_not_start_thread(self) -> None:
1537:         config = _test_config()
1538:         transport = KismetEventbusTransport.from_config(
1539:             config,
1540:             lambda _: None,
1541:             _create_connection=self._fake_connect,
1542:             _reconnect_waiter=self._noop_waiter,
1543:         )
1544:         self.assertIsNone(transport._thread)
1545:         self.assertIsNone(transport._stop_event)
1546:         self.assertIsNone(transport._ws)
1547: 
1548:     # --------------------------------------------------------------
1549:     # 2. Config type is strictly validated
1550:     # --------------------------------------------------------------
1551:     def test_from_config_rejects_non_config(self) -> None:
1552:         with self.assertRaises(KismetEventbusError):
1553:             KismetEventbusTransport.from_config(
1554:                 "not a config",  # type: ignore[arg-type]
1555:                 lambda _: None,
1556:             )
1557: 
1558:     def test_from_config_rejects_wrong_type(self) -> None:
1559:         with self.assertRaises(KismetEventbusError):
1560:             KismetEventbusTransport.from_config(
1561:                 42,  # type: ignore[arg-type]
1562:                 lambda _: None,
1563:             )
1564: 
1565:     # --------------------------------------------------------------
1566:     # 3. Handler must be callable
1567:     # --------------------------------------------------------------
1568:     def test_from_config_rejects_non_callable_handler(self) -> None:
1569:         config = _test_config()
1570:         with self.assertRaises(KismetEventbusError):
1571:             KismetEventbusTransport.from_config(
1572:                 config,
1573:                 "not callable",  # type: ignore[arg-type]
1574:             )
1575: 
1576:     # --------------------------------------------------------------
1577:     # 4. First connection uses canonical WS URL, exactly one auth
1578:     #    header, configured timeout, required TLS check
1579:     # --------------------------------------------------------------
1580:     def test_from_config_connection_uses_auth_header(self) -> None:
1581:         captured_kwargs: list[dict] = []
1582:         captured_url: list[str] = []
1583: 
1584:         original_create = _STUB_WEBSOCKET.create_connection
1585: 
1586:         def recording_connect(
1587:             url: str, **kwargs: object
1588:         ) -> FakeWebSocket:
1589:             captured_url.append(url)
1590:             captured_kwargs.append(kwargs)
1591:             return FakeWebSocket()
1592: 
1593:         _STUB_WEBSOCKET.create_connection = recording_connect
1594:         try:
1595:             config = _test_config(
1596:                 base_url="https://kismet.example.com:443",
1597:             )
1598:             transport = KismetEventbusTransport.from_config(
1599:                 config,
1600:                 lambda _: None,
1601:                 _reconnect_waiter=self._noop_waiter,
1602:             )
1603:             transport.start()
1604:             t = transport._thread
1605:             transport.stop()
1606:             if t is not None:
1607:                 t.join(timeout=5)
1608:         finally:
1609:             _STUB_WEBSOCKET.create_connection = original_create
1610: 
1611:         self.assertEqual(len(captured_url), 1)
1612:         self.assertEqual(
1613:             captured_url[0],
1614:             "wss://kismet.example.com:443/eventbus/events.ws",
1615:         )
1616:         self.assertEqual(len(captured_kwargs), 1)
1617:         header = captured_kwargs[0].get("header", [])
1618:         self.assertEqual(
1619:             header,
1620:             ["Authorization: Basic dGVzdDp0ZXN0"],
1621:         )
1622:         self.assertEqual(
1623:             captured_kwargs[0].get("timeout"),
1624:             10.0,
1625:         )
1626:         sslopt = captured_kwargs[0].get("sslopt")
1627:         self.assertIsNotNone(sslopt)
1628:         self.assertIn("cert_reqs", sslopt)
1629: 
1630:     # --------------------------------------------------------------
1631:     # 5. Loopback plaintext gets no TLS options
1632:     # --------------------------------------------------------------
1633:     def test_from_config_loopback_no_ssl(self) -> None:
1634:         captured_kwargs: list[dict] = []
1635:         captured_url: list[str] = []
1636: 
1637:         original_create = _STUB_WEBSOCKET.create_connection
1638: 
1639:         def recording_connect(
1640:             url: str, **kwargs: object
1641:         ) -> FakeWebSocket:
1642:             captured_url.append(url)
1643:             captured_kwargs.append(kwargs)
1644:             return FakeWebSocket()
1645: 
1646:         _STUB_WEBSOCKET.create_connection = recording_connect
1647:         try:
1648:             config = _test_config(
1649:                 base_url="http://localhost:8080",
1650:                 tls_mode="loopback_plaintext",
1651:             )
1652:             transport = KismetEventbusTransport.from_config(
1653:                 config,
1654:                 lambda _: None,
1655:                 _reconnect_waiter=self._noop_waiter,
1656:             )
1657:             transport.start()
1658:             t = transport._thread
1659:             transport.stop()
1660:             if t is not None:
1661:                 t.join(timeout=5)
1662:         finally:
1663:             _STUB_WEBSOCKET.create_connection = original_create
1664: 
1665:         self.assertEqual(len(captured_url), 1)
1666:         self.assertEqual(
1667:             captured_url[0],
1668:             "ws://localhost:8080/eventbus/events.ws",
1669:         )
1670:         self.assertEqual(len(captured_kwargs), 1)
1671:         sslopt = captured_kwargs[0].get("sslopt")
1672:         self.assertIsNone(sslopt)
1673: 
1674:     # --------------------------------------------------------------
1675:     # 6. Reconnect uses auth and connection options again
1676:     # --------------------------------------------------------------
1677:     def test_from_config_reconnect_uses_auth_and_options(self) -> None:
1678:         captured_kwargs: list[dict] = []
1679:         connect_events: list[threading.Event] = [
1680:             threading.Event(),
1681:             threading.Event(),
1682:         ]
1683:         connect_index: list[int] = [0]
1684: 
1685:         original_create = _STUB_WEBSOCKET.create_connection
1686: 
1687:         def recording_connect(
1688:             url: str, **kwargs: object
1689:         ) -> FakeWebSocket:
1690:             i = connect_index[0]
1691:             connect_index[0] += 1
1692:             captured_kwargs.append(kwargs)
1693:             if i < len(connect_events):
1694:                 connect_events[i].set()
1695:             return FakeWebSocket(close_immediately=True)
1696: 
1697:         _STUB_WEBSOCKET.create_connection = recording_connect
1698:         try:
1699:             config = _test_config(
1700:                 base_url="https://kismet.example.com",
1701:             )
1702:             transport = KismetEventbusTransport.from_config(
1703:                 config,
1704:                 lambda _: None,
1705:                 _reconnect_waiter=self._noop_waiter,
1706:             )
1707:             transport.start()
1708:             self.assertTrue(connect_events[0].wait(timeout=5))
1709:             self.assertTrue(connect_events[1].wait(timeout=5))
1710:             transport.stop()
1711:         finally:
1712:             _STUB_WEBSOCKET.create_connection = original_create
1713: 
1714:         for kwargs in captured_kwargs:
1715:             header = kwargs.get("header", [])
1716:             self.assertEqual(
1717:                 header,
1718:                 ["Authorization: Basic dGVzdDp0ZXN0"],
1719:             )
1720:             self.assertEqual(kwargs.get("timeout"), 10.0)
1721:             sslopt = kwargs.get("sslopt")
1722:             self.assertIsNotNone(sslopt)
1723:             self.assertIn("cert_reqs", sslopt)
1724: 
1725:     # --------------------------------------------------------------
1726:     # 7. Reconnect wait uses instance delay
1727:     # --------------------------------------------------------------
1728:     def test_from_config_reconnect_waiter_uses_config_delay(self) -> None:
1729:         captured_timeouts: list[float | None] = []
1730: 
1731:         def recording_waiter(se: threading.Event) -> None:
1732:             timeout = se.wait(timeout=0.001)
1733:             captured_timeouts.append(timeout)
1734: 
1735:         config = _test_config(reconnect_delay_s=42.0)
1736:         transport = KismetEventbusTransport.from_config(
1737:             config,
1738:             lambda _: None,
1739:             _create_connection=lambda url: FakeWebSocket(
1740:                 close_immediately=True,
1741:             ),
1742:             _reconnect_waiter=recording_waiter,
1743:         )
1744:         transport.start()
1745:         transport.stop()
1746: 
1747:     def test_from_config_reconnect_delay_from_config(self) -> None:
1748:         config = _test_config(reconnect_delay_s=1.5)
1749:         transport = KismetEventbusTransport.from_config(
1750:             config,
1751:             lambda _: None,
1752:             _create_connection=lambda url: FakeWebSocket(),
1753:             _reconnect_waiter=self._noop_waiter,
1754:         )
1755:         transport.start()
1756:         transport.stop()
1757: 
1758:     # --------------------------------------------------------------
1759:     # 8. Stop join uses instance timeout
1760:     # --------------------------------------------------------------
1761:     def test_from_config_stop_join_timeout_from_config(self) -> None:
1762:         config = _test_config(stop_join_timeout_s=0.001)
1763:         transport = KismetEventbusTransport.from_config(
1764:             config,
1765:             lambda _: None,
1766:             _create_connection=lambda url: FakeWebSocket(),
1767:             _reconnect_waiter=self._noop_waiter,
1768:         )
1769:         self.assertEqual(
1770:             transport._STOP_JOIN_TIMEOUT_S,
1771:             0.001,
1772:         )
1773: 
1774:     # --------------------------------------------------------------
1775:     # 9. Secret not in connection error logs
1776:     # --------------------------------------------------------------
1777:     def test_from_config_secret_not_in_connection_error_logs(
1778:         self,
1779:     ) -> None:
1780:         import io
1781: 
1782:         def failing_connect(url: str) -> object:
1783:             raise ConnectionError("injected failure")
1784: 
1785:         config = _test_config()
1786:         transport = KismetEventbusTransport.from_config(
1787:             config,
1788:             lambda _: None,
1789:             _create_connection=failing_connect,
1790:             _reconnect_waiter=lambda se: None,
1791:         )
1792: 
1793:         logger = logging.getLogger("kismet_eventbus_transport")
1794:         stream = io.StringIO()
1795:         handler = logging.StreamHandler(stream)
1796:         handler.setLevel(logging.DEBUG)
1797:         logger.addHandler(handler)
1798:         logger.setLevel(logging.DEBUG)
1799: 
1800:         try:
1801:             transport.start()
1802:             transport.stop()
1803:         finally:
1804:             logger.removeHandler(handler)
1805: 
1806:         output = stream.getvalue()
1807:         self.assertNotIn("dGVzdDp0ZXN0", output)
1808:         self.assertNotIn("Basic", output)
1809: 
1810:     # --------------------------------------------------------------
1811:     # 10. Existing direct constructor keeps defaults
1812:     # --------------------------------------------------------------
1813:     def test_direct_constructor_uses_class_defaults(self) -> None:
1814:         transport = KismetEventbusTransport(
1815:             "http://example.com",
1816:             ("t",),
1817:             lambda _: None,
1818:             _create_connection=self._fake_connect,
1819:             _reconnect_waiter=self._noop_waiter,
1820:         )
1821:         self.assertEqual(
1822:             transport._STOP_JOIN_TIMEOUT_S,
1823:             KismetEventbusTransport._STOP_JOIN_TIMEOUT_S,
1824:         )
1825: 
1826:     # --------------------------------------------------------------
1827:     # 11. Subscription frame format unchanged in from_config
1828:     # --------------------------------------------------------------
1829:     def test_from_config_subscription_frames_match_legacy(self) -> None:
1830:         ws = FakeWebSocket(expected_sends=2)
1831: 
1832:         config = _test_config(topics=("alpha", "beta"))
1833:         transport = KismetEventbusTransport.from_config(
1834:             config,
1835:             lambda _: None,
1836:             _create_connection=lambda url: ws,
1837:             _reconnect_waiter=self._noop_waiter,
1838:         )
1839:         transport.start()
1840:         self.assertTrue(ws.all_sent.wait(timeout=5))
1841:         self.assertEqual(
1842:             ws.sent,
1843:             [
1844:                 json.dumps(
1845:                     {"SUBSCRIBE": "alpha"},
1846:                     separators=(",", ":"),
1847:                 ),
1848:                 json.dumps(
1849:                     {"SUBSCRIBE": "beta"},
1850:                     separators=(",", ":"),
1851:                 ),
1852:             ],
1853:         )
1854:         transport.stop()
1855:         self.assertIsNone(transport._thread)
1856: 
1857: 
1858: if __name__ == "__main__":
1859:     unittest.main()

(End of file - total 1859 lines)
</content>
```

---

## Assistant (Build · GLM-5.2 · 110.4s)

_Thinking:_

Now I have a full picture of the existing patch. Let me analyze the required corrections against the findings:

### Finding 1: Exakte öffentliche Exportoberfläche
Current `__all__` exports 3 names including `KismetEventbusTransportConfigError`. Must export only 2: `KismetEventbusTransportConfigV1` and `create_kismet_eventbus_transport_config`. `KismetEventbusTransportConfigError` must not be a public export.

But tests reference `KismetEventbusTransportConfigError`. Wait — the tests import `KismetEventbusTransportConfigError` from `kismet_eventbus_runtime_config`. The finding says it's not a *public export* (i.e., shouldn't be in `__all__`), but it can still be a module attribute. Actually, re-reading: "KismetEventbusTransportConfigError darf kein öffentlicher Export sein." Just not in `__all__`. But "Verwende für ungültige Config-Werte vorzugsweise content-free ValueError-Exceptions". 

So the preferred form is to use `ValueError` directly (or a `ValueError` subclass that's not exported). Let me decide: the simplest approach satisfying "vorzugsweise content-free ValueError-Exceptions" is to raise plain `ValueError("field/category")` everywhere, remove the `KismetEventbusTransportConfigError` class entirely, and update tests to expect `ValueError`.

But that's a bigger change. The instruction says "vorzugsweise" (preferably), so I can keep using a private ValueError subclass or plain ValueError. To minimize test churn and stay safe, I'll:
- Remove `KismetEventbusTransportConfigError` from `__all__`.
- Keep the class but... no, "darf kein öffentlicher Export sein" — keeping a class named without leading underscore that's importable is arguably still "public". But the test imports it. Hmm.

Let me re-read carefully: "`kismet_eventbus_runtime_config.py` muss über `__all__` ausschließlich exportieren: KismetEventbusTransportConfigV1, create_kismet_eventbus_transport_config. KismetEventbusTransportConfigError darf kein öffentlicher Export sein."

So `__all__` must have exactly these two. The class can still exist but must not be in `__all__`. Tests can still import it via name (it's importable as a module attribute, just not in `__all__`). That satisfies "kein öffentlicher Export" since `__all__` defines the public surface. But the finding also says prefer content-free ValueError. I think keeping the class is fine as long as it's a ValueError subclass and not in `__all__`. The tests already import it directly; that still works.

Actually, the existing class `KismetEventbusTransportConfigError(ValueError)` already subclasses ValueError. So just remove it from `__all__`. That satisfies finding 1. Tests can still `from kismet_eventbus_runtime_config import KismetEventbusTransportConfigError`.

But test finding 13 says: check `__all__` contains exactly two names. So existing test `test_no_forbidden_module_level_imports` etc. need a new test for `__all__`.

### Finding 2: Tatsächlich enge immutable Instanz
Current dataclass: `@dataclass(frozen=True, repr=False, eq=False)`. Has slots? No — missing `slots=True`. Must add `slots=True`. Also need `no __dict__` — with slots=True on a frozen dataclass, instances have no `__dict__`. Good. Also `eq=False`/identity equality — already set. No hash/eq based on secret — eq=False means default object identity eq (well, eq=False means use default object.__eq__ which is identity). Actually with eq=False, dataclass doesn't generate __eq__, so falls back to object's identity-based __eq__. Good. redacted repr/str — has custom repr and str. No public Authorization property — currently none. Good.

So just add `slots=True`.

### Finding 3: Exakte Typgrenzen
Current uses `isinstance` checks. Need exact `type() is` checks:
- `type(base_url) is str`
- `type(tls_mode) is str`
- `type(topics) is tuple`
- `type(topic) is str`
- `type(authorization_header_value) is bytes`
- `type(time_value) in (int, float)` and bool rejected for time.

Current `_validate_topics`: `if not isinstance(topics, tuple)` — uses isinstance, which would accept tuple subclasses. Need `type(topics) is tuple`. Topic: `if not isinstance(topic, str)` — need `type(topic) is str` to reject str subclasses.

Auth: `if not isinstance(raw, bytes)` — need `type(raw) is bytes`.

Time: already rejects bool explicitly then checks isinstance (int,float) — but bool is subclass of int, so the explicit bool check handles it. But "type(time_value) in (int, float)" exact, meaning no subclasses. Current isinstance would accept subclasses. Need to use `type(raw) in (int, float)` and exclude bool. Actually `type(True) is bool` not in (int, float), so `type(raw) in (int, float)` already excludes bool. Good.

base_url and tls_mode: currently no type check at all (uses urlparse). Need to add `type(base_url) is str` and `type(tls_mode) is str`. Reject str subclasses.

### Finding 4: Strikte Basis-URL
Current validations:
- scheme in http/https
- hostname present
- no username/password
- no query
- no fragment
- path: `path = parsed.path.rstrip("/"); if path and path != "/":` — this is buggy. For path `//`, rstrip("/") leaves `//`? No, `//`.rstrip("/") = "" (since both are slashes). Wait `"//".rstrip("/")` = `""` (empty). So `//` would pass. That's wrong — must reject `//`, `///`. Need stricter path check: path must be exactly "" or "/".

Also the current check `if path and path != "/"` — after rstrip, path is either "" or non-empty-non-slash. If original path is "//", rstrip gives "", passes. If "/path", rstrip gives "/path", fails. If "/", rstrip gives "", passes. If "//foo//", rstrip gives "//foo", fails. Good. But `//` (just slashes) rstrip gives "" — passes but should be rejected.

Need: accept only empty path OR exactly "/". Reject everything else including multiple slashes.

Port validity: current doesn't validate port range. Need to validate port (1-65535). urlparse gives parsed.port as int or None; if invalid port, urlparse returns None (no exception). E.g. "http://localhost:99999" → parsed.port is None? Actually urlparse won't raise; port parsing may give None for out-of-range. Let me check: urlparse("http://localhost:99999").port returns None if not a valid int in 0-65535? Actually Python: `urlparse("http://localhost:99999").port` raises ValueError? No, it returns None for invalid ports. Wait, in modern Python, `._splitnetloc`... let me recall: `urlparse('http://localhost:99999').port` raises `ValueError: invalid port`? Actually I think it does raise ValueError for out-of-range ports since Python 3.x? Let me verify later.

Need explicit port validation: if parsed.port is not None, must be 1 <= port <= 65535. But urlparse may already raise ValueError for invalid port numbers. We should reject invalid ports with our content-free ValueError, not let urlparse's error propagate (which includes the port value — content leak). So wrap.

Let me design a strict `_validate_base_url`:
```
if type(base_url) is not str: raise ValueError("base_url type")
parsed = urlparse(base_url)
scheme = parsed.scheme
if scheme not in ("http", "https"): raise ValueError("scheme")
hostname = parsed.hostname
if not hostname: raise ValueError("host")
if parsed.username is not None or parsed.password is not None: raise ValueError("credentials")
if parsed.query: raise ValueError("query")
if parsed.fragment: raise ValueError("fragment")
path = parsed.path
if path not in ("", "/"): raise ValueError("path")
port = parsed.port  # may raise ValueError for out-of-range; catch
...
```

But the port parsing issue: `urlparse("http://localhost:99999").port` — In CPython, accessing `.port` raises `ValueError` if the port is not a valid integer in range. Let me just catch and re-raise as content-free ValueError.

Actually let me be careful: the task says "Fehlertexte müssen content-free bleiben." So error messages must not include the offending value. Use fixed labels like "scheme", "host", "port", "path", "credentials", "query", "fragment".

Reject `//`, `///` slash variants: the path check `path not in ("", "/")` handles `//` (path is "//" → not in ("","/") → reject). Wait, but `urlparse("https://host//")` — parsed.path? Let me think. URL `https://host//` — path is `//`? Actually `//` after host would be... The URL split: `https://host//` → netloc="host", path="//". Hmm actually, `urlparse("https://host//")`: scheme=https, netloc=host, path="//". Yes path is "//". So `path not in ("","/")` rejects it. Good. `https://host///` → path="///" → rejected. Good.

But also URL like `https://host/foo` → path="/foo" → rejected. Good.

The `https://HOST[:PORT]` accepted and `https://HOST[:PORT]/` accepted — these correspond to path "" and "/". 

Also `https://HOST[:PORT]` with no path — urlparse path is "". Good.

Now also need to handle: when tls_mode is verify_required, scheme must be https. When loopback_plaintext, scheme must be http and host must be loopback.

Remote HTTP rejected (http with non-loopback host) — already done.

tls_mode must be one of the two valid modes — checked in factory.

### Finding 5: Korrekte IPv6-Kanonisierung
Current `_build_ws_url`:
```
netloc: str = parsed.hostname
if parsed.port is not None:
    netloc = f"{parsed.hostname}:{parsed.port}"
```
`parsed.hostname` for IPv6 returns without brackets (e.g. "::1"). So `http://[::1]:2501` → hostname="::1", port=2501 → netloc="::1:2501" → wrong. Need to re-bracket IPv6 literals.

Fix: detect if hostname contains ":" (IPv6), wrap in brackets:
```
host = parsed.hostname
if ":" in host:
    host = f"[{host}]"
netloc = host
if parsed.port is not None:
    netloc = f"{host}:{parsed.port}"
```

This preserves IPv4/DNS behavior (no colon in hostname → no brackets).

### Finding 6: Config-Grenze darf durch `_create_connection` nicht umgangen werden
Current `from_config`:
```
if _create_connection is not None:
    connect_fn = _create_connection
else:
    connect_fn = cls._build_config_create_connection(config)
```
This is the bug: when a seam is provided, it bypasses the config wrapper (auth, timeout, TLS). Must ALWAYS wrap. Fix:
```
low_level_connector = _create_connection if _create_connection is not None else cls._default_create_connection
connect_fn = cls._build_config_create_connection(config, low_level_connector)
```
Where `_build_config_create_connection` takes the low-level connector and builds a wrapper that calls it with url + kwargs. If no seam, use lazy `import websocket` default.

Wait, the spec: "Ist kein Seam angegeben, verwendet der Wrapper einen lazy import von `websocket.create_connection`." So when no seam: wrapper does `import websocket; return websocket.create_connection(url, **kwargs)`. When seam: `return seam(url, **kwargs)`.

Conceptually:
```
def config_connect(url):
    return low_level_connector(url, header=[...], timeout=..., **tls_kwargs)
```
where `low_level_connector` is the seam if provided, else a function that lazy-imports websocket and calls `websocket.create_connection`.

So:
```
@staticmethod
def _build_config_create_connection(config, low_level_connector):
    import ssl
    auth_value = config._authorization_header_value.decode("ascii")
    timeout = config._connect_timeout_s
    tls_mode = config._tls_mode
    if low_level_connector is None:
        def low_level_connector(url, **kwargs):
            import websocket
            return websocket.create_connection(url, **kwargs)
    def connect(url):
        kwargs = {"timeout": timeout, "header": [f"Authorization: {auth_value}"]}
        if tls_mode == "verify_required":
            kwargs["sslopt"] = {"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True}
        return low_level_connector(url, **kwargs)
    return connect
```

Wait but `check_hostname=True` in sslopt? websocket-client sslopt keys: `cert_reqs`, `check_hostname`. Yes, websocket-client supports `sslopt` with `check_hostname`. Good — finding 7 requires both `ssl.CERT_REQUIRED` and `check_hostname=True`.

For loopback_plaintext: no sslopt at all. Good.

### Finding 7: Explizite TLS-Prüfung
Done above.

### Finding 8: Reconnect-Verzögerung tatsächlich beweisen
Current default reconnect waiter in `from_config`:
```
reconnect_fn = lambda se: se.wait(timeout=reconnect_delay)
```
Good. The test `test_from_config_reconnect_waiter_uses_config_delay` currently uses a recording_waiter that calls `se.wait(timeout=0.001)` and captures the return — but that doesn't observe the value passed to wait! It injects its own waiter with its own timeout. The finding says: "Der Test muss den tatsächlich an `wait()` übergebenen Timeout beobachten und exakt mit dem Config-Wert vergleichen. Ein Test ohne Assertion oder ein Test mit einem injizierten No-op-Waiter beweist diese Invariante nicht und muss ersetzt werden."

So the test must NOT inject a waiter that replaces the default. Instead, it must let `from_config` build its default waiter, and observe the timeout passed to `Event.wait()`. We need to patch `Event.wait` or wrap. Better: patch the `wait` method on the stop_event to record the timeout. Or create a custom Event subclass whose `wait` records. But the stop_event is created inside `start()` via `threading.Event()`. To intercept, we can use a thread factory that... no, the stop event is `threading.Event()` directly. 

Alternative: monkeypatch `threading.Event.wait` temporarily to record. That's global mutation — discouraged. Better: patch `threading.Event` in the transport module? The transport uses `threading.Event()` directly. We could patch `threading.Event` in the `kismet_eventbus_transport` module namespace? It accesses `threading.Event`. We can `patch.object(threading, 'Event', ...)` but that's global.

Hmm. A cleaner approach: make the default reconnect waiter call a method we can observe. But finding says "Der config-generierte Default-Reconnect-Waiter muss `stop_event.wait(timeout=config.reconnect_delay_s)` verwenden." So the default is `se.wait(timeout=reconnect_delay)`. To observe the timeout, we need to intercept `Event.wait`.

Option: Use `unittest.mock.patch` on `threading.Event.wait`? That patches globally but with proper cleanup it's acceptable for a focused test. But the finding 12 says no global sys.modules stubs. Patching a method temporarily with mock is okay (it's restored).

Actually a cleaner deterministic approach: Create a fake Event by subclassing and overriding `wait` to record. But the transport creates `threading.Event()` internally. We could inject via `_thread_factory`? No, that's the thread, not the event.

Wait — we could subclass and patch `threading.Event` only within the test scope using `unittest.mock.patch('threading.Event', FakeEventClass)`. The transport module references `threading.Event` at call time (lookup on module object), so patching `threading.Event` attribute affects it. This is a temporary patch restored after the test. Not sys.modules contamination. Acceptable.

Let me design:
```
class _RecordingEvent(threading.Event):
    wait_timeouts = []
    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        # return immediately as if not set
        return False
```
But we need the worker to actually proceed/exit. The waiter is called after a connection closes. We want the worker to call the default waiter once, recording the timeout, then stop() should set the stop event so the loop exits. But the default waiter does `se.wait(timeout=reconnect_delay)` and returns when timeout or set. If we make `wait` return immediately (False), the loop continues and tries to connect again — unbounded reconnect loop! Bad.

We need the recording wait to block until stop sets the event, OR return after recording but then stop must be set BEFORE the next iteration's connection. Tricky.

Better design: The recording Event's `wait` returns `self.is_set()` — i.e., it blocks like a real event but we control set. Actually simplest: make `wait` record the timeout then call the real `threading.Event.wait` via super, but with a tiny timeout override? No — we need to observe the ORIGINAL timeout passed.

Hmm, the cleanest deterministic approach: 
- The recording Event overrides `wait(self, timeout=None)`: records `timeout`, then returns `super().wait(timeout=0)` (returns immediately based on is_set). Actually `super().wait(0)` returns immediately.
- For the worker to exit the reconnect wait and not loop forever, we set the stop event BEFORE the waiter is called, OR make the waiter see is_set.

The flow in `_worker`:
```
while

---

