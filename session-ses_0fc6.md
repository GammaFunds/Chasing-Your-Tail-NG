# Kismet Eventbus Config-Block-A Korrektur

**Session ID:** ses_0fc679310ffeIUOnB3RofcJV3s
**Created:** 6/26/2026, 1:02:28 PM
**Updated:** 6/26/2026, 1:03:46 PM

---

## User

# CYT-T-KISMET-EVENTBUS-TRANSPORT-CONFIG-1A-C1 – Einmalige Config-Korrektur

## Routing

Harness: OpenCode Go
Model: Kimi K2.7 Code
Task type: einzige Korrekturrunde für Config-Block A
Fallback: Nach dieser Runde keine weitere Modellkorrektur. Bei Testfehler, Toolfehler, Scope-Verletzung oder unerwartetem Repository-Zustand sofort stoppen und evidenzbasiert berichten.
Codex Review: Noch nicht. Erst nach Block B und unabhängiger vollständiger Acceptance.

## Ziel

Korrigiere ausschließlich die verbliebenen Defekte der Config-Grenze:

1. Entferne den bedeutungslosen und zustandsverändernden Modul-Reload-Test.
2. Prüfe verbotene Imports im gesamten AST, nicht nur auf Modulebene.
3. Lehne leere Portsyntax strikt ab.
4. Schließe weitere bereits bekannte Lücken der strikten URL-Grammatik:

   * leere Querymarker
   * leere Fragmentmarker
   * URL-Parameter beziehungsweise Semikolon-Pfade
   * nicht exakt kleingeschriebene Schemes
5. Kanonisiere gültige Root-Slash-URLs auf dieselbe gespeicherte Basis-URL ohne abschließenden Slash.
6. Beweise Config- und Transport-Kompatibilität im selben Pytest-Prozess.

## Repository

Arbeite ausschließlich in:

```text
/home/miko/GitHub/chasing-your-tail-ng
```

Erwartet:

```text
host=archlinux
user=miko
branch=main
HEAD=08eb5d510c8206938f299e34772869ba9083da0e
origin/main=08eb5d510c8206938f299e34772869ba9083da0e
```

## Erwartete aktuelle Hashes

```text
600375788fcb6fd8dc975b24de6c5264fbda0456544a4f7e6649a6ea037e04d3  kismet_eventbus_runtime_config.py
8e0e85cea53cb416cb2f62e1c2c143276a1d0d6c29837b36f87d34f262cf19f5  tests/test_kismet_eventbus_runtime_config.py

979678ae8ef9ffe74954b8d9a7bc9aa3cbeb6ff90a4fe8b288422133a362b081  kismet_eventbus_transport.py
6d5a3aa26977b446e4291f445ec54838649ea6a2b89ab268d79adf671f61a6c1  tests/test_kismet_eventbus_transport.py

da2c3d2d9b4e2bb5fb29f7c9f727728ec5d202bee2fdd315c817652dbbb57ca7  session-ses_0fc7.md
ea55c4133c01b2f2f257d91123008313f943626e6f786223a2aec52c416040cd  session-ses_0fc8.md
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md

a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py
```

## Erwarteter Ausgangsstatus

```text
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc7.md
?? session-ses_0fc8.md
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py
```

Vor jeder Änderung vollständig verifizieren:

* Host
* Benutzer
* absoluter Repository-Pfad
* Branch
* HEAD
* lokales `origin/main`
* sauberer Index
* exakt die erwarteten tracked und untracked Pfade
* alle oben angegebenen Hashes
* keine `__pycache__`-Verzeichnisse
* keine `.pyc`-Dateien
* `git diff --check`

Bei Abweichung ausschließlich ausgeben:

```text
STOP_PRECONDITION_FAILED
```

Danach nichts verändern.

## Erlaubte Dateien

Ändere ausschließlich:

```text
kismet_eventbus_runtime_config.py
tests/test_kismet_eventbus_runtime_config.py
```

Alle anderen Dateien müssen bytegenau unverändert bleiben.

Insbesondere nicht ändern:

```text
kismet_eventbus_transport.py
tests/test_kismet_eventbus_transport.py
session-ses_0fc7.md
session-ses_0fc8.md
session-ses_0fc9.md
kismet_eventbus_observation_handler.py
tests/test_kismet_eventbus_observation_handler.py
```

Keine neue Datei anlegen.

Kein:

* Commit
* Push
* Netzwerkzugriff
* `git checkout`
* `git restore`
* `git reset`
* `git clean`

## Verbindliche Produktionskorrekturen

### 1. Leere Portsyntax ablehnen

Folgende URLs müssen content-free mit `KismetEventbusTransportConfigError` abgelehnt werden:

```text
https://kismet.example.com:
https://kismet.example.com:/
http://localhost:
http://localhost:/
http://[::1]:
http://[::1]:/
```

Ein fehlender Portdelimiter bleibt gültig:

```text
https://kismet.example.com
https://kismet.example.com/
http://localhost
http://localhost/
http://[::1]
http://[::1]/
```

Eine robuste Lösung darf nach dem Parsing zusätzlich die Authority prüfen. Eine Authority, die mit einem Portdelimiter `:` endet, ist ungültig.

IPv6-Adressen ohne Port dürfen dadurch nicht abgelehnt werden, weil ihre Authority mit `]` endet.

### 2. Strikte Scheme-Grammatik

Akzeptiere ausschließlich exakt:

```text
https
http
```

Nicht mittels `.lower()` normalisieren.

Mindestens ablehnen:

```text
HTTPS://kismet.example.com
Https://kismet.example.com
HTTP://localhost
Http://localhost
```

### 3. Query und Fragment vollständig ablehnen

Nicht nur nichtleere Inhalte ablehnen, sondern auch leere Marker.

Ablehnen:

```text
https://kismet.example.com?
https://kismet.example.com/?
https://kismet.example.com#
https://kismet.example.com/#
```

Keine Eingabewerte in Exceptions.

### 4. Parameter- und Semikolonpfade ablehnen

Die zulässige Pfadmenge bleibt exakt:

```python
{"", "/"}
```

Ablehnen:

```text
https://kismet.example.com/;
https://kismet.example.com/;x
https://kismet.example.com;x
```

Verwende vorzugsweise `urllib.parse.urlsplit`, damit Semikolonbestandteile Bestandteil des Pfades bleiben und nicht als separate `params`-Komponente verschwinden.

### 5. Root-Slash-Kanonisierung

Beide Eingaben müssen dieselbe gespeicherte `base_url` ergeben:

```text
https://kismet.example.com
https://kismet.example.com/
```

Gespeicherte kanonische Form:

```text
https://kismet.example.com
```

Entsprechend:

```text
http://localhost/
```

wird gespeichert als:

```text
http://localhost
```

und:

```text
http://[::1]:2501/
```

wird gespeichert als:

```text
http://[::1]:2501
```

Keine sonstige Host-, Port- oder Case-Normalisierung einführen.

### 6. Parsing-Fehlergrenze

Fange erwartbare URL-Parsingfehler eng als `ValueError` ab.

Kein pauschales:

```python
except Exception:
```

Fehlertext bleibt fest und content-free.

## Verbindliche Testkorrekturen

### 1. Reload-Test vollständig entfernen

Entferne vollständig:

```text
KismetEventbusRuntimeConfigReimportTests
```

Kein `importlib.reload()`.

Kein Entfernen und Neuimportieren des Config-Moduls.

Keine Mutation von `sys.modules`.

Entferne anschließend unbenutzte Imports, insbesondere soweit danach unbenutzt:

```text
importlib
sys
types
os
```

### 2. Gesamten AST auf Imports prüfen

Der Test für verbotene Imports muss alle Importknoten über:

```python
ast.walk(tree)
```

untersuchen.

Er muss sowohl erkennen:

```python
ast.Import
ast.ImportFrom
```

Dies gilt auch für Imports:

* in Funktionen
* in Methoden
* in Klassen
* in verschachtelten Blöcken
* in Exception-Pfaden

Verbotene Importwurzel mindestens:

```text
os
pathlib
netrc
keyring
socket
subprocess
```

### 3. URL-Regressionstests ergänzen

Prüfe ausdrücklich:

* alle sechs leeren Portvarianten
* gültige IPv6-Authority ohne Port
* gültige IPv6-Authority mit Port
* vier gemischte beziehungsweise großgeschriebene Scheme-Varianten
* leeres `?`
* leeres `#`
* Semikolonpfade
* Root-Slash-Kanonisierung für HTTPS, localhost und IPv6 mit Port

### 4. Kein Reload-basierter Importtest

Ein Importtest darf ausschließlich statisch prüfen, dass das Config-Modul keine Side-Effect-Imports oder Aufrufe enthält.

Er darf den bereits geladenen Modulzustand nicht verändern.

### 5. Bestehende Invarianten erhalten

Alle bereits grünen Tests zu folgenden Punkten müssen bestehen bleiben:

* exaktes `__all__`
* frozen
* slots
* kein `__dict__`
* Identity-Equality
* Secret-Redaktion
* exakte Typgrenzen
* Topic-Validierung
* Authorization-Validierung
* alle drei Zeitfelder
* Loopback-Grenze
* content-free Exceptions
* keine I/O- oder Discovery-Aufrufe

## Testprozess

Setze:

```bash
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
```

Führe Config- und Transporttests zwingend im selben Python-/Pytest-Prozess aus:

```bash
python -B -W error::ResourceWarning -m pytest \
  -q \
  -p no:cacheprovider \
  tests/test_kismet_eventbus_runtime_config.py \
  tests/test_kismet_eventbus_transport.py
```

Kein vorheriger oder zwischenzeitlicher separater Pytest-Aufruf.

Danach Import-Smoke-Test in einem frischen Prozess:

```bash
python -B -W error::ResourceWarning -c \
'import kismet_eventbus_runtime_config; import kismet_eventbus_transport'
```

Danach:

```bash
git diff --check
```

Danach:

```bash
find . \
  \( -type d -name __pycache__ -o -type f -name '*.pyc' \) \
  -not -path './.git/*' \
  -print
```

Die Ausgabe muss leer sein.

## Abschlusszustand

