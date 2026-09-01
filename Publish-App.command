#!/bin/bash
# Doppelklick startet die Publish-App (Browser öffnet sich automatisch).
#
# Beim allerersten Start richtet sich alles Nötige selbst ein: eine eigene
# Python-Umgebung unter .venv/ und die Pakete darin. Jeder weitere Start
# überspringt das und startet sofort.
#
# Bei jedem Start holt sich die App ausserdem die neueste Fassung von GitHub.
# Es gibt also nichts nachzuinstallieren, wenn an der App etwas verbessert
# wird — Fenster schliessen, neu doppelklicken, fertig.
#
# Fehlt etwas Grundsätzliches (Python, git, GitHub CLI), fragt das Skript nach
# und installiert oder öffnet die richtige Seite. Nichts davon passiert
# ungefragt, und nichts davon passiert, wenn das Skript nicht in einem
# Terminal-Fenster läuft.
cd "$(dirname "$0")" || exit 1

VENV=".venv"
PY="$VENV/bin/python3"

say() { printf '%s\n' "$*"; }

fail() {
  say ""
  say "$*"
  say ""
  read -r -p "Zum Beenden Eingabetaste drücken … " _
  exit 1
}

# Ja/Nein-Frage, Vorgabe ja (leere Eingabe = ja).
#
# Zwei Sicherungen, weil hinter jedem Ja eine Installation steht: ohne Terminal
# wird gar nicht erst gefragt, und bricht die Eingabe ab (read schlägt fehl,
# etwa am Ende einer Eingabeumleitung), gilt das als Nein. Sonst würde eine
# Frage, die niemand beantworten konnte, eine Installation starten.
ask() {
  [ -t 0 ] || return 1
  local answer
  read -r -p "$1 [J/n] " answer || return 1
  case "$answer" in [Nn]*) return 1 ;; *) return 0 ;; esac
}

open_page() {
  if command -v open >/dev/null 2>&1; then
    open "$1" >/dev/null 2>&1
    say "Die Seite ist im Browser geöffnet."
  else
    say "Bitte im Browser öffnen:  $1"
  fi
}

have_brew()   { command -v brew >/dev/null 2>&1; }
# Nicht nur »liegt eine Datei namens python3 im Pfad« — auf macOS gibt es
# /usr/bin/python3 auch ohne Xcode-Werkzeuge, und der Aufruf schlägt dann fehl.
have_python() { command -v python3 >/dev/null 2>&1 && python3 -V >/dev/null 2>&1; }

# 1) Läuft noch eine alte Instanz (z. B. nach geschlossenem Fenster)?
#    Dann beenden, damit Port 8765 frei ist.
LSOF=$(command -v lsof || echo /usr/sbin/lsof)
OLD=$("$LSOF" -ti :8765 2>/dev/null)
if [ -n "$OLD" ]; then
  say "Beende alte Publish-App (PID $OLD) …"
  kill $OLD
  sleep 1
fi

# 2) Python vorhanden? Ohne Python läuft gar nichts.
if ! have_python; then
  say ""
  say "Python 3 fehlt — ohne das startet die App nicht."
  if have_brew; then
    if ask "Jetzt mit Homebrew installieren (dauert ein paar Minuten)?"; then
      brew install python
    fi
  else
    say "Auf der Python-Seite die neueste Version für macOS laden und die"
    say "geladene Datei per Doppelklick installieren."
    if ask "Die Download-Seite jetzt öffnen?"; then
      open_page "https://www.python.org/downloads/"
    fi
  fi
  have_python || fail "Python 3 ist noch nicht einsatzbereit.

Nach der Installation dieses Fenster schliessen und
Publish-App.command erneut doppelklicken — erst dann kennt
das Terminal das neu installierte Python."
fi

