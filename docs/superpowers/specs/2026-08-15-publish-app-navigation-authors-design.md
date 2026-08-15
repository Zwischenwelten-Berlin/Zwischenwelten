# Publish-App: Top-Navigation & Autor:innen-Bereich

Datum: 2026-08-15 · Status: genehmigt

## Ziel

Die Publish-App (lokales CMS-Backend unter `scripts/publish_app.py` +
`scripts/publish_app.html`) bekommt eine klare Bereichsstruktur mit fester
Top-Navigation und einen eigenen Bereich zum Auflisten, Anlegen und
Bearbeiten von Autor:innen. Nur die Admin-Oberfläche und ihre API wachsen —
der Python-Code bleibt in der bestehenden Ein-Datei-Struktur.

## Navigation & Shell

- Persistenter Header: Marke + drei Tabs — **Neuer Beitrag**, **Beiträge**,
  **Autor:innen**.
- Der Schrittindikator (1 Dateien → 2 Angaben → 3 Vorschau → 4 Fertig)
  erscheint nur innerhalb des Wizards.
- `screen-home` (Kachel-Hub) entfällt; die App startet auf **Neuer Beitrag**
  (Dateien-Screen).
- Tab-Klick wechselt den Bereich, ohne Wizard-Zustand zu zerstören:
  **Neuer Beitrag** springt zurück in den laufenden Wizard-Schritt; ein
  Link „von vorn beginnen" setzt zurück.
- Während Edit-/Translate-Flows (die die gemeinsamen Form-/Preview-Screens
  nutzen) ist der Tab **Beiträge** aktiv, denn dort startete der Flow.
- Bereichs-Hashes `#neu`, `#beitraege`, `#autoren` — Reload/Zurück landet im
  richtigen Bereich (nur Bereichsebene; Wizard-Schritte haben keinen Hash,
  weil die Server-Session einen Deep-Link ohnehin nicht trägt).

## Autor:innen-Bereich

**Liste:** je Autor:in Foto (`assets/autoren/<id>.*`, falls vorhanden),
kanonischer Name, Rolle, Aliasse, Link zur Seite
(`journalistennetzwerk/<id>.html`, falls vorhanden) und Beitragszahl.

**Neu anlegen:** dieselben Felder wie das bestehende Panel im
Beitragsformular (Name, Rolle, optional Bio + Foto → Seite), als eigener
Bereich; nutzt das bestehende `POST /api/new-author`. Das Panel im
Beitragsformular bleibt unverändert.

**Bearbeiten:** Rolle und Aliasse editierbar (reine Registry-Änderung).
Bio/Foto-Änderungen regenerieren die Seite aus dem Template — mit
explizitem Hinweis, dass eine handgebaute Seite überschrieben wird.
Kanonischer Name und `id` bleiben unveränderlich (Referenzen aus
`posts.json`).

## Neue API-Endpunkte (`publish_app.py`)

Bestehende Muster: Fehler lokal fangen, deutsche Fehlertexte, Pfade zur
Aufrufzeit über `publish_post.*` auflösen, Commits über `git_flow`.

- `GET /api/authors` — Registry-Einträge angereichert um `photo`-/`page`-URL
  und `post_count` (Zuordnung der `posts.json`-Autorennamen über den
  bestehenden Fuzzy-Matcher `match_author`, damit übersetzte Namensformen
  zählen).
- `POST /api/update-author` — Body `{id, role, aliases, page?}`;
  Validierung vor jedem Schreiben (bekannte `id`, Rolle nicht leer, Foto
  optional: neues validieren oder vorhandenes weiterverwenden);
  schreibt `authors.json`, optional Foto + regenerierte Seite; Commit
  `content: Autor:in <Name> aktualisiert` via `git_flow`.

## Fehlerbehandlung

Wie überall in der App: `{"ok": false, "error": "…"}` mit deutschem Text;
Validierung vollständig vor dem ersten Schreiben, damit kein
halb-registrierter Zustand entsteht (gleiche Regel wie `api_new_author`).

## Tests

`scripts/tests/test_publish_app.py`, gleiche FakeHandler-Direktaufruf-
Harness: Listing (mit/ohne Seite, Beitragszählung), Update nur
Rolle/Aliasse, Update mit Seitenregeneration (Foto neu und Foto
wiederverwendet), Ablehnungen (unbekannte id, leere Rolle, kaputtes Foto —
Registry unverändert).