`git status --short` darf weiterhin ausschließlich zeigen:

```text
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc7.md
?? session-ses_0fc8.md
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py
```

`git diff --name-only` muss weiterhin exakt enthalten:

```text
kismet_eventbus_transport.py
tests/test_kismet_eventbus_transport.py
```

`git ls-files --others --exclude-standard` muss exakt enthalten:

```text
kismet_eventbus_runtime_config.py
session-ses_0fc7.md
session-ses_0fc8.md
session-ses_0fc9.md
tests/test_kismet_eventbus_runtime_config.py
```

## Geschützte Abschluss-Hashes

Verifiziere:

```bash
sha256sum \
  kismet_eventbus_transport.py \
  tests/test_kismet_eventbus_transport.py \
  session-ses_0fc7.md \
  session-ses_0fc8.md \
  session-ses_0fc9.md \
  kismet_eventbus_observation_handler.py \
  tests/test_kismet_eventbus_observation_handler.py
```

Erwartet:

```text
979678ae8ef9ffe74954b8d9a7bc9aa3cbeb6ff90a4fe8b288422133a362b081  kismet_eventbus_transport.py
6d5a3aa26977b446e4291f445ec54838649ea6a2b89ab268d79adf671f61a6c1  tests/test_kismet_eventbus_transport.py
da2c3d2d9b4e2bb5fb29f7c9f727728ec5d202bee2fdd315c817652dbbb57ca7  session-ses_0fc7.md
ea55c4133c01b2f2f257d91123008313f943626e6f786223a2aec52c416040cd  session-ses_0fc8.md
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md
a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py
```

## Abschlussbericht

Beende mit exakt:

```text
RESULT
FIXED_DEFECTS
CHANGED_FILES
TESTS_RUN
TEST_RESULTS
RESOURCE_WARNING_RESULT
SAME_PROCESS_COMPATIBILITY
IMPORT_SMOKE_TEST
DIFF_CHECK
ARTIFACT_CHECK
PROTECTED_HASHES
WORKTREE_STATE
REMAINING_RISKS
```

`RESULT` darf nur lauten:

```text
CORRECTED
```

wenn:

* beide erlaubten Dateien korrigiert wurden
* alle Config- und Transporttests im selben Prozess grün sind
* kein Reload-Test mehr existiert
* der gesamte AST auf Imports geprüft wird
* leere Ports abgelehnt werden
* Query-/Fragmentmarker vollständig abgelehnt werden
* Semikolonpfade abgelehnt werden
* Schemes exakt validiert werden
* Root-Slash kanonisiert wird
* Import-Smoke-Test grün ist
* `ResourceWarning` als Fehler aktiv war
* `git diff --check` grün ist
* keine Cache-Artefakte bestehen
* alle geschützten Hashes unverändert sind
* keine unerlaubte Datei geändert oder angelegt wurde

Kein Commit und kein Push. 

---

## Assistant (Build · Kimi K2.7 Code · 7.6s)

_Thinking:_

The user wants me to work on a code correction task in a specific repository. This is a complex task with many preconditions and requirements. Let me start by verifying the preconditions carefully.

I need to:
1. Verify host, user, repo path, branch, HEAD, origin/main
2. Verify clean index (except expected modified/untracked)
3. Verify expected hashes
4. Verify no __pycache__ or .pyc files
5. Verify git diff --check

Then make changes only to:
- kismet_eventbus_runtime_config.py
- tests/test_kismet_eventbus_runtime_config.py

And run tests.

Let me start by checking all preconditions in parallel where possible.

Ich starte mit der vollständigen Verifizierung der Vorbedingungen.

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

**Tool: bash**

**Input:**
```json
{
  "command": "git status --short",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
 M kismet_eventbus_transport.py
 M tests/test_kismet_eventbus_transport.py
?? kismet_eventbus_runtime_config.py
?? session-ses_0fc7.md
?? session-ses_0fc8.md
?? session-ses_0fc9.md
?? tests/test_kismet_eventbus_runtime_config.py

```

**Tool: bash**

**Input:**
```json
{
  "command": "sha256sum kismet_eventbus_runtime_config.py tests/test_kismet_eventbus_runtime_config.py kismet_eventbus_transport.py tests/test_kismet_eventbus_transport.py session-ses_0fc7.md session-ses_0fc8.md session-ses_0fc9.md kismet_eventbus_observation_handler.py tests/test_kismet_eventbus_observation_handler.py",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
600375788fcb6fd8dc975b24de6c5264fbda0456544a4f7e6649a6ea037e04d3  kismet_eventbus_runtime_config.py
8e0e85cea53cb416cb2f62e1c2c143276a1d0d6c29837b36f87d34f262cf19f5  tests/test_kismet_eventbus_runtime_config.py
979678ae8ef9ffe74954b8d9a7bc9aa3cbeb6ff90a4fe8b288422133a362b081  kismet_eventbus_transport.py
6d5a3aa26977b446e4291f445ec54838649ea6a2b89ab268d79adf671f61a6c1  tests/test_kismet_eventbus_transport.py
da2c3d2d9b4e2bb5fb29f7c9f727728ec5d202bee2fdd315c817652dbbb57ca7  session-ses_0fc7.md
ea55c4133c01b2f2f257d91123008313f943626e6f786223a2aec52c416040cd  session-ses_0fc8.md
2a8836dbc39f218058b31c4a11a7450f51b3d6838851f7cc7d3454f7d76a3e9f  session-ses_0fc9.md
a4109dfe09e5ad78df8730f31caf19e8fa4071a7ccc1dcdf9a6a1446176c45c5  kismet_eventbus_observation_handler.py
97276b47d4a376b76b67d06e66b7ce0d22f29122828db506498f8358f9de9035  tests/test_kismet_eventbus_observation_handler.py

```

**Tool: bash**

**Input:**
```json
{
  "command": "find . \\( -type d -name __pycache__ -o -type f -name '*.pyc' \\) -not -path './.git/*' -print",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
(no output)
```

**Tool: bash**

**Input:**
```json
{
  "command": "git diff --check",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
(no output)
```

---

## Assistant (Build · Kimi K2.7 Code · 3.6s)

_Thinking:_

All preconditions match. Now I need to read the two files I need to modify:
- kismet_eventbus_runtime_config.py
- tests/test_kismet_eventbus_runtime_config.py