# 3) git vorhanden? Kommt mit den Xcode Command Line Tools; deren Installation
#    ist ein normales Fenster mit Fortschrittsbalken, kein Terminal-Kram.
if ! command -v git >/dev/null 2>&1; then
  say ""
  say "git fehlt — das brauchen wir zum Veröffentlichen."
  if ask "Die Installation der Apple-Entwicklerwerkzeuge jetzt starten?"; then
    xcode-select --install 2>/dev/null
    say "Es öffnet sich ein Fenster von Apple. Dort auf »Installieren« klicken"
    say "und warten, bis es fertig ist."
  fi
  command -v git >/dev/null 2>&1 || fail "git ist noch nicht einsatzbereit.

Wenn die Installation durchgelaufen ist, dieses Fenster schliessen
und Publish-App.command erneut doppelklicken."
fi

# 4) Nach Updates suchen. Muss vor dem Paket-Schritt laufen, damit ein neu
#    hinzugekommenes Paket im selben Start mitinstalliert wird — und vor dem
#    Start der App, damit sie gleich die neue Fassung ausführt.
if git rev-parse --git-dir >/dev/null 2>&1; then
  say "Suche nach Updates …"
  BEFORE=$(git rev-parse HEAD 2>/dev/null)
  if git pull --rebase --autostash --quiet 2>/dev/null; then
    if [ "$BEFORE" != "$(git rev-parse HEAD 2>/dev/null)" ]; then
      say "Update eingespielt."
    fi
  else
    say "Keine Update-Suche möglich (offline?) — starte die vorhandene Fassung."
  fi
fi

# 5) Eigene Python-Umgebung anlegen — nur beim ersten Mal.
#    Eigene Umgebung statt System-Python, weil neuere Python-Installationen
#    ein 'pip install' ins System verweigern (externally-managed-environment).
if [ ! -x "$PY" ]; then
  say "Erste Einrichtung — das dauert einen Moment und passiert nur einmal."
  say "Lege eigene Python-Umgebung an …"
  if ! python3 -m venv "$VENV" >/dev/null 2>&1; then
    rm -rf "$VENV"
    say "Konnte keine eigene Umgebung anlegen — verwende stattdessen System-Python."
  fi
fi

# 6) Pakete installieren. Massgeblich ist scripts/requirements.txt — kommt dort
#    per Update ein Paket dazu, installiert es sich beim nächsten Start von
#    selbst. Der Fingerabdruck der Datei verhindert, dass bei jedem Start
#    unnötig nachinstalliert wird.
REQ="scripts/requirements.txt"
STAMP="$VENV/.requirements-hash"
if [ -x "$PY" ] && [ -f "$REQ" ]; then
  WANT=$(shasum -a 256 "$REQ" 2>/dev/null | awk '{print $1}')
  if [ "$WANT" != "$(cat "$STAMP" 2>/dev/null)" ]; then
    say "Installiere benötigte Pakete …"
    "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
    if "$PY" -m pip install --quiet -r "$REQ"; then
      printf '%s\n' "$WANT" > "$STAMP"
    else
      say ""
      say "Hinweis: Die Pakete liessen sich nicht installieren (kein Internet?)."
      say "Die App startet trotzdem — nur .docx-Dateien funktionieren dann noch nicht."
      say ""
    fi
  fi
fi

# Falls die Umgebung nicht zustande kam: mit System-Python weiterarbeiten.
[ -x "$PY" ] || PY="python3"

# 7) GitHub-Zugang. Nicht zwingend — ohne gh fragt git beim Veröffentlichen
#    selbst nach Zugangsdaten —, aber deutlich bequemer. Der Zugang wird hier
#    geprüft und nicht erst beim Veröffentlichen: sonst fällt die Lücke erst
#    auf, wenn der Beitrag fertig ist.
if ! command -v gh >/dev/null 2>&1; then
  say ""
  say "Die GitHub CLI ('gh') fehlt. Sie merkt sich die Anmeldung, sodass beim"
  say "Veröffentlichen nie nach einem Passwort gefragt wird."
  if have_brew; then
    if ask "Jetzt mit Homebrew installieren?"; then
      brew install gh
    fi
  else
    if ask "Die Download-Seite von GitHub CLI jetzt öffnen?"; then
      open_page "https://cli.github.com/"
      say "Nach der Installation dieses Fenster schliessen und"
      say "Publish-App.command erneut doppelklicken."
    fi
  fi
