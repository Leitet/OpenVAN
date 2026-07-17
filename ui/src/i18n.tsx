import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

// Product-UI localisation. English / Swedish / German, chosen in Settings and
// persisted client-side (the bench stays English by design). Model replies are a
// separate, server-side language setting (Config.language).
export type Lang = "en" | "sv" | "de";
export const LANGS: Lang[] = ["en", "sv", "de"];
export const LANG_NATIVE: Record<Lang, string> = {
  en: "English",
  sv: "Svenska",
  de: "Deutsch",
};

const LS_KEY = "openvan.lang";

type Entry = Record<Lang, string>;

const T: Record<string, Entry> = {
  // --- navigation ---
  "nav.home": { en: "Home", sv: "Hem", de: "Start" },
  "nav.power": { en: "Power", sv: "Energi", de: "Energie" },
  "nav.comfort": { en: "Comfort", sv: "Komfort", de: "Komfort" },
  "nav.journey": { en: "Journey", sv: "Resa", de: "Reise" },
  "nav.security": { en: "Security", sv: "Säkerhet", de: "Sicherheit" },
  "nav.assistant": { en: "Assistant", sv: "Assistent", de: "Assistent" },
  "cam.title": { en: "Cameras", sv: "Kameror", de: "Kameras" },
  "cam.placement": { en: "Camera placement", sv: "Kameraplacering", de: "Kamerastandorte" },
  "cam.none": { en: "No cameras configured.", sv: "Inga kameror konfigurerade.", de: "Keine Kameras konfiguriert." },
  "cam.nosignal": { en: "NO SIGNAL", sv: "INGEN SIGNAL", de: "KEIN SIGNAL" },
  "cam.motion": { en: "MOTION", sv: "RÖRELSE", de: "BEWEGUNG" },
  "sec.sensors": { en: "Sensors & alerts", sv: "Sensorer & larm", de: "Sensoren & Alarme" },
  "sec.door": { en: "Door", sv: "Dörr", de: "Tür" },
  "sec.motion": { en: "Motion", sv: "Rörelse", de: "Bewegung" },
  "sec.camMotion": { en: "Cameras w/ motion", sv: "Kameror m. rörelse", de: "Kameras m. Bewegung" },
  "sec.open": { en: "open", sv: "öppen", de: "offen" },
  "sec.closed": { en: "closed", sv: "stängd", de: "geschlossen" },
  "sec.detected": { en: "detected", sv: "upptäckt", de: "erkannt" },
  "sec.none": { en: "none", sv: "ingen", de: "keine" },
  "nav.settings": { en: "Settings", sv: "Inställningar", de: "Einstellungen" },

  // --- status bar ---
  "status.battery": { en: "battery", sv: "batteri", de: "Batterie" },
  "status.water": { en: "water", sv: "vatten", de: "Wasser" },
  "status.cabin": { en: "cabin", sv: "kupé", de: "Kabine" },
  "status.core": { en: "Core", sv: "Core", de: "Core" },
  "status.coreHint": {
    en: "Connected to OpenVan Core — the van's local system",
    sv: "Ansluten till OpenVan Core — vanens lokala system",
    de: "Mit OpenVan Core verbunden — dem lokalen System des Vans",
  },
  "status.reconnecting": { en: "Reconnecting…", sv: "Återansluter…", de: "Verbinde neu…" },
  "ai.prefix": { en: "AI", sv: "AI", de: "KI" },
  "ai.local": { en: "local", sv: "lokal", de: "lokal" },
  "ai.cloud": { en: "cloud", sv: "moln", de: "Cloud" },
  "ai.rulesOnly": { en: "rules only", sv: "endast regler", de: "nur Regeln" },

  // --- common ---
  "common.on": { en: "On", sv: "På", de: "An" },
  "common.off": { en: "Off", sv: "Av", de: "Aus" },
  "common.heating": { en: "Heating", sv: "Värmer", de: "Heizt" },
  "common.running": { en: "Running", sv: "Kör", de: "Läuft" },
  "common.refresh": { en: "Refresh", sv: "Uppdatera", de: "Aktualisieren" },
  "common.send": { en: "Send", sv: "Skicka", de: "Senden" },
  "common.save": { en: "Save", sv: "Spara", de: "Speichern" },
  "common.saving": { en: "Saving…", sv: "Sparar…", de: "Speichere…" },
  "common.cancel": { en: "Cancel", sv: "Avbryt", de: "Abbrechen" },
  "common.create": { en: "Create", sv: "Skapa", de: "Erstellen" },
  "common.edit": { en: "Edit", sv: "Redigera", de: "Bearbeiten" },
  "common.delete": { en: "Delete", sv: "Ta bort", de: "Löschen" },
  "common.fork": { en: "Fork", sv: "Förgrena", de: "Duplizieren" },

  // --- measurement labels ---
  "label.battery": { en: "Battery", sv: "Batteri", de: "Batterie" },
  "label.freshWater": { en: "Fresh water", sv: "Färskvatten", de: "Frischwasser" },
  "label.greyWater": { en: "Grey water", sv: "Gråvatten", de: "Grauwasser" },
  "label.cabin": { en: "Cabin", sv: "Kupé", de: "Kabine" },
  "label.outside": { en: "Outside", sv: "Ute", de: "Außen" },
  "label.solar": { en: "Solar", sv: "Solel", de: "Solar" },
  "label.voltage": { en: "Voltage", sv: "Spänning", de: "Spannung" },
  "label.heaterDraw": { en: "Heater draw", sv: "Värmareffekt", de: "Heizungslast" },

  // --- devices ---
  "device.cabinLight": { en: "Cabin light", sv: "Kupébelysning", de: "Kabinenlicht" },
  "device.dieselHeater": { en: "Diesel heater", sv: "Dieselvärmare", de: "Dieselheizung" },
  "device.waterPump": { en: "Water pump", sv: "Vattenpump", de: "Wasserpumpe" },

  // --- home ---
  "home.vitals": { en: "Vitals", sv: "Nyckelvärden", de: "Vitalwerte" },
  "home.quickActions": { en: "Quick actions", sv: "Snabbåtgärder", de: "Schnellaktionen" },

  // --- companion ---
  "companion.title": { en: "Companion", sv: "Följeslagare", de: "Begleiter" },
  "companion.briefing": {
    en: "Ask for a briefing",
    sv: "Be om en sammanfattning",
    de: "Um Lagebericht bitten",
  },
  "companion.thinking": { en: "Thinking…", sv: "Tänker…", de: "Denke…" },
  "companion.allGood": {
    en: "All good — nothing needs your attention.",
    sv: "Allt bra — inget kräver din uppmärksamhet.",
    de: "Alles gut — nichts erfordert Ihre Aufmerksamkeit.",
  },

  // --- power / predictions / trends ---
  "power.energy": { en: "Energy", sv: "Energi", de: "Energie" },
  "predictions.title": { en: "Predictions", sv: "Prognoser", de: "Prognosen" },
  "predictions.batteryEmpty": {
    en: "Battery empty in",
    sv: "Batteriet tomt om",
    de: "Batterie leer in",
  },
  "predictions.freshWaterEmpty": {
    en: "Fresh water empty in",
    sv: "Färskvatten tomt om",
    de: "Frischwasser leer in",
  },
  "predictions.greyFull": {
    en: "Grey tank full in",
    sv: "Gråtank full om",
    de: "Grautank voll in",
  },
  "predictions.dieselEmpty": {
    en: "Diesel empty in",
    sv: "Diesel tom om",
    de: "Diesel leer in",
  },
  "predictions.solar24h": {
    en: "Solar (last 24h)",
    sv: "Solel (senaste 24h)",
    de: "Solar (letzte 24h)",
  },
  "predictions.solarForecast": {
    en: "Solar forecast (24h)",
    sv: "Solprognos (24h)",
    de: "Solarprognose (24h)",
  },
  "predictions.notEnough": {
    en: "Not enough history yet — trends appear as signals change.",
    sv: "Inte tillräcklig historik än — trender visas när värden ändras.",
    de: "Noch nicht genug Verlauf — Trends erscheinen, sobald sich Werte ändern.",
  },
  "units.min": { en: "min", sv: "min", de: "Min" },
  "units.h": { en: "h", sv: "h", de: "Std" },
  "units.days": { en: "days", sv: "dygn", de: "Tage" },
  "trends.title": { en: "Trends", sv: "Trender", de: "Trends" },
  "trends.exportCsv": { en: "Export CSV", sv: "Exportera CSV", de: "CSV exportieren" },

  // --- comfort ---
  "comfort.climate": { en: "Climate", sv: "Klimat", de: "Klima" },
  "comfort.water": { en: "Water", sv: "Vatten", de: "Wasser" },
  "comfort.setpoint": { en: "Setpoint", sv: "Börvärde", de: "Sollwert" },
  "heater.heating": {
    en: "Diesel heater: HEATING",
    sv: "Dieselvärmare: VÄRMER",
    de: "Dieselheizung: HEIZT",
  },
  "heater.off": {
    en: "Diesel heater: OFF",
    sv: "Dieselvärmare: AV",
    de: "Dieselheizung: AUS",
  },

  // --- journey ---
  "home.routines": { en: "Routines", sv: "Rutiner", de: "Routinen" },
  "security.title": { en: "Away mode", sv: "Bortaläge", de: "Abwesenheit" },
  "security.armed": { en: "Armed", sv: "Aktiverat", de: "Scharf" },
  "security.disarmed": { en: "Disarmed", sv: "Avstängt", de: "Unscharf" },
  "security.tapArm": { en: "Tap to arm when you leave", sv: "Tryck för att aktivera", de: "Zum Aktivieren tippen" },
  "security.tapDisarm": { en: "Tap to disarm", sv: "Tryck för att stänga av", de: "Zum Deaktivieren tippen" },
  "settings.tuning": { en: "Tuning", sv: "Trösklar", de: "Schwellen" },
  "settings.vehicle": { en: "Vehicle", sv: "Fordon", de: "Fahrzeug" },
  "vehicle.preset": { en: "Load a model", sv: "Ladda en modell", de: "Modell laden" },
  "vehicle.pick": { en: "Pick a model…", sv: "Välj en modell…", de: "Modell wählen…" },
  "vehicle.untitled": { en: "My van", sv: "Min van", de: "Mein Van" },
  "tuning.hint": {
    en: "Thresholds and setpoints for the advisors and scenes. Defaults are sensible; edit to suit your van, or reset.",
    sv: "Trösklar och börvärden för rådgivarna och scenerna. Standard är rimliga; ändra efter din van, eller återställ.",
    de: "Schwellen und Sollwerte für Hinweise und Szenen. Standardwerte sind sinnvoll; anpassen oder zurücksetzen.",
  },
  "tuning.reset": { en: "Reset all to defaults", sv: "Återställ allt", de: "Alles zurücksetzen" },
  "maint.title": { en: "Maintenance", sv: "Underhåll", de: "Wartung" },
  "maint.done": { en: "Done", sv: "Klart", de: "Erledigt" },
  "maint.overdue": { en: "Overdue", sv: "Försenat", de: "Überfällig" },
  "maint.days": { en: "days", sv: "dagar", de: "Tage" },
  "level.title": { en: "Leveling", sv: "Nivellering", de: "Nivellierung" },
  "level.pitch": { en: "Pitch", sv: "Lutning fram/bak", de: "Neigung" },
  "level.roll": { en: "Roll", sv: "Lutning sida", de: "Querneigung" },
  "level.flat": { en: "Nicely level — good to go.", sv: "Fint i våg — redo.", de: "Schön eben — bereit." },
  "level.raise": { en: "Raise", sv: "Höj", de: "Anheben" },
  "level.left": { en: "left side", sv: "vänster sida", de: "linke Seite" },
  "level.right": { en: "right side", sv: "höger sida", de: "rechte Seite" },
  "level.front": { en: "front", sv: "fram", de: "vorne" },
  "level.rear": { en: "rear", sv: "bak", de: "hinten" },
  "comfort.airSafety": { en: "Air & Safety", sv: "Luft & säkerhet", de: "Luft & Sicherheit" },
  "label.co": { en: "Carbon monoxide", sv: "Kolmonoxid", de: "Kohlenmonoxid" },
  "label.lpg": { en: "Propane", sv: "Gasol", de: "Propan" },
  "label.co2": { en: "CO₂", sv: "CO₂", de: "CO₂" },
  "label.humidity": { en: "Humidity", sv: "Luftfuktighet", de: "Luftfeuchtigkeit" },
  "label.propane": { en: "Propane", sv: "Gasol", de: "Propan" },
  "label.fridge": { en: "Fridge", sv: "Kylskåp", de: "Kühlschrank" },
  "label.fridgeDraw": { en: "Fridge draw", sv: "Kyl förbrukning", de: "Kühlschrank-Last" },
  "safety.allClear": { en: "All clear", sv: "Allt lugnt", de: "Alles in Ordnung" },
  "safety.smoke": { en: "Smoke", sv: "Rök", de: "Rauch" },
  "memory.title": { en: "What I've learned", sv: "Vad jag har lärt mig", de: "Was ich gelernt habe" },
  "memory.empty": {
    en: "Nothing yet — chat with me and I'll learn how you like things.",
    sv: "Inget än — prata med mig så lär jag mig hur du vill ha det.",
    de: "Noch nichts — sprich mit mir und ich lerne, wie du es magst.",
  },
  "memory.forget": { en: "Forget", sv: "Glöm", de: "Vergessen" },
  "journey.title": { en: "Journey", sv: "Resa", de: "Reise" },
  "journey.position": { en: "position", sv: "position", de: "Position" },
  "journey.pastStay": { en: "past stay", sv: "tidigare plats", de: "früherer Halt" },
  "journey.hereNow": { en: "here now", sv: "här nu", de: "jetzt hier" },
  "journey.speed": { en: "Speed", sv: "Hastighet", de: "Geschwindigkeit" },
  "journey.heading": { en: "Heading", sv: "Kurs", de: "Kurs" },
  "journey.odometer": { en: "Odometer", sv: "Vägmätare", de: "Kilometerzähler" },
  "journey.positionLabel": { en: "Position", sv: "Position", de: "Position" },
  "journey.camp": { en: "camp spot", sv: "campingplats", de: "Stellplatz" },

  // --- weather ---
  "weather.title": { en: "Weather", sv: "Väder", de: "Wetter" },
  "weather.live": { en: "live", sv: "live", de: "live" },
  "weather.cached": { en: "cached", sv: "cachad", de: "gespeichert" },
  "weather.simulated": { en: "simulated", sv: "simulerad", de: "simuliert" },
  "weather.none": { en: "No forecast yet.", sv: "Ingen prognos än.", de: "Noch keine Vorhersage." },
  "weather.rainShortly": {
    en: "Rain expected shortly",
    sv: "Regn väntas snart",
    de: "Regen bald erwartet",
  },
  "weather.rainIn": {
    en: "Rain expected in about {h}h",
    sv: "Regn väntas om cirka {h}h",
    de: "Regen in etwa {h}h erwartet",
  },

  // --- travel journal ---
  "journal.title": { en: "Travel journal", sv: "Resedagbok", de: "Reisetagebuch" },
  "journal.bookmark": {
    en: "Bookmark this spot",
    sv: "Bokmärk denna plats",
    de: "Diesen Ort merken",
  },
  "journal.here": { en: "Here", sv: "Här", de: "Hier" },
  "journal.campedSince": { en: "camped since", sv: "stått sedan", de: "geparkt seit" },
  "journal.annotateLatest": {
    en: "Annotate latest",
    sv: "Kommentera senaste",
    de: "Letzten kommentieren",
  },
  "journal.namePlace": {
    en: "Name this place…",
    sv: "Namnge denna plats…",
    de: "Diesen Ort benennen…",
  },
  "journal.nameBtn": { en: "Name", sv: "Namnge", de: "Benennen" },
  "journal.addNote": { en: "Add a note…", sv: "Lägg till anteckning…", de: "Notiz hinzufügen…" },
  "journal.noteBtn": { en: "Note", sv: "Anteckning", de: "Notiz" },
  "journal.hereNow": { en: "here now", sv: "här nu", de: "jetzt hier" },
  "journal.used": { en: "{n}% used", sv: "{n}% använt", de: "{n}% verbraucht" },
  "journal.solar": { en: "{n} Wh solar", sv: "{n} Wh solel", de: "{n} Wh Solar" },
  "journal.unknown": { en: "unknown", sv: "okänd", de: "unbekannt" },
  "journal.none": {
    en: "No stays yet — park up (ignition off) and one logs automatically, or bookmark this spot.",
    sv: "Inga platser än — parkera (tändning av) så loggas en automatiskt, eller bokmärk denna plats.",
    de: "Noch keine Halte — parken (Zündung aus) und einer wird automatisch erfasst, oder diesen Ort merken.",
  },

  // --- event log ---
  "log.title": { en: "Activity & safety", sv: "Aktivitet & säkerhet", de: "Aktivität & Sicherheit" },
  "log.empty": { en: "No commands yet.", sv: "Inga kommandon än.", de: "Noch keine Befehle." },

  // --- assistant / chat ---
  "assistant.title": { en: "Assistant", sv: "Assistent", de: "Assistent" },
  "chat.speak": { en: "Speak", sv: "Läs upp", de: "Vorlesen" },
  "chat.speaking": { en: "Speaking", sv: "Läser upp", de: "Liest vor" },
  "chat.whichModel": {
    en: "Which model answers",
    sv: "Vilken modell svarar",
    de: "Welches Modell antwortet",
  },
  "chat.rulesNoModel": {
    en: "rules only · no model",
    sv: "endast regler · ingen modell",
    de: "nur Regeln · kein Modell",
  },
  "chat.emptyLlm": {
    en: "Ask me anything about the van.",
    sv: "Fråga mig vad som helst om bilen.",
    de: "Frag mich alles über den Van.",
  },
  "chat.emptyLlmPersona": {
    en: "Ask me anything about the van — I'm {name}.",
    sv: "Fråga mig vad som helst om bilen — jag är {name}.",
    de: "Frag mich alles über den Van — ich bin {name}.",
  },
  "chat.emptyRules": {
    en: 'Offline rules are active. Try "turn on the cabin light".',
    sv: 'Offline-regler är aktiva. Testa "tänd kupébelysningen".',
    de: 'Offline-Regeln sind aktiv. Versuche „Kabinenlicht einschalten".',
  },
  "chat.tapMic": {
    en: "Tap the mic to speak.",
    sv: "Tryck på mikrofonen för att prata.",
    de: "Tippe aufs Mikrofon zum Sprechen.",
  },
  "chat.askAnything": { en: "Ask anything…", sv: "Fråga vad som helst…", de: "Frag irgendetwas…" },
  "chat.listening": { en: "Listening…", sv: "Lyssnar…", de: "Höre zu…" },
  "chat.tryCommand": {
    en: 'Try "turn on the cabin light"',
    sv: 'Testa "tänd kupébelysningen"',
    de: 'Versuche „Kabinenlicht einschalten"',
  },
  "chat.unreachable": {
    en: "Core isn't reachable right now.",
    sv: "Core går inte att nå just nu.",
    de: "Core ist gerade nicht erreichbar.",
  },

  // --- settings / assistant config ---
  "settings.catGeneral": { en: "General", sv: "Allmänt", de: "Allgemein" },
  "settings.integrations": { en: "Integrations", sv: "Integrationer", de: "Integrationen" },
  "settings.integrationsNote": {
    en: "Hardware ecosystems OpenVan can talk to. Each shows how robust its support is (status), how it connects (transport) and how risky control is (safety). Enable the ones your van has — they run against the simulator until real hardware is attached.",
    sv: "Hårdvaruekosystem som OpenVan kan prata med. Var och en visar hur robust stödet är (status), hur den ansluter (transport) och hur riskabel styrningen är (säkerhet). Aktivera de din bil har — de körs mot simulatorn tills riktig hårdvara ansluts.",
    de: "Hardware-Ökosysteme, mit denen OpenVan sprechen kann. Jedes zeigt, wie robust die Unterstützung ist (Status), wie es verbindet (Transport) und wie riskant die Steuerung ist (Sicherheit). Aktiviere die, die dein Van hat — sie laufen gegen den Simulator, bis echte Hardware angeschlossen ist.",
  },
  "settings.camping": { en: "Camping", sv: "Camping", de: "Camping" },
  "settings.campingNote": {
    en: "Sources for places to stay. The van proposes camp spots from the enabled ones — add more by dropping a source package under campsources/.",
    sv: "Källor för platser att stanna på. Bilen föreslår campingplatser från de aktiverade — lägg till fler genom att lägga en källa under campsources/.",
    de: "Quellen für Übernachtungsplätze. Der Van schlägt Stellplätze aus den aktivierten vor — weitere per Paket unter campsources/ hinzufügen.",
  },
  "settings.needsInternet": {
    en: "needs internet",
    sv: "kräver internet",
    de: "braucht Internet",
  },
  "settings.needsKey": { en: "needs key", sv: "kräver nyckel", de: "braucht Schlüssel" },
  "settings.noCampSources": {
    en: "No camp sources installed.",
    sv: "Inga campingkällor installerade.",
    de: "Keine Camp-Quellen installiert.",
  },
  "settings.assistant": { en: "Assistant", sv: "Assistent", de: "Assistent" },
  "settings.enableAi": {
    en: "Enable AI assistant",
    sv: "Aktivera AI-assistent",
    de: "KI-Assistent aktivieren",
  },
  "settings.connectivityHeading": {
    en: "Connectivity — which model answers",
    sv: "Anslutning — vilken modell svarar",
    de: "Verbindung — welches Modell antwortet",
  },
  "settings.offline": { en: "Offline", sv: "Offline", de: "Offline" },
  "settings.offlineDesc": {
    en: "local model · private, no internet",
    sv: "lokal modell · privat, inget internet",
    de: "lokales Modell · privat, kein Internet",
  },
  "settings.online": { en: "Online", sv: "Online", de: "Online" },
  "settings.onlineDesc": {
    en: "cloud model · needs an API key",
    sv: "molnmodell · kräver API-nyckel",
    de: "Cloud-Modell · benötigt API-Schlüssel",
  },
  "settings.talkingTo": { en: "Talking to", sv: "Pratar med", de: "Spreche mit" },
  "settings.active": { en: "active", sv: "aktiv", de: "aktiv" },
  "settings.cloudFellBackLocal": {
    en: " — cloud unreachable, fell back to local",
    sv: " — molnet går inte att nå, föll tillbaka till lokal",
    de: " — Cloud nicht erreichbar, auf lokal zurückgefallen",
  },
  "settings.cloudFellBackRules": {
    en: " — cloud unreachable, using offline rules",
    sv: " — molnet går inte att nå, använder offline-regler",
    de: " — Cloud nicht erreichbar, nutze Offline-Regeln",
  },
  "settings.voice": { en: "voice", sv: "röst", de: "Stimme" },
  "settings.connectivityGlobal": {
    en: "The connectivity mode is global — it applies to every personality.",
    sv: "Anslutningsläget är globalt — det gäller alla personligheter.",
    de: "Der Verbindungsmodus ist global — er gilt für alle Persönlichkeiten.",
  },
  "settings.localModel": {
    en: "Local model · Ollama",
    sv: "Lokal modell · Ollama",
    de: "Lokales Modell · Ollama",
  },
  "settings.inUse": { en: "in use", sv: "används", de: "aktiv" },
  "settings.model": { en: "Model", sv: "Modell", de: "Modell" },
  "settings.serverUrl": { en: "Server URL", sv: "Server-URL", de: "Server-URL" },
  "settings.cloudModel": { en: "Cloud model", sv: "Molnmodell", de: "Cloud-Modell" },
  "settings.provider": { en: "Provider", sv: "Leverantör", de: "Anbieter" },
  "settings.apiBaseUrl": { en: "API base URL", sv: "API-bas-URL", de: "API-Basis-URL" },
  "settings.chooseModel": {
    en: "— choose a model —",
    sv: "— välj en modell —",
    de: "— Modell wählen —",
  },
  "settings.noModels": {
    en: "— no models (check key / base URL) —",
    sv: "— inga modeller (kontrollera nyckel / URL) —",
    de: "— keine Modelle (Schlüssel / URL prüfen) —",
  },
  "settings.pasteKeyToLoad": {
    en: "— paste a valid key to load models —",
    sv: "— klistra in en giltig nyckel för att ladda modeller —",
    de: "— gültigen Schlüssel einfügen, um Modelle zu laden —",
  },
  "settings.loadingModels": { en: "Loading models…", sv: "Laddar modeller…", de: "Lade Modelle…" },
  "settings.modelsAvailable": {
    en: "{n} models available to this key.",
    sv: "{n} modeller tillgängliga för denna nyckel.",
    de: "{n} Modelle für diesen Schlüssel verfügbar.",
  },
  "settings.modelsAvailable1": {
    en: "{n} model available to this key.",
    sv: "{n} modell tillgänglig för denna nyckel.",
    de: "{n} Modell für diesen Schlüssel verfügbar.",
  },
  "settings.apiKey": { en: "API key", sv: "API-nyckel", de: "API-Schlüssel" },
  "settings.set": { en: "set", sv: "satt", de: "gesetzt" },
  "settings.pasteKey": { en: "paste key", sv: "klistra in nyckel", de: "Schlüssel einfügen" },
  "settings.keyStored": {
    en: "•••••• (stored in memory)",
    sv: "•••••• (i minnet)",
    de: "•••••• (im Speicher)",
  },
  "settings.keyNote": {
    en: "The key is held in memory only (never written to disk). Set it here, or via the OPENVAN_ONLINE_API_KEY environment variable.",
    sv: "Nyckeln hålls endast i minnet (skrivs aldrig till disk). Ange den här eller via miljövariabeln OPENVAN_ONLINE_API_KEY.",
    de: "Der Schlüssel wird nur im Speicher gehalten (nie gespeichert). Hier eingeben oder über die Umgebungsvariable OPENVAN_ONLINE_API_KEY.",
  },
  "settings.system": { en: "System", sv: "System", de: "System" },
  "settings.version": { en: "Version", sv: "Version", de: "Version" },
  "settings.plugins": { en: "Plugins", sv: "Insticksmoduler", de: "Plugins" },
  "settings.persistNote": {
    en: "Settings persist across restarts (saved locally). The API key is the exception — it stays in memory only and is never written to disk.",
    sv: "Inställningar sparas mellan omstarter (lokalt). API-nyckeln är undantaget — den finns bara i minnet och skrivs aldrig till disk.",
    de: "Einstellungen bleiben über Neustarts erhalten (lokal gespeichert). Der API-Schlüssel ist die Ausnahme — er bleibt nur im Speicher und wird nie gespeichert.",
  },
  "settings.loadingSettings": {
    en: "Loading settings…",
    sv: "Laddar inställningar…",
    de: "Lade Einstellungen…",
  },
  "settings.saved": { en: "Saved ✓", sv: "Sparat ✓", de: "Gespeichert ✓" },

  // --- language section ---
  "settings.language": { en: "Language", sv: "Språk", de: "Sprache" },
  "settings.appLanguage": { en: "App language", sv: "Appspråk", de: "App-Sprache" },
  "settings.assistantLanguage": {
    en: "Assistant language",
    sv: "Assistentens språk",
    de: "Assistenten-Sprache",
  },
  "settings.sameAsApp": { en: "Same as app", sv: "Samma som appen", de: "Wie App" },
  "settings.languageNote": {
    en: "The app language sets all on-screen text; the assistant language sets what the model replies in (it still honours a one-off request like “say it in German”).",
    sv: "Appspråket styr all text på skärmen; assistentspråket styr vilket språk modellen svarar på (den följer ändå en engångsbegäran som ”säg det på tyska”).",
    de: "Die App-Sprache setzt den gesamten Bildschirmtext; die Assistenten-Sprache legt fest, worin das Modell antwortet (eine einmalige Bitte wie „sag es auf Deutsch“ wird trotzdem befolgt).",
  },

  // --- personalities ---
  "personalities.title": { en: "Personalities", sv: "Personligheter", de: "Persönlichkeiten" },
  "personalities.subtitle": {
    en: "The companion's voice — how it phrases briefings, never what it decides. Pick one, or fork it to make your own.",
    sv: "Följeslagarens röst — hur den formulerar sig, aldrig vad den bestämmer. Välj en, eller förgrena för att skapa en egen.",
    de: "Die Stimme des Begleiters — wie er formuliert, nie was er entscheidet. Wähle eine oder dupliziere sie für eine eigene.",
  },
  "personalities.active": { en: "✓ Active", sv: "✓ Aktiv", de: "✓ Aktiv" },
  "personalities.use": { en: "Use {name}", sv: "Använd {name}", de: "{name} verwenden" },
  "personalities.nameFork": {
    en: "Name your fork",
    sv: "Namnge din förgrening",
    de: "Benenne deine Kopie",
  },
  "field.name": { en: "Name", sv: "Namn", de: "Name" },
  "field.category": { en: "Category", sv: "Kategori", de: "Kategorie" },
  "field.signature": { en: "Signature line", sv: "Signaturmening", de: "Signaturzeile" },
  "field.traits": {
    en: "Traits (comma-separated)",
    sv: "Egenskaper (kommaseparerade)",
    de: "Eigenschaften (kommagetrennt)",
  },
  "field.voice": {
    en: "Voice / persona (how it speaks)",
    sv: "Röst / persona (hur den talar)",
    de: "Stimme / Persona (wie sie spricht)",
  },
};

function translate(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  const entry = T[key];
  let s = entry ? entry[lang] ?? entry.en : key;
  if (vars) for (const k of Object.keys(vars)) s = s.split(`{${k}}`).join(String(vars[k]));
  return s;
}

export type TFn = (key: string, vars?: Record<string, string | number>) => string;

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: TFn;
}

const I18nCtx = createContext<I18nValue | null>(null);

function initialLang(): Lang {
  const saved = localStorage.getItem(LS_KEY);
  if (saved === "en" || saved === "sv" || saved === "de") return saved;
  const nav = (navigator.language || "en").slice(0, 2);
  return nav === "sv" || nav === "de" ? nav : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((l: Lang) => {
    localStorage.setItem(LS_KEY, l);
    setLangState(l);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback<TFn>((key, vars) => translate(lang, key, vars), [lang]);

  return <I18nCtx.Provider value={{ lang, setLang, t }}>{children}</I18nCtx.Provider>;
}

export function useI18n(): I18nValue {
  const v = useContext(I18nCtx);
  if (!v) throw new Error("useI18n must be used within <I18nProvider>");
  return v;
}

export function useT(): TFn {
  return useI18n().t;
}