And I should also read kismet_eventbus_transport.py to understand the interface/compatibility requirements.

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
13: from dataclasses import dataclass
14: from typing import Any
15: from urllib.parse import urlparse
16: 
17: __all__ = [
18:     "KismetEventbusTransportConfigV1",
19:     "create_kismet_eventbus_transport_config",
20: ]
21: 
22: 
23: class KismetEventbusTransportConfigError(ValueError):
24:     """Raised on invalid configuration values.
25: 
26:     Instances must never contain the authorization value or a full URL
27:     with embedded credentials.
28:     """
29: 
30: 
31: # ------------------------------------------------------------------
32: # Internal helpers
33: # ------------------------------------------------------------------
34: 
35: _TLS_MODES = frozenset({"verify_required", "loopback_plaintext"})
36: 
37: _HTTP_SCHEMES = frozenset({"http", "https"})
38: 
39: 
40: def _is_ipv4_loopback(host: str) -> bool:
41:     """True when *host* is an IPv4 address in 127.0.0.0/8."""
42:     try:
43:         addr = ipaddress.IPv4Address(host)
44:     except ipaddress.AddressValueError:
45:         return False
46:     return addr in ipaddress.IPv4Network("127.0.0.0/8")
47: 
48: 
49: def _is_ipv6_loopback(host: str) -> bool:
50:     """True when *host* is the IPv6 loopback ``::1``."""
51:     try:
52:         addr = ipaddress.IPv6Address(host)
53:     except ipaddress.AddressValueError:
54:         return False
55:     return addr == ipaddress.IPv6Address("::1")
56: 
57: 
58: def _is_loopback_host(host: str) -> bool:
59:     if host == "localhost":
60:         return True
61:     if _is_ipv4_loopback(host):
62:         return True
63:     if _is_ipv6_loopback(host):
64:         return True
65:     return False
66: 
67: 
68: def _validate_tls_mode(tls_mode: Any) -> str:
69:     if type(tls_mode) is not str:
70:         raise KismetEventbusTransportConfigError("tls_mode invalid")
71:     if tls_mode not in _TLS_MODES:
72:         raise KismetEventbusTransportConfigError("tls_mode invalid")
73:     return tls_mode
74: 
75: 
76: def _validate_base_url(
77:     base_url: Any,
78:     tls_mode: str,
79: ) -> str:
80:     if type(base_url) is not str:
81:         raise KismetEventbusTransportConfigError("base_url invalid")
82: 
83:     try:
84:         parsed = urlparse(base_url)
85:         port = parsed.port
86:     except Exception:
87:         raise KismetEventbusTransportConfigError("base_url invalid")
88: 
89:     scheme = parsed.scheme.lower()
90: 
91:     if scheme not in _HTTP_SCHEMES:
92:         raise KismetEventbusTransportConfigError("base_url scheme invalid")
93: 
94:     host = parsed.hostname
95:     if host is None or host == "":
96:         raise KismetEventbusTransportConfigError("base_url host invalid")
97: 
98:     if parsed.username is not None or parsed.password is not None:
99:         raise KismetEventbusTransportConfigError("base_url credentials invalid")
100: 
101:     if parsed.query:
102:         raise KismetEventbusTransportConfigError("base_url query invalid")
103: 
104:     if parsed.fragment:
105:         raise KismetEventbusTransportConfigError("base_url fragment invalid")
106: 
107:     path = parsed.path
108:     if path not in {"", "/"}:
109:         raise KismetEventbusTransportConfigError("base_url path invalid")
110: 
111:     if port is not None and not (1 <= port <= 65535):
112:         raise KismetEventbusTransportConfigError("base_url port invalid")
113: 
114:     if scheme == "https":
115:         if tls_mode != "verify_required":
116:             raise KismetEventbusTransportConfigError("base_url tls mismatch")
117:     elif scheme == "http":
118:         if tls_mode != "loopback_plaintext":
119:             raise KismetEventbusTransportConfigError("base_url tls mismatch")
120:         if not _is_loopback_host(host):
121:             raise KismetEventbusTransportConfigError("base_url loopback invalid")
122: 
123:     return base_url
124: 
125: 
126: def _validate_topics(
127:     topics: Any,
128: ) -> tuple[str, ...]:
129:     if type(topics) is not tuple:
130:         raise KismetEventbusTransportConfigError("topics invalid")
131: 
132:     if len(topics) == 0:
133:         raise KismetEventbusTransportConfigError("topics empty")
134: 
135:     seen: set[str] = set()
136:     result: list[str] = []
137: 
138:     for topic in topics:
139:         if type(topic) is not str:
140:             raise KismetEventbusTransportConfigError("topic invalid")
141:         if topic == "":
142:             raise KismetEventbusTransportConfigError("topic empty")
143:         if topic != topic.strip():
144:             raise KismetEventbusTransportConfigError("topic whitespace")
145: 
146:         if topic not in seen:
147:             seen.add(topic)
148:             result.append(topic)
149: 
150:     return tuple(result)
151: 
152: 
153: def _validate_authorization_header_value(
154:     raw: Any,
155: ) -> bytes:
156:     if type(raw) is not bytes:
157:         raise KismetEventbusTransportConfigError("authorization invalid")
158:     if len(raw) == 0:
159:         raise KismetEventbusTransportConfigError("authorization empty")
160: 
161:     try:
162:         decoded = raw.decode("ascii")
163:     except UnicodeDecodeError:
164:         raise KismetEventbusTransportConfigError("authorization not ascii")
165: 
166:     if "\r" in decoded or "\n" in decoded:
167:         raise KismetEventbusTransportConfigError("authorization line break")
168: 
169:     return raw
170: 
171: 
172: def _validate_time_value(
173:     raw: Any,
174:     name: str,
175: ) -> float:
176:     if type(raw) not in (int, float):
177:         raise KismetEventbusTransportConfigError(f"{name} invalid")
178: 
179:     value = float(raw)
180: 
181:     if math.isnan(value) or math.isinf(value):
182:         raise KismetEventbusTransportConfigError(f"{name} invalid")
183: 
184:     if value <= 0:
185:         raise KismetEventbusTransportConfigError(f"{name} invalid")
186: 
187:     return value
188: 
189: 
190: # ------------------------------------------------------------------
191: # Public config class  (frozen, no secret in repr/str/eq)
192: # ------------------------------------------------------------------
193: 
194: 
195: @dataclass(frozen=True, slots=True, repr=False, eq=False)
196: class KismetEventbusTransportConfigV1:
197:     """Immutable, validated configuration for KismetEventbusTransport.
198: 
199:     Public properties expose only non-secret fields.  The authorization
200:     header value is never exposed through repr, str, equality, or any
201:     public property.
202:     """
203: 
204:     _base_url: str
205:     _topics: tuple[str, ...]
206:     _authorization_header_value: bytes
207:     _tls_mode: str
208:     _connect_timeout_s: float
209:     _reconnect_delay_s: float
210:     _stop_join_timeout_s: float
211: 
212:     def __repr__(self) -> str:
213:         return (
214:             f"{type(self).__name__}("
215:             f"base_url={self._base_url!r}, "
216:             f"topics={self._topics!r}, "
217:             f"authorization_header_value=<redacted>, "
218:             f"tls_mode={self._tls_mode!r}, "
219:             f"connect_timeout_s={self._connect_timeout_s!r}, "
220:             f"reconnect_delay_s={self._reconnect_delay_s!r}, "
221:             f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
222:         )
223: 
224:     def __str__(self) -> str:
225:         return (
226:             f"{type(self).__name__}("
227:             f"base_url={self._base_url!r}, "
228:             f"topics={self._topics!r}, "
229:             f"authorization_header_value=<redacted>, "
230:             f"tls_mode={self._tls_mode!r}, "
231:             f"connect_timeout_s={self._connect_timeout_s!r}, "
232:             f"reconnect_delay_s={self._reconnect_delay_s!r}, "
233:             f"stop_join_timeout_s={self._stop_join_timeout_s!r})"
234:         )
235: 
236:     @property
237:     def base_url(self) -> str:
238:         return self._base_url
239: 
240:     @property
241:     def topics(self) -> tuple[str, ...]:
242:         return self._topics
243: 
244:     @property
245:     def tls_mode(self) -> str:
246:         return self._tls_mode
247: 
248:     @property
249:     def connect_timeout_s(self) -> float:
250:         return self._connect_timeout_s
251: 
252:     @property
253:     def reconnect_delay_s(self) -> float:
254:         return self._reconnect_delay_s
255: 
256:     @property
257:     def stop_join_timeout_s(self) -> float:
258:         return self._stop_join_timeout_s
259: 
260: 
261: # ------------------------------------------------------------------
262: # Public factory
263: # ------------------------------------------------------------------
264: 
265: 
266: def create_kismet_eventbus_transport_config(
267:     *,
268:     base_url: str,
269:     topics: tuple[str, ...],
270:     authorization_header_value: bytes,
271:     tls_mode: str,
272:     connect_timeout_s: float,
273:     reconnect_delay_s: float,
274:     stop_join_timeout_s: float,
275: ) -> KismetEventbusTransportConfigV1:
276:     """Create an immutable validated transport config.
277: 
278:     All arguments are keyword-only.  No I/O is performed.  The returned
279:     config is guaranteed to hold only valid values.
280:     """
281:     validated_tls_mode = _validate_tls_mode(tls_mode)
282:     validated_base_url = _validate_base_url(base_url, validated_tls_mode)
283:     validated_topics = _validate_topics(topics)
284:     validated_auth = _validate_authorization_header_value(
285:         authorization_header_value
286:     )
287: 
288:     validated_connect = _validate_time_value(
289:         connect_timeout_s, "connect_timeout_s"
290:     )
291:     validated_reconnect = _validate_time_value(
292:         reconnect_delay_s, "reconnect_delay_s"
293:     )
294:     validated_stop_join = _validate_time_value(
295:         stop_join_timeout_s, "stop_join_timeout_s"
296:     )
297: 
298:     return KismetEventbusTransportConfigV1(
299:         _base_url=validated_base_url,
300:         _topics=validated_topics,
301:         _authorization_header_value=validated_auth,
302:         _tls_mode=validated_tls_mode,
303:         _connect_timeout_s=validated_connect,
304:         _reconnect_delay_s=validated_reconnect,
305:         _stop_join_timeout_s=validated_stop_join,
306:     )