fi

if command -v gh >/dev/null 2>&1; then
  if ! gh auth status >/dev/null 2>&1; then
    say ""
    say "Die GitHub-Anmeldung fehlt noch. Ohne sie lässt sich am Ende"
    say "nichts veröffentlichen."
    say "Im Anmelde-Dialog wählen:  GitHub.com → HTTPS → Yes → Login with a web browser"
    if ask "Jetzt anmelden?"; then
      gh auth login
    else
      say "Übersprungen — beim Veröffentlichen fragt git dann nach Zugangsdaten."
    fi
  fi
else
  say "Ohne gh fragt git beim ersten Veröffentlichen nach Benutzername und"
  say "Personal Access Token (nicht das Kontopasswort — GitHub akzeptiert es"
  say "nicht mehr)."
  say ""
fi

# 8) Git-Identität. `gh auth login` meldet bei GitHub an, setzt aber nicht den
#    Namen, den git für jeden Commit verlangt. Fehlt er, schlägt nicht etwa der
#    Start fehl, sondern der Commit *nachdem* der Beitrag schon geschrieben und
#    vorgemerkt ist — also mitten im Vorgang. Deshalb hier, vorher, einmal.
if git rev-parse --git-dir >/dev/null 2>&1 &&
   { ! git config user.name >/dev/null 2>&1 || ! git config user.email >/dev/null 2>&1; }; then
  GIT_NAME=""
  GIT_MAIL=""
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    # Eine Abfrage, vier Felder. Ist die Adresse bei GitHub privat, liefert
    # GitHub keine — dann die noreply-Adresse, die GitHub genau dafür vergibt.
    # Getrennt wird mit dem Unit Separator, nicht mit Tab: bei einem
    # Trennzeichen, das Leerraum ist, fasst read aufeinanderfolgende
    # Trenner zu einem zusammen — leere Felder (Name und Adresse sind bei
    # GitHub oft leer) verschwinden dann und alles rutscht eine Stelle vor.
    IDENT=$(gh api user --jq '[.login, (.name // ""), (.email // ""), (.id|tostring)] | join("\u001f")' 2>/dev/null)
    if [ -n "$IDENT" ]; then
      IFS=$'\037' read -r GH_LOGIN GH_NAME GH_MAIL GH_ID <<< "$IDENT"
      GIT_NAME=${GH_NAME:-$GH_LOGIN}
      GIT_MAIL=${GH_MAIL:-"${GH_ID}+${GH_LOGIN}@users.noreply.github.com"}
    fi
  fi

  if [ -n "$GIT_NAME" ]; then
    say ""
    say "git verlangt für jeden Beitrag einen Namen — er steht später in der"
    say "Versionsgeschichte der Website. Aus dem GitHub-Konto ergibt sich:"
    say "    $GIT_NAME <$GIT_MAIL>"
    if ask "So eintragen (gilt nur für diesen Ordner)?"; then
      git config user.name "$GIT_NAME"
      git config user.email "$GIT_MAIL"
      say "Eingetragen."
    fi
  fi

  if ! git config user.name >/dev/null 2>&1 || ! git config user.email >/dev/null 2>&1; then
    say ""
    say "Achtung: Ohne Namen und Adresse kann git nichts committen — das"
    say "Veröffentlichen bricht dann ab, nachdem der Beitrag geschrieben ist."
    say "Im Terminal einmal setzen:"
    say "    git config --global user.name \"Vorname Nachname\""
    say "    git config --global user.email \"adresse@example.org\""
    say ""
  fi
fi

say ""
say "Starte Publish-App …"
exec "$PY" scripts/publish_app.py