(End of file - total 306 lines)
</content>
```

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
9: import builtins
10: import importlib
11: import os
12: import sys
13: import types
14: import unittest
15: from unittest.mock import patch
16: 
17: import kismet_eventbus_runtime_config as _config_module
18: from kismet_eventbus_runtime_config import (
19:     KismetEventbusTransportConfigError,
20:     KismetEventbusTransportConfigV1,
21:     create_kismet_eventbus_transport_config,
22: )
23: 
24: # ------------------------------------------------------------------
25: # Synthetic secret for testing — never a real credential.
26: # "Basic dGVzdDp0ZXN0" is "Basic test:test" in base64.
27: # ------------------------------------------------------------------
28: 
29: _SYNTHETIC_SECRET = b"Basic dGVzdDp0ZXN0"
30: 
31: 
32: def _valid_kwargs(**overrides: object) -> dict:
33:     kwargs: dict = {
34:         "base_url": "https://kismet.example.com",
35:         "topics": ("test-topic",),
36:         "authorization_header_value": _SYNTHETIC_SECRET,
37:         "tls_mode": "verify_required",
38:         "connect_timeout_s": 10.0,
39:         "reconnect_delay_s": 5.0,
40:         "stop_join_timeout_s": 5.0,
41:     }
42:     kwargs.update(overrides)
43:     return kwargs
44: 
45: 
46: class _MyStr(str):
47:     pass
48: 
49: 
50: class _MyTuple(tuple):
51:     pass
52: 
53: 
54: class _MyBytes(bytes):
55:     pass
56: 
57: 
58: class _MyInt(int):
59:     pass
60: 
61: 
62: class _MyFloat(float):
63:     pass
64: 
65: 
66: class KismetEventbusRuntimeConfigSurfaceTests(unittest.TestCase):
67:     """1. Public export surface."""
68: 
69:     def test_module_all_contains_exactly_two_names(self) -> None:
70:         self.assertEqual(
71:             sorted(_config_module.__all__),
72:             sorted(
73:                 [
74:                     "KismetEventbusTransportConfigV1",
75:                     "create_kismet_eventbus_transport_config",
76:                 ]
77:             ),
78:         )
79: 
80:     def test_error_class_missing_from_all(self) -> None:
81:         self.assertNotIn(
82:             "KismetEventbusTransportConfigError",
83:             _config_module.__all__,
84:         )
85: 
86:     def test_public_properties_present(self) -> None:
87:         for name in (
88:             "base_url",
89:             "topics",
90:             "tls_mode",
91:             "connect_timeout_s",
92:             "reconnect_delay_s",
93:             "stop_join_timeout_s",
94:         ):
95:             self.assertTrue(
96:                 hasattr(KismetEventbusTransportConfigV1, name),
97:                 f"missing property {name}",
98:             )
99: 
100: 
101: class KismetEventbusRuntimeConfigImmutabilityTests(unittest.TestCase):
102:     """2. Immutability and identity semantics."""
103: 
104:     def test_config_has_no_instance_dict(self) -> None:
105:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
106:         self.assertFalse(hasattr(config, "__dict__"))
107: 
108:     def test_mutation_fails(self) -> None:
109:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
110:         with self.assertRaises(Exception):
111:             config._base_url = "https://evil.com"  # type: ignore[misc]
112: 
113:     def test_deletion_fails(self) -> None:
114:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
115:         with self.assertRaises(Exception):
116:             del config._base_url  # type: ignore[misc]
117: 
118:     def test_equal_content_not_structurally_equal(self) -> None:
119:         a = create_kismet_eventbus_transport_config(**_valid_kwargs())
120:         b = create_kismet_eventbus_transport_config(**_valid_kwargs())
121:         self.assertIsNot(a, b)
122:         self.assertFalse(a == b)
123:         self.assertIs(a.__eq__(b), NotImplemented)
124: 
125: 
126: class KismetEventbusRuntimeConfigReprStrTests(unittest.TestCase):
127:     """3. Secret not in repr or str."""
128: 
129:     def test_repr_does_not_contain_secret(self) -> None:
130:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
131:         r = repr(config)
132:         self.assertNotIn("dGVzdDp0ZXN0", r)
133:         self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), r)
134:         self.assertNotIn(str(_SYNTHETIC_SECRET), r)
135:         self.assertIn("<redacted>", r)
136: 
137:     def test_str_does_not_contain_secret(self) -> None:
138:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
139:         s = str(config)
140:         self.assertNotIn("dGVzdDp0ZXN0", s)
141:         self.assertNotIn(_SYNTHETIC_SECRET.decode("ascii"), s)
142:         self.assertNotIn(str(_SYNTHETIC_SECRET), s)
143:         self.assertIn("<redacted>", s)
144: 
145:     def test_no_public_authorization_property(self) -> None:
146:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
147:         self.assertFalse(
148:             hasattr(config, "authorization_header_value")
149:         )
150: 
151:     def test_no_public_secret_name_in_dir(self) -> None:
152:         config = create_kismet_eventbus_transport_config(**_valid_kwargs())
153:         public_names = {name for name in dir(config) if not name.startswith("_")}
154:         for name in public_names:
155:             self.assertNotIn("authorization", name)
156:             self.assertNotIn("secret", name)
157: 
158: 
159: class KismetEventbusRuntimeConfigExactTypeTests(unittest.TestCase):
160:     """4. Exact type boundaries reject subclasses and wrong types."""
161: 
162:     def test_base_url_rejects_str_subclass(self) -> None:
163:         with self.assertRaises(KismetEventbusTransportConfigError):
164:             create_kismet_eventbus_transport_config(
165:                 **_valid_kwargs(base_url=_MyStr("https://kismet.example.com"))
166:             )
167: 
168:     def test_base_url_rejects_non_string(self) -> None:
169:         for value in (123, None, b"https://kismet.example.com"):
170:             with self.subTest(value=value):
171:                 with self.assertRaises(KismetEventbusTransportConfigError):
172:                     create_kismet_eventbus_transport_config(
173:                         **_valid_kwargs(base_url=value)
174:                     )
175: 
176:     def test_tls_mode_rejects_str_subclass(self) -> None:
177:         with self.assertRaises(KismetEventbusTransportConfigError):
178:             create_kismet_eventbus_transport_config(
179:                 **_valid_kwargs(tls_mode=_MyStr("verify_required"))
180:             )
181: 
182:     def test_topics_rejects_tuple_subclass(self) -> None:
183:         with self.assertRaises(KismetEventbusTransportConfigError):
184:             create_kismet_eventbus_transport_config(
185:                 **_valid_kwargs(topics=_MyTuple(["a"]))
186:             )
187: 
188:     def test_topics_rejects_non_tuple(self) -> None:
189:         for value in (["a"], {"a"}, "a", None):
190:             with self.subTest(value=value):
191:                 with self.assertRaises(KismetEventbusTransportConfigError):
192:                     create_kismet_eventbus_transport_config(
193:                         **_valid_kwargs(topics=value)
194:                     )
195: 
196:     def test_topic_rejects_str_subclass(self) -> None:
197:         with self.assertRaises(KismetEventbusTransportConfigError):
198:             create_kismet_eventbus_transport_config(
199:                 **_valid_kwargs(topics=(_MyStr("a"),))
200:             )
201: 
202:     def test_authorization_rejects_bytes_subclass(self) -> None:
203:         with self.assertRaises(KismetEventbusTransportConfigError):
204:             create_kismet_eventbus_transport_config(
205:                 **_valid_kwargs(
206:                     authorization_header_value=_MyBytes(b"Basic dGVzdA==")
207:                 )
208:             )
209: 
210:     def test_authorization_rejects_non_bytes(self) -> None:
211:         for value in (
212:             "Basic dGVzdA==",
213:             123,
214:             None,
215:             [b"Basic"],
216:         ):
217:             with self.subTest(value=value):
218:                 with self.assertRaises(KismetEventbusTransportConfigError):
219:                     create_kismet_eventbus_transport_config(
220:                         **_valid_kwargs(authorization_header_value=value)
221:                     )
222: 
223:     def test_time_values_reject_int_subclass(self) -> None:
224:         for field in (
225:             "connect_timeout_s",
226:             "reconnect_delay_s",
227:             "stop_join_timeout_s",
228:         ):
229:             with self.subTest(field=field):
230:                 with self.assertRaises(KismetEventbusTransportConfigError):
231:                     create_kismet_eventbus_transport_config(
232:                         **_valid_kwargs(**{field: _MyInt(5)})
233:                     )
234: 
235:     def test_time_values_reject_float_subclass(self) -> None:
236:         for field in (
237:             "connect_timeout_s",
238:             "reconnect_delay_s",
239:             "stop_join_timeout_s",
240:         ):
241:             with self.subTest(field=field):
242:                 with self.assertRaises(KismetEventbusTransportConfigError):
243:                     create_kismet_eventbus_transport_config(
244:                         **_valid_kwargs(**{field: _MyFloat(5.0)})
245:                     )
246: 
247: 
248: class KismetEventbusRuntimeConfigUrlTests(unittest.TestCase):
249:     """5. Base URL matrix."""
250: 
251:     def _assert_valid(
252:         self, base_url: str, tls_mode: str = "verify_required"
253:     ) -> None:
254:         config = create_kismet_eventbus_transport_config(
255:             base_url=base_url,
256:             topics=("t",),
257:             authorization_header_value=_SYNTHETIC_SECRET,
258:             tls_mode=tls_mode,
259:             connect_timeout_s=10,
260:             reconnect_delay_s=5,
261:             stop_join_timeout_s=5,
262:         )
263:         self.assertEqual(config.base_url, base_url)
264: 
265:     def _assert_invalid(
266:         self, base_url: object, tls_mode: str = "verify_required"
267:     ) -> None:
268:         kwargs = _valid_kwargs(base_url=base_url, tls_mode=tls_mode)
269:         with self.assertRaises(KismetEventbusTransportConfigError):
270:             create_kismet_eventbus_transport_config(**kwargs)
271: 
272:     def test_remote_https(self) -> None:
273:         self._assert_valid("https://kismet.example.com")
274: 
275:     def test_remote_https_with_port(self) -> None:
276:         self._assert_valid("https://kismet.example.com:443")
277: 
278:     def test_remote_https_with_root_slash(self) -> None:
279:         self._assert_valid("https://kismet.example.com/")
280: 
281:     def test_localhost_http(self) -> None:
282:         self._assert_valid(
283:             "http://localhost", tls_mode="loopback_plaintext"
284:         )
285: 
286:     def test_localhost_http_with_port(self) -> None:
287:         self._assert_valid(
288:             "http://localhost:8080", tls_mode="loopback_plaintext"
289:         )
290: 
291:     def test_ipv4_loopback_127_0_0_1(self) -> None:
292:         self._assert_valid(
293:             "http://127.0.0.1", tls_mode="loopback_plaintext"
294:         )
295: 
296:     def test_ipv4_loopback_subnet(self) -> None:
297:         self._assert_valid(
298:             "http://127.0.0.42", tls_mode="loopback_plaintext"
299:         )
300: 
301:     def test_ipv6_loopback(self) -> None:
302:         self._assert_valid(
303:             "http://[::1]", tls_mode="loopback_plaintext"
304:         )
305: 
306:     def test_ipv6_loopback_with_port(self) -> None:
307:         self._assert_valid(
308:             "http://[::1]:8080", tls_mode="loopback_plaintext"
309:         )
310: 
311:     def test_remote_http_rejected(self) -> None:
312:         self._assert_invalid(
313:             "http://kismet.example.com", tls_mode="loopback_plaintext"
314:         )
315: 
316:     def test_credentials_rejected(self) -> None:
317:         self._assert_invalid("https://user:pass@kismet.example.com")
318:         self._assert_invalid("https://user@kismet.example.com")
319:         self._assert_invalid("https://:pass@kismet.example.com")
320: 
321:     def test_query_rejected(self) -> None:
322:         self._assert_invalid("https://kismet.example.com?q=1")
323: 
324:     def test_fragment_rejected(self) -> None:
325:         self._assert_invalid("https://kismet.example.com#frag")
326: 
327:     def test_path_rejected(self) -> None:
328:         self._assert_invalid("https://kismet.example.com/foo")
329:         self._assert_invalid("https://kismet.example.com/foo/")
330: 
331:     def test_double_slash_path_rejected(self) -> None:
332:         self._assert_invalid("https://kismet.example.com//")
333: 
334:     def test_triple_slash_path_rejected(self) -> None:
335:         self._assert_invalid("https://kismet.example.com///")
336: 
337:     def test_port_zero_rejected(self) -> None:
338:         self._assert_invalid("https://kismet.example.com:0")
339: 
340:     def test_port_65536_rejected(self) -> None:
341:         self._assert_invalid("https://kismet.example.com:65536")
342: 
343:     def test_non_numeric_port_rejected(self) -> None:
344:         self._assert_invalid("https://kismet.example.com:abc")
345: 
346:     def test_missing_host_rejected(self) -> None:
347:         self._assert_invalid("https://")
348:         self._assert_invalid("http:///path")
349:         self._assert_invalid("https:///")
350: 
351:     def test_wrong_scheme_rejected(self) -> None:
352:         self._assert_invalid("ftp://kismet.example.com")
353:         self._assert_invalid("ws://kismet.example.com")
354:         self._assert_invalid("//kismet.example.com")
355: 
356:     def test_https_with_loopback_tls_rejected(self) -> None:
357:         self._assert_invalid(
358:             "https://kismet.example.com", tls_mode="loopback_plaintext"
359:         )
360: 
361:     def test_http_with_verify_required_rejected(self) -> None:
362:         self._assert_invalid(
363:             "http://localhost", tls_mode="verify_required"
364:         )
365: 
366:     def test_invalid_tls_mode_rejected(self) -> None:
367:         self._assert_invalid(
368:             "https://kismet.example.com", tls_mode="invalid"
369:         )
370: 
371:     def test_non_string_tls_mode_rejected(self) -> None:
372:         self._assert_invalid(
373:             "https://kismet.example.com", tls_mode=123  # type: ignore[arg-type]
374:         )
375: 
376: 
377: class KismetEventbusRuntimeConfigTopicsTests(unittest.TestCase):
378:     """6. Topic validation."""
379: 
380:     def test_stable_deduplication(self) -> None:
381:         config = create_kismet_eventbus_transport_config(
382:             **_valid_kwargs(topics=("a", "b", "a", "c", "b"))
383:         )
384:         self.assertEqual(config.topics, ("a", "b", "c"))
385: 
386:     def test_empty_tuple_rejected(self) -> None:
387:         with self.assertRaises(KismetEventbusTransportConfigError):
388:             create_kismet_eventbus_transport_config(
389:                 **_valid_kwargs(topics=())
390:             )
391: 
392:     def test_empty_string_topic_rejected(self) -> None:
393:         with self.assertRaises(KismetEventbusTransportConfigError):
394:             create_kismet_eventbus_transport_config(
395:                 **_valid_kwargs(topics=("valid", ""))
396:             )
397: 
398:     def test_leading_whitespace_rejected(self) -> None:
399:         with self.assertRaises(KismetEventbusTransportConfigError):
400:             create_kismet_eventbus_transport_config(
401:                 **_valid_kwargs(topics=(" leading",))
402:             )
403: 
404:     def test_trailing_whitespace_rejected(self) -> None:
405:         with self.assertRaises(KismetEventbusTransportConfigError):
406:             create_kismet_eventbus_transport_config(
407:                 **_valid_kwargs(topics=("trailing ",))
408:             )
409: 
410:     def test_both_whitespace_rejected(self) -> None:
411:         with self.assertRaises(KismetEventbusTransportConfigError):
412:             create_kismet_eventbus_transport_config(
413:                 **_valid_kwargs(topics=(" both ",))
414:             )
415: 
416:     def test_non_tuple_rejected(self) -> None:
417:         for value in (["a"], {"a"}, "a", 123, None):
418:             with self.subTest(value=value):
419:                 with self.assertRaises(KismetEventbusTransportConfigError):
420:                     create_kismet_eventbus_transport_config(
421:                         **_valid_kwargs(topics=value)
422:                     )
423: 
424:     def test_non_string_element_rejected(self) -> None:
425:         for value in (("a", 42), ("a", None), ("a", b"b")):
426:             with self.subTest(value=value):
427:                 with self.assertRaises(KismetEventbusTransportConfigError):
428:                     create_kismet_eventbus_transport_config(
429:                         **_valid_kwargs(topics=value)
430:                     )
431: 
432:     def test_str_subclass_element_rejected(self) -> None:
433:         with self.assertRaises(KismetEventbusTransportConfigError):
434:             create_kismet_eventbus_transport_config(
435:                 **_valid_kwargs(topics=(_MyStr("a"),))
436:             )
437: 
438:     def test_tuple_subclass_rejected(self) -> None:
439:         with self.assertRaises(KismetEventbusTransportConfigError):
440:             create_kismet_eventbus_transport_config(
441:                 **_valid_kwargs(topics=_MyTuple(["a"]))
442:             )
443: 
444: 
445: class KismetEventbusRuntimeConfigAuthTests(unittest.TestCase):
446:     """7. Authorization header validation."""
447: 
448:     def _assert_secret_not_in_exception(self, value: object) -> None:
449:         secret_text = _SYNTHETIC_SECRET.decode("ascii")
450:         with self.assertRaises(KismetEventbusTransportConfigError) as ctx:
451:             create_kismet_eventbus_transport_config(
452:                 **_valid_kwargs(authorization_header_value=value)
453:             )
454:         msg = str(ctx.exception)
455:         self.assertNotIn(secret_text, msg)
456:         self.assertNotIn("dGVzdDp0ZXN0", msg)
457:         self.assertNotIn("Basic", msg)
458: 
459:     def test_valid_bytes_accepted(self) -> None:
460:         config = create_kismet_eventbus_transport_config(
461:             **_valid_kwargs(authorization_header_value=b"Basic dGVzdA==")
462:         )
463:         self.assertIsInstance(config, KismetEventbusTransportConfigV1)
464: 
465:     def test_empty_rejected(self) -> None:
466:         self._assert_secret_not_in_exception(b"")
467: 
468:     def test_string_rejected(self) -> None:
469:         self._assert_secret_not_in_exception("Basic dGVzdA==")
470: 
471:     def test_bytes_subclass_rejected(self) -> None:
472:         self._assert_secret_not_in_exception(_MyBytes(b"Basic dGVzdA=="))
473: 
474:     def test_non_ascii_rejected(self) -> None:
475:         self._assert_secret_not_in_exception(b"\xff\xfe\x00")
476: 
477:     def test_cr_rejected(self) -> None:
478:         self._assert_secret_not_in_exception(b"Basic\rtest")
479: 
480:     def test_lf_rejected(self) -> None:
481:         self._assert_secret_not_in_exception(b"Basic\ntest")
482: 
483:     def test_crlf_rejected(self) -> None:
484:         self._assert_secret_not_in_exception(b"Basic\r\ntest")
485: 
486:     def test_invalid_auth_exception_has_no_value_bytes(self) -> None:
487:         invalid = b"\xff\xfe"
488:         with self.assertRaises(KismetEventbusTransportConfigError) as ctx:
489:             create_kismet_eventbus_transport_config(
490:                 **_valid_kwargs(authorization_header_value=invalid)
491:             )
492:         msg = str(ctx.exception)
493:         self.assertNotIn("\xff", msg)
494:         self.assertNotIn("\xfe", msg)
495:         self.assertNotIn("xff", msg)
496:         self.assertNotIn("xfe", msg)
497: 
498: 
499: class KismetEventbusRuntimeConfigTimeTests(unittest.TestCase):
500:     """8. Time value validation matrix."""
501: 
502:     def _assert_rejected(self, field: str, value: object) -> None:
503:         with self.assertRaises(KismetEventbusTransportConfigError):
504:             create_kismet_eventbus_transport_config(
505:                 **_valid_kwargs(**{field: value})
506:             )
507: 
508:     def _assert_accepted(self, field: str, value: object, expected: float) -> None:
509:         config = create_kismet_eventbus_transport_config(
510:             **_valid_kwargs(**{field: value})
511:         )
512:         self.assertEqual(getattr(config, field), expected)
513: 
514:     def test_valid_int_becomes_float(self) -> None:
515:         for field in (
516:             "connect_timeout_s",
517:             "reconnect_delay_s",
518:             "stop_join_timeout_s",
519:         ):
520:             with self.subTest(field=field):
521:                 self._assert_accepted(field, 5, 5.0)
522: 
523:     def test_valid_float_unchanged(self) -> None:
524:         config = create_kismet_eventbus_transport_config(
525:             **_valid_kwargs(
526:                 connect_timeout_s=15.5,
527:                 reconnect_delay_s=2.5,
528:                 stop_join_timeout_s=3.5,
529:             )
530:         )
531:         self.assertEqual(config.connect_timeout_s, 15.5)
532:         self.assertEqual(config.reconnect_delay_s, 2.5)
533:         self.assertEqual(config.stop_join_timeout_s, 3.5)
534: 
535:     def test_true_rejected(self) -> None:
536:         for field in (
537:             "connect_timeout_s",
538:             "reconnect_delay_s",
539:             "stop_join_timeout_s",
540:         ):
541:             with self.subTest(field=field):
542:                 self._assert_rejected(field, True)
543: 
544:     def test_false_rejected(self) -> None:
545:         for field in (
546:             "connect_timeout_s",
547:             "reconnect_delay_s",
548:             "stop_join_timeout_s",
549:         ):
550:             with self.subTest(field=field):
551:                 self._assert_rejected(field, False)
552: 
553:     def test_none_rejected(self) -> None:
554:         for field in (
555:             "connect_timeout_s",
556:             "reconnect_delay_s",
557:             "stop_join_timeout_s",
558:         ):
559:             with self.subTest(field=field):
560:                 self._assert_rejected(field, None)
561: 
562:     def test_string_rejected(self) -> None:
563:         for field in (
564:             "connect_timeout_s",
565:             "reconnect_delay_s",
566:             "stop_join_timeout_s",
567:         ):
568:             with self.subTest(field=field):
569:                 self._assert_rejected(field, "10")
570: 
571:     def test_zero_rejected(self) -> None:
572:         for field in (
573:             "connect_timeout_s",
574:             "reconnect_delay_s",
575:             "stop_join_timeout_s",
576:         ):
577:             with self.subTest(field=field):
578:                 self._assert_rejected(field, 0)
579:                 self._assert_rejected(field, 0.0)
580: 
581:     def test_negative_rejected(self) -> None:
582:         for field in (
583:             "connect_timeout_s",
584:             "reconnect_delay_s",
585:             "stop_join_timeout_s",
586:         ):
587:             with self.subTest(field=field):
588:                 self._assert_rejected(field, -1)
589:                 self._assert_rejected(field, -1.0)
590: 
591:     def test_nan_rejected(self) -> None:
592:         for field in (
593:             "connect_timeout_s",
594:             "reconnect_delay_s",
595:             "stop_join_timeout_s",
596:         ):
597:             with self.subTest(field=field):
598:                 self._assert_rejected(field, float("nan"))
599: 
600:     def test_positive_inf_rejected(self) -> None:
601:         for field in (
602:             "connect_timeout_s",
603:             "reconnect_delay_s",
604:             "stop_join_timeout_s",
605:         ):
606:             with self.subTest(field=field):
607:                 self._assert_rejected(field, float("inf"))
608: 
609:     def test_negative_inf_rejected(self) -> None:
610:         for field in (
611:             "connect_timeout_s",
612:             "reconnect_delay_s",
613:             "stop_join_timeout_s",
614:         ):
615:             with self.subTest(field=field):
616:                 self._assert_rejected(field, float("-inf"))
617: 
618:     def test_int_subclass_rejected(self) -> None:
619:         for field in (
620:             "connect_timeout_s",
621:             "reconnect_delay_s",
622:             "stop_join_timeout_s",
623:         ):
624:             with self.subTest(field=field):
625:                 self._assert_rejected(field, _MyInt(5))
626: 
627:     def test_float_subclass_rejected(self) -> None:
628:         for field in (
629:             "connect_timeout_s",
630:             "reconnect_delay_s",
631:             "stop_join_timeout_s",
632:         ):
633:             with self.subTest(field=field):
634:                 self._assert_rejected(field, _MyFloat(5.0))
635: 
636: 
637: class KismetEventbusRuntimeConfigSideEffectTests(unittest.TestCase):
638:     """9. No environment, home, file, netrc, keyring, network, socket,
639:     or subprocess usage in the config module.
640:     """
641: 
642:     def test_no_forbidden_module_level_imports(self) -> None:
643:         forbidden = {
644:             "os",
645:             "pathlib",
646:             "netrc",
647:             "keyring",
648:             "keyczar",
649:             "cryptography",
650:             "socket",
651:             "subprocess",
652:         }
653: 
654:         with open("kismet_eventbus_runtime_config.py") as f:
655:             tree = ast.parse(f.read())
656: 
657:         module_level_imports: set[str] = set()
658:         for node in tree.body:
659:             if isinstance(node, ast.Import):
660:                 for alias in node.names:
661:                     module_level_imports.add(alias.name.split(".")[0])
662:             elif isinstance(node, ast.ImportFrom):
663:                 if node.module:
664:                     module_level_imports.add(node.module.split(".")[0])
665: 
666:         found = module_level_imports & forbidden
667:         self.assertEqual(
668:             found,
669:             set(),
670:             f"forbidden module-level imports: {found}",
671:         )
672: 
673:     def test_no_discovery_or_io_calls_in_ast(self) -> None:
674:         forbidden_calls = {
675:             "open",
676:             "getenv",
677:             "environ",
678:             "expanduser",
679:             "netrc",
680:             "get_password",
681:             "socket",
682:             "Popen",
683:             "run",
684:             "call",
685:         }
686: 
687:         with open("kismet_eventbus_runtime_config.py") as f:
688:             tree = ast.parse(f.read())
689: 
690:         for node in ast.walk(tree):
691:             if isinstance(node, ast.Call):
692:                 func = node.func
693:                 if isinstance(func, ast.Name):
694:                     self.assertNotIn(
695:                         func.id,
696:                         forbidden_calls,
697:                         f"forbidden call {func.id}",
698:                     )
699:                 elif isinstance(func, ast.Attribute):
700:                     self.assertNotIn(
701:                         func.attr,
702:                         forbidden_calls,
703:                         f"forbidden call .{func.attr}",
704:                     )
705: 
706:     def test_factory_performs_no_forbidden_io(self) -> None:
707:         def fail(name: str):
708:             def _fail(*args: object, **kwargs: object) -> object:
709:                 raise AssertionError(f"forbidden {name} called")
710:             return _fail
711: 
712:         with patch.object(builtins, "open", fail("open")), \
713:              patch("os.environ.get", fail("os.environ.get")), \
714:              patch("os.path.expanduser", fail("expanduser")), \
715:              patch("netrc.netrc", fail("netrc.netrc")), \
716:              patch("keyring.get_password", fail("keyring.get_password")), \
717:              patch("socket.socket", fail("socket.socket")), \
718:              patch("subprocess.Popen", fail("subprocess.Popen")), \
719:              patch("subprocess.run", fail("subprocess.run")):
720:             config = create_kismet_eventbus_transport_config(**_valid_kwargs())
721:             self.assertIsInstance(config, KismetEventbusTransportConfigV1)
722: 
723: 
724: class KismetEventbusRuntimeConfigReimportTests(unittest.TestCase):
725:     """10. Re-import safety without global sys.modules mutation."""
726: 
727:     def test_reimport_does_not_mutate_sys_modules(self) -> None:
728:         before = set(sys.modules.keys())
729:         importlib.reload(_config_module)
730:         after = set(sys.modules.keys())
731:         self.assertEqual(before, after)
732: 
733: 
734: if __name__ == "__main__":
735:     unittest.main()

(End of file - total 735 lines)
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

## Assistant (Build · Kimi K2.7 Code · 42.0s)

_Thinking:_

Now I understand the codebase. Let me plan the changes:

### Changes to `kismet_eventbus_runtime_config.py`:

1. **Use `urlsplit` instead of `urlparse`** - so semicolon path components stay in path, not in params. Need to import `urlsplit` from urllib.parse.

2. **Reject empty port syntax** - After parsing, check if authority ends with `:`. But need to be careful with IPv6 without port - authority ends with `]`, valid. With port, authority ends with `:port`, valid.

   Wait, with `urlsplit`/`urlparse`, what does `.port` return for `http://[::1]:`? Let me think. Actually `.port` would likely raise ValueError because empty port is invalid. The current code catches Exception and raises base_url invalid. But the requirement says we need to reject with KismetEventbusTransportConfigError, which it already does... but the issue is that `http://[::1]:/` might parse differently? Let me think.

   Actually the requirement says: "Eine robuste Lösung darf nach dem Parsing zusätzlich die Authority prüfen. Eine Authority, die mit einem Portdelimiter `:` endet, ist ungültig."

   So I should add a check: if `parsed.netloc` ends with `:` -> invalid. But `http://[::1]` netloc is `[::1]`, doesn't end with `:`. `http://[::1]:` netloc is `[::1]:`, ends with `:`, invalid. Good.

   But what about `https://kismet.example.com:`? netloc is `kismet.example.com:`, ends with `:`, invalid. `https://kismet.example.com` netloc is `kismet.example.com`, valid. Good.

3. **Strict scheme grammar** - Don't use `.lower()`. Compare scheme exactly against `{"http", "https"}`. So if scheme is `HTTPS` or `Https`, it's not in the set, reject.

4. **Reject empty query/fragment markers** - Currently checks `if parsed.query:` and `if parsed.fragment:`. Need to also reject when query/fragment marker is present but empty. Actually `urlparse("https://kismet.example.com?")` gives `.query == ""`. So I need to check if `'?' in base_url` after the netloc? Or simpler: check if the original URL string contains `?` or `#`? But that might be too broad (e.g., IPv6 brackets contain `:` not `?`/`#`).

   Actually, the parsed result for `https://kismet.example.com?` has `parsed.query == ""`. For `https://kismet.example.com#`, `parsed.fragment == ""`. So I need to detect the presence of the marker.

   The cleanest way is to check if `'?' in base_url` or `'#' in base_url`. But could `?` or `#` appear elsewhere? In valid URLs, `?` only appears as query marker, `#` only as fragment marker. In invalid URLs, if they appear in host/path, they'd be encoded. But we're not a full URL validator. Actually for our allowed URLs, `?` and `#` should never appear. So checking `'?' in base_url` or `'#' in base_url` is reasonable.

   Wait, but IPv6 addresses can contain `:` not `?` or `#`. So checking the raw string is fine.

   But the requirement says: "Nicht nur nichtleere Inhalte ablehnen, sondern auch leere Marker." So I can check if `parsed.query` is non-empty OR if `?` is in the URL. Similarly for fragment.

   Actually a more robust approach: use `urlsplit` and check `parsed.query` (empty string means no query) vs query marker present. Let me check Python behavior:
   - `urlsplit("https://kismet.example.com?")` -> SplitResult(scheme='https', netloc='kismet.example.com', path='', query='', fragment='')
   - `urlsplit("https://kismet.example.com")` -> SplitResult(scheme='https', netloc='kismet.example.com', path='', query='', fragment='')

   Both have `query == ''` and `fragment == ''`. So we can't distinguish from parsed object alone. Need to check the original string.

   I'll check `'?' in base_url` and `'#' in base_url`.

5. **Reject semicolon paths** - The allowed path set is `{"", "/"}`. With `urlsplit`, `https://kismet.example.com/;` has path `/;`. `https://kismet.example.com/;x` has path `/;x`. `https://kismet.example.com;x` - hmm, what does urlsplit do with this? Actually `https://kismet.example.com;x` - the `;x` would be part of path because there's no `/` before `;`. So path is `;x`. So checking `path not in {"", "/"}` will reject all three.

6. **Root-slash canonicalization** - If base_url ends with `/`, strip the trailing slash. But only for the root slash case, not for other paths. Since other paths are already rejected, if path is `/`, we can strip it. So after validation, if `path == "/"`, return `base_url.rstrip("/")` or `base_url[:-1]`.

   Need to be careful: `https://kismet.example.com/` -> strip trailing `/` -> `https://kismet.example.com`. `http://localhost/` -> `http://localhost`. `http://[::1]:2501/` -> `http://[::1]:2501`.

   But we should NOT do host/port/case normalization.

7. **Catch ValueError narrowly** - Change `except Exception:` to `except ValueError:` around urlparse/urlsplit. Actually urlsplit raises ValueError for invalid ports etc.

### Changes to `tests/test_kismet_eventbus_runtime_config.py`:

1. **Remove `KismetEventbusRuntimeConfigReimportTests`** class entirely.

2. **Remove unused imports**: `importlib`, `sys`, `types`, `os` (after checking if used elsewhere). `os` is used in `patch("os.environ.get"...)`, so keep. `importlib`, `sys`, `types` are only used in the reimport test. So remove them.

3. **AST import test** - Change `test_no_forbidden_module_level_imports` to walk entire AST and check all `ast.Import` and `ast.ImportFrom` nodes, not just module-level.

4. **Add URL regression tests**:
   - Six empty port variants
   - IPv6 without port valid
   - IPv6 with port valid
   - Four mixed/uppercase scheme variants rejected
   - Empty `?` and `#` rejected
   - Semicolon paths rejected
   - Root-slash canonicalization for HTTPS, localhost, IPv6 with port

Let me now write the modifications.

First, the config module changes. Let me edit it.

I need to:
- Change `from urllib.parse import urlparse` to `from urllib.parse import urlsplit`
- In `_validate_base_url`: use `urlsplit`, strict scheme, empty port check, empty query/fragment markers, semicolon path rejection, root slash canonicalization, narrow ValueError catch.

Let me write the new `_validate_base_url`:

```python
def _validate_base_url(
    base_url: Any,
    tls_mode: str,
) -> str:
    if type(base_url) is not str:
        raise KismetEventbusTransportConfigError("base_url invalid")

    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        raise KismetEventbusTransportConfigError("base_url invalid")

    scheme = parsed.scheme

    if scheme not in _HTTP_SCHEMES:
        raise KismetEventbusTransportConfigError("base_url scheme invalid")

    host = parsed.hostname
    if host is None or host == "":
        raise KismetEventbusTransportConfigError("base_url host invalid")

    if parsed.username is not None or parsed.password is not None:
        raise KismetEventbusTransportConfigError("base_url credentials invalid")

    if "?" in base_url:
        raise KismetEventbusTransportConfigError("base_url query invalid")

    if "#" in base_url:
        raise KismetEventbusTransportConfigError("base_url fragment invalid")

    path = parsed.path
    if path not in {"", "/"}:
        raise KismetEventbusTransportConfigError("base_url path invalid")

    if port is not None and not (1 <= port <= 65535):
        raise KismetEventbusTransportConfigError("base_url port invalid")

    # Reject empty port syntax: authority must not end with port delimiter.
    netloc = parsed.netloc
    if netloc.endswith(":"):
        raise KismetEventbusTransportConfigError("base_url port invalid")

    if scheme == "https":
        if tls_mode != "verify_required":
            raise KismetEventbusTransportConfigError("base_url tls mismatch")
    elif scheme == "http":
        if tls_mode != "loopback_plaintext":
            raise KismetEventbusTransportConfigError("base_url tls mismatch")
        if not _is_loopback_host(host):
            raise KismetEventbusTransportConfigError("base_url loopback invalid")

    # Canonicalize trailing root slash.
    if path == "/":
        return base_url.rstrip("/")

    return base_url
```

Wait, but `rstrip("/")` could strip multiple slashes. But we've already validated path is in `{"", "/"}`, so there's exactly one trailing slash at most. Actually `https://kismet.example.com/` has one trailing slash. `rstrip("/")` will remove just that one. Good.

But what if base_url is `https://kismet.example.com/`? `base_url.rstrip("/")` -> `https://kismet.example.com`. Good.

What about `http://[::1]:2501/`? -> `http://[::1]:2501`. Good.

Hmm, but what about `https://kismet.example.com:443/`? That's valid and path is `/`. Should we canonicalize to `https://kismet.example.com:443`? The requirement says "Kanonisiere gültige Root-Slash-URLs auf dieselbe gespeicherte Basis-URL ohne abschließenden Slash." Yes, all root-slash URLs. But it specifically mentions examples without ports. The general rule is: root-slash URLs -> no trailing slash. So yes, `https://kismet.example.com:443/` should become `https://kismet.example.com:443`. But the existing test `test_remote_https_with_port` expects `config.base_url == "https://kismet.example.com:443"`. There's no test for `https://kismet.example.com:443/` currently. The new tests should add root-slash canonicalization for IPv6 with port. So `http://[::1]:2501/` -> `http://[::1]:2501`.

Actually, let me think about the order of checks. The empty port check: `netloc.endswith(":")`. For `https://kismet.example.com:`, netloc is `kismet.example.com:`, ends with `:`, invalid. For `http://[::1]:`, netloc is `[::1]:`, ends with `:`, invalid. For `http://[::1]`, netloc is `[::1]`, valid. Good.

But wait, `urlsplit("https://kismet.example.com:")` - what is the netloc? Let me think. `:` after host with no port... The URL is `scheme://host:`. The netloc would be `kismet.example.com:`. And `.port` would raise ValueError? Actually with the current `except Exception`, it would be caught. But if `.port` raises ValueError, we'd already have returned `base_url invalid`. Then the netloc check wouldn't run. Hmm.

Actually, I think `urlsplit("https://kismet.example.com:").port` raises ValueError: "Port could not be cast to integer value as 'b''" or something. So with `except ValueError`, we'd catch it and raise base_url invalid. That would reject empty ports too. But the requirement specifically wants empty port syntax rejected, and using the netloc check is more explicit.

However, we should also handle the case where `.port` doesn't raise but netloc ends with `:`. Actually I think `.port` does raise for empty port. Let me be safe and keep the netloc check after the port check. Actually it doesn't matter much - either way they get rejected. But to be robust and explicit, keep the netloc check.

Wait, but for `https://kismet.example.com:/` - what happens? `urlsplit` netloc is `kismet.example.com:`, path is `/`. `.port` raises ValueError. So rejected.

For `http://[::1]:/` - netloc `[::1]:`, path `/`. `.port` raises ValueError. Rejected.

For `http://[::1]:` - same.

OK so the `.port` access itself will raise ValueError for empty ports. But we want explicit handling. We can put the netloc check before accessing `.port`? Or we can keep `.port` access inside try/except and also add netloc check outside.

Actually if `.port` raises ValueError, we catch it and raise "base_url invalid". That's acceptable but the test might expect "base_url port invalid"? No, the requirement just says content-free with KismetEventbusTransportConfigError. The specific message isn't tested. So either is fine.

But to be more specific and robust, I could avoid `.port` raising by checking netloc first, then accessing `.port`. But netloc check for `endswith(":")` would catch empty ports before `.port` access. For `https://kismet.example.com:`, netloc ends with `:`, raise. For `http://[::1]:`, same. For `https://kismet.example.com:abc`, netloc doesn't end with `:`, `.port` raises ValueError, catch -> base_url invalid. Good.

So order:
1. urlsplit
2. scheme check
3. host check
4. credentials check
5. query/fragment check
6. path check
7. netloc endswith ":" check
8. port range check
9. tls/loopback checks
10. canonicalize trailing slash

Wait, what about `https://kismet.example.com:`? After urlsplit, scheme valid, host valid, no credentials, no query/fragment, path is "" (valid), netloc ends with ":" -> reject. Good.

What about `https://kismet.example.com:/`? path is "/", valid, netloc ends with ":" -> reject. Good.

What about `http://[::1]`? netloc `[::1]`, doesn't end with `:`, `.port` is None, valid.

What about `http://[::1]:`? netloc `[::1]:`, ends with `:`, reject. Good.

What about `http://[::1]:/`? same, reject. Good.

What about `http://[::1]:8080`? netloc `[::1]:8080`, doesn't end with `:`, `.port` is 8080, valid.

Great.

Now the strict scheme: `scheme = parsed.scheme` (no .lower()). Check `scheme not in _HTTP_SCHEMES`. For `HTTPS://...`, scheme is `HTTPS`, not in set, reject. Good.

But wait, the transport module uses `parsed.scheme.lower()` in `_build_ws_url`. The config passes the canonical base_url (with scheme as originally typed, but only if valid). Since we only accept lowercase `http` and `https`, the base_url stored will have lowercase scheme. Actually if someone passes `http://localhost`, scheme is `http`, valid. The stored base_url will be `http://localhost` (unchanged). So the transport will parse it as `http` and map to `ws`. Good.

But what if someone passes `http://localhost/`? We canonicalize to `http://localhost`. Good.

Now empty query/fragment check: `'?' in base_url` and `'#' in base_url`.

But wait, what about the fragment marker being part of a valid URL? It's not, for our allowed set. What if someone passes `http://localhost#`? That's rejected because `#` in base_url. Good.

But there's a subtle issue: `https://kismet.example.com?` - the `?` is in the string, reject. `https://kismet.example.com?q=1` - also reject. Good.

Now the semicolon paths: With urlsplit:
- `https://kismet.example.com/;` -> path `/;`, not in `{"", "/"}`, reject.
- `https://kismet.example.com/;x` -> path `/;x`, reject.
- `https://kismet.example.com;x` -> path `;x`? Let me think. Actually `urlsplit("https://kismet.example.com;x")` - the part after `://` is `kismet.example.com;x`. urlsplit splits this as netloc=`kismet.example.com;x`? Or netloc=`kismet.example.com` and path=`;x`?

Hmm, this is tricky. Let me recall URL parsing rules. In the absence of a path, `;` in the netloc might be interpreted as part of the netloc? Actually RFC 3986 says `;` is a sub-delimiter and can appear in host names? No, host names can't contain `;` unencoded. But urlsplit might be lenient.

Actually I should test this. Let me run a quick Python command to see what urlsplit does.

**Tool: bash**

**Input:**
```json
{
  "command": "python3 - <<'PY'\nfrom urllib.parse import urlsplit\nfor url in [\n    'https://kismet.example.com;x',\n    'https://kismet.example.com/;',\n    'https://kismet.example.com/;x',\n    'https://kismet.example.com?',\n    'https://kismet.example.com/?',\n    'https://kismet.example.com#',\n    'https://kismet.example.com/#',\n    'https://kismet.example.com:',\n    'https://kismet.example.com:/',\n    'http://[::1]:',\n    'http://[::1]:/',\n    'http://[::1]',\n    'http://[::1]/',\n    'http://[::1]:8080',\n    'http://[::1]:8080/',\n    'HTTPS://kismet.example.com',\n    'Https://kismet.example.com',\n]:\n    try:\n        p = urlsplit(url)\n        print(f\"{url!r:45} -> scheme={p.scheme!r} netloc={p.netloc!r} path={p.path!r} query={p.query!r} fragment={p.fragment!r} port={p.port}\")\n    except Exception as e:\n        print(f\"{url!r:45} -> ERROR {type(e).__name__}: {e}\")\nPY",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
'https://kismet.example.com;x'                -> scheme='https' netloc='kismet.example.com;x' path='' query='' fragment='' port=None
'https://kismet.example.com/;'                -> scheme='https' netloc='kismet.example.com' path='/;' query='' fragment='' port=None
'https://kismet.example.com/;x'               -> scheme='https' netloc='kismet.example.com' path='/;x' query='' fragment='' port=None
'https://kismet.example.com?'                 -> scheme='https' netloc='kismet.example.com' path='' query='' fragment='' port=None
'https://kismet.example.com/?'                -> scheme='https' netloc='kismet.example.com' path='/' query='' fragment='' port=None
'https://kismet.example.com#'                 -> scheme='https' netloc='kismet.example.com' path='' query='' fragment='' port=None
'https://kismet.example.com/#'                -> scheme='https' netloc='kismet.example.com' path='/' query='' fragment='' port=None
'https://kismet.example.com:'                 -> scheme='https' netloc='kismet.example.com:' path='' query='' fragment='' port=None
'https://kismet.example.com:/'                -> scheme='https' netloc='kismet.example.com:' path='/' query='' fragment='' port=None
'http://[::1]:'                               -> scheme='http' netloc='[::1]:' path='' query='' fragment='' port=None
'http://[::1]:/'                              -> scheme='http' netloc='[::1]:' path='/' query='' fragment='' port=None
'http://[::1]'                                -> scheme='http' netloc='[::1]' path='' query='' fragment='' port=None
'http://[::1]/'                               -> scheme='http' netloc='[::1]' path='/' query='' fragment='' port=None
'http://[::1]:8080'                           -> scheme='http' netloc='[::1]:8080' path='' query='' fragment='' port=8080
'http://[::1]:8080/'                          -> scheme='http' netloc='[::1]:8080' path='/' query='' fragment='' port=8080
'HTTPS://kismet.example.com'                  -> scheme='https' netloc='kismet.example.com' path='' query='' fragment='' port=None
'Https://kismet.example.com'                  -> scheme='https' netloc='kismet.example.com' path='' query='' fragment='' port=None

```

---

## Assistant (Build · Kimi K2.7 Code · 23.3s)

_Thinking:_

Interesting! So `urlsplit("https://kismet.example.com;x")` puts `;x` in the netloc, not path. This means checking path alone won't reject it.

I need to also reject `;` in netloc? Or reject it more broadly. The requirement says "Semikolonpfade ablehnen" and specifically lists `https://kismet.example.com;x` as a semicolon path. Since urlsplit puts it in netloc, I need to handle this.

Actually the issue is that `;` in host is invalid per RFC. We can check if netloc contains `;` and reject. But also need to handle IPv6 addresses that might contain `;`? No, IPv6 addresses use `:`, not `;`.

So I can add a check: if `";"` in netloc, reject. But wait, what if the path contains `;`? Then `;` is in path. Since we already check path is in `{"", "/"}`, paths with `;` are rejected. So checking for `;` anywhere in netloc or path would cover both cases.

Actually, simplest: if `";"` in base_url, reject. Because semicolons shouldn't appear in valid URLs for our allowed set. But wait, could `;` appear in a password? We reject credentials anyway. Could it appear in host? Invalid. Path? Rejected. Query/fragment? Rejected. So `";"` in base_url always indicates something invalid.

But the requirement specifically mentions semicolon paths and using urlsplit so semicolon components stay in path. However, urlsplit puts `https://kismet.example.com;x` netloc with `;x`. So checking path only won't catch it. I think the safest is to reject if `";"` appears in `parsed.netloc` or `parsed.path`.

Let me check: For `https://kismet.example.com/;`, `;` is in path. For `https://kismet.example.com/;x`, `;` in path. For `https://kismet.example.com;x`, `;` in netloc. So check both.

Actually, I can just check if `";"` in base_url. Let me think if there's any valid case. No. So `if ";" in base_url: raise ... base_url path invalid`. This is simple and robust.

But the requirement says "Verwende vorzugsweise urllib.parse.urlsplit, damit Semikolonbestandteile Bestandteil des Pfades bleiben und nicht als separate params-Komponente verschwinden." This is about using urlsplit instead of urlparse. We are doing that. The rejection can be done by checking the path or the full URL.

Hmm, but for `https://kismet.example.com;x`, urlsplit doesn't put `;x` in path, it puts it in netloc. The requirement might be slightly wrong about urlsplit behavior, or they expect us to handle it. The important thing is to reject it.

I'll add: `if ";" in base_url: raise KismetEventbusTransportConfigError("base_url path invalid")` or maybe a more specific message? The requirement says content-free, so the message doesn't matter. But for clarity, I could use "base_url path invalid".

Actually, let me not check the raw string but check parsed.netloc and parsed.path for `;`. This is more AST-aligned.

Wait, what about `https://kismet.example.com/;?` - both `;` and `?`? The query check would catch `?` first. But order matters for which error is raised. The requirement just says reject, doesn't specify error message. So order is fine.

Actually, I realize I should be careful about the order of checks because some invalid URLs might hit different checks. But as long as they all raise the right exception type, it's fine.

Let me now design the test changes.

### Test changes:

1. Remove imports: `importlib`, `sys`, `types` (keep `os` and others).

2. Remove `KismetEventbusRuntimeConfigReimportTests` class.

3. Rewrite `test_no_forbidden_module_level_imports` to walk entire AST. Something like:

```python
def test_no_forbidden_imports_anywhere_in_ast(self) -> None:
    forbidden = {
        "os",
        "pathlib",
        "netrc",
        "keyring",
        "keyczar",
        "cryptography",
        "socket",
        "subprocess",
    }

    with open("kismet_eventbus_runtime_config.py") as f:
        tree = ast.parse(f.read())

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    found = imports & forbidden
    self.assertEqual(
        found,
        set(),
        f"forbidden imports: {found}",
    )
```

But wait, the requirement says "Verbotene Importwurzel mindestens: os pathlib netrc keyring socket subprocess". The current forbidden set includes keyczar and cryptography too. I should keep those or at least include the minimum. The requirement says "mindestens" (at least), so including more is fine. I'll keep the existing set.

4. URL tests: I need to update `_assert_valid` because now root-slash URLs canonicalize to no trailing slash. Currently `test_remote_https_with_root_slash` asserts `config.base_url == "https://kismet.example.com/"`. This will now fail because it will be `https://kismet.example.com`. I need to update this test.

Actually, the requirement says "Root-Slash-Kanonisierung" - both inputs must result in the same stored base_url without trailing slash. So I should update the existing root slash test to expect the canonical form.

Also add new tests:
- Empty port variants (6): `https://kismet.example.com:`, `https://kismet.example.com:/`, `http://localhost:`, `http://localhost:/`, `http://[::1]:`, `http://[::1]:/`
- IPv6 without port valid (already exists but might need to ensure)
- IPv6 with port valid (already exists)
- Uppercase scheme variants (4): `HTTPS://kismet.example.com`, `Https://kismet.example.com`, `HTTP://localhost`, `Http://localhost`
- Empty `?` and `#` markers: `https://kismet.example.com?`, `https://kismet.example.com/?`, `https://kismet.example.com#`, `https://kismet.example.com/#`
- Semicolon paths: `https://kismet.example.com/;`, `https://kismet.example.com/;x`, `https://kismet.example.com;x`
- Root-slash canonicalization: explicit tests that `https://kismet.example.com` and `https://kismet.example.com/` give same stored URL; `http://localhost/` gives `http://localhost`; `http://[::1]:2501/` gives `http://[::1]:2501`.

Let me think about `_assert_valid`. It currently asserts `config.base_url == base_url`. For canonicalization tests, I need a separate helper or modify it to accept expected URL.

I'll add a helper `_assert_valid_url` that takes both input and expected? Or modify `_assert_valid` to take an optional `expected` parameter:

```python
def _assert_valid(
    self, base_url: str, tls_mode: str = "verify_required", expected: str | None = None
) -> None:
    config = create_kismet_eventbus_transport_config(...)
    self.assertEqual(config.base_url, expected if expected is not None else base_url)
```

Then for root slash tests: `self._assert_valid("https://kismet.example.com/", expected="https://kismet.example.com")`.

Now, let me also consider: the existing `test_remote_https_with_root_slash` should be updated to expect canonical form.

Let me also consider what happens with `test_localhost_http` when input is `http://localhost` (no slash) - base_url stays as is. With `http://localhost/` - canonicalizes to `http://localhost`.

For `test_ipv6_loopback` - input `http://[::1]`, stays. For `test_ipv6_loopback_with_port` - input `http://[::1]:8080`, stays.

OK. Let me now write the edits.

Actually, I realize I should also think about the `urlsplit` vs `urlparse` for query/fragment. With urlsplit:
- `https://kismet.example.com?` -> query='', but `'?' in base_url` catches it.
- `https://kismet.example.com/?` -> query='', `'?' in base_url` catches it.
- Same for `#`.

Good.

Now, what about the `except Exception` to `except ValueError`? `urlsplit` raises ValueError for invalid URLs like bad port. Let me confirm:
- `urlsplit("https://kismet.example.com:abc")` - does it raise? Actually from my test above, it didn't raise; `.port` returned None. Wait, my test showed port=None for `:abc`. Hmm, let me recheck... Actually the output showed `port=None` for `https://kismet.example.com:abc`? Let me look... No, I didn't test `:abc` in that list. Let me test.

**Tool: bash**

**Input:**
```json
{
  "command": "python3 - <<'PY'\nfrom urllib.parse import urlsplit\nfor url in [\n    'https://kismet.example.com:abc',\n    'https://kismet.example.com:0',\n    'https://kismet.example.com:65536',\n]:\n    try:\n        p = urlsplit(url)\n        print(f\"{url!r:45} -> scheme={p.scheme!r} netloc={p.netloc!r} path={p.path!r} port={p.port}\")\n    except Exception as e:\n        print(f\"{url!r:45} -> ERROR {type(e).__name__}: {e}\")\nPY",
  "workdir": "/home/miko/GitHub/chasing-your-tail-ng"
}
```

**Output:**
```
'https://kismet.example.com:abc'              -> ERROR ValueError: Port could not be cast to integer value as 'abc'
'https://kismet.example.com:0'                -> scheme='https' netloc='kismet.example.com:0' path='' port=0
'https://kismet.example.com:65536'            -> ERROR ValueError: Port out of range 0-65535

```

---

## Assistant (Build · Kimi K2.7 Code · 0.4s)

---

